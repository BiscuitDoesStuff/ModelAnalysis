# On-use refresh — uses User env vars. No keys stored here.
# Usage: powershell -File run.ps1  (or run each python line manually)
# For daily runs with churn alerts, register: powershell -File schedule.ps1
python retrieval/fetch_models.py; if ($LASTEXITCODE) { exit $LASTEXITCODE }
python analysis/analyze.py; if ($LASTEXITCODE) { exit $LASTEXITCODE }
python reports/build_report.py; if ($LASTEXITCODE) { exit $LASTEXITCODE }
python alerts/check_churn.py; if ($LASTEXITCODE) { exit $LASTEXITCODE }
