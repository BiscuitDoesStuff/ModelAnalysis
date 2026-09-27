---
name: task-handoff
description: Record or resume an approved task in its existing collaboration record with ownership, dependencies, and exact evidence.
---

# Task handoff

Use when an assigned task needs durable execution tracking, resumption, or handoff.
All paths below are repository-root relative.
Follow canonical `AGENTS.md`, `.sw/workspace.md`, and
`.sw/collaboration.md` (record fields and states).

## Keep one execution record location

Use the existing `.sw/comms/tasks/<task-id>/` directory.
Find the assignment and latest execution event before writing anything.
Follow unique UTC timestamp/contributor/event naming; never edit another author's record.
Keep execution details there rather than creating a parallel memory or TODO ledger.
If no task ID or approved scope exists, resolve that assignment before recording progress.

## Record the execution state

- Approved outcome, scope boundaries, acceptance criteria, contributor, and audience.
- Assigned branch/worktree and full published base SHA, with any later baseline merges.
- Overall and work-item state: `pending`, `in_progress`, `complete`, or `blocked`.
- Dependencies by task or item, their observed state, and what unblocks each item.
- Named file owners, including explicit ownership of every touched binary asset.
- Completed changes, remaining steps, consequential decisions, and known blockers.
- Exact checked SHA or an explicit uncommitted draft and its affected paths.
- Validation runner, timestamp, commands, results, evidence paths, and unverified checks.
- A concrete resume action, its owner, and the evidence needed to call it complete.
- Write the record so it stands without the session transcript; harness transcripts expire.

## Resume or transfer

Recheck Git and actual files before trusting recorded state; identify intervening work.
Treat `complete` as supported by acceptance evidence, not as proof of publication.
Keep local, published, received, built, and manually checked states distinct.
Mark unmet dependencies `blocked`; retain the last useful evidence and next action.
Append the appropriate event for changed facts without duplicating a full history.
Never guess a future commit SHA, publish as an agent, or require optional peer review.
In the response, link the record and summarize the next action and outstanding evidence.
