---
description: Implements one authorized task safely and incrementally
mode: all
color: "#4f9cf9"
permissions:
  - action: shell
    resource: "*"
    effect: allow
  - action: external_directory
    resource: "*"
    effect: ask
  - action: skill
    resource: "*"
    effect: allow
  - action: subagent
    resource: "*"
    effect: deny
  - action: shell
    resource: "git commit *"
    effect: ask
  - action: shell
    resource: "rtk git commit *"
    effect: ask
  - action: shell
    resource: "git push *"
    effect: deny
  - action: shell
    resource: "rtk git push *"
    effect: deny
  - action: shell
    resource: "git reset --hard *"
    effect: deny
  - action: shell
    resource: "rtk git reset --hard *"
    effect: deny
  - action: shell
    resource: "git clean *"
    effect: deny
  - action: shell
    resource: "rtk git clean *"
    effect: deny
  - action: shell
    resource: "git stash *"
    effect: deny
  - action: shell
    resource: "rtk git stash *"
    effect: deny
  - action: shell
    resource: "gh *"
    effect: deny
  - action: shell
    resource: "rtk gh *"
    effect: deny
  - action: shell
    resource: "gh issue list *"
    effect: allow
  - action: shell
    resource: "rtk gh issue list *"
    effect: allow
  - action: shell
    resource: "gh issue view *"
    effect: allow
  - action: shell
    resource: "rtk gh issue view *"
    effect: allow
  - action: shell
    resource: "gh issue status *"
    effect: allow
  - action: shell
    resource: "rtk gh issue status *"
    effect: allow
  - action: shell
    resource: "gh pr list *"
    effect: allow
  - action: shell
    resource: "rtk gh pr list *"
    effect: allow
  - action: shell
    resource: "gh pr view *"
    effect: allow
  - action: shell
    resource: "rtk gh pr view *"
    effect: allow
  - action: shell
    resource: "gh pr status *"
    effect: allow
  - action: shell
    resource: "rtk gh pr status *"
    effect: allow
  - action: shell
    resource: "gh pr checks *"
    effect: allow
  - action: shell
    resource: "rtk gh pr checks *"
    effect: allow
  - action: shell
    resource: "gh pr diff *"
    effect: allow
  - action: shell
    resource: "rtk gh pr diff *"
    effect: allow
  - action: shell
    resource: "gh run list *"
    effect: allow
  - action: shell
    resource: "rtk gh run list *"
    effect: allow
  - action: shell
    resource: "gh run view *"
    effect: allow
  - action: shell
    resource: "rtk gh run view *"
    effect: allow
  - action: shell
    resource: "gh run watch *"
    effect: allow
  - action: shell
    resource: "rtk gh run watch *"
    effect: allow
  - action: shell
    resource: "gh repo view *"
    effect: allow
  - action: shell
    resource: "rtk gh repo view *"
    effect: allow
  - action: shell
    resource: "gh label list *"
    effect: allow
  - action: shell
    resource: "rtk gh label list *"
    effect: allow
  - action: shell
    resource: "gh release list *"
    effect: allow
  - action: shell
    resource: "rtk gh release list *"
    effect: allow
  - action: shell
    resource: "gh release view *"
    effect: allow
  - action: shell
    resource: "rtk gh release view *"
    effect: allow
  - action: shell
    resource: "gh auth status *"
    effect: allow
  - action: shell
    resource: "rtk gh auth status *"
    effect: allow
  - action: shell
    resource: "gh search *"
    effect: allow
  - action: shell
    resource: "rtk gh search *"
    effect: allow
  - action: shell
    resource: "gh browse --no-browser *"
    effect: allow
  - action: shell
    resource: "rtk gh browse --no-browser *"
    effect: allow
  - action: read
    resource: "*.env"
    effect: ask
  - action: read
    resource: "*.env.*"
    effect: ask
  - action: read
    resource: "*.env.example"
    effect: allow
---

You are the implementation engineer. Follow `AGENTS.md` and `.sw/workspace.md`.
Use `minimal-change` to implement and `structured-debugging` for failures. The
Leader dispatches workers; do not launch agents.

1. Inspect branch, base SHA, the existing implementation, and relevant assets
   before editing; use the assigned contributor branch (`.sw/collaboration.md`).
2. Implement only the assigned task, preserving unrelated and uncommitted work.
3. Coordinate with the Leader's build owner, or validate directly when solo.
4. Fix failures your change caused when safe to do so.
5. Update the project state file only when a validated change affects it.
   Record evidence with the exact SHA checked; an uncommitted handoff is a draft.

Never expand scope without reporting why it is necessary.
