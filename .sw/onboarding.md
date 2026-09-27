# Onboarding

For a new contributor joining an existing SuperWorkspace project, on OpenCode
only (Claude Code is an opt-in local adapter; see `.sw/workspace.md`).

## Prerequisites

- git
- PowerShell 7.2+ (`winget install Microsoft.PowerShell`)
- OpenCode Desktop
- Optional: `gh` (GitHub CLI), RTK >= 0.48

## Clone and check

```powershell
git clone <repo-url>
pwsh .sw/sw.ps1 doctor -User <you>
```

`doctor` is read-only: it never installs or changes anything, it only reports
what is missing and the exact command to fix it.

## Model tiers

```powershell
pwsh .sw/sw.ps1 tiers -Reasoning <id> -Standard <id> -Fast <id>
```

Default cost policy is free-first: free OpenCode/OpenRouter models and local
LM Studio, no metered API spend unless you opt in locally. See the
`free-models` skill for dated tier fits.

## OpenCode Desktop setting

Set the default environment to "Local directory". OpenCode Desktop's
automatic-worktree environment creates branches outside this project's
policy, and that cannot be detected by `doctor` or `validate`.

## First session

Open the project in OpenCode. The default agent is `project-leader`. Then:

- `/inbox` - check messages addressed to you
- `/work <task>` - start an approved task
- `/status` - see open work

## Branches and publishing

You work on `<you>/<you>-worktree`, created by the project owner from
published `main`. Agents never push; you publish and merge your own work. See
[collaboration.md](collaboration.md) for task records, messages, and
integration rules.

## Hard rules

- Agents never push.
- Never push to, or work on, another contributor's branch.
- Humans publish and merge; agents only propose.
