# User guide

## Install and configure

Use Python 3.11–3.13 from the repository root:

```powershell
python -m pip install -r requirements.lock
```

Dependencies are `openpyxl` and `python-dotenv`, listed in `requirements.txt` and pinned in `requirements.lock`; update both together and re-run `python -B tools/ci.py`. PowerShell is needed only for `run.ps1` and the PowerShell examples below.

Public retrieval covers OpenRouter, NVIDIA, ZenMux, Zen, models.dev, BenchLM, and best-effort website evidence. Optional credentials:

| Variable | Use |
|---|---|
| `OPENAI_API_KEY` | OpenAI model catalog |
| `ANTHROPIC_API_KEY` | Anthropic model catalog |
| `OPENROUTER_API_KEY` | Optional authentication for the public catalog |
| `AA_API_KEY` | Artificial Analysis scores and prices |
| `LLM_STATS_API_KEY` | LLM Stats API; public website evidence remains available without it |
| `LLM_STATS_DETAIL_MAX` | Override the keyed per-model detail cap; default 12 |

Copy `.env.example` to `.env` if useful. Resolution takes the first **nonempty process value, repository `.env` value, then Windows User value**. Windows User fallback works even when an automation shell inherited an older environment. An existing nonempty process value still wins. Do not print credentials while diagnosing configuration.

Copy `config.example.json` to `config.json` for non-secret settings:

| Field | Default | Meaning |
|---|---:|---|
| `disabled_sources` | `[]` | Explicitly skip named sources, including their website retrieval where applicable |
| `run_days` | 90 | Detailed history retention, with latest complete source baselines protected |
| `daily_days` | 365 | Daily rollup retention |
| `artifact_bundles` | 2 | Number of recent published bundles to keep; minimum 2, current protected |
| `failed_days` | 7 | Failed or interrupted staging bundle retention |
| `website_max_pages` | 40 | Per-source website page budget |
| `cache_days` | 7 | Website cache freshness window |
| `llmstats_detail_max` | 12 | Default keyed detail-fetch cap |

Source names: `openrouter`, `openai`, `anthropic`, `nvidia`, `zenmux`, `zen`, `modelsdev`, `aa`, `benchlm`, `llmstats`, `vals`. For example, `"disabled_sources": ["llmstats", "vals"]`. Empty environment values are not an opt-out because credential fallback still applies. Unknown config fields and invalid integer limits fail early.

## Run and locate output

```powershell
python pipeline.py
python pipeline.py --config config.json --state-dir runs --db analysis/store.sqlite
# Equivalent wrapper:
powershell -File run.ps1 --config config.json
```

Defaults are repository-root `runs/` and `analysis/store.sqlite`. Explicit relative paths resolve from your working directory. Each run fetches catalogs, retrieves selected website evidence, analyzes, builds reports/site, generates any loss alert, and validates before publication. It prints stage timing and the final bundle path.

Read `runs/current.json`, then resolve its relative `bundle` path:

```powershell
$current = Get-Content runs/current.json -Raw | ConvertFrom-Json
$bundle = Join-Path runs $current.bundle
Start-Process (Join-Path $bundle "reports/$($current.run_id)_site/index.html")
# Or open the single-file dashboard:
Start-Process (Join-Path $bundle "reports/$($current.run_id)_report.html")
```

For custom state directories, substitute that directory for `runs`. A missing pointer means no bundle has published there yet. Old `raw/`, `analysis/`, or `reports/` timestamped outputs are not the current-run selector.

Partial retrieval can still publish a report with explicit coverage labels. An OpenRouter outage alone does not block other usable providers. If no provider has usable catalog rows, or a required report/validation step fails, the command fails; before pointer publication the previous current bundle remains selected. Cleanup trouble after successful publication is reported separately.

## Replay and recovery

Offline replay reads saved artifacts and makes **no network calls**:

```powershell
python pipeline.py --snapshot path/to/models.json --state-dir replay-runs --db replay-history.sqlite
python pipeline.py --snapshot path/to/models.json --websites path/to/websites.json --state-dir replay-runs --db replay-history.sqlite
```

The optional website snapshot must belong to the provider snapshot's original run. Replay assigns a new run ID, records the imported origin, and preserves source evidence timestamps. Without `--websites`, website enrichment is empty. Replay-only `--as-of YYYY-MM-DD` sets the evidence day used for registry expiry and the AA index version (default: the run day), and `--registry PATH` replaces `analysis/research.json`; the golden fixture uses both so its results never depend on today's date. Legacy snapshots without completeness evidence can be displayed but cannot establish trusted absence baselines. Separate replay state/history keeps experiments apart from normal history.

After interruption, use the **same state directory and database**:

```powershell
python pipeline.py --recover --state-dir runs --db analysis/store.sqlite
```

Recovery finishes validated, commit-requested bundles already finalized under `bundles/`, revalidates their artifacts, and reconciles the pointer with prepared SQLite history. It does not fetch or rerun incomplete stages. A normal run also performs recovery first. Do not manually promote failed staging directories or edit `current.json` to bypass validation.

## Read scores, free status, and reliability

The static site has independent **AA / BenchLM / LLM Stats / Vals** source tabs, a searchable **Models** directory, a page for every non-router model, Benchmarks, Compare, Methodology, and Confidence. Leaderboard slices show displayed/total counts; the directory provides full model coverage. Nested BenchLM Supported/All tabs operate within their own group.

The dashboard has seven views:

| View | Purpose |
|---|---|
| Start here | Copy-ready quality/value/free picks and reliability information |
| Best value | Nearby AA scores grouped into price comparisons |
| Stack | Max 50+, High 40+, Medium 30+; missing O/C/F groups explicitly flagged |
| Variants | Effort-specific family rows; estimates and ambiguous effort labeled |
| Free | Verified and provisional candidates kept distinct |
| Graph | Up to 12 non-router models/efforts, AA score versus blended token price |
| Explore | Filterable model table with group, price-source, and free-status filters |

**Keyboard and screen readers.** Both the dashboard and the site work without a mouse. The first **Tab** reaches "Skip to content". In a row of tabs, the **arrow keys** switch tabs and **Home**/**End** jump to the first or last. Every route is a button: **Tab** to it and press **Enter** to copy it, and a screen reader announces "Copied …". Display-only rows (AA-only, or `nearest …` hints) have no copy button. A wide table on a narrow screen scrolls inside its own box, which takes focus so the arrow keys can scroll it. The colours follow your system's light or dark setting. A missing price or score shows as *unknown* / *unscored* in muted italics, while `$0/1M` is a real zero price.

To check a bundle in a browser yourself (Node 22 and Chromium needed): `npm ci --prefix tools/a11y`, then `node tools/a11y/check.mjs runs/bundles/<run_id> --shots shots`. It runs axe in both themes, does the keyboard pass and saves screenshots.

AA is the ranking scale. Other benchmarks retain their own scales and provenance; scores are never averaged across them. An inherited score is an estimate, not a measurement of that destination route. Expired/version-incompatible external evidence is reference-only.

`cost_source` is `aa`, `or-derived`, `inherited`, or `none`; prices are blended dollars per million tokens, **not measured per-task costs**. Unknown prices are not zero. Free rows do not enter paid score/price ratios.

Free labels:

- **F / verified:** OpenRouter text-only non-router routes with zero prompt and completion prices or a `:free` ID; Zen `*-free` route evidence also qualifies. Zen text-output confirmation is separately shown; `modality-unverified` means it is missing.
- **F? / provisional-l1:** AA zero pricing plus an OpenRouter listing, without strict free verification.
- **F? / provisional-l0:** AA zero pricing without an OpenRouter listing. A native fallback may be shown; otherwise it is reference-only.

Copy only the displayed callable selector/route. `nearest_callable` and sibling effort hints are display-only. AA-only or benchmark-only rows may have no callable ID. A free label reflects captured evidence; account conditions and limits still belong to the provider.

### Source health and churn

Reliability sections expose `complete`, `partial`, `failed`, and `skipped` source statuses, counts, timestamps, reasons, and baseline references. A successful selected-page crawl can have status `complete` but `complete: false` for catalog coverage: it is not a full catalog. Cached page `fetched_at` values remain the original source-fetch times; a fresh report does not make cached evidence fresh.

Only two comparable complete provider catalogs can establish absence. Failed, skipped, partial, malformed, or bounded-reference data cannot prove removal. The first trusted complete fetch for a source seeds its baseline; another complete run can compare on the **same UTC day**.

The schema-3 `churn` object contains route-level events and daily summaries:

- `verified_free_paid` / `verified_free_removed`: the only alert types; the alert file includes evidence times, verified alternatives, and unknown coverage.
- `verification_unknown`: previous free verification can no longer be established; not proof of payment or removal.
- `free_added`, `free_restored`, and `catalog_added` / `catalog_removed` / `catalog_changed`: informational changes.
- Daily **net events** compare the latest complete catalog that day against the previous complete day. **Observed events** retain intraday changes, so a loss followed by restoration can remain visible even when net change is zero.

No alert file is produced for provisional candidates or ordinary catalog removals. “No events” does not mean every source was checked; read compared/unknown coverage. The old day-level `free_churn` summary was removed; route churn is the only change history.

## Export formats and retention

Within `runs/bundles/<run_id>/`, `raw/` holds snapshots, `analysis/` holds analysis JSON, and `reports/` holds `<run_id>_summary.md`, `_models.json`, `_models.xlsx`, `_report.html`, `_site/`, and the optional `_churn_alert.md`. `manifest.json` records state, stage timings, and validation. Retrieval diagnostics are in `raw/_errors.log` when created.

MD retains nine ranking sections: All Intelligence/Cost/Ratio, OCF Intelligence/Cost/Ratio, Stack, Practical, Outliers. Markdown lists are capped; JSON and Excel retain full lists. JSON section entries reference `models_by_slug`; row fields retain variants, effort/default provenance, callable IDs, score evidence, prices, deprecation, and modality flags.

New-schema Excel sheets: `summary`, `All_Intel`, `All_Cost`, `All_Ratio`, `OCF_Intel`, `OCF_Cost`, `OCF_Ratio`, `OCF_Stack`, `OCF_Practical`, `OCF_Outliers`, `Family_Variants`, `BenchLM_Matrix`, `LLMStats_Matrix`, `Source_Health`, `Churn`, `Identity`, so **16** in total. Legacy inputs without reliability fields produce 13, and analyses from before provider identity produce 15.

Cleanup runs after publication. Defaults retain current + previous bundles, detailed history for 90 days, daily rollups for 365 days, and failed or interrupted staging bundles for 7 days. The latest complete source baselines are protected even across longer outages. Legacy/user files are not pruned by bundle cleanup. SQLite is versioned and pruned, not append-only; migration backs up an existing database and leaves legacy tables untouched. Keep each state directory paired with its database when backing up or moving it.

## Standalone stages and validation

Standalone commands write scratch artifacts; they do not publish, update persistent route history, or prune bundles. Replace `<run_id>` with the ID printed by retrieval, and use a new scratch directory for each experiment:

```powershell
python retrieval/fetch_models.py --output scratch/raw --config config.json
python retrieval/fetch_websites.py --input scratch/raw/<run_id>_models.json --output scratch/raw
python analysis/analyze.py --input scratch/raw/<run_id>_models.json --websites scratch/raw/<run_id>_websites.json --output scratch/analysis
python reports/build_report.py --input scratch/analysis/<run_id>_analysis.json --output scratch/reports
python reports/build_site.py --input scratch/analysis/<run_id>_analysis.json --output scratch/reports
python alerts/check_churn.py --input scratch/reports/<run_id>_models.json --output scratch/reports
```

Website retrieval is a network stage. Omit it and omit analysis `--websites` for local analysis without enrichment. The site needs the matching report JSON already in the same scratch report directory. For persistent route comparisons and atomic publication, use `pipeline.py`.

```powershell
python -B tests/test_units.py
python -B -m unittest discover -s tests -p "test_*.py"
python -B tests/smoke.py
# Select an existing bundle explicitly:
python -B tests/smoke.py --bundle runs/bundles/<run_id>
# Everything CI runs (golden replay + smoke + coverage included):
python -B tools/ci.py
# Evidence refresh: what expires soon (with URLs to re-check), then confirm/retire/version:
python tools/refresh_evidence.py list
# Trace displayed scores/prices to their saved observations (0 orphans expected):
python tools/audit_provenance.py runs/bundles/<run_id>
# Record a trimmed, key-free fixture from the current complete-coverage bundle (verified before writing):
python tools/record_fixture.py
```

Unit/integration checks use fixtures and temporary storage. Smoke checks existing artifacts. These commands do not automatically call live APIs.

## Troubleshooting

| Symptom | Action |
|---|---|
| No usable provider catalog | Inspect failed staging `manifest.json` and `raw/_errors.log`; check source settings/connectivity, then rerun. Current remains selected. |
| Another pipeline writer is running | Let the other writer finish; the OS releases the lock after a crash. Use one writer per paired state directory/database. |
| Mixed-run input error | Pass provider, website, analysis, and report artifacts from the same original run. |
| Publication interrupted | Run `--recover` with the original state directory/database; inspect manifest state if it cannot complete. |
| Missing `openpyxl` or workbook failure | Install requirements and rerun; Excel is a required publication artifact. |
| Source skipped despite a key | Check `disabled_sources` and credential precedence without displaying the value. |
| Mostly unscored or empty tiers | AA coverage or qualified callable rows may be absent; inspect source health and gap labels. |
| LLM Stats quota/rate error | Lower the detail cap or disable the source; retry when quota permits. A public website is not a replacement for its keyed score API. |
| First run has no churn | Expected: a complete new-schema source fetch seeds a baseline. Legacy SQLite rows do not count. |
| Thin website/benchmark coverage | Read scope, component health, page limits, and cache times; reference coverage is intentionally bounded. |
| Research expiry warning | Review the underlying evidence/version and update the registry after verification. |
