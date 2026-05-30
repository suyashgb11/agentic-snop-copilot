# Architecture

## Design principles

1. **Agents are tool-users, not oracles.** Every numeric claim an agent makes comes from a tool call (DuckDB query, StatsForecast run, anomaly rule), not from the LLM's head. The LLM picks tools and explains results.
2. **Trace everything.** The UI shows which agent ran, which tools it called, and what came back. Planners will not trust black boxes.
3. **One graph, many specialists.** Single LangGraph orchestrator routes to specialist agents. Easier to reason about than free-form agent-to-agent chatter.

## Components

### Orchestrator (`agents/orchestrator.py`)

LangGraph `StateGraph` with the following nodes:

- `router` — LLM call that classifies the user query into one of: `forecast`, `anomaly`, `root_cause`, `multi`, `chat`.
- `forecast_agent` — handles forecast questions.
- `anomaly_agent` — handles "what's wrong / what needs my attention" questions.
- `root_cause_agent` — handles "why did X happen" questions.
- `composer` — combines outputs into final user-facing message + trace.

Edges:

```
START -> router
router -> forecast_agent | anomaly_agent | root_cause_agent | composer (for chat)
forecast_agent -> composer
anomaly_agent -> root_cause_agent (if anomaly found and user wants explanation)
                | composer
root_cause_agent -> composer
composer -> END
```

State (Pydantic):

```python
class SnopState(BaseModel):
    user_query: str
    route: Literal["forecast", "anomaly", "root_cause", "multi", "chat"] | None
    sku_filter: list[str] | None
    horizon_days: int | None
    forecast_result: dict | None
    anomalies: list[dict] | None
    root_causes: list[dict] | None
    trace: list[dict]         # [{agent, tool, input, output, ts}, ...]
    final_answer: str | None
```

### Forecast Agent (`agents/forecast_agent.py`)

Tools it can call:
- `get_history(sku, days)` -> DataFrame
- `run_forecast(sku, horizon)` -> {forecast, lo80, hi80, lo95, hi95}
- `get_accuracy(sku)` -> {mape, bias, rmse}

Returns: structured forecast + plain-English summary.

### Anomaly Agent (`agents/anomaly_agent.py`)

Tools:
- `scan_recent(category=None, lookback_days=14)` -> list of flagged SKUs with reason codes.
- `classify_anomaly(sku, date)` -> {type: spike|dip|bias|drift, severity, evidence}

Rules layer is statistical (z-score vs rolling mean, EWMA bias detection). LLM only ranks and narrates — it does not invent numbers.

### Root-Cause Agent (`agents/root_cause_agent.py`)

Tools:
- `get_event_context(sku, date)` -> {is_holiday, is_promo, day_of_week, weather_proxy}
- `compare_to_peers(sku, date)` -> {peer_avg_change, did_peers_spike_too}
- `get_history(sku, days)` -> for narrative

Returns ranked candidate causes with evidence per cause. Never asserts a single cause as fact.

## Data layer

DuckDB file at `data/snop.duckdb` with three tables:

- `sales(sku_id, store_id, date, units)`
- `calendar(date, day_of_week, is_weekend, is_holiday, holiday_name, snap_ca, snap_tx, snap_wi)`
- `forecasts(sku_id, date_made, horizon_date, model, point, lo80, hi80, lo95, hi95)`

All agent tools read from DuckDB. Keeps the LLM out of arithmetic.

## Why this stack will signal what we want it to signal

| Signal we want to send         | How the stack proves it                                  |
|--------------------------------|----------------------------------------------------------|
| "I understand agentic AI"      | LangGraph multi-agent + visible trace                    |
| "I know real planning"         | M5 dataset, StatsForecast, MAPE/bias, S&OP vocabulary    |
| "I can ship, not just notebook"| Streamlit app deployed on HF Spaces with a public URL    |
| "I think about trust + audit"  | Every numeric claim traceable to a tool call             |

## Out of scope for v1

- Scenario / what-if agent (v2)
- Real promo data (M5 has SNAP events; full promo lift modeling is v2)
- Multi-tenant auth
- Writing back to a planning system (e.g., o9, IBP) — interesting demo for v2 via a mock connector
