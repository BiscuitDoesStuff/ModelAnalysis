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

Open `reports/<stamp>_summary.md` — 9 sections, top 20 rows each (full lists in XLSX, uncapped in JSON):

1. **All Data — Intelligence**: every model by score desc, `unscored` tail.
2. **All Data — Cost**: cheapest first in blended $/1M, `cost-unknown` tail.
3. **All Data — Ratio**: paid models by score/cost; then free ranked by score; then `unratable` tail. Free never enters the ratio (infinite).
4–6. **OCF — Intelligence / Cost / Ratio**: same views filtered to OpenAI + Claude + strict-free rows.
7. **OCF — Optimized stack**: Max (50+) / High (40+) / Medium (30+) tiers, score desc with ratio tiebreak. Each tier flags `gaps:` for any of O/C/F with no qualifier. Below 30 excluded from stack only.
8. **OCF — Practical picks**: winner + runner-up per tier for each access variant (OCF, OF, CF, F-only). `— (gap)` where a tier/variant has nothing.
9. **OCF — Outliers**: bargains, overpriced, free gems (free + score 40+).

Row format: `` `id` [groups] — score — $/1M — ratio → `openrouter/id` ``. Groups: O = OpenAI, C = Claude, F = strict-free. Router listings (`openrouter/*`) are excluded from ranked views; the header shows the excluded count.

Excel (`reports/<stamp>_models.xlsx`) sheets:

| `summary` | Header counts + tier sizes + gaps |
| `All_Intel`, `All_Cost`, `All_Ratio` | Full-list versions of MD sections 1–3 |
| `OCF_Intel`, `OCF_Cost`, `OCF_Ratio` | Full-list versions of MD sections 4–6 |
| `OCF_Stack` | Tier + full row; `GAP:` rows for missing groups |
| `OCF_Practical` | `tier, variant, winner, winner_score, winner_ratio, runner_up` (12 rows) |
| `OCF_Outliers` | Bargains + overpriced + free gems |

JSON (`reports/<stamp>_models.json`) holds the 9 sections uncapped (`all_intel`, `all_cost`, `all_ratio_*`, `ocf_*`, `ocf_stack{max,high,medium}`, `ocf_practical[]`, `ocf_outliers`, `quartiles`, `thresholds`) for scripting.

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
| Mostly `unscored` / `cost-unknown` / empty stack | No AA / OpenAI / Anthropic keys — expected for public runs. Add keys and re-run. |
| AA shows $0 prices but no free gems | AA $0 pricing alone is unverified (billing not checked); gem status needs the strict-free rule + score 40+. |
| Diff always empty on first run | No previous day in `store.sqlite` yet; diffs populate from the second distinct day onward. |

## 7. FAQ

**Do I need billing anywhere?** No. The free rule is strict $0 at retrieval time.

**Which free list do I trust?** The F-tagged rows and free-gems block (strict $0 + text-only + no routers). AA $0 pricing alone is unverified — account/billing not checked.

**Why are stack tiers empty / flagged with gaps?** No scored model from that group qualified (often: no keys yet, or no free model scores 50+). Gaps are explicit, not errors.

**How do I use a model in OpenCode?** Take the `openrouter/<id>` form from the free list or `free_rank` sheet.

**How fresh is the data?** Point-in-time per run. Re-run on use.
