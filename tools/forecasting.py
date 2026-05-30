"""
StatsForecast wrapper.  Every number it returns came from a model fit
on real (or synthetic) sales history — the LLM never touches arithmetic.
"""

import os
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import duckdb
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from statsforecast import StatsForecast
from statsforecast.models import AutoARIMA, AutoETS, SeasonalNaive

from tools.data_access import get_con, get_history, get_latest_date, reset_con

load_dotenv()

DB_PATH = Path(os.getenv("DUCKDB_PATH", "data/snop.duckdb"))
SEASON_LENGTH = 7   # weekly seasonality for daily data
MIN_HISTORY_DAYS = 28


def _write_forecast(
    sku_id: str,
    store_id: str,
    date_made: str,
    forecast_df: pd.DataFrame,
    model_name: str,
) -> None:
    """Persist forecasts to the forecasts table using the shared connection."""
    con = get_con()
    con.execute("""
        DELETE FROM forecasts
        WHERE sku_id = ? AND store_id = ? AND date_made = ?
    """, [sku_id, store_id, date_made])

    rows = []
    for _, row in forecast_df.iterrows():
        rows.append({
            "sku_id": sku_id,
            "store_id": store_id,
            "date_made": date_made,
            "horizon_date": str(row["ds"].date()),
            "model": model_name,
            "point": float(max(row.get(model_name, 0), 0)),
            "lo80": float(max(row.get(f"{model_name}-lo-80", 0), 0)),
            "hi80": float(max(row.get(f"{model_name}-hi-80", 0), 0)),
            "lo95": float(max(row.get(f"{model_name}-lo-95", 0), 0)),
            "hi95": float(max(row.get(f"{model_name}-hi-95", 0), 0)),
        })

    if rows:
        df = pd.DataFrame(rows)
        con.execute("INSERT INTO forecasts SELECT * FROM df")


def run_forecast(
    sku_id: str,
    horizon_days: int = 28,
    store_id: str = "CA_1",
    history_days: int = 365,
) -> dict:
    """
    Fit a statistical model and return a point forecast with 80/95% intervals.

    Returns:
        {
          sku_id, store_id, model, horizon_days, date_made,
          forecast: [{date, point, lo80, hi80, lo95, hi95}, ...],
          history_used_days: int
        }
    """
    history = get_history(sku_id, days=history_days, store_id=store_id)
    if len(history) < MIN_HISTORY_DAYS:
        return {
            "error": f"Insufficient history: {len(history)} days (need {MIN_HISTORY_DAYS}+)",
            "sku_id": sku_id,
        }

    train_df = pd.DataFrame({
        "unique_id": sku_id,
        "ds": pd.to_datetime([h["date"] for h in history]),
        "y": [float(h["units"]) for h in history],
    })

    models = [
        AutoARIMA(season_length=SEASON_LENGTH),
        SeasonalNaive(season_length=SEASON_LENGTH),
    ]

    sf = StatsForecast(models=models, freq="D", n_jobs=1)
    fc = sf.forecast(df=train_df, h=horizon_days, level=[80, 95])

    model_col = "AutoARIMA"
    if model_col not in fc.columns:
        model_col = fc.columns[1]

    date_made = get_latest_date()

    _write_forecast(sku_id, store_id, date_made, fc, model_col)

    result_rows = []
    for _, row in fc.iterrows():
        result_rows.append({
            "date": str(row["ds"].date()),
            "point": round(float(max(row.get(model_col, 0), 0)), 1),
            "lo80": round(float(max(row.get(f"{model_col}-lo-80", 0), 0)), 1),
            "hi80": round(float(max(row.get(f"{model_col}-hi-80", 0), 0)), 1),
            "lo95": round(float(max(row.get(f"{model_col}-lo-95", 0), 0)), 1),
            "hi95": round(float(max(row.get(f"{model_col}-hi-95", 0), 0)), 1),
        })

    return {
        "sku_id": sku_id,
        "store_id": store_id,
        "model": model_col,
        "horizon_days": horizon_days,
        "date_made": date_made,
        "history_used_days": len(history),
        "forecast": result_rows,
    }


def get_accuracy(
    sku_id: str,
    store_id: str = "CA_1",
    eval_days: int = 28,
) -> dict:
    """
    Evaluate forecast accuracy via walk-forward last `eval_days`.
    Returns {mape, bias, rmse, coverage_80, n_periods}.
    MAPE and bias are computed by the model — the LLM never does arithmetic.
    """
    history = get_history(sku_id, days=365 + eval_days, store_id=store_id)
    if len(history) < MIN_HISTORY_DAYS + eval_days:
        return {
            "error": "Insufficient history for accuracy evaluation",
            "sku_id": sku_id,
        }

    cutoff = len(history) - eval_days
    train = history[:cutoff]
    test = history[cutoff:]

    train_df = pd.DataFrame({
        "unique_id": sku_id,
        "ds": pd.to_datetime([h["date"] for h in train]),
        "y": [float(h["units"]) for h in train],
    })

    sf = StatsForecast(
        models=[AutoARIMA(season_length=SEASON_LENGTH)],
        freq="D",
        n_jobs=1,
    )
    fc = sf.forecast(df=train_df, h=eval_days, level=[80, 95])

    model_col = "AutoARIMA"
    actuals = np.array([h["units"] for h in test], dtype=float)
    forecasts = np.array([max(float(v), 0) for v in fc[model_col].values], dtype=float)
    lo80 = np.array([max(float(v), 0) for v in fc[f"{model_col}-lo-80"].values], dtype=float)
    hi80 = np.array([max(float(v), 0) for v in fc[f"{model_col}-hi-80"].values], dtype=float)

    n = len(actuals)
    nonzero = actuals > 0
    mape = float(np.mean(np.abs((actuals[nonzero] - forecasts[nonzero]) / actuals[nonzero])) * 100) if nonzero.any() else None
    bias = float(np.mean(forecasts - actuals))
    rmse = float(np.sqrt(np.mean((actuals - forecasts) ** 2)))
    coverage_80 = float(np.mean((actuals >= lo80) & (actuals <= hi80)) * 100)

    return {
        "sku_id": sku_id,
        "store_id": store_id,
        "model": model_col,
        "n_periods": n,
        "mape": round(mape, 1) if mape is not None else None,
        "bias": round(bias, 2),
        "rmse": round(rmse, 2),
        "coverage_80pct": round(coverage_80, 1),
        "interpretation": (
            "over-forecasting" if bias > 2 else
            "under-forecasting" if bias < -2 else
            "unbiased"
        ),
    }
