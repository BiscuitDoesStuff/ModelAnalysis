# On-use refresh — uses User env vars. No keys stored here.
# NOTE: terminals opened BEFORE a key was set won't see it (stale env block).
# Open a fresh terminal after setting keys, or `run.ps1` silently skips keyed sources.
# Usage: powershell -File run.ps1  (or run each python line manually)
if (-not $env:LLM_STATS_API_KEY) { Write-Warning "LLM_STATS_API_KEY absent — LLM Stats bulk/API views will skip (website hints still crawl). This is also shown when the terminal predates the key: open a fresh terminal." }
if (-not $env:AA_API_KEY) { Write-Warning "AA_API_KEY absent — ranking scores will be thin (public run)." }
function Invoke-Stage([string]$name, [scriptblock]$job) {
    $t0 = Get-Date
    Write-Host "[$name] start $($t0.ToString('HH:mm:ss'))"
    & $job
    if ($LASTEXITCODE) { Write-Host "[$name] FAILED ($LASTEXITCODE)"; exit $LASTEXITCODE }
    $dt = (Get-Date) - $t0
    Write-Host "[$name] done in $([math]::Round($dt.TotalSeconds,1))s"
}
Invoke-Stage "fetch"    { python retrieval/fetch_models.py }
Invoke-Stage "websites" { python retrieval/fetch_websites.py }
Invoke-Stage "analyze"  { python analysis/analyze.py }
Invoke-Stage "report"   { python reports/build_report.py }
Invoke-Stage "site"     { python reports/build_site.py }
Invoke-Stage "alerts"   { python alerts/check_churn.py }
