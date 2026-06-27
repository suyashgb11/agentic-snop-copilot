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

_con: Optional[duckdb.DuckDBPyConnection] = None


def get_con() -> duckdb.DuckDBPyConnection:
    """Return the shared DuckDB connection (read-write so forecasting can persist)."""
    global _con
    if _con is None:
        _con = duckdb.connect(str(DB_PATH), read_only=False)
    return _con


def reset_con() -> None:
    global _con
    if _con is not None:
        _con.close()
        _con = None


def get_history(sku_id: str, days: int = 90, store_id: str = "CA_1") -> list[dict]:
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
    con = get_con()
    row = con.execute("""
        SELECT date::TEXT, day_of_week, is_weekend, is_holiday, holiday_name,
               snap_ca, snap_tx, snap_wi
        FROM calendar WHERE date = ?
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


def get_calendar_window(target_date: str, before: int = 3, after: int = 3) -> list[dict]:
    """Calendar entries with holidays or SNAP days within +/- N days of target_date.
    `offset_days` is positive when the row is before target_date."""
    con = get_con()
    rows = con.execute(f"""
        SELECT date::TEXT, day_of_week, is_weekend, is_holiday, holiday_name,
               snap_ca, snap_tx, snap_wi,
               (DATE '{target_date}' - date)::INTEGER AS offset_days
        FROM calendar
        WHERE date BETWEEN DATE '{target_date}' - INTERVAL {before} DAY
                       AND DATE '{target_date}' + INTERVAL {after} DAY
          AND (is_holiday = TRUE OR snap_ca = TRUE OR snap_tx = TRUE OR snap_wi = TRUE)
        ORDER BY date
    """).fetchall()
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return [{
        "date": r[0], "day_of_week": r[1], "day_name": day_names[r[1]],
        "is_weekend": bool(r[2]), "is_holiday": bool(r[3]), "holiday_name": r[4] or "",
        "snap_ca": bool(r[5]), "snap_tx": bool(r[6]), "snap_wi": bool(r[7]),
        "offset_days": int(r[8]),
    } for r in rows]


def get_peer_skus(sku_id: str, n: int = 10) -> list[str]:
    parts = sku_id.split("_")
    if len(parts) < 3:
        return []
    dept_prefix = "_".join(parts[:2])
    con = get_con()
    rows = con.execute("""
        SELECT DISTINCT sku_id FROM sales
        WHERE sku_id LIKE ? AND sku_id != ?
        LIMIT ?
    """, [f"{dept_prefix}_%", sku_id, n]).fetchall()
    return [r[0] for r in rows]


def list_skus(category: Optional[str] = None) -> list[str]:
    con = get_con()
    if category:
        rows = con.execute("""
            SELECT DISTINCT sku_id FROM sales
            WHERE sku_id LIKE ? ORDER BY sku_id
        """, [f"{category.upper()}_%"]).fetchall()
    else:
        rows = con.execute("SELECT DISTINCT sku_id FROM sales ORDER BY sku_id").fetchall()
    return [r[0] for r in rows]


def get_latest_date() -> str:
    con = get_con()
    row = con.execute("SELECT MAX(date)::TEXT FROM sales").fetchone()
    return row[0] if row else ""


def get_recent_summary(sku_id: str, store_id: str = "CA_1", lookback_days: int = 14) -> dict:
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
        WHERE sku_id = '{sku_id}' AND store_id = '{store_id}'
          AND date >= DATE '{latest}' - INTERVAL {lookback_days} DAY
    """).fetchone()
    if row is None or row[0] is None:
        return {}
    return {
        "mean": float(row[0] or 0), "std": float(row[1] or 0),
        "min": int(row[2] or 0), "max": int(row[3] or 0),
        "p25": float(row[4] or 0), "p75": float(row[5] or 0),
        "n_days": int(row[6] or 0), "n_zeros": int(row[7] or 0),
    }


def compare_peer_demand(sku_id: str, target_date: str,
                        store_id: str = "CA_1", window_days: int = 7) -> dict:
    """Compare SKU vs same-category peers in the same store. Two non-overlapping
    7-day windows, both ending at or before target_date (no future leakage)."""
    peers = get_peer_skus(sku_id, n=15)
    if not peers:
        return {"error": "No peers found"}
    con = get_con()
    peer_list = ", ".join(f"'{p}'" for p in peers)
    row = con.execute(f"""
        WITH window_data AS (
            SELECT sku_id,
                SUM(CASE WHEN date BETWEEN DATE '{target_date}' - INTERVAL {window_days*2} DAY
                                       AND DATE '{target_date}' - INTERVAL {window_days + 1} DAY
                         THEN units ELSE 0 END) AS prior_units,
                SUM(CASE WHEN date BETWEEN DATE '{target_date}' - INTERVAL {window_days - 1} DAY
                                       AND DATE '{target_date}'
                         THEN units ELSE 0 END) AS recent_units
            FROM sales
            WHERE store_id = '{store_id}'
              AND date BETWEEN DATE '{target_date}' - INTERVAL {window_days*2} DAY
                           AND DATE '{target_date}'
            GROUP BY sku_id
        ),
        this_sku AS (SELECT * FROM window_data WHERE sku_id = '{sku_id}'),
        peer_agg AS (SELECT AVG(prior_units) AS peer_prior, AVG(recent_units) AS peer_recent
                     FROM window_data WHERE sku_id IN ({peer_list}))
        SELECT t.prior_units, t.recent_units, p.peer_prior, p.peer_recent
        FROM this_sku t, peer_agg p
    """).fetchone()
    if not row:
        return {"error": "Insufficient data"}
    prior, recent, peer_prior, peer_recent = row
    sku_change  = ((recent - prior) / prior) * 100 if prior else 0.0
    peer_change = ((peer_recent - peer_prior) / peer_prior) * 100 if peer_prior else 0.0
    same_direction = (sku_change >= 0) == (peer_change >= 0) and abs(peer_change) >= 5
    return {
        "sku_id": sku_id, "store_id": store_id,
        "sku_prior_avg_daily":  round((prior or 0) / window_days, 1),
        "sku_recent_avg_daily": round((recent or 0) / window_days, 1),
        "peer_prior_avg_daily":  round((peer_prior or 0) / window_days, 1),
        "peer_recent_avg_daily": round((peer_recent or 0) / window_days, 1),
        "sku_pct_change":  round(sku_change, 1),
        "peer_pct_change": round(peer_change, 1),
        "peers_moved_same_direction": same_direction,
        "n_peers": len(peers),
        "window_days": window_days,
    }
