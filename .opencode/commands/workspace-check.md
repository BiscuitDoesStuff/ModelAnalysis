---
description: Check the shared agent workspace contract and report runtime verification limits
agent: project-leader
subagent: false
---

Run `pwsh -NoProfile -File .sw/sw.ps1 validate` from the repository root, then `git diff --check`, and report
exact outcomes. These static checks do not prove runtime enforcement. When
runtime verification is requested, coordinate the verification ladder in
`.sw/workspace.md`: $ARGUMENTS
