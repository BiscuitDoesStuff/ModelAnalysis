# Daily scheduler for ModelAnalysis — registers a Windows Scheduled Task.
# Usage: powershell -File schedule.ps1            (daily 08:00 local)
#        powershell -File schedule.ps1 -Time 21:30 (custom time)
#        powershell -File schedule.ps1 -Remove    (unregister)
# The task runs run.ps1 (fetch -> analyze -> report -> churn alerts) in this directory.
# Keys come from User env vars / .env as usual. No keys stored here.
param([string]$Time = "08:00", [switch]$Remove)

$TaskName = "ModelAnalysisDaily"
if ($Remove) {
    schtasks /Delete /TN $TaskName /F
    exit $LASTEXITCODE
}
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Hour, $Minute = $Time.Split(":")
schtasks /Create /TN $TaskName /TR "powershell -NoProfile -File `"$Dir\run.ps1`"" /SC DAILY /ST "$Hour`:$Minute" /RL LIMITED /F
if ($LASTEXITCODE) { exit $LASTEXITCODE }
Write-Output "registered $TaskName daily at $Time (runs in $Dir)"
schtasks /Query /TN $TaskName
