"""
Forecast agent node.
run_forecast is always called directly — no risk of LLM skipping it.
The LLM only narrates real results; it never does arithmetic.
"""

import json
import re
import time
from tools.llm import simple_call
from tools.forecasting import run_forecast, get_accuracy
from tools.data_access import list_skus, get_latest_date

_NARRATOR_SYSTEM = """You are a demand planning assistant. Summarise the forecast results below.

Rules:
- ONLY use the data provided. Never invent numbers, dates, or SKU IDs.
- State the SKU, the model used, and the first 7 days of the forecast with actual values.
- Mention peak day and lowest day if visible.
- Be concise — 3 to 5 sentences max.
- Do NOT say "based on our previous discussions".
"""


def _extract_sku(query: str, sku_filter: list | None) -> str | None:
    """Pull SKU ID from query or filter."""
    if sku_filter:
        return sku_filter[0]
    # Regex: FOODS_1_001, HOBBIES_1_007, HOUSEHOLD_1_015, etc.
    match = re.search(r"(FOODS|HOBBIES|HOUSEHOLD)_\d+_\d+", query.upper())
    return match.group(0) if match else None


def _extract_horizon(query: str, horizon_hint: int | None) -> int:
    if horizon_hint:
        return int(horizon_hint)
    match = re.search(r"(\d+)\s*day", query.lower())
    if match:
        return int(match.group(1))
    if "week" in query.lower():
        return 7
    if "month" in query.lower():
        return 30
    return 28


def forecast_agent_node(state: dict) -> dict:
    trace: list[dict] = []
    query = state.get("user_query", "")

    sku_id   = _extract_sku(query, state.get("sku_filter"))
    horizon  = _extract_horizon(query, state.get("horizon_days"))

    # If no SKU found, list available ones and pick first FOODS SKU
    if not sku_id:
        skus   = list_skus("FOODS")
        sku_id = skus[0] if skus else "FOODS_1_001"

    # ── Step 1: Always run forecast directly ──────────────────────────────────
    t0 = time.time()
    forecast_result = run_forecast(sku_id, horizon_days=horizon, store_id="CA_1")
    trace.append({
        "agent":       "ForecastAgent",
        "tool":        "run_forecast",
        "input":       {"sku_id": sku_id, "horizon_days": horizon, "store_id": "CA_1"},
        "output":      {k: v for k, v in forecast_result.items() if k != "forecast"}
                       | {"forecast_rows": len(forecast_result.get("forecast", []))},
        "ts_ms":       int(time.time() * 1000),
        "duration_ms": int((time.time() - t0) * 1000),
    })

    # ── Step 2: Optionally get accuracy ───────────────────────────────────────
    if "accura" in query.lower() or "mape" in query.lower() or "bias" in query.lower():
        t0  = time.time()
        acc = get_accuracy(sku_id, store_id="CA_1")
        forecast_result["accuracy"] = acc
        trace.append({
            "agent":       "ForecastAgent",
            "tool":        "get_accuracy",
            "input":       {"sku_id": sku_id},
            "output":      acc,
            "ts_ms":       int(time.time() * 1000),
            "duration_ms": int((time.time() - t0) * 1000),
        })

    return {"forecast_result": forecast_result, "trace": trace}
