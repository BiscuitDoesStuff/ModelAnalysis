# User Guide

Everything a user needs to install, run, and read ModelAnalysis output. Maintainer internals live in `PIPELINE.md`.

## 1. Install

1. Install Python 3.
2. From the repo root:
   ```powershell
   pip install -r requirements.txt
   ```
   Dependencies: `openpyxl` (Excel output), `python-dotenv` (optional `.env` loading).

## 2. Configure keys (optional)

Public-only run works with no keys and covers the OpenRouter catalog.

For more coverage, set any of these in OS / `User` environment variables or a local `.env` file (gitignored — never committed):

```
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
OPENROUTER_API_KEY=      # optional, raises OpenRouter rate limits
AA_API_KEY=              # Artificial Analysis scores/prices
```

Copy `.env.example` to `.env` and fill in only what you need. Missing keys are fine — that provider's section is skipped or marked `skipped`/`error` in the snapshot.

## 3. Run

Full refresh (recommended):

```powershell
powershell -File run.ps1
```

Stages run in order and stop on first failure (`$LASTEXITCODE` checked after each step):

```powershell
python retrieval/fetch_models.py   # stage 1: snapshot
python analysis/analyze.py         # stage 2: analyze + diff
python reports/build_report.py     # stage 3: report
```

Re-run any time to refresh. Each run prunes older outputs so only the latest stamp remains.

## 4. Read the report

Open `reports/<stamp>_summary.md`. Sections:

- Header counts — `OR`, strict free count, `OAI`, `ANT`, `AA`, new/removed, history days.
- Combined free rank (top 20) — strict-$0 OpenRouter models sorted by AA score. `unscored` means no AA match.
- Free list — every strict-$0 ID plus its OpenCode form: `openrouter/<id>`. Use the `openrouter/` form in OpenCode config.
- AA Top 15 — highest Intelligence Index with creator and blended cost.
- Anthropic native IDs — full native listing for the run.
- OpenAI retired — IDs with `shutdown_date` set (first 30).
- Diff vs history — `New` IDs appeared since the previous stored day; `Removed` disappeared.

Excel (`reports/<stamp>_models.xlsx`) sheets:

| Sheet | Contents |
|---|---|
| `summary` | Header counts |
| `free_rank` | `or_id, opencode_id, aa_score, aa_match, context` (top 30) |
| `aa_top15` | `id, name, score, creator, cost_blended` |
| `diff` | `added/removed, id` |

JSON (`reports/<stamp>_models.json`) holds the full analysis object for scripting.

## 5. Retention and storage

- `raw/<stamp>_models.json` — latest raw snapshot only; previous pruned. `_errors.log` records retries/failures for the run.
- `analysis/<stamp>_analysis.json` — latest analysis only.
- `reports/<stamp>_*.md|.json|.xlsx` — latest stamp only.
- `analysis/store.sqlite` — append-only local history used for diffs. Safe to delete to reset history (diffs then show empty until the second run).

None of the above are committed (see `.gitignore`).

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `openrouter failed, keeping previous snapshot` + exit 1 | Network or OpenRouter down; retry. No new snapshot written. |
| `no snapshots in raw/` | Run stage 1 first; `raw/` was empty or pruned. |
| `run analysis first` | No `analysis/*_analysis.json`; run stage 2 first. |
| `xlsx skipped: ...` | `openpyxl` missing — `pip install -r requirements.txt` and re-run stage 3. |
| Empty OAI / ANT / AA sections | Keys missing — expected for public runs. Add keys and re-run. |
| `aa_free_unverified` non-empty but `free_ids` empty | AA $0 pricing is unverified (billing not checked); trust `free_ids` for the strict rule. |
| Diff always empty on first run | No previous day in `store.sqlite` yet; diffs populate from the second distinct day onward. |

## 7. FAQ

**Do I need billing anywhere?** No. The free rule is strict $0 at retrieval time.

**Which free list do I trust?** `free_ids` (strict). `aa_free_unverified` is AA $0 pricing only — account/billing not verified.

**How do I use a model in OpenCode?** Take the `openrouter/<id>` form from the free list or `free_rank` sheet.

**How fresh is the data?** Point-in-time per run. Re-run on use.
