#requires -Version 7.2
<#
.SYNOPSIS
  SuperWorkspace CLI. In the kit: every command. Inside a project (.sw/sw.ps1):
  the project commands only (validate, doctor, claude, tiers, comms, user, gh, usage).
.EXAMPLE
  pwsh sw.ps1 init <project-path> -Profile unreal -Name MyGame
  pwsh .sw/sw.ps1 validate
#>
# No param block on purpose: plain $args keeps "-Name value" tokens bindable when
# splatted into the target function (a typed array would turn them positional).
$Command, $Arguments = $args
if (-not $Command) { $Command = 'help' }
$Arguments = @($Arguments | Where-Object { $null -ne $_ })
$ErrorActionPreference = 'Stop'
# A project copy (<root>/.sw/sw.ps1) defaults to its own project, wherever it is run from.
$env:SW_ROOT = if ((Split-Path $PSScriptRoot -Leaf) -eq '.sw') { Split-Path $PSScriptRoot -Parent } else { '' }
Import-Module (Join-Path $PSScriptRoot 'lib/Sw.Project.psm1') -Force -DisableNameChecking
$kit = Join-Path $PSScriptRoot 'lib/Sw.Kit.psm1'
if (Test-Path -LiteralPath $kit) { Import-Module $kit -Force -DisableNameChecking }

$commands = [ordered]@{
    init     = @('Initialize-SwProject', 'kit', 'Install or adopt SuperWorkspace in a project: init <path> -Profile generic|unreal [-Name] [-GitHubTier 0|1] [-Adopt] [-Claude]')
    update   = @('Update-SwProject', 'kit', 'Re-apply the kit to a project; modified files are skipped and reported: update [<path>] [-Adopt] [-Force (allow a kit downgrade)]')
    global   = @('Invoke-SwGlobal', 'kit', 'User-level setup: global install|check|backup [-Claude] [-ReplaceUnmanaged]')
    remote   = @('Invoke-SwRemote', 'kit', 'OpenCode over Tailscale: remote setup|check [-Port 49374] [-KeepLan]')
    validate = @('Test-SwProject', 'project', 'Static workspace contract check: validate [-Path] [-CheckLinks]')
    doctor   = @('Test-SwDoctor', 'project', 'Read-only setup check for a contributor: doctor [-User <name>]')
    claude   = @('Invoke-SwClaude', 'project', 'Opt-in local Claude adapter: claude enable|disable')
    tiers    = @('Set-SwTiers', 'project', 'Per-user model tiers: tiers -Reasoning <id> -Standard <id> -Fast <id> [-Force]')
    comms    = @('Invoke-SwComms', 'project', 'Messages and task records: comms send|inbox|event|close|archive ...')
    user     = @('Add-SwUser', 'project', 'Record a contributor and create their inbox: user <name>')
    gh       = @('Invoke-SwGitHub', 'project', 'GitHub helpers: gh status (read-only) | gh labels (human-run write)')
    usage    = @('Get-SwUsage', 'project', 'Usage report: RTK savings, OpenCode stats, startup budget')
}

if ($Command -in 'help', '-h', '--help', '/?' -or -not $commands.Contains($Command)) {
    if ($Command -notin 'help', '-h', '--help', '/?') { Write-Output "Unknown command: $Command`n" }
    $version = Join-Path $PSScriptRoot 'VERSION'
    Write-Output "SuperWorkspace $(if (Test-Path -LiteralPath $version) { (Get-Content -LiteralPath $version).Trim() } else { '(project copy)' })"
    foreach ($c in $commands.GetEnumerator()) {
        if ($c.Value[1] -eq 'kit' -and -not (Test-Path -LiteralPath $kit)) { continue }
        Write-Output ('  {0,-9} {1}' -f $c.Key, $c.Value[2])
    }
    Write-Output '  Every writing command accepts -WhatIf.'
    exit $(if ($Command -in 'help', '-h', '--help', '/?') { 0 } else { 2 })
}

$fn = $commands[$Command][0]
if (-not (Get-Command $fn -ErrorAction SilentlyContinue)) { Write-Output "'$Command' is a kit command; run it from your SuperWorkspace clone."; exit 2 }
& $fn @Arguments
if ($Command -in 'validate', 'doctor', 'global') { exit $LASTEXITCODE }
