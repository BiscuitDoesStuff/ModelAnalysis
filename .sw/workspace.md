# Agent workspace

Installed and updated by the SuperWorkspace kit;
files listed in `.sw/manifest.json` are kit-managed (edit them upstream, or
accept that `sw update` will skip your modified copy). OpenCode is the shared
harness: new sessions default to `project-leader`. Use `/work <task>`,
`/resume <task-id>`, `/review`, `/status`, `/validate`, `/workspace-check`,
`/handoff`, and `/inbox`. In these docs `sw <command>` means
`pwsh -NoProfile -File .sw/sw.ps1 <command>` (kit-only commands such as
`update` run from the SuperWorkspace clone).

## Canonical sources

Each rule has one owning source; everything else links to it.

| Source | Owns |
| --- | --- |
| `AGENTS.md` | Project identity and invariants (project-owned), core policy and profile rules (kit-managed blocks) |
| Project state file named in `AGENTS.md` | Implemented state and what work is authorized |
| This file | Roles, approved-plan execution, permissions, tiers, verification |
| `.sw/collaboration.md` | Task records, messages, branches, publication, integration |
| `.sw/config.json` | Profile, GitHub tier, contributors, startup budget |
| `opencode.jsonc`, `.opencode/{agents,commands,skills,plugins}` | Actual shared configuration; inspect these and runtime discovery before asserting behavior |
| Git and `.sw/comms/tasks/` | Ancestry, publication, and approved work; not a second memory ledger |
| `.sw/onboarding.md` | New contributor setup |

Keep required startup reading small: this map is read on demand.

## Roles

| ID | Mode | Tier | Responsibility |
| --- | --- | --- | --- |
| project-leader | primary | session | Approved outcome, direct dispatch, queue, completion |
| project-plan | all | reasoning | Read-only requirements, alternatives, acceptance criteria |
| project-architect | all | reasoning | Read-only architecture and work breakdown |
| project-developer | all | standard | Authorized implementation; may work solo |
| project-worker | subagent | standard | Leader-dispatched parallel work in an assigned worktree |
| project-build | all | standard | Tooling and coordinated validation |
| project-documentation | all | standard | Markdown, factual docs, skills, task records |
| project-research | all | reasoning | Primary-source research, cited Markdown findings |
| project-review | all | reasoning | Read-only correctness, scope, simplicity findings |
| explore (built-in) | subagent | fast | Focused discovery |

The Leader dispatches directly; workers never launch teams. Built-in `build`
may dispatch the specialists plus `general` and `explore` when a user selects
it; that is not permission for recursive delegation.

## Approved-plan execution

Approval covers the agreed outcome, dispatch, routine commands, validation, and
corrections caused by the work. Continue without asking at each step. Review in
a plan runs automatically but stays advisory. Approval never grants
publication, unrelated installs, new branch types, or unapproved scope.

Stop for a material scope change or a real blocker (credentials, tools,
conflicting work, a consequential decision). After three failed attempts at one
issue, continue only with new evidence. On provider quota or rate-limit errors
(429, session or weekly limits): stop spawning or resuming workers, write the
current state to the task record, and report. Do not retry into the limit.

### Assignment and result contract

Every assignment names task ID, approval, exact branch/checkout, owners and
allowed paths/assets, dependencies, acceptance, preservation rules, and the
validation owner. A correction includes the failing command and evidence. Every
result names changed paths, checked SHA plus dirty scope, actual commands and
results, remaining criteria, and next action.

Independent reads may run concurrently. Writers in one checkout are serialized
unless ownership is explicitly disjoint. Child sessions do not isolate files. A
worktree uses an existing assigned contributor branch; Git cannot check out one
branch twice, so coordinate instead of bypassing it. Every binary asset has one
named owner. Turn off OpenCode automatic worktrees (Desktop: default environment
= Local directory); they create detached branches outside this policy. Claude:
leave the desktop worktree option off, and do not use `isolation: worktree`.

One validation owner per checkout. Reuse evidence until changes invalidate it.
Targeted checks before full suites; small corrections inline rather than a new
subagent. On Windows without `pwsh`, the OpenCode shell is Windows PowerShell
5.1, which rejects `&&`/`||`: use separate calls or `;` with
`if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }`.

## Permissions and portability

Execution roles have host-user shell authority, **not a sandbox**; pattern rules
cannot recognize every shell spelling. Three words describe every rule:
*enforced* (tool lists and file-tool rules the harness applies), *guardrail*
(shell pattern rules, which stop the command as written and nothing else;
`git -C . push`, `bash -c`, aliases and absolute paths get past them), and
*stated* (role text the model is asked to follow). Never bypass a denied action with another
tool, shell form, or child. Read-only roles inspect only. Documentation edits
Markdown only. `*.env` read prompts cover direct reads; never grep or print
secret files to get around them.

| Rule | OpenCode (agent frontmatter) | Claude adapter |
| --- | --- | --- |
| Read-only roles: no edits | enforced | enforced (no Edit or Write tool) |
| Read-only roles: shell limited to listed git reads | enforced (read forms of `status`, `diff`, `log`, `show`; `--output`, `--ext-diff`, `--textconv` denied) | stated (Bash is available; only session-wide denies apply) |
| Documentation: edit `*.md` only | enforced | stated |
| `git push`, `reset --hard`, `clean`, `stash` denied | guardrail | guardrail |
| `.env` reads prompt | enforced (ask) | guardrail (Read tool only; shell reads are not covered) |
| Non-leader roles: no subagent launch | enforced | enforced (`disallowedTools: Agent`) |

OpenCode applies only each agent's own frontmatter rules; desktop 2.0.17 and
2.0.18 ignore the project-level list in `opencode.jsonc`. So `sw update`
writes the session rules (base denies and asks, profile edit denies, GitHub
tier, `.env` asks) at the head of every kit agent's `permissions`, and the
role's own rules follow (last match wins). OpenCode's built-in agents other
than Build carry no kit rules; Build gets them only from `opencode.jsonc`
(`agents.build`). The RTK plugin rewrites shell commands before OpenCode's
permission check, so the kit renders an `rtk ` twin after every shell rule;
another plugin that rewrites commands would bypass the rules the same way.
Claude settings rules are session-wide, so per-role limits
there are stated only. The solo ruleset on `main` (`.sw/collaboration.md`)
stops force pushes and branch deletion, not ordinary pushes.

Sandboxes are documented, never configured: Claude users on macOS, Linux or
WSL2 may enable `/sandbox` locally; Codex users get one by default and on
native Windows choose its mode themselves; OpenCode has none. Sandbox settings
are machine-specific, so the kit never writes them.

GitHub access follows `githubTier` in `.sw/config.json`, as guardrails in
every kit agent (run `sw update` after a change); the Claude adapter's list
is a denylist, so unknown verbs, aliases and extensions fall to Claude's
default mode:

| Tier | Agents may |
| --- | --- |
| 0 (default) | Read only: issue/pr/run/repo/label/release list, view, status, checks, diff |
| 1 | Tier 0 plus `gh issue create/edit/comment`, `gh pr comment/edit`, and `gh pr create --draft ...` (the `--draft` flag must come first) |

At every tier agents never push, merge, publish releases, or change repo
settings. Humans push branches and merge.

No shared model/provider pins, credentials, shell paths, or absolute paths are
committed; `sw validate` enforces this. Each contributor's tier map lives in the
git-ignored `.opencode/opencode.jsonc` (`sw tiers`). Users supply provider access.
A Claude subscription is not OpenCode API access.

## Model tiers

Single source for role-to-tier membership (the table above): reasoning =
project-plan, project-architect, project-research, project-review; standard =
project-developer, project-worker, project-build, project-documentation; fast =
explore; the Leader inherits the session model. Default cost policy is
free-first: free OpenCode/OpenRouter models and local LM Studio, no metered API
spend unless a contributor opts in locally. To pick free models per tier, follow
the `free-models` skill's procedure; the kit ships no model IDs or tier fits.
Local models with small context windows must override `compaction` locally.

## Usage optimization

- Startup budget: `AGENTS.md` + role body + skill names/descriptions (the Leader
  also counts the other agents' descriptions), capped per role by `sw validate`
  (`startupBudgetBytes` in `.sw/config.json`); tokens are a bytes/4 estimate.
- Skills and docs load on demand; do not re-read `AGENTS.md`.
- RTK rewrites shell output through `.opencode/plugins/rtk.ts` (fails open).
- context7 MCP for library docs instead of web search; it receives your queries,
  so send no secrets or private source. It is the one third-party remote MCP
  server the kit ships; add only MCP servers you trust.
- Resume from task records, not chat summaries; batch independent calls.
- Subagents pay a cold start; the Leader does small work inline.

## Claude adapter (opt-in, local)

`sw claude enable` generates a git-ignored `.claude/` from these sources:
pointer agents and commands, copied skills, permission rules for the GitHub
tier, and a SessionStart hook that makes the main session the Leader.
`sw update` regenerates it when `.claude/.sw-generated` exists; otherwise run
`sw claude enable`. `sw validate` reports drift. Never hand-edit generated
files; edit the `.opencode/` source instead. Claude applies instruction edits
and `update` output only after `/clear`, `/compact` or a restart. Keep one
model per session in every harness: switching mid-session breaks the prompt
cache.

## Verification ladder

Record each level separately; a lower level never proves a higher one.

1. Static contract: `sw validate` and `git diff --check`.
2. Runtime discovery: the OpenCode CLI `api` against `/api/agent`,
   `/api/command`, `/api/skill` with an explicit
   `?location%5Bdirectory%5D=<encoded-repo-path>` (omitting it reads home config).
   The first request for a new directory can return an empty command list
   while discovery warms up; repeat it before reporting a failure.
3. Permission API evaluation: expected decisions, not executed denials.
4. Controlled workflow: a harmless approved dispatch, skill load, and
   fresh-session resume, only when available and in scope.
5. Independent read-only review.

Missing runtime, second-user, or interactive evidence is reported as not run.
Never execute destructive commands to prove a denial.
