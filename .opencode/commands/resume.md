---
description: Reconcile a task record with Git and resume its approved remaining steps
agent: project-leader
subagent: false
---

Resume task: $ARGUMENTS

Load `task-handoff`. Locate the task under `.sw/comms/tasks/` (or its
`SUMMARY.md` under `.sw/comms/archive/`). Verify approved scope, checkout,
ownership, Git diff, dependencies, and preserved validation evidence. Resume
unambiguous approved steps without asking to continue. If no task is named,
find the unique active approved task; ask only when records are ambiguous. A
historical recommendation or draft plan is never approval.
