---
name: project-planning
description: Clarify an assigned task and decompose it into bounded work with acceptance criteria and dependencies.
---

# Project planning

Use for requirements or decomposition work, not as a mandatory task preamble.
All paths below are repository-root relative.
Follow `AGENTS.md` as canonical policy and `.sw/workspace.md` for
workspace orchestration; consult `.sw/collaboration.md` for task records.

## Establish the task

1. Read the required startup context and inspect the relevant implementation.
2. State the requested outcome, observed baseline, and acceptance criteria.
3. Separate confirmed requirements from assumptions and open questions.
4. Confirm authorization in the project state file; a roadmap is not approval.
5. Ask only questions that affect scope, ownership, or a consequential decision.
   Continue independent inspection while awaiting answers when useful.

## Decompose deliberately

- Prefer the smallest independently verifiable steps that deliver the outcome.
- For each step name its result, dependencies, file owners, and validation.
- Identify shared files and binary assets before proposing concurrent work.
- Reuse existing systems; include migration or compatibility work only if needed.
- Mark blocked dependencies explicitly rather than assuming another task shipped.
- Delegation requires an explicit assignment and the workspace workflow.
- Keep speculative follow-ups outside the approved implementation scope.

## Deliver the plan

Return a concise ordered plan with decisions needed and completion evidence.
In Plan mode, keep planning read-only and in the response; write a plan file
only when explicitly requested and permitted by the active mode.
When authorized to persist execution details, use the existing task record
under `.sw/comms/tasks/<task-id>/`; avoid a second planning ledger.
A plan does not itself authorize work, branch changes, or implementation.
