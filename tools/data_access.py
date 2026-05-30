"""
DuckDB query functions used by agents as tools.
Every function returns plain Python types (no DataFrames) so the LLM
can receive the results as JSON-serialisable tool outputs.
"""

import os
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Optional

import duckdb
from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path(os.getenv("DUCKDB_PATH", "data/snop.duckdb"))

# -------------------------------------------------------------------
# Connection (read-only; one connection is fine for single-process UI)
# -------------------------------------------------------------------

_con: Optional[duckdb.DuckDBPyConnection] = None


def get_con() -> duckdb.DuckDBPyConnection:
    """Return the shared DuckDB connection (read-write so forecasting can persist results)."""
    global _con
    if _con is None:
        _con = duckdb.connect(str(DB_PATH), read_only=False)
    return _con


def reset_con() -> None:
    """Close and reset the shared connection (useful after external writes)."""
    global _con
    if _con is not None:
        _con.close()
        _con = None


# -------------------------------------------------------------------
# Tool functions
# -------------------------------------------------------------------

def get_history(sku_id: str, days: int = 90, store_id: str = "CA_1") -> list[dict]:
    """
    Return the last `days` days of daily sales for a SKU/store.
    Output: [{date, units}, ...] sorted ascending.
    """
    con = get_con()
    latest = con.execute("SELECT MAX(date)::TEXT FROM sales").fetchone()[0]
    rows = con.execute(f"""
        SELECT date::TEXT AS date, units
        FROM sales
        WHERE sku_id = '{sku_id}'
          AND store_id = '{store_id}'
          AND date >= DATE '{latest}' - INTERVAL {days} DAY
        ORDER BY date
    """).fetchall()

    if not rows:
        return []
    return [{"date": r[0], "units": r[1]} for r in rows]


def get_calendar_context(target_date: str) -> dict:
    """
    Return calendar metadata for a specific date.
    Output: {date, day_of_week, is_weekend, is_holiday, holiday_name,
             snap_ca, snap_tx, snap_wi}
    """
    con = get_con()
    row = con.execute("""
        SELECT
            date::TEXT,
            day_of_week,
            is_weekend,
            is_holiday,
            holiday_name,
            snap_ca,
            snap_tx,
            snap_wi
        FROM calendar
        WHERE date = ?
    """, [target_date]).fetchone()

    if row is None:
        return {"error": f"No calendar entry for {target_date}"}

    return {
        "date": row[0],
        "day_of_week": row[1],
        "day_name": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][row[1]],
        "is_weekend": bool(row[2]),
        "is_holiday": bool(row[3]),
        "holiday_name": row[4] or "",
        "snap_ca": bool(row[5]),
        "snap_tx": bool(row[6]),
        "snap_wi": bool(row[7]),
    }


def get_peer_skus(sku_id: str, n: int = 10) -> list[str]:
    """
    Return up to `n` SKUs from the same category and department, excluding sku_id.
    """
    parts = sku_id.split("_")
    if len(parts) < 3:
        return []
    dept_prefix = "_".join(parts[:2])  # e.g. "FOODS_1"

    con = get_con()
    rows = con.execute("""
        SELECT DISTINCT sku_id
        FROM sales
        WHERE sku_id LIKE ? AND sku_id != ?
        LIMIT ?
    """, [f"{dept_prefix}_%", sku_id, n]).fetchall()

    return [r[0] for r in rows]


def list_skus(category: Optional[str] = None) -> list[str]:
    """
    Return all SKU IDs in the dataset, optionally filtered by category
    (FOODS, HOBBIES, or HOUSEHOLD).
    """
    con = get_con()
    if category:
        rows = con.execute("""
            SELECT DISTINCT sku_id FROM sales
            WHERE sku_id LIKE ?
            ORDER BY sku_id
        """, [f"{category.upper()}_%"]).fetchall()
    else:
        rows = con.execute(
            "SELECT DISTINCT sku_id FROM sales ORDER BY sku_id"
        ).fetchall()

    return [r[0] for r in rows]


def get_latest_date() -> str:
    """Return the most recent date in the sales table."""
    con = get_con()
    row = con.execute("SELECT MAX(date)::TEXT FROM sales").fetchone()
    return row[0] if row else ""


def get_recent_summary(
    sku_id: str,
    store_id: str = "CA_1",
    lookback_days: int = 14,
) -> dict:
    """
    Return a statistical summary of recent demand for a SKU.
    Output: {mean, std, min, max, p25, p75, n_days, n_zeros}
    """
    con = get_con()
    latest = con.execute("SELECT MAX(date)::TEXT FROM sales").fetchone()[0]
    row = con.execute(f"""
        SELECT
            ROUND(AVG(units), 2)    AS mean,
            ROUND(STDDEV(units), 2) AS std,
            MIN(units)              AS min,
            MAX(units)              AS max,
            ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY units), 2) AS p25,
            ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY units), 2) AS p75,
            COUNT(*)                AS n_days,
            SUM(CASE WHEN units = 0 THEN 1 ELSE 0 END) AS n_zeros
        FROM sales
        WHERE sku_id = '{sku_id}'
          AND store_id = '{store_id}'
          AND date >= DATE '{latest}' - INTERVAL {lookback_days} DAY
    """).fetchone()

    if row is None or row[0] is None:
        return {}

    return {
        "mean": float(row[0] or 0),
        "std": float(row[1] or 0),
        "min": int(row[2] or 0),
        "max": int(row[3] or 0),
        "p25": float(row[4] or 0),
        "p75": float(row[5] or 0),
        "n_days": int(row[6] or 0),
        "n_zeros": int(row[7] or 0),
    }


def compare_peer_demand(
    sku_id: str,
    target_date: str,
    store_id: str = "CA_1",
    window_days: int = 7,
) -> dict:
    """
    Compare the SKU's recent demand trend vs its category peers.
    Returns percent change for this SKU vs peer average over the window.
    """
    peers = get_peer_skus(sku_id, n=15)
    if not peers:
        return {"error": "No peers found"}

    con = get_con()
    peer_list = ", ".join(f"'{p}'" for p in peers)

    row = con.execute(f"""
        WITH window_data AS (
            SELECT
                sku_id,
                SUM(CASE WHEN date >= DATE '{target_date}' - INTERVAL {window_days} DAY
                              AND date < DATE '{target_date}' THEN units ELSE 0 END) AS prior_units,
                SUM(CASE WHEN date >= DATE '{target_date}' THEN units ELSE 0 END) AS recent_units
            FROM sales
            WHERE store_id = '{store_id}'
              AND date BETWEEN DATE '{target_date}' - INTERVAL {window_days*2} DAY
                           AND DATE '{target_date}' + INTERVAL {window_days} DAY
            GROUP BY sku_id
        ),
        this_sku AS (SELECT * FROM window_data WHERE sku_id = '{sku_id}'),
        peers AS (SELECT AVG(prior_units) AS peer_prior, AVG(recent_units) AS peer_recent
                  FROM window_data WHERE sku_id IN ({peer_list}))
        SELECT
            t.prior_units, t.recent_units,
            p.peer_prior, p.peer_recent
        FROM this_sku t, peers p
    """).fetchone()

    if not row:
        return {"error": "Insufficient data"}

    prior, recent, peer_prior, peer_recent = row
    sku_change = ((recent - prior) / max(prior, 1)) * 100 if prior else 0
    peer_change = ((peer_recent - peer_prior) / max(peer_prior, 1)) * 100 if peer_prior else 0

    return {
        "sku_id": sku_id,
        "sku_prior_avg_daily": round(prior / window_days, 1) if prior else 0,
        "sku_recent_avg_daily": round(recent / window_days, 1) if recent else 0,
        "sku_pct_change": round(sku_change, 1),
        "peer_pct_change": round(peer_change, 1),
        "peers_moved_same_direction": (sku_change > 0) == (peer_change > 0),
        "n_peers": len(peers),
    }
