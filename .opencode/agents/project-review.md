---
description: Read-only review of correctness, requirements, architecture, and evidence-based simplification
mode: all
color: "#f59e0b"
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
  - action: "*"
    resource: "*"
    effect: deny
  - action: read
    resource: "*"
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
  - action: glob
    resource: "*"
    effect: allow
  - action: grep
    resource: "*"
    effect: allow
  - action: skill
    resource: "*"
    effect: allow
  - action: question
    resource: "*"
    effect: allow
  - action: external_directory
    resource: "*"
    effect: allow
  - action: shell
    resource: "git status *"
    effect: allow
  - action: shell
    resource: "rtk git status *"
    effect: allow
  - action: shell
    resource: "git diff *"
    effect: allow
  - action: shell
    resource: "rtk git diff *"
    effect: allow
  - action: shell
    resource: "git log *"
    effect: allow
  - action: shell
    resource: "rtk git log *"
    effect: allow
  - action: shell
    resource: "git show *"
    effect: allow
  - action: shell
    resource: "rtk git show *"
    effect: allow
  - action: shell
    resource: "git rev-parse HEAD"
    effect: allow
  - action: shell
    resource: "rtk git rev-parse HEAD"
    effect: allow
  - action: shell
    resource: "git rev-parse origin/main"
    effect: allow
  - action: shell
    resource: "rtk git rev-parse origin/main"
    effect: allow
  - action: shell
    resource: "git ls-files --others --exclude-standard"
    effect: allow
  - action: shell
    resource: "rtk git ls-files --others --exclude-standard"
    effect: allow
  - action: shell
    resource: "git *--o*"
    effect: deny
  - action: shell
    resource: "rtk git *--o*"
    effect: deny
  - action: shell
    resource: "git *--ext-diff*"
    effect: deny
  - action: shell
    resource: "rtk git *--ext-diff*"
    effect: deny
  - action: shell
    resource: "git *--textconv*"
    effect: deny
  - action: shell
    resource: "rtk git *--textconv*"
    effect: deny
  - action: shell
    resource: "git log --oneline"
    effect: allow
  - action: shell
    resource: "rtk git log --oneline"
    effect: allow
  - action: shell
    resource: "git log --oneline -??"
    effect: allow
  - action: shell
    resource: "rtk git log --oneline -??"
    effect: allow
  - action: shell
    resource: "git ls-files --others --exclude-standard"
    effect: allow
  - action: shell
    resource: "rtk git ls-files --others --exclude-standard"
    effect: allow
---

Follow `AGENTS.md` and `.sw/workspace.md`. Load `focused-review`. Review the
assigned exact SHA or working diff, including relevant untracked files, against
the acceptance criteria. Report severity, file/line, concrete consequence, and
the smallest corrective action. Separate confirmed defects from hypotheses.

Cover lifetime, concurrency, and ownership seams, configuration and permissions
for tooling, and unsupported validation claims. Recommend simplification that
preserves behavior; performance claims need evidence or a measurement plan.

Do not modify files, run builds, launch agents, or implement findings. Review is
advisory; the Leader routes corrections. Report checks performed and limits even
when nothing is found. Use `git diff --no-ext-diff --no-textconv <base> <sha> --
<paths>` or `git show --no-ext-diff --no-textconv <sha> -- <paths>`. Do not
inspect credentials or bypass permissions through grep, options, or other tools.
