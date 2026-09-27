---
name: structured-debugging
description: Investigate a reproducible failure using evidence, explicit hypotheses, and a focused root-cause fix.
---

# Structured debugging

Use for a concrete failure, regression, or unexplained behavior.
All paths below are repository-root relative.
Follow canonical `AGENTS.md` and the coordination rules in `.sw/workspace.md`.

## Establish evidence

1. Record expected behavior, actual behavior, reproduction steps, and frequency.
2. Inspect startup context, the active worktree, and relevant existing changes.
3. Capture the exact failing command or interaction, environment, and useful logs.
4. Distinguish observations, user reports, and assumptions in the investigation.
5. If reproduction is unavailable, describe the gap; do not invent a confirmed cause.

## Narrow the cause

- Trace the failing path through inputs, state ownership, lifetime, and outputs.
- Compare with a working path or known baseline without resetting user work.
- Form a specific hypothesis and predict evidence that would support or reject it.
- Choose the cheapest discriminating check and evaluate one hypothesis at a time.
- Use targeted logging or inspection only when it resolves a real uncertainty.
- Inspect ownership, callbacks, object validity, and configuration defaults as relevant.
- Record rejected hypotheses briefly when they prevent repeated investigation.
- Coordinate shared builds and tool access before attempting reproduction.

## Fix and verify

Apply the smallest authorized root-cause fix after evidence supports it.
Do not bundle speculative repairs or hide a failure with unrelated fallback behavior.
Verify the original reproduction and the affected boundary or regression path.
Run the applicable validation sequence from `AGENTS.md`.
Remove temporary instrumentation you introduced when it is no longer needed.
Report cause, fix, exact checks, and any still-unverified behavior.
If blocked, record the next discriminating check and its owner in the task record.
