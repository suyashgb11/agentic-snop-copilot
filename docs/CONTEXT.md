# Project Context — Agentic S&OP Copilot

One-page briefing. If you open this file fresh and read top to bottom, you can start writing code without re-reading the rest of the repo.

## What we are building

A multi-agent AI demand planning copilot on the M5 Walmart dataset. A demand planner asks natural-language questions ("what needs my attention this week?", "why did SKU 4421 spike?", "forecast HOBBIES_1_001 for 28 days") and a system of specialist agents collaborates to answer them. The UI shows the full agent trace so every claim is auditable.

The project ships in 6 weeks as a public demo, on a public dataset, with public code. It exists so a working demand planner has a real artifact that demonstrates "I understand agentic AI in supply chain" to recruiters and hiring managers on LinkedIn.

## The one rule that defines the system

The LLM is not allowed to do arithmetic.

Every number in the output traces back to a tool call (StatsForecast, DuckDB, a statistical rule). The LLM picks tools, reads results, and writes explanations in English. It does not multiply, average, aggregate, or "summarize the trend" numerically.

This is the rule that separates a planner-grade tool from a chatbot. If this rule breaks, the project fails its design goal. Every implementation decision should preserve it.

## Architecture

```
[User] -> Streamlit chat
   |
   v
[Orchestrator] LangGraph state machine
   |
   |-- Forecast Agent       (tools: StatsForecast wrapper)
   |-- Anomaly Agent        (tools: DuckDB rules + LLM ranker)
   |-- Root-Cause Agent     (tools: event ctx + peer compare)
   |
   v
[Composer] -> Streamlit response + trace panel
```

Single LangGraph `StateGraph`. Router node classifies the user query. One or more specialist nodes execute. Composer node produces the final answer. Agents do not call each other directly. The state object is the only communication channel.

## State

```python
from pydantic import BaseModel
from typing import Literal

class SnopState(BaseModel):
    user_query: str
    route: Literal["forecast", "anomaly", "root_cause", "multi", "chat"] | None = None
    sku_filter: list[str] | None = None
    horizon_days: int | None = None
    forecast_result: dict | None = None
    anomalies: list[dict] | None = None
    root_causes: list[dict] | None = None
    trace: list[dict] = []        # [{agent, tool, input, output, ts_ms}, ...]
    final_answer: str | None = None
```

Every tool call appends to `trace`. The UI renders `trace` as a collapsible panel.

## Stack

| Layer        | Choice                          |
|--------------|---------------------------------|
| Language     | Python 3.11+                    |
| Orchestration| LangGraph                       |
| LLM          | Anthropic Claude Sonnet 4.6     |
| Forecasting  | StatsForecast (Nixtla)          |
| Data         | DuckDB on M5 dataset            |
| UI           | Streamlit + Plotly              |
| Deploy       | Hugging Face Spaces             |

## Data

Source: M5 Forecasting (Walmart), public on Kaggle and mirrored on Hugging Face.
Scale: 30,490 SKUs across 10 stores in CA, TX, WI. 1,941 days of daily sales. Holiday and SNAP event flags.
For the demo: subset to ~100 SKUs across 3 categories (Foods, Hobbies, Household) so forecasts run fast and the LLM has fewer SKU codes to keep straight.

Three DuckDB tables:

```sql
sales(sku_id TEXT, store_id TEXT, date DATE, units INTEGER)
calendar(date DATE, day_of_week INTEGER, is_weekend BOOL, is_holiday BOOL,
         holiday_name TEXT, snap_ca BOOL, snap_tx BOOL, snap_wi BOOL)
forecasts(sku_id TEXT, date_made DATE, horizon_date DATE, model TEXT,
          point DOUBLE, lo80 DOUBLE, hi80 DOUBLE, lo95 DOUBLE, hi95 DOUBLE)
```

## File layout (already scaffolded, mostly empty)

```
agentic-snop-copilot/
  README.md                done
  requirements.txt         done
  .env.example             done
  .gitignore               done
  app.py                   TODO  Streamlit entry
  agents/
    __init__.py
    forecast_agent.py      TODO
    anomaly_agent.py       TODO
    root_cause_agent.py    TODO
    orchestrator.py        TODO  LangGraph StateGraph
  tools/
    __init__.py
    data_access.py         TODO  DuckDB query fns
    forecasting.py         TODO  StatsForecast wrapper
    anomaly_detection.py   TODO  z-score + EWMA rules
  data/
    __init__.py
    load_m5.py             TODO  download + subset + load DuckDB
    prep.py                TODO  data quality / zero handling
  ui/
    __init__.py
    chat.py                TODO
    dashboard.py           TODO
    trace_view.py          TODO
  tests/
    __init__.py
  docs/
    ARCHITECTURE.md        done
    LINKEDIN_PLAYBOOK.md   done
    CONTEXT.md             this file
```

## Build order (start at the top)

1. **`data/load_m5.py`** — download M5 (Hugging Face mirror, no Kaggle auth needed), subset to 100 SKUs across 3 categories, load into `data/snop.duckdb`. Idempotent.
2. **`tools/data_access.py`** — DuckDB query functions the agents will call: `get_history(sku, days)`, `get_calendar_context(date)`, `get_peer_skus(sku, n=10)`, `list_skus()`.
3. **`tools/forecasting.py`** — StatsForecast wrapper: `run_forecast(sku, horizon)`, `get_accuracy(sku)`. Fits AutoARIMA or ETS based on seasonality detection. Writes results to the `forecasts` table.
4. **`tools/anomaly_detection.py`** — pure-Python statistical rules: `scan_recent(category, lookback_days)` returns candidate anomalies with reason codes. Z-score against rolling mean, EWMA bias detection, week-over-week percent change.
5. **`agents/forecast_agent.py`** — LangGraph node. Receives `SnopState`. Picks tools from step 3. Returns updated state with `forecast_result` populated and trace appended.
6. **`agents/anomaly_agent.py`** — LangGraph node. Calls step 4 to generate candidates, then asks the LLM to rank which ones matter for a planner this week. Populates `anomalies`.
7. **`agents/root_cause_agent.py`** — LangGraph node. For each anomaly, fetches calendar context + peer comparison, returns ranked candidate causes with evidence. Populates `root_causes`.
8. **`agents/orchestrator.py`** — LangGraph `StateGraph`. Router node + edges to specialist nodes + composer node.
9. **`app.py`** — Streamlit. Chat input on the left, conversation + plots in the center, trace panel on the right.
10. **Deploy** — push to Hugging Face Spaces with `ANTHROPIC_API_KEY` as a secret.

## Hard rules (do not break)

1. The LLM does not do arithmetic. Every number = tool call.
2. Tools return structured Pydantic objects, not free-form strings.
3. State transitions are explicit LangGraph nodes, not agent-to-agent chatter.
4. Every action appends to `state.trace` before the composer reads state.
5. Refusal is a feature. Agents must be allowed to say "insufficient history", "ambiguous query", "no anomalies this week". Never bluff a number.

## Quickstart

```bash
cd agentic-snop-copilot
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # then paste ANTHROPIC_API_KEY=...
python data/load_m5.py              # builds data/snop.duckdb
python tools/forecasting.py         # fits baselines, writes forecasts table
streamlit run app.py                # opens the UI
```

## LinkedIn launch timeline (parallel deliverable)

| Week | Code milestone                | LinkedIn post                                |
|------|-------------------------------|----------------------------------------------|
| 0    | Scaffold (done)               | Kickoff: "6-week build starting today"       |
| 1    | Data layer                    | "How a planner thinks about a sales dataset" |
| 2    | Forecast agent                | "The LLM is not allowed to do math"          |
| 3    | Anomaly agent                 | 90-second demo video                         |
| 4    | Root-cause + orchestrator     | "The most expensive S&OP question"           |
| 5    | Deploy + launch               | Public demo URL + lessons learned            |
| 6    | Retro                         | "5 lessons from building agentic AI"         |

Full post drafts are in `docs/LINKEDIN_PLAYBOOK.md`.

## Open questions (revisit at week 4)

- Open-source the repo, or keep closed and offer hosted demo only? (Open = reach, closed = DMs.)
- Add a v2 scenario agent (what-if promo lift) or save it for a separate launch?
- Mock writeback to o9/IBP via a connector stub, or skip?
- Pitch the project to Supply Chain Now / The Logistics of Logistics podcast after week 6?

## Glossary (for non-planners reading the code)

- **S&OP** — Sales and Operations Planning. The weekly/monthly meeting where forecasts, inventory, supply, and demand are reconciled.
- **MAPE** — Mean Absolute Percent Error. The most common forecast accuracy metric in planning.
- **Bias** — Whether a forecast consistently over- or under-predicts. Bias of zero means no systematic skew.
- **SNAP** — Supplemental Nutrition Assistance Program. M5 includes per-state SNAP event flags because they correlate with grocery demand spikes.
- **SKU** — Stock Keeping Unit. The most granular product identifier.
- **Stockout** — Inventory hit zero and you couldn't sell. Looks like "zero demand" in the data but isn't.
