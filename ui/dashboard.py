"""
Plotly charts — forecast fan, anomaly bar, history line.
"""

import plotly.graph_objects as go
import streamlit as st

_DARK_BG   = "rgba(15,17,23,0)"
_GRID_COL  = "#1e2533"
_TEXT_COL  = "#94a3b8"
_FONT      = dict(family="Inter, sans-serif", color=_TEXT_COL)


def _base_layout(**kwargs) -> dict:
    return dict(
        font=_FONT,
        plot_bgcolor=_DARK_BG,
        paper_bgcolor=_DARK_BG,
        xaxis=dict(gridcolor=_GRID_COL, zerolinecolor=_GRID_COL, tickfont=dict(color=_TEXT_COL)),
        yaxis=dict(gridcolor=_GRID_COL, zerolinecolor=_GRID_COL, tickfont=dict(color=_TEXT_COL)),
        margin=dict(l=50, r=30, t=60, b=40),
        **kwargs,
    )


def render_forecast_chart(forecast_result: dict) -> None:
    if not forecast_result or "forecast" not in forecast_result:
        return
    rows = forecast_result["forecast"]
    if not rows:
        return

    dates = [r["date"] for r in rows]
    point = [r["point"] for r in rows]
    lo80  = [r["lo80"]  for r in rows]
    hi80  = [r["hi80"]  for r in rows]
    lo95  = [r["lo95"]  for r in rows]
    hi95  = [r["hi95"]  for r in rows]

    sku   = forecast_result.get("sku_id", "SKU")
    model = forecast_result.get("model", "AutoARIMA")
    mape  = forecast_result.get("mape")
    mape_txt = f" · MAPE {mape}%" if mape else ""

    fig = go.Figure()

    # 95% confidence band
    fig.add_trace(go.Scatter(
        x=dates + dates[::-1], y=hi95 + lo95[::-1],
        fill="toself", fillcolor="rgba(99,102,241,0.08)",
        line=dict(color="rgba(0,0,0,0)"),
        name="95% interval", hoverinfo="skip",
    ))
    # 80% confidence band
    fig.add_trace(go.Scatter(
        x=dates + dates[::-1], y=hi80 + lo80[::-1],
        fill="toself", fillcolor="rgba(99,102,241,0.18)",
        line=dict(color="rgba(0,0,0,0)"),
        name="80% interval", hoverinfo="skip",
    ))
    # Point forecast
    fig.add_trace(go.Scatter(
        x=dates, y=point, mode="lines+markers",
        name="Forecast",
        line=dict(color="#818cf8", width=2.5),
        marker=dict(size=5, color="#818cf8"),
        hovertemplate="%{x}<br><b>%{y:.1f} units</b><extra></extra>",
    ))

    fig.update_layout(
        **_base_layout(
            title=dict(text=f"📈 Demand Forecast — {sku}  <sup>{model}{mape_txt}</sup>",
                       font=dict(size=15, color="#e2e8f0")),
            height=360,
            legend=dict(orientation="h", y=1.08, x=1, xanchor="right",
                        font=dict(color=_TEXT_COL), bgcolor="rgba(0,0,0,0)"),
        )
    )
    st.plotly_chart(fig, use_container_width=True)


def render_anomaly_chart(anomalies: list[dict]) -> None:
    if not anomalies:
        return

    # Use z-score if available, otherwise use % deviation from baseline
    def _score(a: dict) -> float:
        if a.get("zscore") is not None:
            return abs(float(a["zscore"]))
        base = a.get("baseline_avg") or 1
        rec  = a.get("recent_avg") or 0
        return abs((rec - base) / base) * 10   # scale to be comparable

    def _label(a: dict) -> str:
        if a.get("zscore") is not None:
            return f"z = {abs(a['zscore']):.1f}"
        base = a.get("baseline_avg") or 1
        rec  = a.get("recent_avg") or 0
        pct  = (rec - base) / base * 100
        return f"{pct:+.0f}%"

    top        = sorted(anomalies, key=_score, reverse=True)[:10]
    skus       = [f"{a['sku_id']}\n({a.get('store_id','?')})" for a in top]
    scores     = [_score(a) for a in top]
    severities = [a.get("severity", "low") for a in top]
    labels     = [_label(a) for a in top]

    color_map = {"high": "#ef4444", "medium": "#f59e0b", "low": "#34d399"}
    colors    = [color_map.get(s, "#64748b") for s in severities]

    fig = go.Figure(go.Bar(
        x=scores, y=skus,
        orientation="h",
        marker_color=colors,
        text=labels,
        textposition="outside",
        textfont=dict(color=_TEXT_COL, size=11),
        hovertemplate="%{y}<br>Score: <b>%{x:.2f}</b><extra></extra>",
    ))
    fig.update_layout(
        **_base_layout(
            title=dict(text=f"🚨 Anomaly Scan — {len(top)} SKUs Flagged",
                       font=dict(size=15, color="#e2e8f0")),
            height=max(300, len(top) * 42),
            xaxis_title="Anomaly Score (z-score or scaled % deviation)",
            showlegend=False,
        )
    )
    st.plotly_chart(fig, use_container_width=True)


def render_history_chart(history: list[dict], sku_id: str) -> None:
    if not history:
        return
    dates = [h["date"]  for h in history]
    units = [h["units"] for h in history]

    fig = go.Figure(go.Scatter(
        x=dates, y=units, mode="lines",
        name="Actuals",
        line=dict(color="#34d399", width=2),
        fill="tozeroy", fillcolor="rgba(52,211,153,0.08)",
        hovertemplate="%{x}<br><b>%{y} units</b><extra></extra>",
    ))
    fig.update_layout(
        **_base_layout(
            title=dict(text=f"Sales History — {sku_id}",
                       font=dict(size=14, color="#e2e8f0")),
            height=280,
        )
    )
    st.plotly_chart(fig, use_container_width=True)
