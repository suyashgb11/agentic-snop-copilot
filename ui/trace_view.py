"""
Agent trace panel — shows every tool call with inputs/outputs.
"""

import json
import streamlit as st

_AGENT_META = {
    "Router":        {"icon": "🔀", "color": "#6366f1"},
    "ForecastAgent": {"icon": "📈", "color": "#10b981"},
    "AnomalyAgent":  {"icon": "🚨", "color": "#f59e0b"},
    "RootCauseAgent":{"icon": "🔍", "color": "#ef4444"},
    "Composer":      {"icon": "✍️", "color": "#8b5cf6"},
}


def _fmt(obj) -> str:
    if isinstance(obj, (dict, list)):
        s = json.dumps(obj, indent=2, default=str)
        return s[:600] + f"\n… ({len(s)-600} more chars)" if len(s) > 600 else s
    return str(obj)[:400]


def render_trace(trace: list[dict]) -> None:
    if not trace:
        return

    total_ms = sum(t.get("duration_ms", 0) for t in trace)

    st.markdown(f"""
    <div style='font-size:13px; font-weight:600; color:#e2e8f0; margin-bottom:4px'>
        Agent Trace
    </div>
    <div style='font-size:11px; color:#64748b; margin-bottom:8px'>
        {len(trace)} tool calls · {total_ms:,} ms total
    </div>
    """, unsafe_allow_html=True)

    for i, entry in enumerate(trace):
        agent    = entry.get("agent", "Unknown")
        tool     = entry.get("tool", "?")
        duration = entry.get("duration_ms", 0)
        meta     = _AGENT_META.get(agent, {"icon": "⚙️", "color": "#64748b"})

        label = f"{meta['icon']} **{agent}** › `{tool}`  ·  {duration} ms"

        with st.expander(label, expanded=(i == len(trace) - 1)):
            inp = entry.get("input", {})
            out = entry.get("output", {})

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("<span style='font-size:11px;color:#64748b'>INPUT</span>", unsafe_allow_html=True)
                st.code(_fmt(inp), language="json")
            with c2:
                st.markdown("<span style='font-size:11px;color:#64748b'>OUTPUT</span>", unsafe_allow_html=True)
                st.code(_fmt(out), language="json")
