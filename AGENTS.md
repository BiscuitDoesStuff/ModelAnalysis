# ModelAnalysis agent instructions

## Project identity

Owned by this project, never overwritten by SuperWorkspace. Replace this with
one paragraph: what ModelAnalysis is, where its implemented state is recorded,
and what work is currently authorized.

## Architecture invariants

Owned by this project. List the rules an agent must never break: single state
owners, one path per concern, and boundaries between layers.

<!-- sw:begin core -->
## Required startup

The harness auto-loads this file; do not re-read it. Before a meaningful change:

1. Read the project state file named in Project identity, startup section only.
2. Run `git status --short --branch` and `git log --oneline -10`; inspect the
   existing implementation relevant to the task before editing.
3. Confirm the work is authorized. A roadmap, backlog, or old record is not
   approval. If Git contradicts recorded state, stop instead of guessing.

## Principles

- Preserve working behavior before adding new behavior.
- Smallest independently testable change; reuse before writing; no unrelated
  refactors or speculative scope. Load `minimal-change` when implementing.
- Never claim a check, manual test, or publication that did not happen.
- No third-party assets, plugins, or dependencies without explicit approval.
- Do not add systems because they seem like the natural next step; new scope
  needs explicit planning and approval.

## Validation

Choose checks by changed scope. Workspace/docs-only work runs
`pwsh -NoProfile -File .sw/sw.ps1 validate` and `git diff --check`. Code work
follows the profile section below. Report exact commands and outcomes, and keep
automated, headless, and manual results separate. Fix failures your change
caused; report others without broad repairs.

## Git

- Only `main` and owner-designated `<user>/<user>-worktree` branches exist
  (solo projects: `main` only); no task, feature, review, sandbox, or automatic
  branches. Never work on another contributor's branch. Unexpected branches
  are reported, never deleted.
- Never discard, reset, stash, clean, or overwrite existing work. Commit only
  when explicitly asked. Agents never push; humans publish their own branch.
- GitHub writes follow the tier in `.sw/config.json` (see `.sw/workspace.md`).
- Stage selected paths only; never `git add .` in a shared checkout.

## Workspace

OpenCode is the shared harness; other harnesses are optional local adapters.
`.sw/workspace.md` owns roles, approved-plan execution, permissions, tiers, and
runtime checks. `.sw/collaboration.md` owns task records, messages, branches,
and integration. Credentials, machine paths, and model choices stay local.
<!-- sw:end core -->

<!-- sw:begin profile -->
## Profile: generic

Validation order for code changes: (1) the project's build or type check,
(2) its automated tests, targeted first, then the suite, (3) manual or
interactive checks only when a real session exists, (4) `git diff --check` and
trailing-whitespace checks on new files. Discover the actual commands from the
repository (README, package manifest, CI workflow) instead of assuming them.
<!-- sw:end profile -->
