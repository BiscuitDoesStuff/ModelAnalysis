# On-use refresh — uses User env vars. No keys stored here.
# NOTE: terminals opened BEFORE a key was set won't see it (stale env block).
# Open a fresh terminal after setting keys, or `run.ps1` silently skips keyed sources.
# Usage: powershell -File run.ps1  (or run each python line manually)
if (-not $env:LLM_STATS_API_KEY) { Write-Warning "LLM_STATS_API_KEY absent — LLM Stats bulk/API views will skip (website hints still crawl). This is also shown when the terminal predates the key: open a fresh terminal." }
if (-not $env:AA_API_KEY) { Write-Warning "AA_API_KEY absent — ranking scores will be thin (public run)." }
python retrieval/fetch_models.py; if ($LASTEXITCODE) { exit $LASTEXITCODE }
python retrieval/fetch_websites.py; if ($LASTEXITCODE) { exit $LASTEXITCODE }
python analysis/analyze.py; if ($LASTEXITCODE) { exit $LASTEXITCODE }
python reports/build_report.py; if ($LASTEXITCODE) { exit $LASTEXITCODE }
python reports/build_site.py; if ($LASTEXITCODE) { exit $LASTEXITCODE }
python alerts/check_churn.py; if ($LASTEXITCODE) { exit $LASTEXITCODE }
