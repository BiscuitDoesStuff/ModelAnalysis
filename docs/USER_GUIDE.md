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
GROQ_API_KEY=            # Groq OpenAI-compatible catalog (skipped when absent)
CEREBRAS_API_KEY=        # Cerebras OpenAI-compatible catalog (skipped when absent)
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
python alerts/check_churn.py       # stage 4: churn summary + alert file
```

Re-run any time to refresh. Each run prunes older outputs so only the latest stamp remains. The last stage prints a churn summary vs the previous day; on free→paid flips or disappearances it also writes `reports/<stamp>_churn_alert.md`.

For daily runs, register a scheduled task (runs `run.ps1` every day; churn diffs populate from the second distinct day onward):

```powershell
powershell -File schedule.ps1          # daily 08:00 local
powershell -File schedule.ps1 -Time 21:30
powershell -File schedule.ps1 -Remove  # unregister
```

## 4. Read the report

Open `reports/<stamp>_report.html` in a browser — tabbed dashboard of all 9 sections with per-tab search and click-to-copy OpenCode IDs. `reports/<stamp>_summary.md` holds the same 9 sections as text (top 20 rows each; full lists in HTML/XLSX, uncapped in JSON):

1. **All Data — Intelligence**: every model by score desc, `unscored` tail.
2. **All Data — Cost**: cheapest first in blended $/1M, `cost-unknown` tail.
3. **All Data — Ratio**: paid models by score/cost; then verified-free ranked by score; then provisional-free `[F?]` by score; then `unratable` tail. Free never enters the ratio (infinite).
4–6. **OCF — Intelligence / Cost / Ratio**: same views filtered to OpenAI + Claude + strict-free rows plus provisional-free `[F?]` (AA $0, billing unverified; exact level in JSON/XLSX).
7. **OCF — Optimized stack**: Max (50+) / High (40+) / Medium (30+) tiers, score desc with ratio tiebreak. Callable ID required (`or_id`/native); AA-only rows stay in Intel/Cost/Ratio. Each tier flags `gaps:` for any of O/C/F with no verified qualifier (tier filled only by provisional still flags `F`). Below 30 excluded from stack only.
8. **OCF — Practical picks**: winner + runner-up per tier for each access variant (OCF, OF, CF, F-only). `— (gap)` where a tier/variant has nothing.
9. **OCF — Outliers**: bargains, overpriced, free gems (verified/provisional free + score 40+, callable only).

Row format: `` `id` [groups] — score — $/1M — ratio → `openrouter/id` ``. Groups: O = OpenAI, C = Claude, F = strict-free, `F?` = provisional-free (AA $0, unverified). Router listings (`openrouter/*`) are excluded from ranked views; the header shows the excluded count.

Excel (`reports/<stamp>_models.xlsx`) sheets (data sheets carry a `free_status` column: `verified` / `provisional-l1` / `provisional-l0` / `none`):

| `summary` | Header counts + tier sizes + gaps |
| `All_Intel`, `All_Cost`, `All_Ratio` | Full-list versions of MD sections 1–3 |
| `OCF_Intel`, `OCF_Cost`, `OCF_Ratio` | Full-list versions of MD sections 4–6 |
| `OCF_Stack` | Tier + full row; `GAP:` rows for missing groups |
| `OCF_Practical` | `tier, variant, winner, winner_score, winner_ratio, runner_up` (12 rows) |
| `OCF_Outliers` | Bargains + overpriced + free gems |

JSON (`reports/<stamp>_models.json`) holds the 9 sections uncapped (`all_intel`, `all_cost`, `all_ratio_*`, `ocf_*`, `ocf_stack{max,high,medium}`, `ocf_practical[]`, `ocf_outliers`, `quartiles`, `thresholds`) plus `free_churn` (free→paid / free→free flips, disappeared and new slugs vs the previous day; empty until two distinct days exist) for scripting.

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
| A provider shows `{"error": ...}` in the snapshot | Keyless public catalogs (NVIDIA/ZenMux/Zen) degrade gracefully — that catalog is skipped for the run, everything else proceeds. Retry on next run. |
| Mostly `unscored` / `cost-unknown` / empty stack | No AA / OpenAI / Anthropic keys — expected for public runs. Add keys and re-run. |
| AA shows $0 prices but no free gems | AA $0 pricing alone lands in provisional `[F?]` (L1 with an OR listing, L0 AA-only; billing not checked); gem status needs score 40+ plus a callable ID. |
| Diff always empty on first run | No previous day in `store.sqlite` yet; diffs populate from the second distinct day onward. |

## 7. FAQ

**Do I need billing anywhere?** No. The free rule is strict $0 at retrieval time.

**Which free list do I trust?** The F-tagged rows and free-gems block (strict $0 + text-only + no routers). `[F?]` rows are provisional (AA $0, account/billing not checked): L1 has a second OR listing and a callable ID, L0 is AA-only with no callable ID.

**Why are stack tiers empty / flagged with gaps?** No scored model from that group qualified (often: no keys yet, or no free model scores 50+). Gaps are explicit, not errors.

**How do I use a model in OpenCode?** Take the `openrouter/<id>` form from the free list or `free_rank` sheet.

**How fresh is the data?** Point-in-time per run. Re-run on use.
