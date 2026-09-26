# Pipeline Internals (maintainer reference)

User-facing usage lives in `USER_GUIDE.md`. This file documents exact stage contracts, schemas, and extension points.

## Stages

```
retrieval/fetch_models.py → raw/<stamp>_models.json
analysis/analyze.py       → analysis/<stamp>_analysis.json + analysis/store.sqlite
reports/build_report.py   → reports/<stamp>_summary.md|.json|.xlsx
```

`run.ps1` runs the three stages in order, exiting on first non-zero `$LASTEXITCODE`.

## Stage 1 — retrieval (`retrieval/fetch_models.py`)

- Hybrid: OpenRouter public first (no key), authed sources only when keys exist.
- `get()` retries 3x with backoff on 5xx/network errors; 4xx fails fast. All retries/failures append to `raw/_errors.log` (truncated at run start).
- Endpoints: OpenRouter `GET /api/v1/models`; OpenAI `GET /v1/models` (`Authorization: Bearer`); Anthropic `GET /v1/models` (`x-api-key` + `anthropic-version: 2023-06-01`); AA `GET /api/v2/data/llms/models` (`x-api-key`).
- Missing keys return `{"skipped": "no <KEY>"}`; exceptions return `{"error": ...}` via `safe()`. OpenRouter failure exits 1 with no snapshot.
- Snapshot schema: `{retrieved_at, openrouter: [...], openai: [...]|{...}, anthropic: [...]|{...}, aa: {...}}`.
- Retention: `prune(keep=1)` — only the newest `raw/*_models.json` survives.

## Stage 2 — analysis (`analysis/analyze.py`)

Input: newest `raw/*_models.json`. Output: `analysis/<stamp>_analysis.json` (newest only) + upsert into `store.sqlite`.

Free classification (`or_rows[].free`), all must hold:

1. `float(pricing.prompt) == 0 and float(pricing.completion) == 0`, OR id ends with `:free`; AND
2. `(architecture.output_modalities) == ["text"]`; AND
3. id does not start with `openrouter/`.

AA rows: `{id: slug|id, name, creator, score: evaluations.artificial_analysis_intelligence_index, cost_blended: pricing.price_1m_blended_3_to_1, zero_price: input==0 and output==0}`. Top 15 by score; `aa_free_unverified` = zero-price IDs (billing/account NOT checked).

Combined rank: strict-free OpenRouter rows joined to AA by exact normalized-slug match — `norm(id) = re.sub(r"[^a-z0-9]", "", lower(id))` applied to `or_id.split(":")[0].split("/")[-1]`. No match → `aa_score 0`, `aa_match ""`. Top 30 by score.

SQLite (`analysis/store.sqlite`, table `models`):

```
(id TEXT, source TEXT, day TEXT, free INT, PRIMARY KEY(id, source, day))
```

Legacy tables lacking `source` are renamed to `models_old_<stamp>` and rebuilt. Diffs compare current OpenRouter IDs against the max stored `day < today`: `new_ids_vs_history`, `removed_ids_vs_history` (capped at 50 in JSON, full counts in `new_total`/`removed_total`).

Analysis JSON keys: legacy counts, native ID lists, retired/diff/history keys (unchanged) plus `models[]` canonical rows
`{id, or_id, name, groups[O/C/F], providers[], score|null, cost_blended|null, ratio|null,
context, free, router, tier}`, `collisions[]` (same tail slug merged from distinct listings),
`thresholds{max:50, high:40, medium:30}`, `cost_method: aa_blended_primary_or_derived_fallback_per_1M`.
Dead keys (`free_ids`, `aa_top15`, `aa_free_unverified`, `combined_free_rank`) were removed; the report no longer consumes them.

## Stage 3 — report (`reports/build_report.py`)

Input: newest `analysis/*_analysis.json` (`models[]` canonical rows). Outputs share one `<stamp>`; older stamps pruned. 9 sections:

1–3. All Intel / Cost / Ratio (ratio = paid only + free-by-score block + unratable tail).
4–6. OCF-gated versions of the same (rows with any O/C/F tag).
7. Stack: tiers by `thresholds`, hierarchy = score desc + ratio tiebreak, `gaps[]` per tier.
8. Practical: 3 tiers × 4 variants (OCF/OF/CF/F) = 12 `{tier, variant, winner, runner_up}` — winner is first hierarchy row after removing toggled-off groups.
9. Outliers: bargains / overpriced via quartiles over OCF paid scored+costed set; free gems = free + score ≥ 40.

- `.md`: header counts + 9 sections, top 20 per list, gap flags inline.
- `.json`: 9 section keys uncapped + `quartiles` + `score_dist` (p10/p50/p90/max for threshold calibration) + `thresholds` + `routers_excluded` + `collisions`.
- `.xlsx` (requires `openpyxl`, else `xlsx skipped`): `summary | All_Intel | All_Cost | All_Ratio | OCF_Intel | OCF_Cost | OCF_Ratio | OCF_Stack | OCF_Practical | OCF_Outliers`.

## Extension points

- New provider: add `fetch_*()` + `safe()` call in snapshot, normalize in stage 2, render in stage 3. Keep missing-key behavior as `{"skipped": ...}`.
- New free signal: extend the strict predicate in `analyze.py`, never in the report layer; keep `aa_free_unverified` semantics unchanged.
- New report sheet/section: read from analysis JSON only — stages must stay decoupled via file contracts above.
