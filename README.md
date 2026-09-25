# Model Watch — mass real-time retrieval
# Scope: Anthropic, OpenAI, OpenRouter + all no-billing FREE models usable in OpenCode
# Cadence: on-use (run when needed) | Storage: raw JSON + store.sqlite | Reports: MD + XLSX + JSON
# Retention: raw/analysis/reports keep latest run only (auto-pruned); store.sqlite keeps history for diffs

## Layout
- `retrieval/fetch_models.py` — 1. Data Retrieval Process
- `analysis/analyze.py` — 2. Data Analysis
- `reports/build_report.py` — 3. Report
- `raw/` — latest snapshot `YYYY-MM-DD_HHMM_models.json` (+ `_errors.log` for that run)
- `analysis/store.sqlite` — history; diffs compare against the previous day
- `reports/` — latest `YYYY-MM-DD_HHMM_summary.md`, `_models.xlsx`, `_models.json`

## On-use run (PowerShell)
```powershell
powershell -File run.ps1
```
Or step by step:
```powershell
python retrieval/fetch_models.py
python analysis/analyze.py
python reports/build_report.py
```

## Keys (local env only, never committed)
See `.env.example`. Public-only run works with no keys (OpenRouter only).
Full catalog needs: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY` (optional, raises limits), `AA_API_KEY` (scores/prices).

## Free rule
Strict $0 at retrieval time. Trials/limits allowed IFF no billing info required (account + API key max).
