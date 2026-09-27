---
description: Read-only status of branches, project state, tasks, and validation
agent: project-review
subagent: true
---

Produce a concise project status report without modifying files: $ARGUMENTS

1. Read the startup section of the project state file named in `AGENTS.md`.
2. Use `git status --short --branch`, `git log --oneline -10`,
   `git rev-parse HEAD`, and `git rev-parse origin/main` to separate local
   commits, uncommitted work, and the last-fetched `main`. Without independent
   remote confirmation, publication status is unknown.
3. List active tasks under `.sw/comms/tasks/` with their latest event state.

Report: current authorized work and its state, branch/HEAD/local changes and
publication status, active tasks and blockers, last known validation (labeled
historical), and the next authorized step or why work is blocked. Never invent
dates, tests, or features; call out ambiguity instead of guessing.
