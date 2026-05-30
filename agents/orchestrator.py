"""
LangGraph StateGraph — the single orchestration layer.
"""

import json
import time
from typing import Annotated, Optional
import operator

from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from tools.llm import simple_call
from agents.forecast_agent   import forecast_agent_node
from agents.anomaly_agent    import anomaly_agent_node
from agents.root_cause_agent import root_cause_agent_node

# ─────────────────────────────────────────────
# State
# ─────────────────────────────────────────────

class SnopState(TypedDict):
    user_query:      str
    route:           Optional[str]
    sku_filter:      Optional[list[str]]
    horizon_days:    Optional[int]
    forecast_result: Optional[dict]
    anomalies:       Optional[list[dict]]
    root_causes:     Optional[list[dict]]
    trace:           Annotated[list[dict], operator.add]
    final_answer:    Optional[str]


# ─────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────

_ROUTER_SYSTEM = """You are a query router for a demand planning copilot.
Classify the user query and extract parameters. Reply with ONLY valid JSON, no markdown.

JSON schema:
{
  "route": "forecast"|"anomaly"|"root_cause"|"multi"|"chat",
  "sku_filter": ["SKU_ID", ...] or null,
  "horizon_days": integer or null
}

route meanings:
- forecast    : user wants a demand forecast for one or more SKUs
- anomaly     : user wants to know what's unusual / needs attention
- root_cause  : user wants to know WHY a specific SKU behaved oddly
- multi       : user wants anomaly detection AND root cause in one shot
- chat        : general question, no numerical analysis needed

SKU IDs follow the pattern FOODS_1_001, HOBBIES_1_007, HOUSEHOLD_1_015, etc.
horizon_days: extract if mentioned (28 days, 4 weeks = 28, next month = 30).
"""


def router_node(state: SnopState) -> dict:
    t0 = time.time()
    text = simple_call(_ROUTER_SYSTEM, state["user_query"])

    # Strip markdown code fences if present
    text = text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = {"route": "chat", "sku_filter": None, "horizon_days": None}

    trace_entry = {
        "agent":       "Router",
        "tool":        "classify_query",
        "input":       {"query": state["user_query"]},
        "output":      parsed,
        "ts_ms":       int(time.time() * 1000),
        "duration_ms": int((time.time() - t0) * 1000),
    }
    return {
        "route":       parsed.get("route", "chat"),
        "sku_filter":  parsed.get("sku_filter"),
        "horizon_days":parsed.get("horizon_days"),
        "trace":       [trace_entry],
    }


# ─────────────────────────────────────────────
# Composer
# ─────────────────────────────────────────────

_COMPOSER_SYSTEM = """You are a demand planning copilot. Summarise ONLY the analysis results provided below.

STRICT RULES:
1. If results contain anomaly data → quote the actual SKU IDs, store IDs, severity, and numbers. Do NOT invent any.
2. If results contain forecast data → quote the actual dates and unit values shown.
3. If results contain root cause data → quote the calendar context and peer comparison numbers.
4. NEVER invent SKU IDs, store IDs, percentages, or any numbers not shown in the results.
5. NEVER say "based on our previous discussions" — this is a single-turn analysis.
6. If results section is empty → say exactly: "The analysis did not return any findings."
7. Keep it under 120 words.
"""


def composer_node(state: SnopState) -> dict:
    parts = [f"User query: {state['user_query']}\n"]

    if state.get("forecast_result"):
        fc = state["forecast_result"]
        if "error" not in fc and fc.get("forecast"):
            preview = ", ".join(
                f"{r['date']}: {r['point']}" for r in fc["forecast"][:7]
            )
            parts.append(
                f"Forecast for {fc.get('sku_id')} ({fc.get('model')}, "
                f"horizon={fc.get('horizon_days')}d, "
                f"history={fc.get('history_used_days')}d):\n"
                f"First 7 days: {preview}"
            )
        elif "error" in fc:
            parts.append(f"Forecast error: {fc['error']}")

    if state.get("anomalies"):
        lines = []
        for a in state["anomalies"][:5]:
            lines.append(
                f"  - {a['sku_id']} ({a.get('store_id','?')}): "
                f"{', '.join(a.get('anomaly_types', []))} "
                f"severity={a.get('severity')} "
                f"recent={a.get('recent_avg')} vs baseline={a.get('baseline_avg')}"
            )
        parts.append("Anomalies:\n" + "\n".join(lines))

    if state.get("root_causes"):
        lines = []
        for rc in state["root_causes"][:3]:
            lines.append(f"  SKU: {rc.get('sku_id','?')}")
            if rc.get("candidate_causes"):
                # Structured format
                for c in rc["candidate_causes"][:3]:
                    lines.append(f"    Cause: {c.get('cause')} | Evidence: {c.get('evidence')} | Confidence: {c.get('confidence')}")
            if rc.get("anomaly_detail"):
                a = rc["anomaly_detail"]
                lines.append(f"    Anomaly: type={a.get('type')} severity={a.get('severity')} zscore={a.get('zscore')} actual={a.get('actual_units')} baseline={a.get('baseline_mean')} — {a.get('evidence','')}")
            if rc.get("calendar_context"):
                cal = rc["calendar_context"]
                lines.append(f"    Calendar: day={cal.get('day_name','?')}, holiday={cal.get('holiday_name') or 'none'}, snap_ca={cal.get('snap_ca')}, snap_tx={cal.get('snap_tx')}, snap_wi={cal.get('snap_wi')}")
            if rc.get("peer_comparison"):
                peer = rc["peer_comparison"]
                lines.append(f"    Peers: sku_change={peer.get('sku_pct_change')}% vs peer_change={peer.get('peer_pct_change')}%, peers_same_direction={peer.get('peers_moved_same_direction')}, n_peers={peer.get('n_peers')}")
            if rc.get("agent_analysis"):
                lines.append(f"    Agent notes: {rc['agent_analysis'][:300]}")
        parts.append("Root cause analysis:\n" + "\n".join(lines))

    if not any([state.get("forecast_result"), state.get("anomalies"), state.get("root_causes")]):
        parts.append(
            "No analysis was run. Answer the user's general demand planning question."
        )

    t0 = time.time()
    answer = simple_call(_COMPOSER_SYSTEM, "\n\n".join(parts))

    trace_entry = {
        "agent":       "Composer",
        "tool":        "compose_answer",
        "input":       {"route": state.get("route")},
        "output":      {"preview": answer[:120] + "..." if len(answer) > 120 else answer},
        "ts_ms":       int(time.time() * 1000),
        "duration_ms": int((time.time() - t0) * 1000),
    }
    return {"final_answer": answer, "trace": [trace_entry]}


# ─────────────────────────────────────────────
# Routing edges
# ─────────────────────────────────────────────

def _after_router(state: SnopState) -> str:
    route = state.get("route", "chat")
    if route == "forecast":                  return "forecast_agent"
    if route in ("anomaly", "multi"):        return "anomaly_agent"
    if route == "root_cause":                return "root_cause_agent"
    return "composer"


def _after_anomaly(state: SnopState) -> str:
    if state.get("route") == "multi" and state.get("anomalies"):
        return "root_cause_agent"
    return "composer"


# ─────────────────────────────────────────────
# Graph
# ─────────────────────────────────────────────

def build_graph():
    g = StateGraph(SnopState)
    g.add_node("router",           router_node)
    g.add_node("forecast_agent",   forecast_agent_node)
    g.add_node("anomaly_agent",    anomaly_agent_node)
    g.add_node("root_cause_agent", root_cause_agent_node)
    g.add_node("composer",         composer_node)

    g.add_edge(START, "router")
    g.add_conditional_edges("router", _after_router, {
        "forecast_agent":   "forecast_agent",
        "anomaly_agent":    "anomaly_agent",
        "root_cause_agent": "root_cause_agent",
        "composer":         "composer",
    })
    g.add_edge("forecast_agent", "composer")
    g.add_conditional_edges("anomaly_agent", _after_anomaly, {
        "root_cause_agent": "root_cause_agent",
        "composer":         "composer",
    })
    g.add_edge("root_cause_agent", "composer")
    g.add_edge("composer", END)
    return g.compile()


graph = build_graph()
