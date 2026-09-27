---
name: free-models
description: Procedure for finding, verifying and mapping free models to tiers; each machine verifies against its own provider list.
---

# Free models

Use when choosing free models or effort levels for OpenCode tiers. This is
procedure, not configuration: it holds no provider credentials, no config
blocks, and no model IDs, prices, endpoints or effort levels. Those change
within days; read them from the machine and the provider, never from memory
or an old note.

## Find and verify

1. List what this machine can use: `opencode models --verbose` (or `/models`
   in a session). Only IDs listed there are candidates.
2. Confirm each candidate is free today from the provider's own list, not by
   name: a zero prompt and completion price or a `:free` ID on OpenRouter; a
   `*-free` route on the OpenCode Zen pricing page. Routers are not models.
3. Read each candidate's data-use terms on the provider page. Some free
   endpoints log prompts or train on them; get explicit user consent before
   routing real work to one.
4. Read the effort levels (variants) the client exposes for that exact ID.
   Configure only levels observed there; a level named in vendor docs may be
   rejected on a free tier.
5. Match IDs character-for-character, including `-free` suffixes.

## Hard constraints

- Never configure a rejected level to chase a headline benchmark figure;
  unreachable scores are not a configuration problem.
- Never override sampling values a model locks in thinking mode.
- Free endpoints may silently ignore effort settings server-side. If a
  variant change alters neither behavior nor response length, the server
  is locking the level; do not "fix" this in config.
- Treat free-endpoint flakiness (refused tool use, bare provider errors,
  mid-run failures) as normal: retry once, then route around, never
  reconfigure.
- No qualitative ranking (such as "strongest coder" or "fastest") is
  sourced here; choose levels by observed behavior on the task, not labels.

## Tier mapping

Role-to-tier membership lives only in `.sw/workspace.md` (Model tiers). A
blank tier inherits the session model unless a local override selects one.
Map tiers with `sw tiers -Reasoning <id> -Standard <id> -Fast <id>`, or by
hand in the git-ignored `.opencode/opencode.jsonc`. An ID may carry an effort
variant (`-Reasoning opencode/<id>#high`); `sw tiers` writes it as given.

Fit by behavior verified above, never by name alone:

- Reasoning: a thinking model at a high effort level; slower and more
  thorough, suited to architecture and review work.
- Standard: a thinking model that finishes multi-turn agent tasks reliably,
  for implementation work.
- Fast: a model with thinking or effort off, for low-latency exploration.

A paid model is the upgrade path for any tier once usage is available; match
its exact ID against `/models` the same way.

## Variants

- Select effort interactively with the composer effort dropdown (desktop
  shows it only for models that have variants). Programmatically, use the
  `#variant` suffix: `provider/model#variant` (in `run --model`, or a
  session/agent/command model field). There is no `/variants` command in V2.
- Variant keybinds depend on the installed client and version: the CLI
  keybind reference (fetched 2026-09-25) defines `variant.cycle`
  (default `ctrl+t`) and an unbound `variant.list`. Desktop bindings may
  differ; verify against the installed client's keybind reference and
  version before asserting a shortcut exists.
- An unknown variant errors loudly at selection. A wrong model ID in config
  fails silently: variants attach to nothing and the options never appear,
  which looks identical to "no levels available."
- Badge/label behavior is version-dependent and unverified here. Confirm
  the active variant from the session/model ref, not just any badge.
