# ModelAnalysis

On-use snapshot of usable free LLM catalogs. Pulls OpenRouter, OpenAI, Anthropic, Groq, Cerebras, NVIDIA, ZenMux, OpenCode Zen, models.dev capabilities, and Artificial Analysis, filters to strict-$0 free models plus provisional free candidates, and writes a ranked Markdown + Excel + JSON + HTML report.

No keys required for a public run. No billing. Keys stay local and are never committed.

## Features

- Public-first retrieval — OpenRouter, NVIDIA, ZenMux, OpenCode Zen, and models.dev work with no keys; authed sources are skipped gracefully when keys are absent
- Strict-$0 free filter — text-output models with zero prompt + completion pricing (or `:free` suffix), Zen `*-free` free routes (text-out confirmed via models.dev or flagged `modality-unverified`), routers excluded; AA-$0 rows without strict confirmation listed as provisional `[F?]`
- Quality ranking — canonical deduped models joined to Artificial Analysis Intelligence Index where available; inherited route/effort estimates flagged with evidence, external metrics kept reference-only
- Cost provenance + effort disambiguation — per-row `cost_source` (`aa`/`or-derived`/`inherited`/`none`), `ambiguous-effort` vs `base (unspecified effort)` labels, sibling `efforts_hint`, display-only `nearest_callable`, `deprecated-upstream` + `modality-unverified` badges, `non-reasoning` vs `metadata-missing` split
- Diffs vs history — new / removed listings plus free-status churn (free→paid flips, disappearances) compared against local SQLite history
- One-command run — `run.ps1` refreshes snapshot → analysis → report → churn alerts, keeping only the latest run

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
python alerts/check_churn.py
```

## What you get

After a run, all dated with `YYYY-MM-DD_HHMM`:

| Output | Path |
|---|---|
| User-friendly dashboard: Start here · Best value · Stack · Variants · Free · Explore | `reports/<stamp>_report.html` |
| Human-readable ranking (9 sections, top 20) | `reports/<stamp>_summary.md` |
| Churn alert (only on free→paid/disappearances) | `reports/<stamp>_churn_alert.md` |
| Spreadsheet (11 tabs: summary, All_* / OCF_* views, stack, practical, outliers, Family_Variants) | `reports/<stamp>_models.xlsx` |
| Machine-readable analysis | `reports/<stamp>_models.json` |
| Intermediate analysis (canonical rows + score evidence) | `analysis/<stamp>_analysis.json` |
| Raw provider snapshot | `raw/<stamp>_models.json` |
| History for diffs | `analysis/store.sqlite` |
| Score-evidence registry (committed source) | `analysis/research.json` |

Only the latest run is kept on disk (auto-pruned each run). Generated outputs are gitignored; source is what gets committed.

The summary lists all 9 sections (top 20 each): All-Data Intelligence / Cost / Ratio, OCF Intelligence / Cost / Ratio, Optimized Stack (Max/High/Medium with gap flags), Practical picks table (12 tier × variant cells), and Outliers. The HTML dashboard reorganizes the same data into 6 user pages: Start here (Top quality / Best value / Free copy cards), Best value (score bands ±1.5, cheapest-first with saving), Stack (tiered callable picks + per-tier value note + practical), Variants (per-family side-by-side, e.g. 5.5 max→low with #variant guidance), Free (verified + provisional [F?]), Explore (one filterable table replacing All/OCF duplicates). Variants (`max`/`xhigh`/`high`/`medium`/…) are separate ranked rows with `efforts` shown; set `reasoning_effort` locally to select. Costs show `[aa|or-derived|inherited]` provenance; ambiguous efforts, sibling hints, deprecated/modality badges, and display-only nearest-callable hints are inline. Excel holds the 9 sections as full-list tabs; JSON holds them uncapped.

## Configuration

Keys are local-only (`.env`, OS env, or `User` env vars). Never committed. See `.env.example`.

| Key | Needed for | Required? |
|---|---|---|
| _(none)_ | OpenRouter public catalog | No |
| `OPENAI_API_KEY` | OpenAI `/v1/models` listing | Only for OpenAI section |
| `ANTHROPIC_API_KEY` | Anthropic `/v1/models` listing | Only for Anthropic section |
| `OPENROUTER_API_KEY` | Higher OpenRouter rate limits | Optional |
| `AA_API_KEY` | Artificial Analysis scores/prices | Only for AA sections |
| `GROQ_API_KEY` | Groq `/openai/v1/models` listing | Only for Groq coverage (skipped when absent) |
| `CEREBRAS_API_KEY` | Cerebras `/v1/models` listing | Only for Cerebras coverage (skipped when absent) |
| `NVIDIA_API_KEY`, `GOOGLE_AI_STUDIO_KEY` | Reserved for future validation | Not used in v1 |

## Free rule

A model counts as free only if it costs $0 at retrieval time: zero prompt + completion price (or `:free` ID), Zen `*-free` free route, text-only output, no `openrouter/*` router entries. Trials and rate limits are fine as long as no billing info is required (account + API key at most). Artificial Analysis $0 rows without strict-free confirmation are listed separately as provisional `[F?]` (L1: AA $0 + OR listing, L0: AA $0 only, intel-only unless a native `fallback_id` is shown).

## Project structure

```
retrieval/fetch_models.py  — stage 1: fetch snapshots from all providers (incl. models.dev minimal)
analysis/analyze.py        — stage 2: normalize, free-filter, variants/efforts/fallback, Tier 1 capabilities, cost/ambiguity badges, rank, diff vs SQLite
analysis/enrichment.py     — stage 2b: evidence-backed scores (AA-canonical, external reference-only, inherited estimates w/ models.dev validation)
analysis/research.json     — committed evidence registry (benchmark versions, equivalence URLs, expiry)
reports/build_report.py    — stage 3: write MD + XLSX + JSON + HTML report with score evidence + provenance badges
alerts/check_churn.py      — stage 4: churn summary + alert file on free→paid/disappearances
tests/smoke.py             — verify 9-section + provisional + variants + evidence + churn + Tier 1 + backlog contract
raw/                       — timestamped snapshots (gitignored)
analysis/store.sqlite      — local history (gitignored)
reports/                   — dated reports (gitignored)
docs/                      — user guide and pipeline internals
```

## Docs

- `docs/USER_GUIDE.md` — setup, running, reading reports, troubleshooting
- `docs/PIPELINE.md` — pipeline internals, schemas, and extension points (maintainer reference)

## Notes and limits
- Provider rate limits and data-use policies change — verify in provider docs before heavy use.
- Per-model OpenCode compatibility is not verified by this tool.
- Snapshots are point-in-time; re-run on use to refresh.

## License

MIT — see `LICENSE`.
