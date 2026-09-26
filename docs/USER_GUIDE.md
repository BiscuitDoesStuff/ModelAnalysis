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

Public-only run needs no keys and covers the OpenRouter, NVIDIA, ZenMux, OpenCode Zen, and models.dev capability catalogs.

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

## 4. Read the report

Open `reports/<stamp>_report.html` in a browser — 6-page dashboard (Start here · Best value · Stack · Variants · Free · Explore) with search, Explore filters, and click-to-copy OpenCode IDs. `reports/<stamp>_summary.md` holds the 9 sections as text (top 20 rows each; full lists in XLSX, uncapped in JSON):

1. **Start here**: copy-ready Top quality / Best value / Free cards + tier cards + practical winners + churn/freshness notes.
2. **Best value**: paid OCF rows in score bands (±1.5, 30+ floor), cheapest-first in band with saving vs priciest. Answers close-score/big-cost choices.
3. **Stack**: Max (50+) / High (40+) / Medium (30+) tiers, score desc with ratio tiebreak + per-tier value note. Callable ID required (`or_id`/native); AA-only rows intel-only. Gaps flagged per O/C/F. Below 30 excluded.
4. **Variants**: per-family side-by-side (e.g. 5.5 max/xhigh/high/medium/low). AA-only rows show `nearest display-only` + `provider/model#variant` guidance.
5. **Free**: verified free by score + provisional `[F?]` + unscored note, with `deprecated-upstream` / `modality-unverified` flags.
6. **Explore**: one filterable All-models table (groups / cost-source / free-status + text) replacing the old All/OCF Intel/Cost/Ratio duplicates.

MD/JSON/XLSX keep the 9-section contract (All Intel/Cost/Ratio, OCF Intel/Cost/Ratio, Stack, Practical, Outliers) for scripting; HTML is the user view.

MD sections (unchanged, top 20 each):

1. **All Data — Intelligence**: every model by score desc, `unscored` tail.
2. **All Data — Cost**: cheapest first in blended $/1M, `cost-unknown` tail.
3. **All Data — Ratio**: paid models by score/cost; then verified-free ranked by score; then provisional-free `[F?]` by score; then `unratable` tail. Free never enters the ratio (infinite).
4–6. **OCF — Intelligence / Cost / Ratio**: same views filtered to OpenAI + Claude + strict-free rows plus provisional-free `[F?]` (AA $0, billing unverified; exact level in JSON/XLSX). AA-only OpenAI/Anthropic variant rows (creator-mapped O/C) are included here as separate ranked rows even with no callable ID.
7. **OCF — Optimized stack**: Max (50+) / High (40+) / Medium (30+) tiers, score desc with ratio tiebreak. Callable ID required (`or_id`/native); AA-only rows stay in Intel/Cost/Ratio. Each tier flags `gaps:` for any of O/C/F with no verified qualifier (tier filled only by provisional still flags `F`). Below 30 excluded from stack only.
8. **OCF — Practical picks**: winner + runner-up per tier for each access variant (OCF, OF, CF, F-only). `— (gap)` where a tier/variant has nothing.
9. **OCF — Outliers**: bargains, overpriced, free gems (verified/provisional free + score 40+, callable only).

Variants: reasoning-effort rows (`max`/`xhigh`/`high`/`medium`/`low`/`minimal`) are separate ranked rows from AA (e.g. `Claude Opus 5 (medium)` 44.8 vs `(max)` 50.8; `Muse Spark 1.3 (max)` 48.1 vs `(xhigh)` 45.1). Meta variants live in All views (no O/C group); O/C variants live in both All and OCF. To use a variant, set `reasoning_effort` locally — OR `supported_efforts` per row shown as `efforts a/b/c *default`, or `(default unspecified)` when OR lists efforts but no default, or `(hint, sibling)` when an AA-only row borrows efforts from a callable sibling (source `sibling`, display-only). Scored rows without a variant in a multi-effort family flag `(ambiguous-effort)`; singletons show `(base, unspecified effort)`. OR rows without reasoning split into `[non-reasoning]` (upstream confirms no reasoning) vs `[metadata-missing]` (no capability info or upstream says reasoning but OR omits it).

Row format: `` `id` (variant) [groups] — score — $/1M [cost-source] — ratio — efforts a/b/c *default → `selector|openrouter/id` — evidence [source] ``. Cost source is `[aa]` (AA blended primary), `[or-derived]` (OpenRouter fallback), `[inherited]` (derived $0 estimate), or `cost-unknown`. `→ opencode/<route>#<variant>` for inherited estimates, `→ openrouter/...` when OR ID exists; `→ <native> (zen/...) (native, no OR)` for L0/zen-only fallback; `AA-only, no callable ID` otherwise (+ `nearest <id> display-only` hint when a callable sibling exists — never copy it). `[deprecated-upstream]` means models.dev flags the route deprecated (e.g. 1.2 Contributor-free); `[modality-unverified]` means a Zen route lacks text-out confirmation. Scores show `(estimate)` when inherited. Evidence is `aa-api / <version>`, `inherited-estimate from <slug>`, or `unscored`, with links to equivalence/capability/upstream sources. External metrics (e.g. llm-stats) appear as reference-only and never replace AA ranking scores. Groups: O = OpenAI, C = Claude, F = strict-free (OR $0 or Zen `*-free`), `F?` = provisional-free (AA $0, unverified). Router listings (`openrouter/*`) are excluded from ranked views; the header shows the excluded count.

Excel (`reports/<stamp>_models.xlsx`) sheets (data sheets carry `free_status`: `verified` / `provisional-l1` / `provisional-l0` / `none`, plus `variant`, `variant_ambiguous`, `efforts`, `default_effort`, `efforts_hint`, `or_reasoning_status`, `fallback_id`, `fallback_provider`, `nearest_callable` display-only, `deprecated_upstream`, `modality_status`, `cost_source`):

| `summary` | Header counts + tier sizes + gaps |
| `All_Intel`, `All_Cost`, `All_Ratio` | Full-list versions of MD sections 1–3 |
| `OCF_Intel`, `OCF_Cost`, `OCF_Ratio` | Full-list versions of MD sections 4–6 |
| `OCF_Stack` | Tier + full row; `GAP:` rows for missing groups |
| `OCF_Practical` | `tier, variant, winner, winner_variant, winner_score, winner_ratio, winner_copy_id, runner_up` (12 rows) |
| `OCF_Outliers` | Bargains + overpriced + free gems |
| `Family_Variants` | Full per-family table: `family, peak` + full row for every multi-variant family |

JSON (`reports/<stamp>_models.json`) holds the 9 sections uncapped (`all_intel`, `all_cost`, `all_ratio_*`, `ocf_*`, `ocf_stack{max,high,medium}`, `ocf_practical[]`, `ocf_outliers`, `family_variants`, `quartiles`, `thresholds`) plus `free_churn` (free→paid flips, newly free, disappeared and new slugs vs the previous day; empty until two distinct days exist) for scripting. Each model row carries `variant`, `variant_ambiguous`, `aa_variant_name`, `efforts[]`, `default_effort`, `efforts_hint`, `or_reasoning_status`, `fallback_id`, `fallback_provider`, `nearest_callable` (display-only), `cost_source`, `deprecated_upstream`, `modality_status`.

Verify with `python tests/smoke.py` (MD/JSON 9-section + HTML 6-page contract + provisional-free + variants + Zen-free + churn + Tier 1 models.dev + cost/ambiguity/capability badges; warns when research registry is past `expires_at`).

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
| A provider shows `{"error": ...}` in the snapshot | Keyless public catalogs (NVIDIA/ZenMux/Zen/models.dev) degrade gracefully — that catalog is skipped for the run, everything else proceeds. Retry on next run. |
| Mostly `unscored` / `cost-unknown` / empty stack | No AA / OpenAI / Anthropic keys — expected for public runs. Add keys and re-run. |
| AA shows $0 prices but no free gems | AA $0 pricing alone lands in provisional `[F?]` (L1 with an OR listing, L0 AA-only; billing not checked); gem status needs score 40+ plus a callable ID. |
| Diff always empty on first run | No previous day in `store.sqlite` yet; diffs populate from the second distinct day onward. |
| `warn research expired` / `warn snapshot modelsdev missing` | Evidence registry past `expires_at` (manual refresh needed) or snapshot pre-dates Tier 1 — re-run retrieval to repopulate models.dev, then refresh `research.json` dates. |

## 7. FAQ

**Do I need billing anywhere?** No. The free rule is strict $0 at retrieval time.

**Which free list do I trust?** The F-tagged rows and free-gems block (OR strict-$0 or Zen `*-free` + text-only + no routers). `[F?]` rows are provisional (AA $0, account/billing not checked): L1 has a second OR listing and a callable ID, L0 has no OR listing (it may carry a native `fallback_id` from NVIDIA/ZenMux/Zen or AA-only with no callable ID — intel-only until verified).

**Why are stack tiers empty / flagged with gaps?** No scored model from that group qualified (often: no keys yet, or no free model scores 50+). Gaps are explicit, not errors.

**How do I use a model in OpenCode?** Copy the ID shown: `opencode/<route>#<variant>` for estimates, `openrouter/<or_id>` when present, else the native `fallback_id` (e.g. Zen `muse-spark-1.3-contributor-free`) with provider noted. AA-only rows show `AA-only, no callable ID` — use for comparison only (the `nearest <id> display-only` hint is not copyable). Check limits in provider docs. Inherited scores are estimates from a matched effort on another route, not measurements of the destination — see the evidence links.

**What do cost-source / deprecation / modality badges mean?** `$/1M [aa]` is AA blended primary, `[or-derived]` is OpenRouter fallback, `[inherited]` is a derived $0 estimate, `cost-unknown` means no price anywhere. `[deprecated-upstream]` means models.dev flags the route deprecated (still listed, verify before use). `[modality-unverified]` means a Zen route lacks text-out confirmation — do not trust it as text-only free until checked.

**How do I use variants (high/xhigh/max)?** Variants are separate rows with own scores. The base OR row lists `supported_efforts` (e.g. `max/xhigh/high/medium/low/minimal *medium`, `*` = default). In OpenCode V2 select an available `provider/model#variant` (e.g. `opencode/muse-spark-1.3-contributor-free#xhigh`); variant names come from catalog metadata and unknown variants error. Example: `meta/muse-spark-1.3 (max)` 48.1 vs `(xhigh)` 45.1; `Claude Opus 5 (medium)` 44.8 vs `(max)` 50.8 — compare in All Intel, O/C variants also in OCF Intel. The free Contributor estimate uses `xhigh` because models.dev lists only up to `xhigh` for that route — `max` is not advertised there.

**How fresh is the data?** Point-in-time per run. Re-run on use.
