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

- Hybrid: public catalogs first (OpenRouter required; NVIDIA/ZenMux/Zen keyless), authed sources only when keys exist.
- `get()` retries 3x with backoff on 5xx/network errors; 4xx fails fast. All retries/failures append to `raw/_errors.log` (truncated at run start).
- Endpoints: OpenRouter `GET /api/v1/models`; OpenAI `GET /v1/models` (`Authorization: Bearer`); Anthropic `GET /v1/models` (`x-api-key` + `anthropic-version: 2023-06-01`); Groq `GET /openai/v1/models` (OpenAI-compatible, `Authorization: Bearer`); Cerebras `GET /v1/models` (OpenAI-compatible, `Authorization: Bearer`); NVIDIA `GET /v1/models` on `integrate.api.nvidia.com` (public, keyless); ZenMux `GET /api/v1/models` (public, keyless; richest schema: display names, modalities, context, per-MToken pricings); OpenCode Zen `GET /zen/v1/models` on `opencode.ai` (public, keyless; bare-slug IDs, `-free` suffixed free routes); AA `GET /api/v2/data/llms/models` (`x-api-key`).
- Missing keys return `{"skipped": "no <KEY>"}`; exceptions return `{"error": ...}` via `safe()`. OpenRouter failure exits 1 with no snapshot. Groq/Cerebras need `GROQ_API_KEY` / `CEREBRAS_API_KEY`; when absent their catalogs are skipped and analysis proceeds without them.
- Snapshot schema: `{retrieved_at, openrouter: [...], openai: [...]|{...}, anthropic: [...]|{...}, groq: [...]|{...}, cerebras: [...]|{...}, nvidia: [...]|{...}, zenmux: [...]|{...}, zen: [...]|{...}, aa: {...}}`. Keyless public sources (OpenRouter, NVIDIA, ZenMux, Zen) always fetch; a failure there returns `{"error": ...}` and analysis proceeds without that catalog (only OpenRouter failure aborts the run).
- Retention: `prune(keep=1)` — only the newest `raw/*_models.json` survives.

## Stage 2 — analysis (`analysis/analyze.py`)

Input: newest `raw/*_models.json`. Output: `analysis/<stamp>_analysis.json` (newest only) + upsert into `store.sqlite`.

Free classification (`or_rows[].free`), all must hold:

1. `float(pricing.prompt) == 0 and float(pricing.completion) == 0`, OR id ends with `:free`; AND
2. `(architecture.output_modalities) == ["text"]`; AND
3. id does not start with `openrouter/`.

AA rows: `{id: slug|id, name, creator, score: evaluations.artificial_analysis_intelligence_index, cost_blended: pricing.price_1m_blended_3_to_1, zero_price: input==0 and output==0}`. Zero-price IDs are billing/account-unverified by definition.

Provisional-free (Phase 1, fully automatic, no human registry): per canonical row `free_status` ∈ `verified` (OR strict-free) / `provisional-l1` (AA $0 + OR listing exists) / `provisional-l0` (AA $0 only) / `none`, plus `free_evidence[]` (`or:strict-free`, `aa:zero-price`, `or:listed`). `free` bool and `F` group stay verified-only. Output adds `free_status_counts{verified, provisional-l1, provisional-l0, none}`.

Canonical dedupe (reports-layer union; raw snapshots untouched): all providers merge by normalized tail slug — `norm(id) = re.sub(r"[^a-z0-9]", "", lower(id))` applied to `id.split(":")[0].split("/")[-1]` — into `models[]` rows with `providers[]` tags. Same-slug merges from distinct OR listings are recorded in `collisions[]` (kept merged).

SQLite (`analysis/store.sqlite`, table `models`):

```
(id TEXT, source TEXT, day TEXT, free INT, PRIMARY KEY(id, source, day))
```

Sources stored: openrouter (free = strict-free flag), openai / anthropic / groq / cerebras / nvidia / zenmux / zen (free = 0). Legacy tables lacking `source` are renamed to `models_old_<stamp>` and rebuilt. Diffs compare current OpenRouter IDs against the max stored `day < today`: `new_ids_vs_history`, `removed_ids_vs_history` (capped at 50 in JSON, full counts in `new_total`/`removed_total`). OR free-flag flips for IDs present on both days are reported as `free_churn.or_flipped_to_paid|or_flipped_to_free`.

Churn (`free_history` table: `(slug TEXT, day TEXT, free_status TEXT, disp_id TEXT, PRIMARY KEY(slug, day))`, non-router canonical rows only): each run upserts the current day, then diffs against the max stored `day < today` → `free_churn{prev_day, flipped_to_paid (was free-ish, now none), flipped_to_free (was none, now free-ish), level_changed (free-ish → other free-ish level), disappeared (slug gone), new_slugs}`. Lists capped at 50 with `*_total` counts. Empty (`prev_day: null`) until a second distinct day exists — same convention as the OR diffs. The report passes `free_churn` through to JSON uncapped-meta, plus a one-line MD/HTML overview note when `prev_day` exists.

Analysis JSON keys: legacy counts, native ID lists, retired/diff/history keys (unchanged) plus `total_groq` / `groq_ids`, `total_cerebras` / `cerebras_ids`, `total_nvidia` / `nvidia_ids`, `total_zenmux` / `zenmux_ids`, `total_zen` / `zen_ids`, plus `models[]` canonical rows
`{id, slug, or_id, name, groups[O/C/F], providers[openrouter/openai/anthropic/groq/cerebras/nvidia/zenmux/zen], score|null, cost_blended|null, ratio|null,
context, free, router, tier, free_status[verified/provisional-l1/provisional-l0/none], free_evidence[]}`, `collisions[]` (same tail slug merged from distinct listings),
`thresholds{max:50, high:40, medium:30}`, `free_status_counts`, `free_churn{prev_day, flipped_to_paid[_total], flipped_to_free[_total], level_changed[_total], disappeared[_total], new_slugs[new_total], or_flipped_to_paid[_total], or_flipped_to_free[_total]}` (lists capped at 50), `cost_method: aa_blended_primary_or_derived_fallback_per_1M`.

Groq/Cerebras/NVIDIA/ZenMux/Zen normalize like OAI/ANT (OpenAI-compatible `{id, owned_by}`; ZenMux additionally supplies `display_name`, used for names). Union merges them by tail slug; `providers[]` gains `groq`/`cerebras`/`nvidia`/`zenmux`/`zen` tags (no new `groups`; OCF stays O/C/F + provisional). Display priority: oai/ant native → OR → groq → cerebras → nvidia → zenmux → zen → AA. `has_callable` (stack/practical/outliers gate) counts `or_id` or any listed provider.
Dead keys (`free_ids`, `aa_top15`, `aa_free_unverified`, `combined_free_rank`) were removed; the report no longer consumes them.

## Stage 3 — report (`reports/build_report.py`)

Input: newest `analysis/*_analysis.json` (`models[]` canonical rows). Outputs share one `<stamp>`; older stamps pruned. 9 sections:

1–3. All Intel / Cost / Ratio (ratio = paid only + verified-free-by-score + provisional-free-by-score `[F?]` + unratable tail).
4–6. OCF-gated versions of the same (rows with any O/C/F tag OR provisional `free_status`; `[F?]` marker in MD/HTML, exact level in JSON/XLSX `free_status`).
7. Stack: tiers by `thresholds`, hierarchy = score desc + ratio tiebreak, `gaps[]` per tier. Callable ID required (`or_id` or native provider); AA-only rows stay in Intel/Cost/Ratio only. Tier filled only by provisional still flags `gap: F(verified)` (provisional carries no `F` group).
8. Practical: 3 tiers × 4 variants (OCF/OF/CF/F) = 12 `{tier, variant, winner, runner_up}` — winner is first hierarchy row after removing toggled-off groups.
9. Outliers: bargains / overpriced via quartiles over OCF paid scored+costed set (provisional excluded from quartiles); free gems = verified/provisional free + score ≥ 40, callable only.

- `.md`: header counts + 9 sections, top 20 per list, gap flags inline. Provisional rows show `[F?]` in the groups bracket.
- `.json`: 9 section keys uncapped + `quartiles` + `score_dist` (p10/p50/p90/max for threshold calibration) + `thresholds` + `routers_excluded` + `collisions` + `free_status_counts` + `*_verified_free_by_score` / `*_provisional_free_by_score` ratio splits + `free_churn` (same object as analysis).
- `.html`: tabbed dashboard (Overview + 9 sections), per-tab search, click-to-copy OpenCode IDs, no dependencies. Overview shows a churn line (`→paid / →free / disappeared / new vs <prev_day>`) once two distinct days exist.
- `.xlsx` (requires `openpyxl`, else `xlsx skipped`): `summary | All_Intel | All_Cost | All_Ratio | OCF_Intel | OCF_Cost | OCF_Ratio | OCF_Stack | OCF_Practical | OCF_Outliers`. Data sheets carry a `free_status` column (`verified` / `provisional-l1` / `provisional-l0` / `none`); `summary` carries `free_verified` / `provisional_l1` / `provisional_l0` counts.

## Stage 4 — alerts (`alerts/check_churn.py`)

Input: newest `reports/*_models.json` (`free_churn`). Always exits 0 (never breaks `run.ps1`).

- No `prev_day` (single day in history) → prints "no baseline yet", writes nothing.
- Bad news (`flipped_to_paid_total + disappeared_total + or_flipped_to_paid_total > 0`) → prints `ALERT` line and writes `reports/<stamp>_churn_alert.md` (counts + top-20 lists + verify-billing note). Pruned with the run like other reports.
- Good news only or no churn → prints summary, writes nothing.

## Extension points

- New provider: add `fetch_*()` + `safe()` call in snapshot, normalize in stage 2, render in stage 3. Keep missing-key behavior as `{"skipped": ...}`.
- New free signal: extend the strict predicate in `analyze.py`, never in the report layer; keep `aa_free_unverified` semantics unchanged.
- New report sheet/section: read from analysis JSON only — stages must stay decoupled via file contracts above.
