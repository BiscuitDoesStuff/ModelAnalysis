# ModelAnalysis agent instructions

## Project identity

ModelAnalysis takes local, on-use snapshots of LLM catalogs, free routes, prices and benchmark evidence into Markdown, Excel, JSON, an offline dashboard and a static site. Implemented state lives in `docs/PLAN.md` (handoff section first, then phase Status notes), dated evidence in `docs/run-notes.md`, execution history in the latest events under `.sw/comms/tasks/<task-id>/`, and published truth in Git (`main` baseline, owner's `biscuit-worktree`). Currently authorized: the Phase 6 post-quota-window live pair plus fixture recording (owner-approved, procedure in the latest `phase6-measure-first` event and PLAN steps 4/7), and the standing owner items in the PLAN handoff (steps 4, R, 8). Phase 7 and anything beyond are roadmap order, not approval.

## Architecture invariants

Owned by this project. Rules an agent must never break:
- `source_health`/`website_health` flow analyze → history overlay → pipeline → reports untouched; renderers never reinterpret missing evidence (unknown is not zero) and replay never touches the network.
- One shared report renderer (`build_report.reliability_tables` + `reports/ui.py`) feeds the dashboard and the site; new tables/pages must use `ui.*` or `validate_bundle` fails the run.
- Retrieval measures without changing behaviour: same requests, retries, completeness and cached `fetched_at`; quota readings come only from existing account calls, never invented.
- No mutable module state in retrieval; explicit per-invocation contexts. Offline experiments use fixtures, `tools/golden_bundle.py` or temp state dirs — never the real `runs/` or history database.
- Agents never commit, push, or run `run.ps1` (quota spend + real history writes); the owner approves and publishes.

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
