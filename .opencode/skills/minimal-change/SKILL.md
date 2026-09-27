---
name: minimal-change
description: Choose a reuse-first, narrowly scoped implementation for an approved change.
---

# Minimal change

Use when choosing or implementing a bounded fix or feature.
All paths below are repository-root relative.
`AGENTS.md` is canonical; use `.sw/workspace.md` for workspace ownership.
This skill supplies an implementation method, not additional scope.

## Choose the smallest rung

Stop at the first rung that holds: does this need to exist at all (skip
speculative work)? Does an existing project helper or contract cover it? Does
the platform or standard library cover it? Does an already-used
dependency cover it? Can it be one line? Only then write the minimum new code.

- Fix a reported symptom at its shared root cause, not at one call site.
- Prefer deleting code to adding it.
- Mark a knowing shortcut with a `ponytail:` comment naming its ceiling and
  upgrade trigger.
- Leave one small runnable check behind for non-trivial logic.
- Never simplify away validation, data-loss handling, security, or accessibility.

Adapted from Ponytail (MIT), https://github.com/DietrichGebert/ponytail.

## Find the existing route

1. Trace the behavior from its caller to its state owner and presentation.
2. Search for a working sibling implementation and reusable project contracts.
3. Identify the smallest seam that can satisfy the approved acceptance criteria.
4. Prefer configuring existing data, then extending an existing abstraction,
   before introducing a new abstraction or subsystem.
5. Explain a new component only when existing responsibilities cannot hold it cleanly.

## Make the bounded change

- Match nearby naming, idioms, and error-handling conventions.
- Keep state rules with their owner and presentation in its existing layer.
- Preserve existing public contracts and the behavior other code relies on.
- Check object lifetime, ownership, and concurrency where relevant.
- Prefer events or cached updates over new per-frame work or world scans.
- Preserve asset references and defaults unless their change is required.
- Keep generated files, plugins, and third-party assets within `AGENTS.md` limits.
- Avoid unrelated formatting, cleanup, speculative generality, and duplicate state.
- If the small edit exposes a larger required change, explain and resolve scope first.

## Finish

Review the diff against the acceptance criteria and remove accidental churn.
Run applicable validation under `AGENTS.md`, with evidence tied to this worktree.
Add regression coverage when it verifies a meaningful failure or boundary.
Report changed behavior, exact checks, and remaining limitations concisely.
Preserve concurrent work and leave changes uncommitted unless requested.
