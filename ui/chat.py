"""
Chat rendering helpers.
"""

import streamlit as st

_EXAMPLES = [
    ("🔍", "What needs my attention this week?"),
    ("📈", "Forecast FOODS_1_003 for 28 days"),
    ("🔍", "Why did FOODS_1_003 spike recently?"),
    ("🚨", "Any anomalies in the HOBBIES category?"),
    ("📊", "Forecast accuracy for HOUSEHOLD_1_015"),
    ("📈", "Forecast HOBBIES_1_007 for 14 days"),
]


def render_message(role: str, content: str) -> None:
    with st.chat_message(role):
        st.markdown(content)


def render_chat_history(messages: list[dict]) -> None:
    for msg in messages:
        render_message(msg["role"], msg["content"])


def render_example_queries() -> None:
    st.markdown("<span style='font-size:12px; color:#64748b; font-weight:600'>EXAMPLE QUERIES</span>",
                unsafe_allow_html=True)
    for icon, q in _EXAMPLES:
        if st.button(f"{icon} {q}", key=f"eq_{q[:25]}", use_container_width=True):
            st.session_state["pending_query"] = q
            st.rerun()
