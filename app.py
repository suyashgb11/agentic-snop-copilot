"""
Streamlit entry point — S&OP Copilot.
Run: streamlit run app.py
"""

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="S&OP Copilot",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.stApp { background-color: #0f1117; }
[data-testid="stSidebar"] {
    background-color: #161b27;
    border-right: 1px solid #1e2533;
}
[data-testid="stChatMessage"] {
    background-color: #1a1f2e;
    border-radius: 10px;
    margin-bottom: 8px;
    border: 1px solid #1e2533;
}
[data-testid="stChatInput"] textarea {
    background-color: #1a1f2e !important;
    border: 1px solid #2d3748 !important;
    color: #e2e8f0 !important;
    border-radius: 10px !important;
}
[data-testid="stMetric"] {
    background-color: #1a1f2e;
    border: 1px solid #1e2533;
    border-radius: 8px;
    padding: 12px;
}
[data-testid="stExpander"] {
    background-color: #1a1f2e;
    border: 1px solid #1e2533;
    border-radius: 8px;
}
.team-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
    margin-right: 6px;
    margin-bottom: 6px;
}
.badge-active   { background:#1e3a5f; color:#60a5fa; border: 1px solid #2563eb; }
.badge-soon     { background:#1a1f2e; color:#475569; border: 1px solid #334155; }
</style>
""", unsafe_allow_html=True)

# ── Imports ───────────────────────────────────────────────────────────────────
from agents.orchestrator import graph
from ui.chat import render_message, render_example_queries
from ui.dashboard import render_forecast_chart, render_anomaly_chart
from ui.trace_view import render_trace

# ── Session state ─────────────────────────────────────────────────────────────
for key, default in [
    ("messages", []),       # each entry: {role, content, forecast?, anomalies?, trace?}
    ("query_count", 0),
    ("last_trace", []),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='text-align:center; padding: 8px 0 4px 0;'>
        <span style='font-size:32px'>📦</span><br>
        <span style='font-size:18px; font-weight:700; color:#e2e8f0'>S&OP Copilot</span><br>
        <span style='font-size:11px; color:#64748b'>AI-powered supply chain intelligence</span>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # Status row
    db_path  = os.getenv("DUCKDB_PATH", "data/snop.duckdb")
    db_ok    = Path(db_path).exists()
    llm_name = (
        f"Ollama · {os.getenv('OLLAMA_MODEL','llama3.1')}"
        if os.getenv("OLLAMA_MODEL") else
        f"Gemini · {os.getenv('GOOGLE_MODEL','gemini-2.5-flash')}"
        if os.getenv("GOOGLE_API_KEY") else
        f"Claude · {os.getenv('ANTHROPIC_MODEL','claude-sonnet-4-6')}"
    )
    c1, c2 = st.columns(2)
    c1.metric("LLM", llm_name.split("·")[0].strip(), llm_name.split("·")[1].strip() if "·" in llm_name else "")
    c2.metric("Queries", st.session_state.query_count)
    if not db_ok:
        st.error("Database not found — run `python data/load_m5.py`")

    st.divider()
    render_example_queries()
    st.divider()

    if st.session_state.last_trace:
        render_trace(st.session_state.last_trace)
    else:
        st.caption("Agent trace will appear here after your first query.")

# ── Main header ───────────────────────────────────────────────────────────────
st.markdown("""
<h2 style='margin-bottom:2px; color:#e2e8f0'>S&OP Copilot</h2>
<p style='color:#64748b; margin-top:0; font-size:13px'>
    AI-powered supply chain intelligence across demand, inventory, supply, and logistics.
</p>
""", unsafe_allow_html=True)

# ── Team navigation ───────────────────────────────────────────────────────────
st.markdown("""
<div style='margin-bottom: 16px;'>
    <span class='team-badge badge-active'>📈 Demand Planning</span>
    <span class='team-badge badge-soon'>📦 Inventory</span>
    <span class='team-badge badge-soon'>🏭 Supply Planning</span>
    <span class='team-badge badge-soon'>🚚 Logistics</span>
    <span class='team-badge badge-soon'>💰 Finance</span>
</div>
""", unsafe_allow_html=True)

st.divider()

# ── DB check (auto-bootstrap on first run, e.g. Hugging Face Spaces) ──────────
if not Path(db_path).exists():
    with st.spinner("First-time setup: building synthetic M5 dataset (about 30 seconds)…"):
        from data.load_m5 import load as _load_db
        _load_db(force=True)
    st.rerun()

# ── Conversation — render each message + its attached charts ──────────────────
for i, msg in enumerate(st.session_state.messages):
    render_message(msg["role"], msg["content"])

    # Charts are stored with each assistant message — persist across turns
    if msg["role"] == "assistant":
        fc  = msg.get("forecast")
        anom = msg.get("anomalies")
        if fc and "forecast" in fc:
            render_forecast_chart(fc, key=f"fc_{i}")
        if anom:
            render_anomaly_chart(anom, key=f"anom_{i}")

# ── Pending query from sidebar buttons ────────────────────────────────────────
pending    = st.session_state.pop("pending_query", None)
user_input = st.chat_input("Ask your demand planning question…") or pending

if user_input:
    render_message("user", user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.spinner("🤖 Agents running…"):
        try:
            result   = graph.invoke({
                "user_query": user_input, "route": None, "sku_filter": None,
                "horizon_days": None, "forecast_result": None, "anomalies": None,
                "root_causes": None, "trace": [], "final_answer": None,
            })
            answer   = result.get("final_answer") or "I wasn't able to generate a response."
            trace    = result.get("trace") or []
            forecast = result.get("forecast_result")
            anomalies= result.get("anomalies") or []

            # Store charts WITH the message so they persist across turns
            assistant_msg = {
                "role":      "assistant",
                "content":   answer,
                "forecast":  forecast,
                "anomalies": anomalies,
                "trace":     trace,
            }
            st.session_state.messages.append(assistant_msg)
            st.session_state.last_trace  = trace
            st.session_state.query_count += 1

        except Exception as e:
            answer = f"**Error:** {e}"
            st.session_state.messages.append({"role": "assistant", "content": answer})
            st.session_state.last_trace = []

    render_message("assistant", answer)
    st.rerun()
