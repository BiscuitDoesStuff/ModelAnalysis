# Run notes

- 2026-09-26: second-day churn validated live. Run `2026-09-26_0133` populated `free_churn.prev_day = 2026-09-25`, no churn found, no alert file written (correct: alerts only on bad news). Store holds days 2026-09-25, 2026-09-26.
- 2026-09-26: full `run.ps1` at 01:44 (`2026-09-26_0144`) clean: empty `_errors.log`, churn vs 2026-09-25 all zero, no alert; only removal vs history `anthropic/claude-3-haiku`; both Spark estimates cite Meta primary docs; smoke 0 failures.
- 2026-09-26: estimate expansion reviewed. 21 verified-free routes unscored; only `deepseekv4flashfree` had an effort-matched scored source, skipped because the route left the Zen free list (deprecated upstream). Routes whose scored sibling has no effort variant (`ling30flashfinfree`, `nemotron35lightningfree`, gemma `-it`) are blocked by the `variant in supported_efforts` guard by design.
