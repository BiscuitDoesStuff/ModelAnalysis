---
description: Optional read-only review of local changes or a published SHA
agent: project-review
subagent: true
---

Review $ARGUMENTS. With no target, inspect current uncommitted changes including
untracked files. For a supplied branch or SHA, verify the exact available commit
and review it from the recorded task base; do not fetch or assume a local commit
is published. Gather status, history, and diff with read-only tools. State the
exact reviewed SHA or working tree and the evidence limits.

Check regressions, lifetime and ownership issues, duplication, work in the wrong
layer, needless per-frame or hot-path cost, validation overclaims, and scope
creep. Report findings by severity with file/line references. Separate confirmed
defects from risks and questions. Do not change, stage, commit, or push anything.
