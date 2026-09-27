# phase6-measure-first - review - 2026-09-27T164300Z-plan - project-review

- **Author / audience:** project-review (read-only) for owner + Leader; advisory only, no authorization to change anything.
- **Approval:** Owner requested the review ("Send plan review"); read-only review of the Phase 7 plan.
- **Scope / acceptance:** `.sw/comms/tasks/phase6-measure-first/2026-09-27T163800Z-phase7-plan.md` (7 items + validation + non-goals + sequencing + Q1–Q5) against `docs/PLAN.md` Phase 7 bullets, Handoff invariants, and existing CI gates. No builds/tests run, no files modified, no secrets inspected.
- **Status:** complete; verdict **GO with notes** — plan is implementable after the gate; 4 low defects/clarifications below, none blocking planning approval.
- **Branch / base:** Informational only per assignment (biscuit-worktree checkout); review touches no branch state.
- **Checked revision / changed:** Nothing changed by review.
- **Owners / dependencies:** Leader routes corrections at Phase 7 dispatch; owner resolves Q-defaults only by objection (per 163800Z progress record).
- **Decisions / remaining:** (a) PASS completeness — all 7 PLAN bullets mapped (see check). (b) PASS scope — non-goals explicitly fence retrieval, renderer forks, deps/assets, format removals, runs/DB/network. (c) PASS technical claims verified against code (see check). (d) PASS gating — hard gate stated 5x; budgets provisional until live numbers land, correctly ordered. (e) ACCEPTANCE mostly independently testable offline with named commands; gaps are D1–D4. (f) PASS invariant/CI compatibility — no break found; one ruff reminder in notes.

## Completeness check (PLAN bullets → plan items)

| PLAN bullet | Plan item | Verdict |
|---|---|---|
| measure_bundle + record live numbers | Item 1 + run-notes recording | pass |
| make_large.py 5k+20k deterministic; no broken links / no missing non-router pages / displayed==total | Item 2 + Item 3 | pass |
| Budgets 5 MB / 10 MB / 60 s, slow test Linux-only CI | Item 3 (values + Linux-only slow job match PLAN verbatim) | pass |
| Directory first page + whole-catalog `.js` index (file://) | Item 4 | pass |
| Dashboard pagination | Item 5 | pass |
| Static pages; subfolder split only if measured need | Item 6 (default zero-change + conditional) | pass |
| Full JSON+XLSX stay + optional models.csv | Item 7 | pass |
| Done: 20k passes coverage+links in budget; search full catalog; offline works | Item 3 + 4 acceptances + file:// validation | pass |

## Correctness checks performed (evidence, not author-reported)

- Manifest per-stage seconds: CONFIRMED — `pipeline.py:230-238` `stage()` writes `manifest["stages"][name].seconds`; stage names at lines 248–288 are exactly fetch/websites/analyze/report/site/alerts/validate. "Already present, do not recompute" is accurate.
- Routers excluded + coverage/link/a11y checks: CONFIRMED — `pipeline.py:81` (`if not m.get("router")`), 83–84 exact coverage set, 90–94 `check_html` on dashboard + every site page, 100–109 link/fragment resolution.
- `check_html` scope: CONFIRMED — `reports/ui.py:319-328` (named buttons, labelled fields, tab wiring, captioned/scoped tables, copy-only-callable). Item 5 pager acceptance is checkable by it.
- `model_filename`/`model_link` coupling: CONFIRMED — `reports/build_site.py:49-51, 106-110`; plan correctly flags link-scheme + coverage-set as jointly changed only if item 6 splits.
- Offline validation commands named and consistent with repo usage — `tools/golden_bundle.py <tmp>`, `pipeline.py --snapshot … --state-dir … --db …`, `tests/smoke.py --bundle`, `audit_provenance --sample 0` (0=all), `unittest discover`, `tools/ci.py` golden/recorded-only scope. No live run needed for Phase 7: sound.
- `file://` script-include rationale matches PLAN verbatim; no defect.

## Confirmed defects (all low; fix at dispatch, not blockers)

- **D1 (low, acceptance vague): item 5 filter×pagination interaction undecided.** `filter_input` filters current DOM, so with pagination it silently becomes per-page unless specified. *Smallest fix:* pick one sentence — e.g. "filter searches the full catalog and resets to page 1" — and assert it in `test_scale`/`test_ui`.
- **D2 (low, acceptance vague): item 7 enable-flag unnamed.** `validate_bundle` asserts csv "when enabled" but no opt-in mechanism is named. *Smallest fix:* name the flag + default (suggest config key, default off); both sides read it.
- **D3 (low, acceptance vague): item 3 "site generation ≤ 60 s" key ambiguous.** Manifest `stages["site"].seconds` alone vs report+site unclear. *Smallest fix:* name exact manifest key(s) in the acceptance line.
- **D4 (low, internal tension): item 4 scope vs Q3 wording.** Scope says index holds "slug/id/name only"; Q3 default says "cap snippet fields," presupposing snippets. *Smallest fix:* reword Q3 to "keep slug/id/name only; any additional field needs owner approval rather than a budget raise."

## Hypotheses — no action

- H1: `make_golden.py` row builders cleanly reusable for `make_large.py`; fallback "extract shared helper" already covers failure. Not verified (file not read).
- H2: "5k replays in CI time" unmeasured; fallback "else Linux-only too" plus Q2 default is the measurement plan.
- H3: `measure_bundle` "exit non-zero on missing bundle only" — malformed-manifest behavior unspecified; treat invalid JSON as missing bundle at implementation.
- H4: Phase 6 description (4 threads, fixed order, budget default 0, 304 column) taken as given from prior review + progress record; not re-verified.
- H5: Item 1 "top-N largest" N unnamed — suggest N=10 at implementation; trivial.

## Optional simplifications

- S1: Default item 3's 5k check to the Linux-only slow job alongside 20k instead of "may ride ci.py only if cheap" — removes the one CI-scope conditional; revisit only with timing data.
- S2: Add `ruff check --select F401,F811,F821,F841` to the per-item validation list — new files must pass the same gate CI enforces.
- S3: Items 4+5 both extend shared `ui.py` SCRIPT; order item 5's pager helper first so item 4 reuses rather than invents pager markup.

## Limits (not verified)

No builds, tests, or commands run; all validation evidence is static reads. Did not read `make_golden.py`, `build_report.main` output set, `.github/workflows/ci.yml`, or `tools/a11y/check.mjs` in full; did not assess 20k feasibility, timing budgets, or index-size arithmetic empirically. Live bundle numbers pending the Phase 6 gate (quota window 00:00 UTC 2026-09-28). Credential handling and secret-adjacent paths untouched.

## Next action

Leader may treat the plan as approved-for-dispatch once Phase 6 live verification is recorded; fold D1–D4 + S1–S3 into the implementation assignments (one line each). Owner action: none required — Q1–Q5 defaults stand unless objected to.
