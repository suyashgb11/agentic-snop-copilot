# Handoff — Agentic S&OP Copilot

Drop this into a new Cowork session (or any fresh chat) and the agent can pick up exactly where we left off.

Updated: 2026-06-27

## What this project is

A multi-agent demand planning copilot built on synthetic M5 Walmart data. A planner asks a natural-language question, a LangGraph orchestrator routes to a specialist agent (forecast, anomaly, root cause), and the answer comes back with a full agent trace.

The one rule that defines the whole system: **the LLM is not allowed to do arithmetic**. Every number in the output comes from a tool call (DuckDB query, StatsForecast model, statistical rule). The LLM only narrates real results. Agents call tools directly in Python rather than via LLM tool-calling, because llama3.1 was hallucinating SKU IDs and percentages during testing.

This is a portfolio project. It runs free and local on Ollama. The plan is to ship one LinkedIn post per week showing progress, with the GitHub repo public from day one.

- Repo: github.com/suyashgb11/agentic-snop-copilot
- LinkedIn: linkedin.com/in/suyashkulkarni11/
- Local path: `C:\Users\suyas\Desktop\Claude\projects\agentic-snop-copilot`

## Stack

- Python 3.13 on Windows
- LangGraph for the orchestrator (StateGraph, TypedDict state, append-only trace)
- DuckDB for all data queries (single shared read-write connection)
- StatsForecast (AutoARIMA + SeasonalNaive) for forecasting
- Ollama running llama3.1 locally for the LLM layer
- Streamlit + Plotly for the dark-themed UI

## Data

- 100 SKUs across 3 stores (CA_1, TX_1, WI_1), 1,941 days of daily history, 582,300 rows total
- Realistic patterns: weekday effects, holiday boosts, SNAP-day bumps
- 25+ injected anomalies across the full history (spikes, stockouts, drift, regional events, category shocks)
- Regenerate with `python data/load_m5.py` (pass `force=True` to rebuild)

## What is done

**Week 1**
- End-to-end working system: load data, run baselines, query through Streamlit chat
- Provider abstraction layer (Ollama, Gemini, Anthropic) in `tools/llm.py`
- Three working agents wired into the orchestrator
- Initial CA_1 baselines, anomaly chart, forecast fan chart
- GitHub repo pushed, README written, LinkedIn Post 1 published

**Week 2**
- Baselines run for all 3 stores: 5,628 forecast rows, 100 OK, 0 skipped (`tools/run_baselines.py`)
- Combined chart: 60 days of green actuals merging into purple forecast with 80/95% bands and a dashed "Forecast start" line (`ui/dashboard.py:render_forecast_chart`)
- Fixed `add_vline` crash on string dates by switching to `add_shape` + `add_annotation`
- Fixed Streamlit duplicate-element-id error by passing per-message `key=` to every `plotly_chart` call
- Charts persist across conversation turns (stored on each assistant message in session state)
- UI headings updated: "S&OP Copilot" with greyed-out team badges for future expansion (Inventory, Supply Planning, Logistics, Finance)
- LinkedIn Post 2 drafted: angle is "the LLM is not allowed to do arithmetic"

## Open items right now

1. Commit and push Week 2 + 3 + 4 changes from PowerShell. The Cowork sandbox cannot write into `.git/` on the Windows mount. Files to stage:
   - `app.py`, `ui/dashboard.py`, `tools/run_baselines.py`, `.gitignore` (Week 2)
   - `agents/anomaly_agent.py` (Week 3 multi-store scan)
   - `agents/root_cause_agent.py`, `agents/root_cause_helpers.py` (new), `tools/data_access.py` (Week 4 calendar window + peer math + candidate causes)
   - `requirements.txt` (google-genai, ollama)
   - `docs/HANDOFF.md`, `docs/HF_DEPLOY.md`
2. Hard-refresh smoke test: forecast + anomaly + root-cause in one session, confirm no duplicate-key error and the multi-store anomaly list spans CA_1/TX_1/WI_1.
3. Take a screenshot of the combined chart, post LinkedIn Post 2 ("the LLM is not allowed to do arithmetic").

## Week 3 + 4 (done)

- **Week 3**: `agents/anomaly_agent.py` now scans CA_1, TX_1, WI_1 by default and re-ranks merged results. Per-store filter still works ("scan TX_1 ...").
- **Week 4**: root cause agent
  - New `tools/data_access.get_calendar_window(target_date, before, after)`. Returns nearby holidays + SNAP days with offset_days.
  - `compare_peer_demand` rewritten: two non-overlapping 7-day windows both ending at or before target_date (no future leakage).
  - New `agents/root_cause_helpers.py`: `build_candidate_causes` ranks stockout / holiday / SNAP / category-wide / idiosyncratic with high/medium/low confidence.
  - `root_cause_agent_node` extracts date from "on YYYY-MM-DD" and store from "CA_1/TX_1/WI_1" in the query.

## Week 5 onward

- **Week 5**: deploy to Hugging Face Spaces. Playbook in `docs/HF_DEPLOY.md`. App now auto-bootstraps the DB on cold start.
- **Week 6**: polish, write a case-study post, add a "what I learned" section to the README. Future agents: Inventory, Supply Planning.

## Sandbox gotcha discovered 2026-06-27

The Windows mount truncates large single file writes from Claude's tools (about 3.5 to 7.5 KB depending on path). Symptoms: file ends mid-line, syntax error on compile. Workaround: write in two passes with bash heredoc (`head -n N file > head.py; cat head.py tail.py > file`), or split modules so each stays under the threshold (that's why `root_cause_helpers.py` exists separately from `root_cause_agent.py`).

## Things to know before touching the code

- **DuckDB does not support `DATE ?` parameterized queries.** Use f-string interpolation in `tools/data_access.py`. Yes it looks ugly. Yes it was the only thing that worked.
- **Single shared read-write DuckDB connection.** Both `data_access.py` and `forecasting.py` go through `get_con()`. Do not open a second connection or you will hit a lock.
- **If Streamlit is running, the DB is locked.** Kill the Streamlit process before running test scripts that write to the DB.
- **Ollama llama3.1 passes integers as strings** when tool-calling. `_coerce_args()` in `tools/llm.py` handles this. Do not remove it.
- **Agents do not use LLM tool-calling.** They call tools directly in Python and pass results into `simple_call()` for narration. This is intentional, not laziness. It is the only way to guarantee no hallucinated numbers.
- **No em-dashes in any user-facing writing.** This includes LinkedIn posts, README, and code comments.
- **`.env` is never committed.** `.env.example` was removed at the user's request. Do not recreate it.

## How to run

```powershell
cd C:\Users\suyas\Desktop\Claude\projects\agentic-snop-copilot
python -m streamlit run app.py
```

App opens at `localhost:8501`. Ollama must be running (`ollama serve` in another terminal, or the desktop app open) with `llama3.1` pulled.

## Test prompts

- `Forecast FOODS_1_003 for 28 days`
- `Forecast HOBBIES_1_007 for 14 days store TX_1`
- `Scan for anomalies in CA_1`
- `Why did FOODS_3_586 spike on 2015-02-08?`
