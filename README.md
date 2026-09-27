# ModelAnalysis

Local, on-use snapshots of LLM catalogs, free routes, prices, and benchmark evidence. Produces Markdown, Excel, JSON, an offline dashboard, and a browsable static site. Provider coverage and source timestamps travel with each report; incomplete retrieval is never evidence that a route disappeared.

## Quickstart

Use Python 3.10+; PowerShell is optional.

```powershell
python -m pip install -r requirements.txt
python pipeline.py
# Windows wrapper, forwarding the same options:
powershell -File run.ps1
```

Public catalogs need no keys. Optional credentials add OpenAI, Anthropic, Artificial Analysis, and LLM Stats API coverage. Retrieval lists catalogs and evidence; it does not invoke model inference.

For local settings, copy `config.example.json` to `config.json` and `.env.example` to `.env` as needed:

```powershell
python pipeline.py --config config.json --state-dir runs --db analysis/store.sqlite
```

Credential precedence is **nonempty process environment → repository `.env` → Windows User environment**. Empty process values do not disable a source; use `disabled_sources` in configuration. Keep keys local.

## Open the current report

`runs/current.json` is the publication pointer. Its `bundle` path is relative to `runs/`; do not select files by modification time.

```powershell
$current = Get-Content runs/current.json -Raw | ConvertFrom-Json
$bundle = Join-Path runs $current.bundle
Start-Process (Join-Path $bundle "reports/$($current.run_id)_site/index.html")
```

Each bundle is `runs/bundles/<run_id>/`, with a unique UTC timestamp plus random suffix and a `manifest.json` recording publication state and validation:

| Within the bundle | Contents |
|---|---|
| `raw/<run_id>_models.json` | Provider/reference snapshots and source health |
| `raw/<run_id>_websites.json` | Selected website evidence, original fetch times, cache metadata |
| `analysis/<run_id>_analysis.json` | Canonical models, observations/views, route churn |
| `reports/<run_id>_site/` | Source leaderboards, all-model directory, every non-router model page, Compare, Methodology, Confidence, `data.json` |
| `reports/<run_id>_report.html` | Start here, Best value, Stack, Variants, Free, Graph, Explore |
| `reports/<run_id>_summary.md` | Nine ranking sections plus reliability details |
| `reports/<run_id>_models.xlsx` | 15 sheets for new-schema output; 13 for legacy input |
| `reports/<run_id>_models.json` | Slug-indexed rankings, model table, source health and structured churn |
| `reports/<run_id>_churn_alert.md` | Only when a verified-free route becomes paid or is removed |

Default retention: current + previous published bundle, 90 days of detailed SQLite history, 365 days of daily summaries, and 7 days of failed or interrupted staging runs. The last complete baseline for each source survives longer outages. History defaults to `analysis/store.sqlite`; cache and staging live under `runs/`.

## What the results mean

- **Free evidence:** OpenRouter text-only, non-router routes with zero prompt/completion prices or a `:free` ID; Zen `*-free` routes carry route evidence, with missing text-output confirmation flagged. AA-only zero prices are provisional `[F?]`, not verified access.
- **Scores:** AA remains the ranking scale. BenchLM, LLM Stats, and Vals use parallel views, never averaged. Estimates, effort variants, price sources, and reference-only evidence are labeled.
- **Coverage:** partial reports can publish when usable provider data remains. With no usable provider catalog, publication fails and the current report stays selected.
- **Churn:** compares exact `(provider, route ID)` identities against each source's last published complete catalog, including earlier runs on the same day. Daily net and observed events preserve different views of change. Only verified-free paid/removal events alert; provisional candidates remain informational.
- **Publication:** stages write a private bundle, validate artifacts and site links, then replace the current pointer. Interrupted publication is reconciled with SQLite before another run calculates baselines. A writer lock prevents concurrent writers to the same state directory.

## Replay, recover, validate

```powershell
# Offline replay; optionally supply website evidence from the snapshot's original run.
python pipeline.py --snapshot path/to/models.json --websites path/to/websites.json --state-dir replay-runs --db replay-history.sqlite
# Complete a validated interrupted publication, without fetching.
python pipeline.py --recover

python -B tests/test_units.py
python -B -m unittest discover -s tests -p "test_*.py"
python -B tests/smoke.py
```

Validation uses fixtures/temporary storage or existing artifacts, with no automatic live API calls. Standalone stages require explicit inputs and scratch outputs; see the guide.

## Code and docs

- `pipeline.py`, `pipeline_common.py`: orchestration, identity, configuration, publication and retention.
- `retrieval/`: provider retrieval and bounded website evidence.
- `analysis/`: normalization, crosswalks, evidence, views, `churn.py` rules and `history.py` persistence.
- `reports/`, `alerts/`: local presentation and verified-free loss alerts.
- [User guide](docs/USER_GUIDE.md): configuration, commands, report interpretation, troubleshooting.
- [Pipeline contracts](docs/PIPELINE.md): schemas, recovery, history, extension points.
- [Roadmap](docs/ROADMAP.md): scoped follow-up goals and acceptance criteria.
- [Run notes](docs/run-notes.md): dated implementation history.

Snapshots are point-in-time, and per-model client compatibility is not verified. Check current provider limits and data-use terms before heavy use or redistribution.

## License

MIT — see `LICENSE`.
