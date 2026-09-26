# ModelAnalysis

On-use snapshot of usable free LLM catalogs. Pulls OpenRouter, OpenAI, Anthropic, and Artificial Analysis, filters to strict-$0 free models, and writes a ranked Markdown + Excel + JSON report.

No keys required for a public run. No billing. Keys stay local and are never committed.

## Features

- Public-first retrieval — OpenRouter works with no keys; authed sources are skipped gracefully when keys are absent
- Strict-$0 free filter — text-output models with zero prompt + completion pricing (or `:free` suffix), routers excluded
- Quality ranking — OpenRouter free list joined to Artificial Analysis Intelligence Index where available
- Diffs vs history — new / removed model IDs compared against local SQLite history
- One-command run — `run.ps1` refreshes snapshot → analysis → report, keeping only the latest run

## Quickstart

Requirements: Python 3 and PowerShell.

```powershell
pip install -r requirements.txt
powershell -File run.ps1
```

Public-only run needs no keys. For the full catalog, add keys (see Configuration).

Step by step:

```powershell
python retrieval/fetch_models.py
python analysis/analyze.py
python reports/build_report.py
```

## What you get

After a run, all dated with `YYYY-MM-DD_HHMM`:

| Output | Path |
|---|---|
| Human-readable ranking | `reports/<stamp>_summary.md` |
| Spreadsheet (summary, free_rank, aa_top15, diff) | `reports/<stamp>_models.xlsx` |
| Machine-readable analysis | `reports/<stamp>_models.json` |
| Raw provider snapshot | `raw/<stamp>_models.json` |
| History for diffs | `analysis/store.sqlite` |

Only the latest run is kept on disk (auto-pruned each run). Generated outputs are gitignored; source is what gets committed.

The summary lists all 9 sections (top 20 each): All-Data Intelligence / Cost / Ratio, OCF Intelligence / Cost / Ratio, Optimized Stack (Max/High/Medium with gap flags), Practical picks table (12 tier × variant cells), and Outliers. Excel holds the same sections as full-list tabs; JSON holds them uncapped.

## Configuration

Keys are local-only (`.env`, OS env, or `User` env vars). Never committed. See `.env.example`.

| Key | Needed for | Required? |
|---|---|---|
| _(none)_ | OpenRouter public catalog | No |
| `OPENAI_API_KEY` | OpenAI `/v1/models` listing | Only for OpenAI section |
| `ANTHROPIC_API_KEY` | Anthropic `/v1/models` listing | Only for Anthropic section |
| `OPENROUTER_API_KEY` | Higher OpenRouter rate limits | Optional |
| `AA_API_KEY` | Artificial Analysis scores/prices | Only for AA sections |
| `NVIDIA_API_KEY`, `GOOGLE_AI_STUDIO_KEY` | Reserved for future validation | Not used in v1 |

## Free rule

A model counts as free only if it costs $0 at retrieval time: zero prompt + completion price (or `:free` ID), text-only output, no `openrouter/*` router entries. Trials and rate limits are fine as long as no billing info is required (account + API key at most).

## Project structure

```
retrieval/fetch_models.py  — stage 1: fetch snapshots from all providers
analysis/analyze.py        — stage 2: normalize, free-filter, rank, diff vs SQLite
reports/build_report.py    — stage 3: write MD + XLSX + JSON report
raw/                       — timestamped snapshots (gitignored)
analysis/store.sqlite      — local history (gitignored)
reports/                   — dated reports (gitignored)
docs/                      — user guide and pipeline internals
```

## Docs

- `docs/USER_GUIDE.md` — setup, running, reading reports, troubleshooting
- `docs/PIPELINE.md` — pipeline internals, schemas, and extension points (maintainer reference)

## Notes and limits

- Provider rate limits and data-use policies change; the limits table in reports is hand-maintained (last checked 2026-09-25) — verify in provider docs before heavy use.
- Per-model OpenCode compatibility is not verified by this tool.
- Snapshots are point-in-time; re-run on use to refresh.
