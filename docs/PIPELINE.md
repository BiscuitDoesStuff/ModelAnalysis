# Pipeline contracts

See [USER_GUIDE.md](USER_GUIDE.md) for commands and interpretation. This describes the publication and history contracts implemented by `pipeline.py`, `pipeline_common.py`, `analysis/history.py`, and `analysis/churn.py`.

## Run identity and stage APIs

`run.ps1` forwards arguments to `pipeline.py` and propagates failure. The coordinator accepts `--config`, `--state-dir`, `--db`, `--snapshot`, `--websites` (requires `--snapshot`), and `--recover`.

Default state is `<repository>/runs`; default history is `<repository>/analysis/store.sqlite`. A run ID combines a UTC `YYYY-MM-DD_HHMMSS` timestamp with a random suffix. All artifacts in a run share this identity; filename order/mtime never selects stage inputs.

| Stage | Python API | File contract |
|---|---|---|
| Fetch | `fetch_models.main(output_dir, run_id, started_at, config)` | Writes `raw/<run_id>_models.json` |
| Websites | `fetch_websites.main(input_path, output_dir, cache_dir, config)` | Exact provider snapshot → matching `raw/<run_id>_websites.json` |
| Analyze | `analyze.main(input_path, output_dir, websites_path=None)` | Exact snapshot + optional matching websites → `analysis/<run_id>_analysis.json` |
| Report | `build_report.main(input_path, output_dir)` | Analysis → summary MD, model JSON/XLSX, dashboard HTML |
| Site | `build_site.main(input_path, output_dir)` | Analysis + matching `<run_id>_models.json` in output directory → `<run_id>_site/` |
| Alerts | `check_churn.main(input_path, output_dir)` | Exact report JSON → optional `<run_id>_churn_alert.md` |

Standalone CLIs require `--input` and `--output`, except fetch requires `--output` with optional `--config`; analysis also accepts `--websites`. They are scratch tools, with no publication or retention responsibility. Analysis uses an in-memory legacy compatibility calculation, not the persistent route database. The coordinator adds trusted history before report generation.

## Publication, interruption, and concurrency

1. Acquire the OS-owned, nonblocking `state_dir/writer.lock`. A crashed process releases the OS lock; file existence alone does not mean a writer is active.
2. Reconcile interrupted finalized publications before choosing any baseline.
3. Create `staging/<run_id>/{raw,analysis,reports}` and a `pending` manifest. Record stage completion and elapsed seconds.
4. Fetch/import pinned inputs and analyze. Reject a run with no nonempty usable provider catalog. `prepare_run` writes **prepared**, baseline-ineligible SQLite history and returns structured churn to embed in analysis.
5. Build all required outputs, including XLSX. Validate run identities, required nonempty reports, exact non-router model-page coverage, internal site links/fragments, and duplicate HTML IDs.
6. Write a `validated`, `commit_requested: true` manifest; rename staging to `bundles/<run_id>`. Atomically replace `current.json` with a pointer whose `bundle` is relative to the state directory, e.g. `bundles/<run_id>`.
7. Call `publish_run` to make history baseline-eligible and update daily rollups; mark the bundle manifest `published`.
8. Prune history and generated bundles. A cleanup failure is reported without undoing publication.

The filesystem pointer is the publication commit record. **Filesystem rename and SQLite commit are separate operations**, not one cross-store transaction. Interruption after finalization can leave a validated bundle or a pointer whose DB row remains prepared. Recovery revalidates finalized, commit-requested bundles, advances the pointer when appropriate, idempotently publishes history, and finishes manifests. It never promotes arbitrary pending/failed stages. Failure while staging still exists records a failed manifest and propagates the error.

`--recover` performs only this reconciliation under the writer lock. Normal runs do it too. Keep the same state/database pairing: locking is scoped to the state directory, so different state directories must not be used to coordinate competing writers to one database.

## Configuration, retrieval, and source health

`pipeline_common.load_config` rejects unknown settings. `config.example.json` documents all fields: `disabled_sources`, `run_days=90`, `daily_days=365`, `artifact_bundles=2` (minimum 2), `failed_days=7`, `website_max_pages=40`, `cache_days=7`, `llmstats_detail_max=12`.

Credentials resolve nonempty process environment → repository `.env` → Windows User environment. `disabled_sources` is the explicit opt-out. Diagnostics sanitize credential/query values; resolved credential mappings must never be logged.

Provider sources are `openrouter`, `openai`, `anthropic`, `nvidia`, `zenmux`, `zen`. Reference sources are `modelsdev`, `aa`, `benchlm`, `llmstats`, `vals`. Public retrieval is available without credentials; OpenAI, Anthropic, AA, and LLM Stats API require their corresponding keys. Anthropic catalog pagination must complete before absence can be inferred. Failed pagination retains usable rows as partial. Benchmark components record their own bounded/paged health rather than masquerading as provider catalogs.

Source health records include:

```text
status: complete | partial | failed | skipped
complete: boolean
scope: catalog | reference | bounded-reference | selected-pages | ...
count, fetched_at, reason, enabled, attempted
optional components, attempted_count, failed_count, cache_hits, oldest_data_at
history additions: baseline, compared
```

`status=complete` means the requested operation completed, not necessarily that an entire provider catalog was observed. Absence comparison requires **status complete + complete true + scope catalog + valid route rows**, and a comparable published baseline. Duplicate/malformed catalog routes prevent trusted comparison. Skipped/partial/failed catalogs and selected reference pages never imply removal.

Website retrieval uses a free/frontier-relevant allowlist, per-source page budgets, and `state_dir/cache`. Cache hits retain each page's original `fetched_at`; cache eligibility uses that timestamp, not file mtime. Legacy cache entries without a trustworthy timestamp refresh. Website health uses `selected-pages`, reports cache/failure counts and oldest evidence time, and remains catalog-incomplete even when every selected page succeeded. Analysis exposes it separately as `website_health`.

Partial reports publish with explicit report coverage labels when usable provider data exists. No usable provider data, mismatched identities, report errors, or validation errors block publication. There is no blanket “all failures exit 0” contract.

### Offline import

`--snapshot` imports a provider snapshot without any network stage, assigns a new run identity, and records `imported_from`. Optional `--websites` must match the snapshot's **original** identity before both artifacts are assigned the new identity. Without it, website evidence is empty. Original source timestamps remain evidence timestamps. Legacy snapshots lacking health metadata are labeled `legacy-unverified` and cannot establish loss baselines.

## Route history and events

`analysis/churn.py` uses exact `(provider, id)` catalog identity. Canonical display/model grouping is separate; merging display rows cannot itself create a free-route loss. Pure route evidence recognizes strict OpenRouter free routes and Zen `*-free` routes; missing prices/modality are not paid evidence. Display-only, provisional, benchmark-only, and inherited score rows cannot manufacture verified free access.

`analysis/history.py` public APIs:

```python
prepare_run(db_path, snapshot, models, run_id, started_at, source_health)
publish_run(db_path, run_id)
prune_history(db_path, now, run_days=90, daily_days=365)
```

The separately versioned SQLite schema has `history_schema`, `history_runs`, `history_sources`, `history_routes`, `history_events`, and `history_daily`. `history_runs.state` is `prepared` or `published`; this is distinct from filesystem manifest states. Migration uses SQLite's backup API before changing an existing database (`<db>.backup-v<version>[-N].sqlite`), leaves legacy tables untouched, and rejects newer unsupported schemas. Legacy `models`, `free_history`, and observation tables do not become trusted route history.

`prepare_run` atomically stages source snapshots and immutable event results. Identical repeated preparation returns the saved result; changed input cannot rewrite a published run. The baseline is each source's latest earlier **published complete catalog with the same rule version**, ordered by `started_at` and run ID. A first new comparable complete fetch seeds the source baseline; later runs may compare within the same UTC day. Incomplete runs do not replace it. `publish_run` is idempotent and updates retained daily rollups transactionally.

Event types:

| Type | Meaning | Alert? |
|---|---|---|
| `verified_free_paid` | Previously verified route now has explicit paid evidence | Yes |
| `verified_free_removed` | Previously verified route absent from a complete catalog | Yes |
| `verification_unknown` | Route persists but free verification is no longer established | No |
| `free_added` / `free_restored` | Verified free access appears / returns for a known-free route | No |
| `catalog_added` / `catalog_removed` / `catalog_changed` | General exact-route catalog differences | No |

A catalog event and a free-status event may describe the same route transition. Loss events include verified alternatives on other routes, `unknown_sources`, `unknown_routes`, `unknown_coverage`, and `access_status` (`verified_alternative`, `unknown`, or `no_verified_route`). Alternative matching respects canonical/namespace evidence; incomplete sources cannot prove that no alternatives exist. Alerts require a trusted baseline and previously verified evidence, not simply a disappearance count. There is no provisional-triage alert output.

Daily rollups keep each source's latest complete catalog for a UTC day, its prior complete-day baseline, `net_events`, `observed_events`, and run coverage. Intraday paid→free reversals may yield zero net loss while remaining visible in observed events. Runs with no complete catalog add coverage information rather than false empty snapshots. Rollups preserve observed events when detailed runs age out.

## JSON and report read contracts

Top-level artifact `schema_version` is **3**. The history payload/schema and churn rule also carry their own versions; those are separate from the artifact version.

- Identity: `run_id`, `started_at`, and compatibility `stamp`/`retrieved_at` where applicable.
- Raw provider JSON: source payloads plus `source_health`; websites have matching identity, `allowlist`, page mappings and their health.
- Analysis: `models[]`, `observations_count`, `views`, counts, thresholds, source/website health, `churn`, and compatibility fields.
- Report JSON: `models_by_slug` stores full model rows once. `all_*`, `ocf_*`, practical, stack and family sections refer to slugs. `source_health`, `website_health`, and `churn` pass through to consumers.
- `churn`: `run_id`, `rule_version`, `trusted_route_history`, `events`, `alert_events`, `counts`, `source_health`, `coverage`, and `daily.sources`. Event readers can use `kind`/`source`/`route_id`/`model` aliases; original fields remain `type`/`provider`/`id`/`canonical_id`. Detailed events carry stable event IDs and baseline/run references.
- The legacy day-level `free_churn`, `new_ids_vs_history`, `removed_ids_vs_history` and `history_days` fields were removed: they were computed against a throwaway in-memory database and never had a baseline. `alerts/check_churn.py` still reads `free_churn` from pre-removal reports, and prefers a present `churn` even when its event list is empty.

Report readers should tolerate legacy inputs without reliability fields and label missing coverage/baselines unknown. `reports.build_report.reliability_data` passes supported fields through; `health_entries` merges source comparison evidence; `reliability_tables` renders source health, route events, and daily summaries without reinterpreting missing evidence as zero loss.

Ranking keeps AA scores separate from BenchLM/LLM Stats/Vals scales. Normalization, crosswalks, observations, and views live in `analysis/analyze.py`, `crosswalk.py`, `observations.py`, and `views.py`; `enrichment.py` and `research.json` provide version/expiry/equivalence evidence. Display canonicalization currently merges normalized tail slugs and records collisions; broader identity resolution remains roadmap work. `nearest_callable` is display-only and never a fallback for `copy_id`.

MD/JSON/XLSX retain nine ranking sections. New-schema XLSX adds `Source_Health` and `Churn` to the 13 legacy sheets (15 total). Required workbook errors propagate. The dashboard has seven views; Graph is local/inlined and uses token rates rather than measured task costs. Site output includes `index.html`, `models.html`, a page for **every non-router model**, `benchmarks.html`, `compare.html`, `methodology.html`, `confidence.html`, and `data.json`. Model filenames encode slugs safely. Source and nested benchmark tabs are group-scoped; truncated leaderboard views show counts and link to the full directory.

## Retention and checks

Only the coordinator prunes, after publication:

- Keep recent `artifact_bundles` published bundles and always protect `current.json`'s target (default current + previous).
- Remove manifested failed or interrupted (`pending`) staging bundles older than `failed_days`; leave unrelated/legacy files alone. Ctrl+C marks a run `failed`; a hard kill leaves `pending`, which is safe to prune because cleanup runs under the writer lock.
- Prune detailed runs older than `run_days`, protecting the last complete published source baseline per rule version, including its route/known-free evidence through outages.
- Retain daily summaries for `daily_days`; these are independent of full artifact retention.

Validation commands are `python -B tests/test_units.py`, `python -B -m unittest discover -s tests -p "test_*.py"`, and `python -B tests/smoke.py` (optionally `--bundle <bundle-directory>`). Automated tests use fixtures/temporary databases and directories; smoke reads existing artifacts. No validation command automatically performs live API retrieval. The pipeline's publication validator additionally checks the exact staged bundle before selection.

## Extension points

- Provider: add explicit source/config support, bounded retrieval, health/completeness evidence, exact route normalization, and fixture coverage before allowing absence inference.
- History rule: version semantics, preserve publication gates, and test same-day changes, missing coverage, outages/restorations, replay, migration, retention, and recovery.
- Benchmark: add observations and a separate view with source/version/scale provenance; do not insert unrelated scores into AA ranking or ratios.
- Free signal: change evidence rules rather than presentation heuristics; keep unknown and provisional states distinct from verified paid/free evidence.
- Report: read only the selected artifact and paired files, preserve schema metadata, generate valid links for all linked models, and keep scratch output separate from published bundles.
- Evidence registry: verify URLs, benchmark versions, effort equivalence, and expiry before updating entries. See [ROADMAP.md](ROADMAP.md) for broader follow-up scope.
