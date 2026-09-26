# Pipeline Internals (maintainer reference)

User-facing usage lives in `USER_GUIDE.md`. This file documents exact stage contracts, schemas, and extension points.

## Stages

```
retrieval/fetch_models.py → raw/<stamp>_models.json
analysis/analyze.py       → analysis/<stamp>_analysis.json + analysis/store.sqlite
reports/build_report.py   → reports/<stamp>_summary.md|.json|.xlsx
alerts/check_churn.py     → console churn summary + reports/<stamp>_churn_alert.md on bad news
```

`run.ps1` runs the four stages in order, exiting on first non-zero `$LASTEXITCODE`.

## Stage 1 — retrieval (`retrieval/fetch_models.py`)

- Hybrid: public catalogs first (OpenRouter required; NVIDIA/ZenMux/Zen/models.dev keyless), authed sources only when keys exist.
- `get()` retries 3x with backoff on 5xx/network errors; 4xx fails fast. All retries/failures append to `raw/_errors.log` (truncated at run start).
- Endpoints: OpenRouter `GET /api/v1/models`; OpenAI `GET /v1/models` (`Authorization: Bearer`); Anthropic `GET /v1/models` (`x-api-key` + `anthropic-version: 2023-06-01`); Groq `GET /openai/v1/models` (OpenAI-compatible, `Authorization: Bearer`); Cerebras `GET /v1/models` (OpenAI-compatible, `Authorization: Bearer`); NVIDIA `GET /v1/models` on `integrate.api.nvidia.com` (public, keyless); ZenMux `GET /api/v1/models` (public, keyless; richest schema: display names, modalities, context, per-MToken pricings); OpenCode Zen `GET /zen/v1/models` on `opencode.ai` (public, keyless; bare-slug IDs, `-free` suffixed free routes); models.dev `GET /api.json` (public, keyless, ~8k routes; minimal projection only: provider, id, cost input/output, modalities in/out, reasoning bool + effort values, deprecated flag, context/output limits, last_updated); AA `GET /api/v2/data/llms/models` (`x-api-key`).
- Missing keys return `{"skipped": "no <KEY>"}`; exceptions return `{"error": ...}` via `safe()`. OpenRouter failure exits 1 with no snapshot. Groq/Cerebras need `GROQ_API_KEY` / `CEREBRAS_API_KEY`; when absent their catalogs are skipped and analysis proceeds without them.
- Snapshot schema: `{retrieved_at, openrouter: [...], openai: [...]|{...}, anthropic: [...]|{...}, groq: [...]|{...}, cerebras: [...]|{...}, nvidia: [...]|{...}, zenmux: [...]|{...}, zen: [...]|{...}, modelsdev: [...]|{error}, aa: {...}}`. Keyless public sources (OpenRouter, NVIDIA, ZenMux, Zen, models.dev) always fetch; a failure there returns `{"error": ...}` and analysis proceeds without that catalog (only OpenRouter failure aborts the run).
- Retention: `prune(keep=1)` — only the newest `raw/*_models.json` survives.

## Stage 2 — analysis (`analysis/analyze.py`)

Input: newest `raw/*_models.json`. Output: `analysis/<stamp>_analysis.json` (newest only) + upsert into `store.sqlite`.

Free classification (`or_rows[].free` plus Zen free routes), all must hold for OR strict-free:

1. `float(pricing.prompt) == 0 and float(pricing.completion) == 0`, OR id ends with `:free`; AND
2. `(architecture.output_modalities) == ["text"]`; AND
3. id does not start with `openrouter/`.

Zen `*-free` IDs (OpenCode Zen free routes) count as verified free with evidence `zen:free-route`. Modality is confirmed via models.dev (`modalities.output == ["text"]` on the matching opencode route → `modality_status: confirmed-text`); Zen rows with no text confirmation stay `modality-unverified` (e.g. no models.dev entry).

AA rows: `{id: slug|id, name, creator, score: evaluations.artificial_analysis_intelligence_index|null when missing, cost_blended: pricing.price_1m_blended_3_to_1, zero_price: input==0 and output==0}`. Zero-price IDs are billing/account-unverified by definition.

Cost provenance (per-row `cost_source`): `aa` when AA blended price present (primary), else `or-derived` when OpenRouter pricing fills (blended `(3*prompt+completion)/4*1e6`), else `inherited` for derived estimates (destination-route $0), else `none` (cost-unknown). `cost null iff cost_source none`.

Tier 1 capabilities (models.dev + ZenMux promotion): models.dev routes indexed by tail slug (`md_by_slug`) provide `modelsdev_count`, `modelsdev_efforts` (union of `reasoning_options[type==effort].values`), `deprecated_upstream` + `deprecated_sources` (`status == deprecated`, e.g. `opencode/muse-spark-1.2-contributor-free`), and modality confirmation. ZenMux entries (previously id-only) now contribute `zenmux_reasoning` (True/False/None from `capabilities.reasoning`), `zenmux_output` (output modalities), plus pricings/context for reference (ranking still uses AA/OR costs only). OR rows without `reasoning` split into `or_reasoning_status`: `listed` (efforts present), `non-reasoning` (upstream confirms no reasoning), `metadata-missing` (no upstream info or upstream says reasoning but OR omits it), `no-or-listing` (no OR ids). Default effort without OR default marks `default_effort_source: unspecified-upstream` (models.dev lists values but no default); display shows `(default unspecified)`.

Enrichment (`analysis/enrichment.py` + `analysis/research.json`, committed source): every model gets `score_source` (`aa-api` with `benchmark: aa-intelligence-index`, `version` from `snapshot_benchmarks[day]`, else null when unscored), `external_scores[]` (registry entries for that slug, each with `eligible` flag), and `research_notes[]`. External AA-version-matched entries may fill a missing score (`kind: external`); different-metric entries (e.g. `llm-stats-overall`) stay reference-only and never enter ranking. Cross-benchmark comparison is forbidden — `eligible` requires same `variant`, same `benchmark`, and same `version` as the snapshot cohort. Registry entries carry `checked_at`/`expires_at` (7-day default); expired entries stay visible as references but lose eligibility. Smoke warns (not fails) when analysis `day > expires_at` — manual refresh needed. Derived route/effort estimates are new rows (never silent overwrites): e.g. `musespark13contributorfree__xhigh` inherits `musespark13xhigh` 45.1 as `kind: inherited-estimate` with `upstream`, `equivalence_urls`, `capability_url` (models.dev), and `rationale`, `selector: opencode/<route>#<variant>`, destination-route pricing, `cost_source: inherited`, `efforts_source: inherited`, and `history_excluded: true` (excluded from `free_history` churn to avoid noise; included in `free_status_counts`). Inheritance requires same effort in `supported_efforts`, finite source score, provider present on target, and documented equivalence — plus Tier 1 validation that `supported_efforts` is a subset of models.dev `reasoning_efforts` for the target when models.dev knows the route — otherwise the base stays unscored.

Provisional-free (Phase 1, fully automatic, no human registry): per canonical row `free_status` ∈ `verified` (OR strict-free or Zen `*-free`) / `provisional-l1` (AA $0 + OR listing exists) / `provisional-l0` (AA $0 only) / `none`, plus `free_evidence[]` (`or:strict-free`, `zen:free-route`, `aa:zero-price`, `or:listed`). `free` bool and `F` group stay verified-only. Output adds `free_status_counts{verified, provisional-l1, provisional-l0, none}`.

Variants (reasoning efforts, separate ranked rows): OR `reasoning.supported_efforts[]` + `default_effort` preserved per OR ID into `efforts[]` / `default_effort` (`efforts_source: or`, `default_effort_source: or` or `unspecified-upstream` when default missing). AA variant suffix parsed from AA name/slug (`(max)` / `Max Effort` / `-xhigh`) into `variant` + `aa_variant_name`. Canonical slugs stay separate (`musespark13` vs `musespark13xhigh`); merged OR+AA rows keep OR display ID but carry AA variant label. Effort-disambiguation (post-enrich family pass, `family = slug stripped of variant suffix + __suffix`): scored rows with `variant == ""` in a family that already has scored effort-specific rows get `variant_ambiguous: true` (`ambiguous-effort` label); singletons get `variant_label: base (unspecified effort)`. Rows with empty `efforts` inherit `efforts_hint[]` + `efforts_hint_source: sibling` + `efforts_hint_from` from the highest-scored OR-listed sibling in the same family. AA-only rows (no `or_id`, no callable provider) get `nearest_callable` + `nearest_callable_slug` from the best callable sibling — display-only, never copyable (report `copy_id` never uses it). AA-only OpenAI/Anthropic rows gain O/C groups via `model_creator` so variant scores stay visible in OCF Intel/Cost/Ratio with `fallback_id` = AA slug (`fallback_provider: aa`). L0/zen-only rows with no `or_id` carry `fallback_id`/`fallback_provider` = first native `openai/anthropic/groq/cerebras/nvidia/zenmux/zen` ID (report copy uses `or_id` else fallback; AA-only shows no callable ID + nearest hint).

Canonical dedupe (reports-layer union; raw snapshots untouched): all providers merge by normalized tail slug — `norm(id) = re.sub(r"[^a-z0-9]", "", lower(id))` applied to `id.split(":")[0].split("/")[-1]` — into `models[]` rows with `providers[]` tags. Same-slug merges from distinct OR listings are recorded in `collisions[]` (kept merged).

SQLite (`analysis/store.sqlite`, table `models`):

```
(id TEXT, source TEXT, day TEXT, free INT, PRIMARY KEY(id, source, day))
```

Sources stored: openrouter (free = strict-free flag), openai / anthropic / groq / cerebras / nvidia / zenmux / zen (free = 0). Legacy tables lacking `source` are renamed to `models_old_<stamp>` and rebuilt. Diffs compare current OpenRouter IDs against the max stored `day < today`: `new_ids_vs_history`, `removed_ids_vs_history` (capped at 50 in JSON, full counts in `new_total`/`removed_total`). OR free-flag flips for IDs present on both days are reported as `free_churn.or_flipped_to_paid|or_flipped_to_free`.

Churn (`free_history` table: `(slug TEXT, day TEXT, free_status TEXT, disp_id TEXT, PRIMARY KEY(slug, day))`, non-router canonical rows only): each run upserts the current day, then diffs against the max stored `day < today` → `free_churn{prev_day, flipped_to_paid (was free-ish, now none), flipped_to_free (was none, now free-ish), level_changed (free-ish → other free-ish level), disappeared (slug gone), new_slugs}`. Lists capped at 50 with `*_total` counts. Empty (`prev_day: null`) until a second distinct day exists — same convention as the OR diffs. The report passes `free_churn` through to JSON uncapped-meta, plus a one-line MD/HTML overview note when `prev_day` exists.

Analysis JSON keys: legacy counts, native ID lists, retired/diff/history keys (unchanged) plus `total_groq` / `groq_ids`, `total_cerebras` / `cerebras_ids`, `total_nvidia` / `nvidia_ids`, `total_zenmux` / `zenmux_ids`, `total_zen` / `zen_ids`, `total_modelsdev` (8181-route minimal projection count), plus `models[]` canonical rows
`{id, slug, or_id, name, groups[O/C/F], providers[openrouter/openai/anthropic/groq/cerebras/nvidia/zenmux/zen], score|null, cost_blended|null, cost_source[aa/or-derived/inherited/none], ratio|null,
context, free, router, tier, free_status[verified/provisional-l1/provisional-l0/none], free_evidence[], variant[max/xhigh/high/medium/low/minimal/none/""],
variant_ambiguous, variant_label, aa_variant_name, aa_id, efforts[], default_effort, efforts_source[or/inherited/""], default_effort_source[or/unspecified-upstream/""],
efforts_hint[], efforts_hint_source[sibling/""], efforts_hint_from, or_reasoning_status[listed/non-reasoning/metadata-missing/no-or-listing],
deprecated_upstream, deprecated_sources[], modality_status[confirmed-text/modality-unverified/""],
modelsdev_count, modelsdev_efforts[], zenmux_reasoning, zenmux_output[],
fallback_id, fallback_provider, nearest_callable (display-only), nearest_callable_slug, selector, score_source{kind: aa-api/external/inherited-estimate, benchmark, version, url, upstream}, external_scores[], research_notes[], history_excluded}`, `collisions[]` (same tail slug merged from distinct listings),
`thresholds{max:50, high:40, medium:30}`, `free_status_counts`, `free_churn{prev_day, flipped_to_paid[_total], flipped_to_free[_total], level_changed[_total], disappeared[_total], new_slugs[new_total], or_flipped_to_paid[_total], or_flipped_to_free[_total]}` (lists capped at 50), `cost_method: aa_blended_primary_or_derived_fallback_per_1M`.

Groq/Cerebras/NVIDIA/ZenMux/Zen normalize like OAI/ANT (OpenAI-compatible `{id, owned_by}`; ZenMux additionally supplies `display_name`, used for names). Union merges them by tail slug; `providers[]` gains `groq`/`cerebras`/`nvidia`/`zenmux`/`zen` tags (no new `groups`; OCF stays O/C/F + provisional). Display priority: oai/ant native → OR → groq → cerebras → nvidia → zenmux → zen → AA. `has_callable` (stack/practical/outliers gate) counts `or_id` or any listed provider.
Dead keys (`free_ids`, `aa_top15`, `aa_free_unverified`, `combined_free_rank`) were removed; the report no longer consumes them.

## Stage 3 — report (`reports/build_report.py`)

Input: newest `analysis/*_analysis.json` (`models[]` canonical rows). Outputs share one `<stamp>`; older stamps pruned. MD/JSON/XLSX keep 9 sections; HTML is a 6-page user view over the same data:

1–3. All Intel / Cost / Ratio (ratio = paid only + verified-free-by-score + provisional-free-by-score `[F?]` + unratable tail).
4–6. OCF-gated versions of the same (rows with any O/C/F tag OR provisional `free_status`; `[F?]` marker in MD/HTML, exact level in JSON/XLSX `free_status`).
7. Stack: tiers by `thresholds`, hierarchy = score desc + ratio tiebreak, `gaps[]` per tier. Callable ID required (`or_id` or native provider); AA-only rows stay in Intel/Cost/Ratio only. Tier filled only by provisional still flags `gap: F(verified)` (provisional carries no `F` group).
8. Practical: 3 tiers × 4 variants (OCF/OF/CF/F) = 12 `{tier, variant, winner, runner_up}` — winner is first hierarchy row after removing toggled-off groups.
9. Outliers: bargains / overpriced via quartiles over OCF paid scored+costed set (provisional excluded from quartiles); free gems = verified/provisional free + score ≥ 40, callable only.

- `.md`: header counts + 9 sections, top 20 per list, gap flags inline. Provisional rows show `[F?]` in the groups bracket. Variant rows show `(max/xhigh/…)` or `(ambiguous-effort)` / `(base, unspecified effort)` + `[deprecated-upstream]` / `[modality-unverified]` badges; `efforts a/b/c *default` or `(default unspecified)` or `(hint, sibling)` or `[non-reasoning]`/`[metadata-missing]`; cost shows `$/1M [aa|or-derived|inherited]`; copy ID is `selector` when present else `openrouter/<or_id>` else native `fallback_id (provider)` else `AA-only, no callable ID` (+ `nearest <id> display-only` hint when a callable sibling exists). Every row ends with score evidence (`aa-api / <version>`, `inherited-estimate from <slug>`, or `unscored`) plus `[source]` links (equivalence + capability + upstream).
- `.json`: 9 section keys uncapped + `quartiles` + `score_dist` (p10/p50/p90/max for threshold calibration) + `thresholds` + `routers_excluded` + `collisions` + `free_status_counts` + `*_verified_free_by_score` / `*_provisional_free_by_score` ratio splits + `free_churn` (same object as analysis) + `family_variants` (full per-family table). Model rows carry `variant`, `variant_ambiguous`, `efforts`, `efforts_hint`, `nearest_callable` (display-only), `cost_source`, `deprecated_upstream`, `modality_status`, `fallback_id`, `selector`, `score_source`, `external_scores`.
- `.html`: 6-page dashboard (Start here · Best value · Stack · Variants · Free · Explore), per-table search + Explore group/cost/free filters, click-to-copy route IDs (selector else OR else fallback; AA-only shows `AA-only / no callable ID` + nearest display-only hint, never copyable), Variant/Efforts columns (ambiguous/base/deprecated/modality badges, cost-source sublabels, hint/sibling + default-unspecified labels) + Score-evidence column with source links, no dependencies. Start here shows copy-ready Top quality / Best value / Free cards + churn line (`→paid / →free / disappeared / new vs <prev_day>`) once two distinct days exist, plus variant/`provider/model#variant` usage note (OpenCode V2). Best value groups paid OCF rows into score bands (width ±1.5, 30+ floor): cheapest-first within band with saving vs priciest. Variants shows per-family side-by-side (AA-only greyed, callable sibling hinted). Free consolidates verified + provisional `[F?]` (was scattered across ratio sub-blocks). Explore is one filterable All-models table replacing the old All/OCF Intel/Cost/Ratio duplicates (full lists stay in JSON/XLSX).
- `.xlsx` (requires `openpyxl`, else `xlsx skipped`): `summary | All_Intel | All_Cost | All_Ratio | OCF_Intel | OCF_Cost | OCF_Ratio | OCF_Stack | OCF_Practical | OCF_Outliers | Family_Variants`. Data sheets carry `free_status` (`verified` / `provisional-l1` / `provisional-l0` / `none`) + `variant` / `variant_ambiguous` / `variant_label` / `efforts` / `default_effort` / `default_effort_source` / `efforts_source` / `efforts_hint` / `or_reasoning_status` / `fallback_id` / `fallback_provider` / `nearest_callable` (display-only) / `deprecated_upstream` / `modality_status` + `cost_source` + `score_source` / `score_urls` / `external_scores`; `summary` carries `free_verified` / `provisional_l1` / `provisional_l0` / `total_modelsdev` counts. `OCF_Practical` carries `winner_variant` + `winner_copy_id`. `Family_Variants` carries `family` + `peak` + full row (every multi-variant family, all rows).

## Stage 4 — alerts (`alerts/check_churn.py`)

Input: newest `reports/*_models.json` (`free_churn`). Always exits 0 (never breaks `run.ps1`).

- No `prev_day` (single day in history) → prints "no baseline yet", writes nothing.
- Bad news (`flipped_to_paid_total + disappeared_total + or_flipped_to_paid_total > 0`) → prints `ALERT` line and writes `reports/<stamp>_churn_alert.md` (counts + top-20 lists + verify-billing note). Pruned with the run like other reports.
- Good news only or no churn → prints summary, writes nothing.

## Extension points

- New provider: add `fetch_*()` + `safe()` call in snapshot, normalize in stage 2, render in stage 3. Keep missing-key behavior as `{"skipped": ...}`. models.dev is the Tier 1 capabilities reference (keyless, minimal projection); keep it failure-tolerant like other public catalogs.
- New free signal: extend the strict predicate in `analyze.py` (OR `is_free_or` + Zen `*-free`), never in the report layer; keep provisional `verified/provisional-l1/provisional-l0` semantics (dead `aa_free_unverified` key removed). Use `modality_status` / models.dev to confirm text-out; never trust bare IDs alone.
- New report sheet/section: read from analysis JSON only — stages must stay decoupled via file contracts above. Variant/effort/fallback columns (`variant`, `efforts`, `default_effort`, `fallback_id`) are display-only; OCF gating stays groups/provisional-based. `nearest_callable` is display-only by contract — never feed it to `copy_id`.
- New score evidence: add entries to `analysis/research.json` with `checked_at`/`expires_at`, `benchmark`+`version`, and rationale/URLs — never mix benchmark scales. Update `snapshot_benchmarks[day]` when the AA Intelligence Index revision changes; expired entries become reference-only automatically via `eligible`. Inheritance `supported_efforts` must stay a subset of models.dev `reasoning_efforts` when the route is known.
