# Pinned six-stage pipeline: fetch, websites, analyze, report, site, alerts.
# alerts/check_churn.py is invoked by pipeline.py after building this run's reports.
# Credential resolution (including Windows User fallback) is shared in Python.
# All text here is ASCII so Windows PowerShell 5.1 needs no encoding workaround.
$ErrorActionPreference = "Stop"
& python (Join-Path $PSScriptRoot "pipeline.py") @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
