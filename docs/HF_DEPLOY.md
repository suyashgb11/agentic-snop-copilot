# Deploying to Hugging Face Spaces

This is the playbook to put the public demo at `huggingface.co/spaces/suyashgb11/agentic-snop-copilot` (or similar).

## Why Spaces

The repo is local-first (Ollama). A planner clicking a GitHub link cannot try the app. Spaces gives a free, public URL with a Streamlit runtime and lets you store the API key as a secret.

## What changed in the codebase for this

1. `app.py` now auto-bootstraps the DuckDB on first run (it calls `data.load_m5.load(force=True)` if the DB is missing). The first request after a cold start takes about 30 seconds.
2. `requirements.txt` now includes `google-genai` and `ollama`. Only `google-genai` is actually used on Spaces; `ollama` is harmless dead weight that lets dev machines keep working.
3. The LLM abstraction in `tools/llm.py` already supports Gemini. Setting `GOOGLE_API_KEY` and unsetting `OLLAMA_MODEL` flips the provider.

## Deploy steps

1. Create the Space on Hugging Face: SDK = Streamlit, hardware = CPU basic (free).
2. Connect or push the repo. The Space repo is just a clone of this one.
3. Add the YAML frontmatter to the very top of `README.md` (do this on the Space side, not in the GitHub README, so the GitHub page stays clean):

```yaml
---
title: S&OP Copilot
emoji: 📈
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: "1.40.0"
app_file: app.py
pinned: false
---
```

4. In the Space settings, add secrets:
   - `GOOGLE_API_KEY` = your Gemini key (https://aistudio.google.com)
   - Do NOT set `OLLAMA_MODEL` (the provider picker prioritises Ollama if it sees that var).
5. First build will install requirements then run the app. First user query triggers the DB build.

## Known limits

- Gemini free tier is 5 requests/minute, 20/day. The demo will throttle hard if more than one person uses it at once. Acceptable for a portfolio piece, not for a launch.
- The Space disk is ephemeral by default. The DB will be rebuilt every cold start (about 30 seconds). Acceptable.
- StatsForecast baselines are NOT pre-computed on the Space. The first forecast request will fit AutoARIMA live. Add `tools/run_baselines.py` to a startup hook if this becomes a problem.

## Smoke test after deploy

1. Open the Space URL. Wait for the DB build banner to clear.
2. Run: `Forecast FOODS_1_003 for 28 days`. Expect a green-to-purple chart with 80/95 bands.
3. Run: `Scan for anomalies`. Expect a list spanning CA_1, TX_1, WI_1.
4. Open the agent trace panel. Confirm tool calls are visible.
