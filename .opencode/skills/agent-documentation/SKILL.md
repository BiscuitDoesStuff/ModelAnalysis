---
name: agent-documentation
description: Maintain concise agent instructions and documentation while preserving canonical sources and historical evidence.
---

# Agent documentation

Use for an explicitly assigned documentation or agent-instruction change.
All paths below are repository-root relative.
`AGENTS.md` is canonical project policy; `.sw/workspace.md` owns workspace guidance.

## Choose the source

1. Inspect the requested document, its callers or links, and relevant current evidence.
2. Use the project state file named in `AGENTS.md` for implemented state and authorization.
3. Use Git for live branch, commit, publication, and worktree facts.
4. Use the changelog and dated task records for historical evidence.
5. Use `.sw/collaboration.md` for collaboration records.
6. Resolve contradictions explicitly; do not silently promote history to current policy.

## Write for the next task

- Put each rule in its owning source and link to it from commands or skills.
- Prefer short actionable instructions and concrete paths over repeated background.
- Keep required startup reading small; make specialist references read-on-demand.
- Distinguish implemented, authorized, proposed, blocked, and unverified work.
- Preserve dated evidence; add a correction event rather than rewriting another author.
- Update current state only after the corresponding implementation and checks exist.
- Avoid hand-maintained live SHA inventories and duplicate memory or status ledgers.
- Date every volatile fact (`Observed YYYY-MM-DD`) and keep it out of instructions when a procedure can replace it.
- Use original project wording; do not import external instructions or dependencies.
- Describe tool limitations accurately and keep harness details out of product policy.

## Check the result

Check links, paths, frontmatter when present, and consistency with canonical policy.
Check that a new instruction cannot accidentally authorize future work.
Run `git diff --check` and explicit trailing-whitespace checks on new files.
Report exact checks and any unresolved cross-document dependency.
Keep documentation validation distinct from build or interactive evidence.
