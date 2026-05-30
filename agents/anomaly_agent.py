"""
Anomaly detection agent node.
scan_recent is always called directly in Python — no risk of the LLM skipping it.
The LLM only narrates real results; it never invents numbers.
"""

import json
import time
from tools.llm import simple_call
from tools.anomaly_detection import scan_recent, classify_anomaly
from tools.data_access import get_latest_date

_NARRATOR_SYSTEM = """You are a demand planning assistant. Your job is to summarise
anomaly scan results for a planner.

Rules:
- ONLY use the data provided below. Never invent SKU IDs, store IDs, or numbers.
- If the results show anomalies, lead with the most severe one and give specific numbers.
- If results are empty, say: "No anomalies detected this week across all SKUs."
- Be concise — 2 to 4 sentences max.
- Do NOT say "based on our previous discussions" or reference anything not in the data.
"""


def anomaly_agent_node(state: dict) -> dict:
    trace: list[dict] = []
    category = None

    # Detect category filter from query
    query = state.get("user_query", "").upper()
    for cat in ["FOODS", "HOBBIES", "HOUSEHOLD"]:
        if cat in query:
            category = cat
            break

    # ── Step 1: Always call scan_recent directly ──────────────────────────────
    t0 = time.time()
    raw = scan_recent(category=category, lookback_days=28, store_id="CA_1")
    trace.append({
        "agent":       "AnomalyAgent",
        "tool":        "scan_recent",
        "input":       {"category": category, "lookback_days": 28, "store_id": "CA_1"},
        "output":      raw[:20],
        "ts_ms":       int(time.time() * 1000),
        "duration_ms": int((time.time() - t0) * 1000),
    })

    # ── Step 2: Classify top anomalies in detail ──────────────────────────────
    latest = get_latest_date()
    for a in raw[:3]:
        if a.get("severity") in ("high", "medium"):
            t0 = time.time()
            detail = classify_anomaly(a["sku_id"], latest, a.get("store_id", "CA_1"))
            a["detail"] = detail
            trace.append({
                "agent":       "AnomalyAgent",
                "tool":        "classify_anomaly",
                "input":       {"sku_id": a["sku_id"], "date": latest},
                "output":      detail,
                "ts_ms":       int(time.time() * 1000),
                "duration_ms": int((time.time() - t0) * 1000),
            })

    # ── Step 3: LLM narrates real results — no tool calls, no arithmetic ──────
    if raw:
        lines = []
        for a in raw[:5]:
            lines.append(
                f"SKU {a['sku_id']} (store {a.get('store_id','CA_1')}): "
                f"{', '.join(a.get('anomaly_types', []))} | "
                f"severity={a.get('severity')} | "
                f"zscore={a.get('zscore')} | "
                f"recent_avg={a.get('recent_avg')} vs baseline={a.get('baseline_avg')}"
            )
        data_block = "\n".join(lines)
        prompt = f"Anomaly scan results ({len(raw)} SKUs flagged):\n{data_block}\n\nSummarise for the planner."
    else:
        prompt = "Anomaly scan returned 0 flagged SKUs. Inform the planner clearly."

    # Note: simple_call adds a trace entry of its own via the orchestrator composer
    # We don't need an LLM trace entry here — the data is the truth

    return {"anomalies": raw, "trace": trace}
