# phase6-measure-first - progress - 2026-09-27T153500Z - owner

- **Author / audience:** Project Leader for the owner; step-4 push fix + comms convention.
- **Approval:** Owner reported step-4 failure (push rejected), steps 2–3 done; asked to keep task-record-type files on biscuit-worktree only, never main.
- **Scope / acceptance:** Diagnose the rejection, hand the exact fix order, record the comms convention. No pushes/commits by agent.
- **Status:** in_progress; owner executes the fix below.
- **Branch / base:** Owner is on biscuit-worktree at 3507b7d + dirty Phase 6 draft, behind origin/biscuit-worktree (f21f8f1, the content-empty PR #1 merge). origin/main still 3507b7d → step 1 (commit+push main) not yet done; the draft is intact.
- **Owners / dependencies:** Owner runs all git steps. No binary assets.
- **Decisions / remaining:** (1) Rejection cause is history-only lag (empty tree diff), so `git pull --ff-only` is safe despite the dirty tree. Order: sync worktree → switch main → commit+push Phase 6 → back to worktree → merge origin/main → push. (2) Convention agreed: `.sw/comms/` committed on biscuit-worktree only when useful, never on main; upkeep via `sw comms close` on integration. Untracked records ride the working directory across switches until committed, so selective `git add` is the enforcement. PLAN.md records the rule.
- **Validation:** `git diff --check` clean after the PLAN edit. No code changes.
- **Not validated / risks:** Fix unexecuted; post-midnight pair still pending its window.
- **Publication:** local-only; no agent commit/push.
- **Next action:** Owner runs the fix commands (see chat), then the step-1 commit/push.
