"""
Statistical anomaly detection rules.
All arithmetic happens here in Python — never in the LLM.
"""

import os
from pathlib import Path
from typing import Optional

import duckdb
import numpy as np
from dotenv import load_dotenv

from tools.data_access import get_con, get_latest_date, list_skus

load_dotenv()

DB_PATH = Path(os.getenv("DUCKDB_PATH", "data/snop.duckdb"))

ZSCORE_THRESHOLD = 2.5
WOW_THRESHOLD = 0.40        # 40% week-over-week change
EWMA_BIAS_THRESHOLD = 0.25  # 25% persistent over/under vs rolling mean
MIN_HISTORY_DAYS = 21


def _zscore_flag(recent: list[float], rolling_mean: float, rolling_std: float) -> Optional[float]:
    """Return z-score if the most recent value is anomalous, else None."""
    if rolling_std < 0.5:
        return None
    z = (recent[-1] - rolling_mean) / rolling_std
    if abs(z) >= ZSCORE_THRESHOLD:
        return round(float(z), 2)
    return None


def _ewma_bias(values: list[float], span: int = 14) -> float:
    """
    Compute EWMA bias: persistent over/under of recent actuals vs smoothed baseline.
    Positive = actuals consistently above baseline (demand lifting).
    Negative = actuals consistently below (demand erosion / stockout).
    """
    if len(values) < span * 2:
        return 0.0
    arr = np.array(values, dtype=float)
    weights = np.exp(-np.log(2) / (span / 2) * np.arange(span, 0, -1))
    weights /= weights.sum()
    baseline = np.average(arr[-span * 2: -span], weights=weights[-span:])
    recent_mean = arr[-span:].mean()
    if baseline < 0.5:
        return 0.0
    return round(float((recent_mean - baseline) / baseline), 3)


def _wow_change(values: list[float]) -> Optional[float]:
    """Week-over-week percent change: last 7 days vs prior 7 days."""
    if len(values) < 14:
        return None
    prior = sum(values[-14:-7])
    recent = sum(values[-7:])
    if prior < 1:
        return None
    return round(float((recent - prior) / prior), 3)


def scan_recent(
    category: Optional[str] = None,
    lookback_days: int = 28,
    store_id: str = "CA_1",
) -> list[dict]:
    """
    Scan all SKUs (or a category subset) for anomalies over the last `lookback_days`.

    Returns a list of flagged SKUs:
    [
      {
        sku_id, store_id, category,
        anomaly_types: ["spike"|"dip"|"drift_up"|"drift_down"|"wow_spike"|"wow_dip"],
        zscore: float|None,
        wow_change: float|None,
        ewma_bias: float|None,
        severity: "high"|"medium"|"low",
        recent_avg: float,
        baseline_avg: float,
      }, ...
    ]
    """
    skus = list_skus(category)
    latest = get_latest_date()
    con = get_con()

    baseline_days = lookback_days * 3

    flagged = []
    for sku in skus:
        rows = con.execute(f"""
            SELECT units FROM sales
            WHERE sku_id = '{sku}' AND store_id = '{store_id}'
              AND date >= DATE '{latest}' - INTERVAL {baseline_days} DAY
            ORDER BY date
        """).fetchall()

        if len(rows) < MIN_HISTORY_DAYS:
            continue

        values = [float(r[0]) for r in rows]
        recent_values = values[-lookback_days:]
        baseline_values = values[:-lookback_days]

        if not baseline_values:
            continue

        rolling_mean = float(np.mean(baseline_values))
        rolling_std = float(np.std(baseline_values))
        recent_mean = float(np.mean(recent_values))

        anomaly_types = []
        zscore = _zscore_flag(recent_values, rolling_mean, rolling_std)
        if zscore is not None:
            anomaly_types.append("spike" if zscore > 0 else "dip")

        wow = _wow_change(values)
        if wow is not None and abs(wow) >= WOW_THRESHOLD:
            anomaly_types.append("wow_spike" if wow > 0 else "wow_dip")

        bias = _ewma_bias(values)
        if abs(bias) >= EWMA_BIAS_THRESHOLD:
            anomaly_types.append("drift_up" if bias > 0 else "drift_down")

        if not anomaly_types:
            continue

        if zscore and abs(zscore) >= 4.0:
            severity = "high"
        elif zscore and abs(zscore) >= 3.0:
            severity = "medium"
        elif wow and abs(wow) >= 0.60:
            severity = "high"
        elif wow and abs(wow) >= 0.40:
            severity = "medium"
        else:
            severity = "low"

        cat = sku.split("_")[0]
        flagged.append({
            "sku_id": sku,
            "store_id": store_id,
            "category": cat,
            "anomaly_types": anomaly_types,
            "zscore": zscore,
            "wow_change": wow,
            "ewma_bias": bias,
            "severity": severity,
            "recent_avg": round(recent_mean, 1),
            "baseline_avg": round(rolling_mean, 1),
        })

    flagged.sort(
        key=lambda x: ({"high": 0, "medium": 1, "low": 2}[x["severity"]], -abs(x.get("zscore") or 0))
    )
    return flagged


def classify_anomaly(
    sku_id: str,
    date: str,
    store_id: str = "CA_1",
    context_days: int = 60,
) -> dict:
    """
    Classify the anomaly type and severity for a specific SKU on a given date.

    Returns:
    {
      sku_id, date, store_id,
      type: "spike"|"dip"|"drift"|"none",
      severity: "high"|"medium"|"low"|"none",
      zscore: float,
      magnitude_pct: float,  # how far from baseline, in percent
      baseline_mean: float,
      baseline_std: float,
      actual_units: int,
      evidence: str
    }
    """
    con = get_con()
    window = context_days + 7
    rows = con.execute(f"""
        SELECT date::TEXT, units FROM sales
        WHERE sku_id = '{sku_id}' AND store_id = '{store_id}'
          AND date <= DATE '{date}'
          AND date >= DATE '{date}' - INTERVAL {window} DAY
        ORDER BY date
    """).fetchall()

    if len(rows) < MIN_HISTORY_DAYS:
        return {"error": f"Insufficient history ({len(rows)} days)", "sku_id": sku_id}

    target_row = next((r for r in rows if r[0] == date), None)
    if target_row is None:
        return {"error": f"No sales record for {date}", "sku_id": sku_id}

    actual = float(target_row[1])
    history = [float(r[1]) for r in rows if r[0] < date]

    if not history:
        return {"error": "No prior history", "sku_id": sku_id}

    mean = float(np.mean(history[-context_days:]))
    std = float(np.std(history[-context_days:]))

    zscore = ((actual - mean) / std) if std > 0.5 else 0.0
    magnitude_pct = ((actual - mean) / max(mean, 1)) * 100

    if abs(zscore) >= 4.0:
        severity = "high"
    elif abs(zscore) >= 2.5:
        severity = "medium"
    elif abs(zscore) >= 1.5:
        severity = "low"
    else:
        severity = "none"

    if actual == 0 and mean > 2:
        atype = "dip"
        severity = "high"
        evidence = f"Zero demand against a baseline of {mean:.1f} units/day — likely stockout."
    elif zscore > 0:
        atype = "spike"
        evidence = f"Demand was {actual:.0f} units vs baseline of {mean:.1f} (z={zscore:.1f})."
    elif zscore < 0:
        atype = "dip"
        evidence = f"Demand was {actual:.0f} units vs baseline of {mean:.1f} (z={zscore:.1f})."
    else:
        atype = "none"
        evidence = "No significant anomaly detected."

    return {
        "sku_id": sku_id,
        "date": date,
        "store_id": store_id,
        "type": atype,
        "severity": severity,
        "zscore": round(zscore, 2),
        "magnitude_pct": round(magnitude_pct, 1),
        "baseline_mean": round(mean, 1),
        "baseline_std": round(std, 1),
        "actual_units": int(actual),
        "evidence": evidence,
    }
