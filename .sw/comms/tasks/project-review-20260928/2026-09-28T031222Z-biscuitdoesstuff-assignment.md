# project-review-20260928 - assignment - 2026-09-28T031222Z - biscuitdoesstuff

- **Author / audience:** Project Leader for the owner; implementation of the approved review fixes.
- **Approval:** Owner approved the plan in chat 2026-09-28 (~03:05 UTC): C1 fix + test, H1 PLAN text; C2, C3, C4/H3 deferred. Tier: Execution Light, inline by the Leader.
- **Scope / acceptance:** C1: Vals href → model match is exact key first, else the longest allowlisted slug contained in the key; empty keys match nothing; one regression test that fails on the old code. H1: PLAN test count, "Current work" heading, known-issue line for the two LLM Stats 404 pages. Excluded: negative caching, fetched_at stamping, parse-retry changes, any live run.
- **Status:** in_progress (implemented + validated locally; awaiting owner commit/push and CI).
- **Branch / base:** biscuit-worktree @ `ccfc6f8`; `origin/main` @ `8466483`.
- **Checked revision / changed:** `ccfc6f8` plus uncommitted: `retrieval/fetch_websites.py` (match rule, 3 lines), `tests/test_retrieval.py` (`test_vals_pages_match_exact_or_longest_model_key`), `docs/PLAN.md` (H1).
- **Owners / dependencies:** Owner: commit + push. Leader: CI check, close task.
- **Decisions / remaining:** Deferred with reasons: C4/H3 saves 2 keyless requests/run and health would stay `partial` anyway; C2 display-only and conservative; C3 unobserved — revisit if LLM Stats quota shows unexplained spend. Live effect of C1 appears on the owner's next ordinary run.
- **Validation:** Leader, 2026-09-28 ~03:10 UTC: new test run on old code → FAILED (all three hrefs mapped to `claudeopus5`, last one `/models/`); after fix `python -B -m unittest discover -s tests -p "test_*.py"` → 136 OK; `python -B tools/ci.py` → `CI checks passed` (golden + recorded replay/audit); `git diff --check` clean; `sw.ps1 validate` reported in chat.
- **Not validated / risks:** Ruff (CI-only); no live run (not needed: logic covered offline).
- **Publication:** local-only until a human pushes
- **Next action:** Owner commits the listed paths + this task folder and pushes; Leader verifies CI + sw-validate, then `sw comms close -Task project-review-20260928`.
