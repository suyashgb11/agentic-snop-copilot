# S&OP Copilot

**An agentic AI system for supply chain planning — built on real Walmart data.**

Ask a question in plain English. A team of specialist AI agents collaborates to answer it using statistical models and live data — never guessing, never hallucinating.

---

## What it does

A demand planner types a question. The system routes it to the right specialist agent, runs the analysis, and returns a grounded answer with charts and a full audit trace.

| Question | What runs |
|---|---|
| *"What needs my attention this week?"* | Scans 100 SKUs with z-score + EWMA rules, ranks anomalies by severity |
| *"Forecast FOODS_1_003 for 28 days"* | Fits AutoARIMA on 5 years of history, returns point forecast + 80/95% confidence bands |
| *"Why did FOODS_1_003 spike recently?"* | Checks holiday calendar, compares against category peers, explains the most likely causes |

---

## The one rule that defines the system

**The LLM is not allowed to do arithmetic.**

Every number in the output traces back to a tool call — a DuckDB query, a StatsForecast model, a statistical rule. The LLM reads results and writes English. It never multiplies, averages, or summarises the trend numerically.

This is what separates a planning-grade tool from a chatbot.

---

## Architecture

```
User query
    │
    ▼
 Router          ← classifies query: forecast / anomaly / root_cause / chat
    │
    ├── Forecast Agent      ← AutoARIMA via StatsForecast
    ├── Anomaly Agent       ← z-score + EWMA + week-over-week rules
    └── Root Cause Agent    ← holiday calendar + peer comparison
    │
    ▼
 Composer        ← synthesises results into plain English
    │
    ▼
Streamlit UI     ← chat + Plotly charts + full agent trace panel
```

Single LangGraph `StateGraph`. Agents communicate only through shared state — no agent-to-agent chatter. Every tool call appends to a trace the planner can inspect.

---

## Stack

| Layer | Choice |
|---|---|
| Orchestration | LangGraph |
| LLM | Ollama (local, free) · Gemini · Claude |
| Forecasting | StatsForecast — AutoARIMA |
| Data | DuckDB on M5 Walmart dataset |
| UI | Streamlit + Plotly |

---

## Data

M5 Forecasting dataset (Walmart) — public domain.

- **100 SKUs** across Foods, Hobbies, Household
- **3 stores** — CA, TX, WI (different SNAP schedules per state)
- **5.3 years** of daily sales history (582,300 rows)
- **25+ anomaly events** spread across the full history — demand spikes, stockouts, slow drifts, regional events, category-wide shocks

---

## Quickstart

```bash
# 1. Clone and install
git clone https://github.com/suyashgb11/agentic-snop-copilot
cd agentic-snop-copilot
pip install -r requirements.txt

# 2. Set up LLM — free and local
#    Download Ollama from https://ollama.com then:
ollama pull llama3.1

# 3. Configure
cp .env.example .env
# .env needs one line: OLLAMA_MODEL=llama3.1

# 4. Build the database
python data/load_m5.py

# 5. Run baseline forecasts (optional but recommended)
python tools/run_baselines.py

# 6. Launch
streamlit run app.py
```

Open **http://localhost:8501** and start asking questions.

---

## Project structure

```
agentic-snop-copilot/
├── app.py                    # Streamlit entry point
├── agents/
│   ├── orchestrator.py       # LangGraph StateGraph — router + composer
│   ├── forecast_agent.py     # Forecast specialist node
│   ├── anomaly_agent.py      # Anomaly detection node
│   └── root_cause_agent.py   # Root cause analysis node
├── tools/
│   ├── llm.py                # Provider abstraction (Ollama / Gemini / Claude)
│   ├── data_access.py        # DuckDB query functions
│   ├── forecasting.py        # StatsForecast wrapper
│   ├── anomaly_detection.py  # z-score, EWMA, week-over-week rules
│   └── run_baselines.py      # Batch forecast runner (all 100 SKUs)
├── data/
│   ├── load_m5.py            # Dataset generation + DuckDB loader
│   └── prep.py               # Data quality report
└── ui/
    ├── chat.py               # Chat message rendering
    ├── dashboard.py          # Plotly forecast + anomaly charts
    └── trace_view.py         # Agent trace panel
```

---

## Why this project exists

I built this to show what agentic AI looks like in a supply chain context — not a notebook, not a prototype, but a working system where every design decision is justified.

The supply chain AI space is full of demos where the LLM does the maths and presents it confidently. This project takes the opposite position: statistical models do the maths, the LLM only explains what they found.

---

## Roadmap

- [ ] Inventory agent — days of cover, reorder point alerts
- [ ] Supply planning agent — supplier lead time analysis
- [ ] Multi-store anomaly correlation
- [ ] Deploy to Hugging Face Spaces — public demo URL

---

## Author

Built by Suyash Kulkarni — supply chain professional building with agentic AI.

[LinkedIn](https://www.linkedin.com/in/suyashkulkarni11/) · [GitHub](https://github.com/suyashgb11)
