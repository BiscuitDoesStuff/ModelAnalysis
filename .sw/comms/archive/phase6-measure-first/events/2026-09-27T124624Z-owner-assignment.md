# phase6-measure-first - assignment - 2026-09-27T124624Z - owner

- **Author / audience:** Project Leader for the project owner; implementation and review agents.
- **Approval:** Owner requested roadmap continuation, approved the measurement-first plan in chat, and selected "Move to solo main" after the new workspace branch-policy conflict was reported.
- **Scope / acceptance:** Measurement-only shared HTTP client, explicit invocation/source contexts, per-source and per-host request/body-byte/time/retry metrics, cache hits, numeric LLM Stats quota before/after, and an accessible Retrieval table. Preserve current request/retry behavior, completeness, evidence timestamps, and network-free replay. Offline regression tests and full CI/lint must pass. No optimizations until a separately approved live baseline.
- **Status:** in_progress; startup reconciled, implementation next.
- **Branch / base:** main created from 3507b7d9713d5e516abda3c589f88be9f0c7317d, preserving the existing biscuit branch. No published main exists. Origin advertises biscuit at c8b56815926ef0ba2a97d4efc7a5d01721b3dd89.
- **Checked revision / changed:** 3507b7d9713d5e516abda3c589f88be9f0c7317d; clean before this record.
- **Owners / dependencies:** Developer owns retrieval code, scoped report integration and tests; Leader owns task records and roadmap/docs updates. Developer is the sole validation owner during implementation. No binary assets. Live baseline depends on explicit owner approval and available quota.
- **Decisions / remaining:** Missing historical metrics mean unknown, not zero. Replay retains original fetch measurements, not new network activity. Existing LLM Stats account calls supply quota measurements; no extra calls. No agent commits or pushes. Steps 4, R and 8 remain independent. Review follows passing offline checks.
- **Validation:** Leader: git status/log inspected; git pull origin biscuit succeeded (up-to-date); git ls-remote --heads origin showed only biscuit; git switch -c main succeeded. A timestamp command used unsupported PowerShell 5.1 Get-Date -AsUTC, then was corrected to [DateTime]::UtcNow; no repository effect.
- **Not validated / risks:** Code tests not yet run. New HTTP module must not shadow stdlib http in direct-script invocation. No live retrieval authorized.
- **Publication:** local-only. Human publishes main when ready; existing remote biscuit unchanged.
- **Next action:** Developer implements measurement increment and runs targeted checks, python -B tools/ci.py, and ruff check --select F401,F811,F821,F841 .; Leader reviews and requests live baseline approval only after offline acceptance.
