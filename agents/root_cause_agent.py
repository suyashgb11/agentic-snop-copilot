"""
Root-cause agent node.
Tools are always called directly in Python. The LLM only narrates real results.

Week 4 upgrades:
- Pulls a +/- 3 day calendar window to name nearby holidays and SNAP days.
- Fixed peer comparison so windows do not leak future data.
- Ranks candidate causes (stockout, holiday, SNAP, category shift, idiosyncratic)
  with a confidence label, so the composer can lead with the most likely one.
- Extracts a target date from the query when the user says "on YYYY-MM-DD".
"""

import re
import time

from tools.llm import simple_call
from tools.data_access import (
    get_calendar_context,
    get_calendar_window,
    compare_peer_demand,
    get_latest_date,
)
from tools.anomaly_detection import classify_anomaly, scan_recent
from agents.root_cause_helpers import build_candidate_causes, extract_date, extract_store, ALL_STORES


def root_cause_agent_node(state: dict) -> dict:
    trace: list[dict] = []
    query = state.get("user_query", "")
    latest = get_latest_date()

    # Step 1: Identify SKU, store, anomaly date
    anomalies = state.get("anomalies") or []
    explicit_date = extract_date(query)
    explicit_store = extract_store(query)

    if anomalies:
        top = anomalies[0]
        sku = top["sku_id"]
        store = explicit_store or top.get("store_id", "CA_1")
        date = explicit_date or latest
    else:
        m = re.search(r"(FOODS|HOBBIES|HOUSEHOLD)_\d+_\d+", query.upper())
        sku = m.group(0) if m else (state.get("sku_filter") or [None])[0]
        store = explicit_store or "CA_1"
        date = explicit_date or latest

        if not sku:
            t0 = time.time()
            raw = scan_recent(lookback_days=28, store_id=store)
            trace.append({
                "agent": "RootCauseAgent", "tool": "scan_recent",
                "input": {"lookback_days": 28, "store_id": store},
                "output": raw[:5],
                "ts_ms": int(time.time() * 1000),
                "duration_ms": int((time.time() - t0) * 1000),
            })
            if raw:
                sku = raw[0]["sku_id"]
                store = raw[0].get("store_id", store)
            else:
                return {"root_causes": [], "trace": trace}

    # Step 2: Classify the anomaly on this specific date
    t0 = time.time()
    detail = classify_anomaly(sku, date, store)
    trace.append({
        "agent": "RootCauseAgent", "tool": "classify_anomaly",
        "input": {"sku_id": sku, "date": date, "store_id": store},
        "output": detail,
        "ts_ms": int(time.time() * 1000),
        "duration_ms": int((time.time() - t0) * 1000),
    })

    # Step 3: Calendar (today + +/- 3 day window)
    t0 = time.time()
    cal_today = get_calendar_context(date)
    trace.append({
        "agent": "RootCauseAgent", "tool": "get_calendar_context",
        "input": {"target_date": date}, "output": cal_today,
        "ts_ms": int(time.time() * 1000),
        "duration_ms": int((time.time() - t0) * 1000),
    })

    t0 = time.time()
    cal_window = get_calendar_window(date, before=3, after=3)
    trace.append({
        "agent": "RootCauseAgent", "tool": "get_calendar_window",
        "input": {"target_date": date, "before": 3, "after": 3},
        "output": cal_window,
        "ts_ms": int(time.time() * 1000),
        "duration_ms": int((time.time() - t0) * 1000),
    })

    # Step 4: Peer comparison
    t0 = time.time()
    peer = compare_peer_demand(sku, date, store)
    trace.append({
        "agent": "RootCauseAgent", "tool": "compare_peer_demand",
        "input": {"sku_id": sku, "target_date": date, "store_id": store},
        "output": peer,
        "ts_ms": int(time.time() * 1000),
        "duration_ms": int((time.time() - t0) * 1000),
    })

    # Step 5: Rank candidate causes (rule-based, no LLM math)
    candidate_causes = build_candidate_causes(detail, cal_today, cal_window, peer, store)

    root_causes = [{
        "sku_id":           sku,
        "date":             date,
        "store_id":         store,
        "anomaly_detail":   detail,
        "calendar_context": cal_today,
        "calendar_window":  cal_window,
        "peer_comparison":  peer,
        "candidate_causes": candidate_causes,
    }]

    return {"root_causes": root_causes, "trace": trace}
