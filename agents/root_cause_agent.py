"""
Root-cause agent node.
Tools are always called directly in Python — no risk of LLM skipping them.
The LLM only narrates real results.
"""

import json
import re
import time
from tools.llm import simple_call
from tools.data_access import get_calendar_context, compare_peer_demand, get_latest_date
from tools.anomaly_detection import classify_anomaly, scan_recent


def root_cause_agent_node(state: dict) -> dict:
    trace: list[dict] = []
    query   = state.get("user_query", "")
    latest  = get_latest_date()

    # ── Step 1: Identify SKU and anomaly date ─────────────────────────────────
    anomalies = state.get("anomalies") or []

    if anomalies:
        # Came from anomaly agent — use top result
        top   = anomalies[0]
        sku   = top["sku_id"]
        store = top.get("store_id", "CA_1")
        date  = latest
    else:
        # Direct root cause query — extract SKU from query
        match = re.search(r"(FOODS|HOBBIES|HOUSEHOLD)_\d+_\d+", query.upper())
        sku   = match.group(0) if match else (state.get("sku_filter") or [None])[0]
        store = "CA_1"
        date  = latest

        if not sku:
            # No SKU — scan to find something interesting
            t0  = time.time()
            raw = scan_recent(lookback_days=28, store_id=store)
            trace.append({"agent": "RootCauseAgent", "tool": "scan_recent",
                          "input": {"lookback_days": 28}, "output": raw[:5],
                          "ts_ms": int(time.time()*1000), "duration_ms": int((time.time()-t0)*1000)})
            if raw:
                sku = raw[0]["sku_id"]
            else:
                return {"root_causes": [], "trace": trace}

    # ── Step 2: Classify the anomaly ─────────────────────────────────────────
    t0     = time.time()
    detail = classify_anomaly(sku, date, store)
    trace.append({"agent": "RootCauseAgent", "tool": "classify_anomaly",
                  "input": {"sku_id": sku, "date": date, "store_id": store},
                  "output": detail,
                  "ts_ms": int(time.time()*1000), "duration_ms": int((time.time()-t0)*1000)})

    # ── Step 3: Calendar context ──────────────────────────────────────────────
    t0  = time.time()
    cal = get_calendar_context(date)
    trace.append({"agent": "RootCauseAgent", "tool": "get_calendar_context",
                  "input": {"target_date": date}, "output": cal,
                  "ts_ms": int(time.time()*1000), "duration_ms": int((time.time()-t0)*1000)})

    # ── Step 4: Peer comparison ───────────────────────────────────────────────
    t0   = time.time()
    peer = compare_peer_demand(sku, date, store)
    trace.append({"agent": "RootCauseAgent", "tool": "compare_peer_demand",
                  "input": {"sku_id": sku, "target_date": date, "store_id": store},
                  "output": peer,
                  "ts_ms": int(time.time()*1000), "duration_ms": int((time.time()-t0)*1000)})

    # ── Step 5: Build root_causes ─────────────────────────────────────────────
    root_causes = [{
        "sku_id":           sku,
        "date":             date,
        "store_id":         store,
        "anomaly_detail":   detail,
        "calendar_context": cal,
        "peer_comparison":  peer,
    }]

    return {"root_causes": root_causes, "trace": trace}
