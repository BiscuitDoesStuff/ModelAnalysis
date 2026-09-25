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

Analysis JSON keys: `stamp, day, total_openrouter, free_count, free_ids[:300], new_ids_vs_history[:50], new_total, removed_ids_vs_history[:50], removed_total, history_days, total_openai, openai_ids, openai_retired[:50], total_anthropic, anthropic_ids, total_aa, aa_top15, aa_free_unverified[:100], aa_free_count, combined_free_rank[:30]`.

## Stage 3 — report (`reports/build_report.py`)

Input: newest `analysis/*_analysis.json`. Outputs share one `<stamp>`; older stamps pruned.

- `.md`: header counts, combined rank (20), free list with OpenCode IDs `openrouter/<or_id>` (100), AA Top 15, Anthropic IDs, OpenAI retired (30), diffs, verification-tier note, hand-maintained `LIMITS` table (last checked 2026-09-25 — verify in provider docs), on-use source note.
- `.json`: full analysis object verbatim.
- `.xlsx` (requires `openpyxl`, else `xlsx skipped`): sheets `summary | free_rank(30) | aa_top15 | diff`.

## Extension points

- New provider: add `fetch_*()` + `safe()` call in snapshot, normalize in stage 2, render in stage 3. Keep missing-key behavior as `{"skipped": ...}`.
- New free signal: extend the strict predicate in `analyze.py`, never in the report layer; keep `aa_free_unverified` semantics unchanged.
- New report sheet/section: read from analysis JSON only — stages must stay decoupled via file contracts above.
