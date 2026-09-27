---
description: Run the profile builds, tests, and diff checks for the current change
agent: project-build
subagent: false
---

Validate the current worktree without changing scope: $ARGUMENTS

1. Inspect `git status --short --branch` and classify the changed scope.
2. Workspace/docs-only: run `pwsh -NoProfile -File .sw/sw.ps1 validate` and
   `git diff --check`; say builds were not run.
3. Code: follow the validation order in the `AGENTS.md` profile section and
   load the profile's validation skill. Run only existing tests; never invent one.
4. Check new and untracked files for trailing whitespace; `git diff --check`
   does not cover them.
5. Fix failures caused by the current change only when in scope.

Report separately: build, automated tests with exact outcomes, manual checks or
`not available`, diff check, exact branch and SHA (uncommitted is not
published), checks impossible here, and remaining warnings.
