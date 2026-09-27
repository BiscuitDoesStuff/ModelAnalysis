---
name: focused-review
description: Perform an optional read-only review of assigned changes for correctness, specification fit, and unnecessary complexity.
---

# Focused review

Use when review is requested for an explicit diff or exact task SHA.
All paths below are repository-root relative.
`AGENTS.md` is canonical; follow `.sw/workspace.md` and
`.sw/collaboration.md` for review boundaries and evidence.

## Establish the target

1. Read startup context, approved scope, acceptance criteria, and relevant task records.
2. Identify the exact reviewed SHA and base, or name the uncommitted files reviewed.
3. Inspect the diff and surrounding implementation, including important callers.
4. Check whether supplied validation actually applies to this revision and scope.
5. Keep review read-only: report findings rather than editing files or creating records.

## Review in priority order

- Correctness: failures, regressions, invalid state, ownership, and missing boundaries.
- Specification: missing acceptance behavior or additions outside approved scope.
- Platform safety: lifetime, ownership, concurrency, authority, and asset references.
- Simplicity: duplicated rules, avoidable abstraction, or work in the wrong layer.
- Validation: meaningful uncovered failure paths or unsupported verification claims.
- Tie each finding to evidence and an affected path; avoid speculative issue lists.
- Distinguish a defect from an optional preference and prioritize by actual impact.
- Read logs or existing results without launching builds or editors that mutate state.
  Request coordinated validation separately when evidence is insufficient.

## Return findings

Lead with actionable findings, ordered by severity, with file/line references.
For each, explain the failing condition, consequence, and a bounded correction direction.
List material assumptions, questions, and validation gaps separately from defects.
If no actionable findings were found, say so and state the review coverage limits.
Distinguish directly observed evidence from author-reported checks.
Review is advisory; it neither authorizes scope nor proves integration readiness.
