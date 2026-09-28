# phase6-measure-first - progress - 2026-09-27T145200Z - owner

- **Author / audience:** Project Leader for the owner; next execution session (post-00:00-UTC).
- **Approval:** Owner chose option (a): the step-7 two-run before/after pair after 00:00 UTC, doubling as owner step 4 (recorded fixture). Approved 2026-09-27 ~14:52 UTC. Quota resets 00:00 UTC 2026-09-28 (~9 h away); no runs until then — a run now would repeat the llmstats refusal and pointlessly write runs/history.
- **Scope / acceptance:** Two consecutive live runs a few minutes apart on the current draft (measure-first + A + B), then record_fixture.py on the second bundle iff complete coverage. Success = second run shows 304 revalidation (not_modified > 0, reduced body bytes) with identical completeness; recorder writes tests/fixtures with secret scan clean; CI shows recorded replay + recorded provenance audit green.
- **Status:** in_progress; blocked on quota window (00:00 UTC), otherwise ready.
- **Branch / base:** main over 3507b7d9713d5e516abda3c589f88be9f0c7317d; uncommitted draft unchanged since 143917Z validation (135 tests, CI + ruff + diff-check green).
- **Owners / dependencies:** Leader runs the pair + recorder when the owner gives the post-midnight go-ahead (or the owner runs the commands themselves). No binary assets.
- **Decisions / remaining:** Procedure for the window (PowerShell, Windows User-scope key injection first, per PLAN local-environment note):
  1. `powershell -NoProfile -File run.ps1` → expect `Published <run1> (complete coverage)`; if llmstats still refused, record and stop (do not debug further).
  2. A few minutes later, `powershell -NoProfile -File run.ps1` again → expect complete coverage; extract both Retrieval tables and compare (requests, bytes, not_modified, cache_hits).
  3. `python -B tests/smoke.py`, `python tools/audit_provenance.py "runs/<bundle2>"`, `python tools/record_fixture.py` per PLAN Step 4.
  4. If recorder succeeds: owner runs pre-push `python -B tools/ci.py` + ruff gate, then commits `tests/fixtures` and publishes; Leader checks CI `recorded replay` / `recorded provenance audit` jobs green.
  5. Record both runs + comparison in docs/run-notes.md; close Phase 6.
- **Validation:** None new this event (no code changes; 143917Z evidence stands).
- **Not validated / risks:** Same as 143917Z, plus: second-run savings depend on providers sending ETag/Last-Modified (if none do, not_modified stays 0 with bytes unchanged — a valid measured result, not a failure); complete coverage needs llmstats quota sufficient for ~19 data responses.
- **Publication:** local-only; no agent commit/push.
- **Next action:** Owner pings after 00:00 UTC (or runs the procedure and pastes Published/smoke/audit/recorder output). Leader then executes steps 1–5.
