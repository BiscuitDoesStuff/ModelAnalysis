# ModelAnalysis — full roadmap execution plan

## Handoff (for the next session)

**Read this first.** You're continuing the roadmap plan below on branch `biscuit` of `BiscuitDoesStuff/ModelAnalysis`. Work and push directly on `biscuit`, which is the owner's working branch. Use the plan's phase order.

**Where things stand (2026-09-27):**
- `d8ff832`: interrupted runs' staging now gets pruned; smoke checks the manifest and route churn.
- `891efc7`: Phase 0b–d, meaning the dead in-memory history is removed, helpers are shared in `analysis/common.py`, and nothing is created on import.
- Both are verified by the owner's live run `2026-09-27_095157_f0e75f9fb295`: smoke 0 failures, complete coverage.
- The Context bullets below describe the code *before* `891efc7`. The first bullet (in-memory history) and the import side-effects are already fixed.
- 0a (`research.json` refresh) is pushed as `1330219` and verified by live run `2026-09-27_102010_2272b1477638`: no AA pin warning, 2 inherited estimates, `ok research registry current`, smoke 0 failures. Entries expire 2026-10-04.
- That run was **partial coverage** only because LLM Stats' daily quota was spent (`quota too low (4 remaining)`); the fetcher's guard skipped it by design. Nothing to fix.
- **Phase 1 is pushed** (see its Status note): `requirements.lock`, `.github/workflows/ci.yml`, `tools/ci.py`, a **synthetic** golden fixture, `--as-of`/`--registry` replay flags, cross-process lock test, ruff job. Verified locally in clean 3.11 and 3.13 venvs, and **CI run #1 is green** on all 5 jobs (https://github.com/BiscuitDoesStuff/ModelAnalysis/actions/runs/36312905540).
- **Owner decided `record`** (accepting that a trimmed real fixture publishes some AA/BenchLM/LLM Stats data in this public repo). `tools/record_fixture.py` is built and pushed; the owner records from the next complete-coverage run (step 4). The synthetic fixture stays and CI replays both. First attempt (10:43 UTC 09-27) was correctly refused (quota); retry after 00:00 UTC.
- **Phase 2 is pushed** (see its Status note): `analysis/identity.py` + `identity.json`, churn rule 3 (report identity + Zen `created` ignored), identity conflicts in site/XLSX/MD, `tools/compare_bundles.py`, registry-slug warning. Offline only so far; the owner's step 5 replay review decides any joins/splits.

**Next action: Phase 3 (provenance).** Step 4 (record fixture) still waits for a complete-coverage run after 00:00 UTC; when its push lands, check CI shows `== recorded replay` green. Step 4 (record fixture) is independent: when that push lands, check its CI run includes `== recorded replay` and is green. Phase 3 starts after step 5 is settled. The evidence entries now expire on **2026-10-04**; the next refresh is due before then (repeat step 2, then the 0a pattern).

**Constraints that aren't obvious from the code:**
- **Cloud sessions can't reach the provider APIs** (a proxy returns 403). Live runs happen only on the owner's Windows machine, so validate offline and ask the owner for a live run at the plan's checkpoints.
- **The owner uses Windows PowerShell 5.1 and Python 3.13.14.**
  - Commands for them must be PowerShell.
  - For big JSON files, pipe a here-string into Python (`@' ... '@ | python -`) instead of using `ConvertFrom-Json`, which fails on large files in 5.1.
  - `runs/current.json` is small, so `ConvertFrom-Json` is fine for that one.
- **LLM Stats quota:** each live run uses about 19 of the 250 daily requests, so don't ask for repeated runs on the same day.
- **Before every push:** `python -B tools/ci.py` (fixture staleness, unit checks, 77 unittest tests, golden replay + smoke + coverage) and `ruff check --select F401,F811,F821,F841 .`; CI runs both on every push.
- **`runs/`, `raw/` and all generated reports are gitignored.** The owner's bundles exist only on their machine.
- **Route churn:** Phase 2 bumped `churn.RULE_VERSION` to 3, so the first live run after it only sets baselines ("no trusted baseline" is expected); the ~82 Zen `catalog_changed` events disappear from the run after that.
- **Owner preferences:**
  - Stay on the plan and don't wander into side topics.
  - Update this plan (its Status table and "Your steps") as work lands, and keep `docs/run-notes.md` current.

---

## Status (updated 2026-09-27)

| Item | State | Evidence |
|---|---|---|
| Phase 0b–d cleanup | **Done**, pushed as `891efc7` | Offline: 57 tests OK. Live run `2026-09-27_095157_f0e75f9fb295`: complete coverage, smoke 0 failures, 1,136 models (31 verified / 13 L1 / 234 L0), 2 inherited estimates |
| Your step 1: Python version | **Done** | You run 3.13.14 |
| Your step 2: evidence check | **Done** | Results and decisions are in 0a below |
| Your step 3: live run | **Done** | Route churn ran for the first time: 82 events, 0 alerts. You diagnosed all 82 as Zen noise (see Phase 2) |
| 0a: `research.json` refresh | **Done**, pushed as `1330219`, live-verified in step 3b | Offline: registry check (current 09-27 and 10-04, expired 10-05), 57 tests OK, fixture replay smoke shows `ok research registry current` and only the known variant-label failure. Entries now expire 2026-10-04 |
| Your step 3b: live run | **Done** | Run `2026-09-27_102010_2272b1477638`: no AA pin warning, 2 inherited estimates, `ok research registry current`, smoke 0 failures, 82 churn events / 0 alerts. But **partial coverage**: `llmstats: failed (0)`, and canonical models dropped to 1,131 from 1,136 |
| LLM Stats failure | **Closed**: daily quota spent | `quota too low (4 remaining), need ~8 for base calls; wait for UTC reset`. The guard worked as designed |
| Phase 1: CI | **Done**: [run #1](https://github.com/BiscuitDoesStuff/ModelAnalysis/actions/runs/36312905540) green on Windows + Linux × 3.11 + 3.13, and lint | `python -B tools/ci.py` passes in clean Python 3.11 and 3.13 venvs from `requirements.lock`: 59 tests, golden replay, smoke 0 failures, golden coverage OK |
| Your step 5: identity review | **Done** | Replay `2026-09-27_105813_e741d6e03a9d` vs `104304`: 1,129 → 1,129 entities, 0 splits/merges/renames, 0 rank/score/free/pick changes. 6 `aa-creator-unaliased` (grok420/43/45/46/47, longcat20) resolved by aliases `spacexai`→`xai`, `longcat`→`meituan` |
| Phase 2: identity | **Done**, live-verified in step 6 |
| Your step 6: live run | **Done** | Run `2026-09-27_110352_9cb7c4c6bb66`: 0 identity conflicts, each route owned once, XLSX 16 tabs, churn 0 events (rule-3 baseline run), smoke 0 failures. Partial coverage only from LLM Stats quota | 77 tests incl. `test_identity.py` (all plan fixtures), `test_compare_bundles.py`, Zen fingerprint test; CI green |
| Fixture source | **Decided: record** | `tools/record_fixture.py` pushed; synthetic fixture kept alongside. Your step 4 records the real one |

## Context

The pipeline is working. Commit `d8ff832` on `biscuit` passed a live run and smoke with 0 failures: 1,136 models, 31 verified free. `docs/ROADMAP.md` lists 7 follow-up items. You asked for a thorough plan with no scope limit, so this covers all 7, plus urgent fixes and cleanup found while reading the code.

Reading the code turned up problems that change the order of work:

- **The old history code runs on a throwaway in-memory database.** `analysis/analyze.py:517-600` opens `sqlite3.connect(":memory:")`. Because of that, `free_churn` never has a previous day, `new_ids_vs_history` and `removed_ids_vs_history` are always empty, the observation "90-day prune" does nothing, and `history_days` is always 1. The report, spreadsheet and site still show this dead data.
- **Matching models across providers is loose.**
  - `union` (`analyze.py:215-247`) groups every provider's routes by the end of the model ID only. It ignores the vendor part, so `vendorA/foo` and `vendorB/foo` merge.
  - Collisions are only detected among OpenRouter IDs, and are only printed.
  - `aa_by_base` (`analyze.py:102`) silently overwrites when two AA slugs end the same way.
  - Churn uses a stricter rule (`churn.same_model`, which checks the vendor part), so the two halves of the pipeline disagree.
- **Observations are never saved.** `build_observations` output is only counted (`observations_count`). Every observation is dated with the run day, not the source's fetch time. Some price rows use a cost-source label (`or-derived`) where a source name belongs.
- **The AA index version must be pinned by hand every day.** `research.json`'s `snapshot_benchmarks` has no entry for 2026-09-27, so the code falls back to the latest pin with a warning. The evidence entries expire on **2026-10-03**.
- **The same helpers exist in several places**, which makes fixes easy to miss:
  - `norm` and `base_slug` in analyze, crosswalk and fetch_websites;
  - `get` and `get_text` in both fetchers;
  - effort lists in analyze and build_report;
  - the 50/40/30 tier thresholds in analyze, enrichment and smoke.
- **Retrieval has rough edges.** The fetchers create folders when imported (`fetch_websites.py:25-27`, `analyze.py:11`), change module-level settings inside `main()`, keep `prune()` functions nothing calls, and have out-of-date docstrings. A 429 (rate limited) response gives up immediately instead of waiting and retrying.
- **There's no CI** (`.github/` doesn't exist), and `requirements.txt` has no pinned versions.
- **The site is hard to use by keyboard or screen reader.** Copy is an `onclick` on `<code>`, so it can't be reached by keyboard. Tabs have no ARIA roles. Search boxes have no labels, tables have no `th scope`, there are no focus styles, and there's no `@media` in the site CSS. The report and the site each have their own CSS.

**Goal:** finish every roadmap item with fixtures and acceptance checks, keep the reliability behaviour already built (bundles, route history, alerts), and remove the dead or misleading output.

## How the work is delivered

- Each phase lands as small commits on `biscuit`, the same flow as `d8ff832`.
- Before every push: the full offline suite (`python -B -m unittest discover -s tests -p "test_*.py"` and `python -B tests/test_units.py`), plus CI once Phase 1 is in.
- Phases that change retrieval, matching or scoring end with **you** doing a live `run.ps1` and `python -B tests/smoke.py`, because this environment can't reach the provider APIs.
- `docs/run-notes.md`, README, USER_GUIDE, PIPELINE and ROADMAP are updated in the same commit as the behaviour they describe.

---

## Phase 0: Urgent fixes and cleanup (do first)

**0a. Evidence refresh before 2026-10-03 (you, with my help).** Re-check the AA release page and LLM Stats for Muse Spark 1.3/1.2, and the Zen free-list status of the two contributor routes. Then move `checked_at` and `expires_at` forward in `analysis/research.json`, and add a `snapshot_benchmarks` pin for each run day. This is temporary: Phase 4 removes per-day pins. I can prepare the exact edits. The pages have to be read from your machine, because this environment's network blocks them.

**0a. The edits to make.** Based on your 2026-09-27 check:
- **Your findings:**
  - AA index is still v4.3.2; 1.3 is 48 max / 45 xhigh.
  - The AA API now returns 48.1 and 45.1 directly.
  - LLM Stats is unchanged at 53.8.
  - 1.3 contributor-free is on the Zen docs free list; 1.2 contributor-free is not, is marked deprecated in models.dev, but is still in Zen's API catalog.
  - Meta's pricing docs list 1.3 and 1.2 in both tiers.
- **Your decisions:** keep the 1.2 estimate with refreshed dates, and retire the two AA score entries.

Changes to `analysis/research.json`:
1. **`snapshot_benchmarks`:** add a `"4.3.2"` pin for each day from `2026-09-27` to `2026-10-04`, covering the new evidence window. That stops the "no AA benchmark pinned" warning. Phase 4 replaces these per-day pins with version ranges.
2. **`scores`:**
   - Remove the two `aa-intelligence-index` entries (`musespark13` max 48, `musespark13xhigh` xhigh 45). They never apply now, because `enrich` only uses a registry score when the API has none.
   - Keep the LLM Stats entry and move its dates to `checked_at: 2026-09-27`, `expires_at: 2026-10-04`.
3. **`inheritance`**, both entries: `checked_at: 2026-09-27`, `expires_at: 2026-10-04`, and add a re-confirmation sentence to each `rationale`:
   - **1.3:** "Re-confirmed 2026-09-27: listed on the opencode.ai/docs/zen free list; Meta pricing docs list 1.3 in both tiers; source row now scored by the AA API (xhigh 45.1, v4.3.2)."
   - **1.2:** "2026-09-27: still in the Zen API catalog but absent from the opencode.ai/docs/zen free list and flagged deprecated in models.dev; Meta pricing docs still list 1.2 in both tiers. Kept until the route leaves the catalog; route churn alerts on its removal."
4. **`docs/run-notes.md`:** a dated entry recording the check, the retirement of the AA entries, and the conflict note from those entries (AA launch coverage reported 62 max / 61 xhigh on an earlier index revision; v4.3.2 48/45 is canonical and now comes from the API), so that history isn't lost.

**Verification:**
- A throwaway script loads `research.json` and asserts that every entry is current on `2026-09-27` and `2026-10-04`, and not on `2026-10-05`.
- The full offline suite and a fixture replay pass.
- Then your step 3 live run covers both this and the 0b–d cleanup. Expect 2 inherited estimates, no AA pin warning, and `ok research registry current` in smoke.

**0b. Remove the dead in-memory history** (`analysis/analyze.py:500-600`).
- Delete the in-memory tables (`models`, `free_history`, `observations`, `bench_sources`) and the fields computed from them: `free_churn`, `new_ids_vs_history`, `removed_ids_vs_history`, `history_days`.
- Replace every reader with the schema-3 route churn (`a["churn"]`), which `pipeline.py` already attaches:
  - `reports/build_report.py`: the overview churn note (~582), the `free_churn` JSON key (~942), and the summary sheet's `churn_*` rows (~984);
  - `reports/build_site.py` `data.json` (~314);
  - `alerts/check_churn.py`, which keeps its legacy fallback for old reports only;
  - `tests/smoke.py`, which drops the legacy `free_churn` block, since the schema-3 checks added in `d8ff832` replace it.
- Keep the `models[]` fields other code depends on: `free_status`, `free_evidence`, `collisions` (until Phase 2).

**0c. One shared home for duplicated helpers.** Add `analysis/common.py`, or extend `pipeline_common.py`, with `norm`, `base_slug`, `kebab`, `EFFORTS`, `TIERS` (50/40/30 with `tier_of`), and blended cost. Point `analyze.py`, `crosswalk.py`, `enrichment.py`, `views.py`, `build_report.py` and `fetch_websites.py` at it.

**0d. No side effects on import.** Remove `os.makedirs` from module level in `fetch_models.py`, `fetch_websites.py` and `analyze.py`. Remove the unused `prune()` functions. Fix the docstrings: "reads newest raw/*" is wrong now, because inputs are explicit.

**Done when:** all tests pass, smoke passes on a replayed bundle, the report JSON has no `free_churn`, and a text search finds no `":memory:"` in `analyze.py`.

---

## Phase 1: CI and reproducible installs (roadmap item 6; before the big refactors)

**Status (2026-09-27): done; CI run #1 green.** What landed and how it differs from the list below:
- **Two fixtures.** The synthetic one (`tests/fixtures/make_golden.py` writes `golden_*.json`; `--check` fails CI when stale) always runs: invented names, prices and scores covering every case listed below, and `tools/ci.py` fails if a replay stops producing any of them (`golden_coverage`). The **recorded** one (`recorded_*.json`) comes from `tools/record_fixture.py` on a real bundle and runs once committed. It uses the file prefix `recorded_` so it never overwrites the synthetic files, and a slightly relaxed coverage check: at least 1 inherited estimate, and no registry AA score or `claudeopus5medium` required, since live data no longer guarantees those.
- **`tools/record_fixture.py`:**
  - It refuses bundles without complete coverage.
  - It keeps rows for a selected set of models: registry targets, free-status samples, stack and practical picks, variants, benchmark joins, bench-only rows and a router. Everything is filtered by canonical key.
  - It drops OpenRouter descriptions and cuts BenchLM pages to 1,500 characters.
  - It redacts resolved credential values and key-like query params, then runs a secret scan that reports JSON paths only, never values.
  - It copies `research.json` as `recorded_research.json` and pins the bundle's evidence day.
  - It replays the result, runs smoke and the coverage check, and only writes if all of that passes.
  - Tests: `tests/test_record_fixture.py` (trimming, redaction, secret block, partial refusal).
- **Replay flags `--as-of` and `--registry`** (replay-only; analysis accepts them too). The fixture pins its evidence day and registry, so CI results don't change when `research.json` entries expire or get refreshed. A test proves the pin: 2 inherited estimates on the fixture day, 0 one day after its registry expires.
- **`tools/ci.py`** is the single command CI runs and the one to run locally.
- **Lock test:** `test_writer_lock_excludes_other_process` holds the lock in a child process (msvcrt on Windows runners, fcntl on Linux).
- **ruff** job with `F401,F811,F821,F841` only; the 3 existing unused imports were removed.
- CI sets `PYTHONIOENCODING=utf-8` because Windows pipes default to the ANSI code page. It deliberately doesn't set UTF-8 mode, which would hide file-encoding bugs you'd hit locally.

- **Pinned dependencies.** Keep `requirements.txt` as the top-level list and add a pinned `requirements.lock`, generated with `pip-compile` or written by hand. Support Python **3.11–3.13**, the versions CI proves. Record that in README. Your machine runs 3.13.14, so 3.13 is the version that must stay green; 3.11 is the oldest supported.
- **`.github/workflows/ci.yml`:**
  - Matrix: `windows-latest` and `ubuntu-latest` × Python 3.11 and 3.13.
  - Steps: install from the lock file; run `tests/test_units.py` and the unittest discovery; run `pipeline.py --snapshot tests/fixtures/golden_snapshot.json --state-dir <tmp> --db <tmp>`; then `tests/smoke.py --bundle <that bundle>`.
  - No secrets, and no network beyond pip.
- **Golden fixture** (`tests/fixtures/golden_snapshot.json` + `golden_websites.json`): a trimmed, key-free snapshot covering every smoke check. It needs effort variants, Zen `-free` routes, L0 and L1 provisional rows, BenchLM and LLM Stats rows, and inherited estimates. The current thin fixture fails "md shows variant labels", so smoke can't gate CI yet.
- **`tools/record_fixture.py`:** makes a fixture from a real bundle by cutting it to N models per source and stripping anything key-like (reuse `safe_error` patterns). You run it once locally on a real snapshot and commit the output.
- **Windows lock coverage:** a test that holds `writer_lock` in a subprocess and checks a second writer fails. That covers both the `msvcrt` and `fcntl` paths across the matrix.
- **Optional:** add `ruff` with a minimal rule set (unused imports and names, undefined names) as a separate CI job. Don't mass-reformat.

**Done when:** CI is green on both OSes; smoke runs against the golden bundle in CI; README documents the one command that reproduces CI locally.

---

## Phase 2: Provider identity and collisions (roadmap item 1)

**Status (2026-09-27): done.** Step 5 review clean (0 splits, 2 aliases added); step 6 live run: 0 conflicts, smoke 0 failures. Built as described below, with these specifics:
- **AA creator not in the alias table:** the AA row still joins when it's the only AA row for its tail and exactly one entity has that tail. It's recorded as an `aa-creator-unaliased` conflict, so an unaliased creator can't silently lose a model's score; add the alias to confirm it. With two AA rows for a tail, the strict rule applies.
- **Zen `-free` routes stay separate report entities,** as before. The `research.json` inheritance rules decide their scores. For churn, a free-only Zen entity gets its paid counterpart's `canonical_id` when exactly one entity has that tail, so loss alerts still list it as an alternative.
- **Benchmark-only rows** (BenchLM, LLM Stats rankings) attach to the one entity with their tail. They're skipped if several share it, and become reference-only rows if none do.
- **`enrich` returns registry slugs that match no model.** They print a warning, land in `analysis.registry_missing_targets`, and fail the fixture coverage check.
- **`tools/compare_bundles.py`** rebuilds route ownership for pre-identity bundles from the old tail rule. It also lists score changes, which is where a detached AA score would show up.
- **Golden fixture** gains an alias pair (`meta-llama`/`meta`), a two-vendor collision (`acme`/`orbit` `nova-1`) and an ambiguous Zen `nova-1`.

**New module `analysis/identity.py`** (pure functions, heavily fixture-tested). It takes over the grouping logic from `analyze.py:215-262`.

1. **Route records.** For every provider row, build `{provider, route_id, vendor, tail, free_suffix}`.
   - `vendor` comes from the ID's first segment, normalised through a committed alias table (`meta-llama`→`meta`, `mistralai`→`mistral`, `google`/`gemini`, …).
   - Providers whose catalogs have no vendor get an implied one: OpenAI → `openai`, Anthropic → `anthropic`.
   - Zen stays vendor-unknown.
   - Build these with `churn.build_routes`/`canonical_id` rules where they apply, so history and analysis agree.
2. **Join rule** (strict by default):
   - Same tail and same vendor after aliasing → one entity.
   - Same tail with a vendor-unknown route: join only if exactly one vendor has that tail. Otherwise the route stays on its own and is recorded as `ambiguous`.
   - Same tail with different known vendors → **separate entities**, and the collision is recorded.
3. **Explicit overrides:** a committed `analysis/identity.json` with `joins` and `splits`. Each entry has `routes`, `evidence_urls`, `checked_at` and `rationale`, validated like `research.json` (see Phase 4).
4. **AA matching.** Use AA's `model_creator` together with the tail. Two AA slugs that normalise to the same key become a recorded conflict and are never silently overwritten.
5. **Slugs.** Entities that don't collide keep their current slug (usually the tail), so page links, `research.json` targets and user bookmarks stay stable. Split entities get `<tail>.<vendor>`. `norm` never produces a `.`, so this can't clash with existing slugs or with `__variant`. `model_filename` already escapes it.
6. **Output.** Each model gets:
   - `routes: [{provider, id, free_evidence}]`;
   - `identity: {key, basis: exact|alias|explicit|unique-tail, conflicts: [...]}`.
   - Top level: `identity_conflicts` replaces `collisions`.

**Churn integration.**
- Pass `models[].routes` into `history.prepare_run`. `churn.build_routes` already accepts explicit `routes` and `canonical_id`, so alternative-route suggestions use the same identity as the report.
- **Stop Zen's fake churn** (from your step 3 diff). All 82 Zen routes register as `catalog_changed` on every run. Zen rows are just `{id, object, created, owned_by}`, and `created` moves forward on every fetch, while `churn.build_routes` fingerprints the whole row (`"catalog_hash": digest(row)`, `analysis/churn.py:118`).
  - Fix: add `VOLATILE_FIELDS = {"zen": {"created"}}` in `churn.py` and hash the row without those fields.
  - Don't exclude `created` for other providers. NVIDIA, ZenMux and OpenAI showed no false events, so their `created` looks stable.
  - The 4 OpenRouter events you saw (`qwen/qwen3-30b-a3b`, `z-ai/glm-5.3`, `~moonshotai/kimi-latest`, `~z-ai/glm-latest`) look like real changes and are left alone.
  - Test: a Zen row whose only change is `created` produces no event, while a real field change on the same row still produces `catalog_changed`.
- Bump `churn.RULE_VERSION` to 3. This covers both the identity change and the Zen fingerprint fix, so there's only one baseline reset. Until Phase 2 lands, each run keeps showing about 82 Zen `catalog_changed` events. They're harmless: `catalog_changed` never alerts. The existing version check means the first run after the upgrade only sets baselines and can't raise a false alert. Document both changes in run-notes.

**Where it shows:**
- Confidence page: an "Identity conflicts" table with the routes on each side and the reason.
- Model pages: list every route, with provider, copy control and free evidence.
- XLSX: a new `Identity` sheet (smoke's expected tab set grows).
- MD summary: a conflicts count.

**Migration check.** `enrichment.enrich` currently skips a missing `target_slug` without a word. Make it warn, and fail in tests, so a slug change can't quietly drop an estimate.

**Fixtures** (`tests/test_identity.py`), one for each of:
- same tail with two vendors;
- OpenRouter plus native OpenAI;
- a Zen tail with no vendor that is unique, and one that is ambiguous;
- two AA slugs that differ only in creator;
- an explicit join and an explicit split;
- an alias (`meta-llama` vs `meta`);
- a guard that the join result doesn't depend on input order.

**Measuring the effect before merging.** Add `tools/compare_bundles.py OLD NEW`, which takes either bundle folders or state folders (for a state folder it reads `current.json`), and reports:
- how many entities were added, split or merged;
- rank changes in the top 50;
- changes in free-status counts;
- changes in the stack and practical picks.

You replay your latest real snapshot through the new code into `replay-runs/` and a separate `replay-history.sqlite` (both added to `.gitignore`), then paste the diff; see step 5. We review every split before merging.

**Done when:** collisions between different vendors stay separate unless an explicit join says otherwise; conflicts are visible in the site, XLSX and MD; alternatives in alerts follow report identity; the rule version is bumped; the bundle diff has been reviewed.

---

## Phase 3: Benchmark provenance and scale audit (roadmap item 2)

- **Save observations.** Write the full observations list into `analysis/<run>_analysis.json`. Give each one an `obs_id` (a hash of entity, source, field and version) so report cells can reference it. Leave it out of the slim report JSON, which only carries `obs_id` references.
- **Real timestamps.** `observed_at` = the source's `fetched_at` from `source_health`, or the original `fetched_at` of a cached website page, not the run day. Carry `expires_at` from registry entries.
- **Fix source and unit fields.** Price observations use the real source (`openrouter`, `aa`, `zenmux`, `registry`) and keep `cost_source` as a separate field. Add a closed **unit/scale list** in `analysis/scales.py`: `aa-index`, `benchlm-100`, `llmstats-trueskill`, `llmstats-rank`, `percent`, `usd-per-1m-blended-3to1`, `usd-per-test`, `tokens`, `effort-list`, …. Every observation must use a listed unit, and a score observation must have a `benchmark` and either a `url` or `url_unavailable_reason`.
- **One vocabulary for evidence types** (in the Phase 0c shared module): `measured`, `external-reference`, `inherited-estimate`, `hint`, `provisional`, `unknown`. Reports and the site render labels from it and never from ad-hoc strings (`score_evidence`/`evidence_html` in build_report).
- **Every displayed cell carries its source.** Each score or price cell in the HTML dashboard, the site and XLSX (an adjacent `*_source` column) comes from one observation and carries its `obs_id`, source, version and `observed_at` (tooltip or `title`). MD gets a footnote legend.
- **Scale guard.** A test that `views.build_views` and the ranking and ratio code only ever read `aa-index` observations. Any ratio or rank over another scale fails.
- **Audit tool.** `tools/audit_provenance.py <bundle>` samples N displayed cells per page and format and follows each one back to its observation and URL. It reports orphans, missing versions and stale evidence. CI runs it on the golden bundle, and it must report zero orphans.

**Done when:** sampled cells trace to saved evidence; unknown versions and units are shown explicitly; different scales never meet in a rank or ratio; labels match across MD, JSON, XLSX, dashboard and site.

---

## Phase 4: Evidence and benchmark-version maintenance (roadmap item 4)

- **Replace per-day pins.** `snapshot_benchmarks` becomes `aa_index_versions: [{version, valid_from, valid_to|null, source_url, checked_at}]`, and a day resolves to the version whose range contains it. If the AA API response includes an index version field (check against a recorded fixture), prefer it and warn when it disagrees with the registry. A version change then invalidates, by rule, any `scores`/`inheritance` entries on the old version.
- **Registry validation** (`analysis/registry.py`), run by `enrich` and by a unit test:
  - required fields and ISO dates;
  - `checked_at ≤ expires_at`;
  - URLs well-formed;
  - `variant ∈ supported_efforts`;
  - `benchmark` in the scale list;
  - `target_slug`/`source_slug` found in the latest analysis (a warning in the pipeline, an error on the golden fixture).
  - `identity.json` gets the same checks.
- **Refresh tool.** `tools/refresh_evidence.py`:
  - `list` shows entries expiring within N days and the URLs to re-check;
  - `confirm <entry> --checked YYYY-MM-DD [--value ...] [--note ...]` updates dates and optionally the value, then appends a dated line to `docs/run-notes.md`;
  - `retire <entry>` removes an entry.
  - It never marks anything verified without an explicit `confirm`.
- **Warnings before expiry.**
  - `pipeline.py` prints a warning when any entry expires within 3 days.
  - The report's Start page and the site's Methodology page show "evidence expires in N days".
  - Expired entries lose eligibility by rule; the existing `current()` check does this and gets its own tests.
- **Boundary tests:** `checked_at == day`, `expires_at == day`, the day after expiry, a version change mid-range, an effort mismatch, and an inherited source that loses its score.

**Done when:** a refresh is one documented command sequence; expired or mismatched evidence drops out predictably; a version change can't pass incompatible scores through.

---

## Phase 5: UX convergence and accessibility (roadmap item 3)

- **Shared UI module `reports/ui.py`:**
  - one colour-token CSS: dark (current look) plus light via `prefers-color-scheme`, with contrast pairs checked to WCAG AA 4.5:1 by a unit test on the token values;
  - `esc`, a copy button, tabs, badges, provenance labels, and zero-vs-unknown formatting.
  - `build_report.py` (1,079 lines) and `build_site.py` both use it.
  - Split `build_html` into one function per page while doing this.
- **Accessibility:**
  - Copy becomes a `<button type=button aria-label="Copy route …">` with an `aria-live` confirmation. Display-only routes get no button (keeps the "never copyable" rule).
  - Tabs get `role=tablist/tab/tabpanel`, `aria-selected`, `aria-controls` and arrow-key navigation.
  - Search inputs get a `<label>`; tables get `<caption>` and `th scope`.
  - Add a skip link and `:focus-visible` outlines.
  - The graph (`reports/graph.js`) SVG gets `role=img`, `<title>`/`<desc>` and a data table beneath it as a fallback.
  - Narrow screens (≤480px) get tables scrolling inside their own container and navigation that wraps.
- **Consistency:** the dashboard and site show the same columns for identity, free status, price and price source, and evidence, all built from one row-view helper.
- **Tests:**
  - HTML structure tests: every button has an accessible name, every input a label, every tab panel an owner, and no copy control on display-only routes.
  - A cross-format test that one model shows identical values in the dashboard, the site page and the XLSX row.
  - Optional CI job: Playwright (Chromium) + axe-core against the golden bundle, served over file://.
- **UI review:** I publish screenshots at desktop and phone widths in light and dark, so you can review before merging.

**Done when:** keyboard-only use reaches every control; axe reports no serious or critical issues; zero and unknown look different; common rows match across views.

---

## Phase 6: Retrieval efficiency and observability (roadmap item 5)

- **One HTTP client `retrieval/http.py`** replacing both copies of `get`/`get_text`:
  - retries with jitter;
  - 429 and 503 wait for `Retry-After` (capped);
  - per-host counts of requests, bytes, seconds and retries;
  - safe error text via `safe_error`.
- **A run context instead of module state.** The fetchers get their output folder, cache folder, error log and config as arguments, so `main()` no longer changes module-level `RAW`/`CACHE`/`ERRLOG`/`CONFIG`.
- **Measure first.** Save per-source request counts, bytes, time, cache hits and LLM Stats quota before and after into `source_health`, and show them in a "Retrieval" table on the Confidence page. Record the baseline from one live run in run-notes.
- **Then optimise, only where the measurements show a gain:**
  - conditional requests (`ETag`/`If-Modified-Since`) for catalogs and BenchLM JSON, with the validators kept next to the website cache;
  - fetching independent sources in parallel (bounded to 4 threads, with output order kept fixed);
  - an LLM Stats daily budget setting (`llmstats_daily_budget`) that cuts back detail fetches.
  - Cache hits keep their original `fetched_at` (already true for website pages; extend it to catalogs).
  - Interrupted pagination stays `partial`; existing tests cover this.
- **Replay tests** built from recorded fixtures, with no network and no quota use, for: 429 then success, `Retry-After`, a 304 (not modified) reuse, a budget cutoff, and parallel fetches with fixed output order.

**Done when:** a before/after pair of live runs shows fewer requests with identical completeness; quota use is visible and within budget; validation never touches the network.

---

## Phase 7: Scalable browsing and output size (roadmap item 7)

- **Measure.** `tools/measure_bundle.py <bundle>` reports bundle size, the size of each output file, page count, generation seconds per stage (already in the manifest) and the largest pages. Record the numbers for your live bundle.
- **Large synthetic fixture.** `tests/fixtures/make_large.py` builds 5k and 20k models deterministically. A test checks that there are no broken links, no missing non-router pages, and that displayed and total counts match.
- **Budgets** (set from the measurements; starting targets): dashboard HTML ≤ 5 MB, `data.json` ≤ 10 MB, site generation ≤ 60 s at 20k models. They're enforced as a slow test that CI runs on Linux only.
- **Directory and search.**
  - The model directory shows the first page and searches the **whole** catalog through a small search index written as a `.js` file. Browsers block `fetch()` of JSON from `file://`, so a script include keeps the site working offline.
  - Dashboard tables get pagination.
  - Model pages stay static; split them into subfolders by first character only if the measurements call for it.
- **Full exports stay:** full JSON and XLSX, plus an optional `models.csv`.

**Done when:** the 20k fixture passes coverage and link checks within budget; search reaches the full catalog; the site still works offline.

---

## Order and dependencies

```
Phase 0 (urgent, includes 0a before Oct 3)
  └─ Phase 1 CI ──────────────┐   (guards everything after)
       └─ Phase 2 Identity ───┼─ Phase 3 Provenance ─ Phase 4 Evidence
                              └─ Phase 5 UX/a11y (can start after Phase 2's output format settles)
                                   Phase 6 Retrieval (independent; after Phase 1)
                                   Phase 7 Scale (last; uses measurements from 3/5/6)
```

Phases 5 and 6 can run alongside 3 and 4. Each phase is independently shippable.

## Files touched (representative)

- **New:**
  - `analysis/identity.py`, `analysis/identity.json`, `analysis/scales.py`, `analysis/registry.py`
  - `retrieval/http.py`, `reports/ui.py`
  - `tools/{record_fixture,compare_bundles,audit_provenance,refresh_evidence,measure_bundle}.py`
  - `.github/workflows/ci.yml`, `requirements.lock`, `tests/fixtures/*`
  - `tests/test_{identity,provenance,registry,ui,http,scale}.py`
- **Changed:**
  - `analysis/{analyze,crosswalk,enrichment,observations,views,churn,history}.py`
  - `reports/{build_report,build_site,graph.js}`, `alerts/check_churn.py`
  - `retrieval/{fetch_models,fetch_websites}.py`, `pipeline.py`, `pipeline_common.py`
  - `tests/smoke.py`, docs.
- **Reused as-is:**
  - `atomic_json`, `source_status`, `safe_error`, `check_identity`, `stage_cli` (`pipeline_common.py`)
  - `churn.build_routes` explicit mappings and `same_model`
  - `history` rule-version checks
  - `pipeline.validate_bundle` link checker (extend it with the a11y structure checks)
  - the `failpoint` hooks for crash tests.

## Verification (every phase)

1. **Offline:** `python -B tests/test_units.py`, `python -B -m unittest discover -s tests -p "test_*.py"`, a golden-fixture replay through `pipeline.py --snapshot`, then `tests/smoke.py --bundle <replay>`.
2. **CI** green on Windows and Linux (from Phase 1 on).
3. **Phase-specific tools:**
   - `compare_bundles.py` for identity (you review the diff);
   - `audit_provenance.py`, which must report zero orphans;
   - `refresh_evidence.py list`;
   - `measure_bundle.py` against the budgets;
   - an axe and screenshot review for UX.
4. **Live check by you** after Phases 0, 2, 3 and 6: `powershell -File run.ps1` then `python -B tests/smoke.py`. After Phase 2, expect a baseline-only run because of the rule-version bump.

## Your steps, in order

Run every command in PowerShell from `C:\DevProjects\ModelAnalysis`. Unless a step says otherwise, start with `git pull origin biscuit`.

| # | When | Time | What |
|---|---|---|---|
| 1 | — | — | ✅ Done: Python 3.13.14 |
| 2 | — | — | ✅ Done: evidence check (results in 0a) |
| 3 | — | — | ✅ Done: live run `095157_f0e75f9fb295`, smoke 0 failures |
| 3b | — | — | Live run checkpoint: expect no "no AA benchmark pinned" warning, 2 inherited estimates, `ok research registry current` |
| 3c | — | — | ✅ Done: LLM Stats failure was the daily quota |
| 4 | **After 00:00 UTC** (LLM Stats quota reset) | ~15 min | `run.ps1`, then record and commit the real fixture. Tries at 10:43 and 11:03 UTC on 09-27 were correctly refused (quota) |
| 5 | — | — | ✅ Done: 0 splits; 2 aliases added |
| 6 | — | — | ✅ Done: run `110352_9cb7c4c6bb66`, 0 conflicts, smoke 0 failures |
| 6b | Any run after 00:00 UTC | — | Informational: Zen `catalog_changed` noise should be gone (0 events vs ~82) | Live run checkpoint (first run after rule 3 sets baselines only) |
| 7 | After Phases 3 and 6 | ~10 min each | Live run checkpoints (Phase 6 needs two runs) |
| 8 | During Phase 5 | ~10 min | Review screenshots and try the site by keyboard |

### Step 1: Python version
```powershell
python --version
```
Paste the result. It sets the oldest Python version CI tests.

### Step 2: Evidence refresh (before 2026-10-03)

**2a. Read your latest snapshot.** Nothing is fetched; this uses Python because Windows PowerShell 5.1's `ConvertFrom-Json` fails on large files.
```powershell
@'
import json
c = json.load(open("runs/current.json", encoding="utf-8"))
b, r = "runs/" + c["bundle"], c["run_id"]
raw = json.load(open(f"{b}/raw/{r}_models.json", encoding="utf-8"))
print("run:", r)
print("models.dev contributor routes:")
for m in raw.get("modelsdev", []) if isinstance(raw.get("modelsdev"), list) else []:
    if "muse-spark" in m["id"] and "contributor" in m["id"]:
        print(" ", m["provider"], m["id"], m["cost"], m["modalities"]["output"], m["reasoning_efforts"], "DEPRECATED" if m["deprecated"] else "")
print("zen muse routes:", [m["id"] for m in raw.get("zen", []) if isinstance(m, dict) and "muse-spark" in m.get("id", "")])
aa = raw.get("aa", {})
print("AA muse rows:")
for m in aa.get("data", []) if isinstance(aa, dict) else []:
    if "muse-spark" in (m.get("slug") or ""):
        print(" ", m.get("slug"), (m.get("evaluations") or {}).get("artificial_analysis_intelligence_index"))
print("AA response keys besides data:", [k for k in aa if k != "data"] if isinstance(aa, dict) else aa)
'@ | python -
```

**2b. Open these pages in your browser and note what you see:**
1. https://artificialanalysis.ai/models/releases/muse-spark-1-3: the **Intelligence Index version** (currently 4.3.2), and the scores for **max** (currently 48) and **xhigh** (currently 45).
2. https://llm-stats.com/models/muse-spark-1.3: the overall score (currently 53.8).
3. https://opencode.ai/docs/zen: whether `muse-spark-1.3-contributor-free` and `muse-spark-1.2-contributor-free` are still on the free list. (1.2 was already missing on 09-26.)
4. https://dev.meta.ai/docs/pricing-rate-limits: whether muse-spark 1.3 and 1.2 are still listed in both the Standard and Contributor tiers.

**2c. Paste the 2a output plus this filled-in template:**
```
AA index version: ____   1.3 max: ____   1.3 xhigh: ____
LLM Stats 1.3 overall: ____
Zen free list: 1.3-contributor-free listed? Y/N   1.2-contributor-free listed? Y/N
Meta pricing docs: 1.3 both tiers? Y/N   1.2 both tiers? Y/N
Checked on (date): ____
```
I then prepare the `research.json` edits: new dates, per-day pins through the new expiry, and dropping 1.2 if it's gone. I push them, and you run step 3.

### Step 3 (and 6, 7): Live run checkpoint
```powershell
git pull origin biscuit
powershell -File run.ps1
python -B tests/smoke.py
```
Paste:
- the final `Published <run_id> (... coverage)` line;
- any `WARNING`/`warn` lines from `run.ps1`;
- any `FAIL` lines from smoke, or "0 failures";
- whether `runs/bundles/<run_id>/reports/<run_id>_churn_alert.md` was written. If it was, paste it.

Notes:
- Each run uses about 19 of the 250 daily LLM Stats quota, so don't run it many times in one day.
- **After Phase 2:** expect "no trusted baseline" churn on the first run. That's the rule-version bump, not a bug.
- **After Phase 6:** run twice, a few minutes apart, and paste the Retrieval table from the site's Confidence page for both runs. The second run shows the cache and conditional-request savings.

### Step 4: Record the real fixture (Phase 1)
The recorder needs a bundle where **every** source is complete. Your current one (`2026-09-27_102010_2272b1477638`) isn't, because LLM Stats was out of quota, so the recorder would refuse it. Do this after 00:00 UTC, when the quota resets.
```powershell
git pull origin biscuit
powershell -File run.ps1
python tools/record_fixture.py
```
The run must end with `Published <run_id> (complete coverage)`. The recorder must print `secret scan: clean` and `fixture verified: smoke 0 failures, coverage OK`. If either is missing, nothing is written; paste its output instead. If both are there:
```powershell
git add tests/fixtures
git commit -m "test: recorded fixture from live run"
git push origin biscuit
```
Paste the recorder's output. I'll check that the CI run for your push replays the recorded fixture and is green.

CI itself is already confirmed green ([run #1](https://github.com/BiscuitDoesStuff/ModelAnalysis/actions/runs/36312905540)). To reproduce it locally, offline and with no quota: `python -m pip install -r requirements.lock`, then `python -B tools/ci.py`, which ends with `CI checks passed`.

### Step 5: Identity review (Phase 2)
This replays your latest real snapshot through the new matching into a **separate** state folder and database, so your real history is untouched.
```powershell
git pull origin biscuit
$c = Get-Content runs/current.json -Raw | ConvertFrom-Json
$b = "runs/$($c.bundle)"; $r = $c.run_id
python pipeline.py --snapshot "$b/raw/${r}_models.json" --websites "$b/raw/${r}_websites.json" --state-dir replay-runs --db replay-history.sqlite
python tools/compare_bundles.py runs replay-runs > identity-diff.txt
Get-Content identity-diff.txt
```
Paste `identity-diff.txt`. It lists every model that was split, merged or became ambiguous, plus changes in rank, free status and stack picks.

For each split, reply with one of:
- **keep split**: they really are different models; or
- **join** + an evidence link: the same model, which I add to `analysis/identity.json`.

`replay-runs/` and `replay-history.sqlite` will be gitignored, so delete them once we're done.

### Step 8: UX review (Phase 5)
I'll send screenshots at desktop and phone widths, in light and dark. Also open your current site (`runs/bundles/<run_id>/reports/<run_id>_site/index.html`) and try it without a mouse:
- **Tab** reaches every link and button;
- **Enter** copies a route;
- the **arrow keys** switch leaderboard tabs.

Reply with anything that looks or feels wrong.
