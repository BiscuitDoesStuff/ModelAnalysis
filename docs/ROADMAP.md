# Roadmap

The reliability foundation is implemented: pinned run bundles, staged publication and recovery, source-qualified route history, verified-free-only alerts, configurable retention, and full non-router model-page coverage. Validation results belong in dated run notes; this list is follow-up scope, not a claim that every quality gate has passed.

## 1. Provider identity and collision handling

**Goal:** preserve exact provider routes while improving canonical model/family joins. Make ambiguous same-tail matches reviewable instead of silently broadening equivalence.

**Dependencies:** route identity/history contracts, recorded collisions, explicit crosswalk evidence and representative multi-provider fixtures.

**Acceptance:** namespace collisions stay distinct unless evidence supports a join; conflicting mappings are visible; model pages and alternative-route suggestions preserve route provenance; identity changes cannot create false loss/restoration events. Any history-rule change is versioned.

## 2. Benchmark provenance and scale audit

**Goal:** audit every displayed score, price, and estimate for source, measurement/version, effort, units, and freshness. Keep AA rankings and other benchmark scales separate.

**Dependencies:** stable entity mappings, observations/views, evidence registry, saved source fixtures.

**Acceptance:** representative cells trace to captured evidence; unknown version/unit remains explicit; incompatible scales never enter a shared rank/ratio; supported versus estimated evidence is consistently labeled across MD, JSON, XLSX, dashboard, and site.

## 3. UX convergence and accessibility

**Goal:** align dashboard and reference-site labels, filters, copy behavior, coverage summaries, and navigation while preserving their useful views.

**Dependencies:** shared report contracts and provenance vocabulary; source-tab/model-directory fixes already provide the baseline.

**Acceptance:** common rows show the same identity, free status, price source, and evidence; keyboard navigation, focus visibility, labels, tab semantics, contrast, and narrow-screen layouts are checked; no display-only route is copyable; unknown and zero remain visually distinct.

## 4. Evidence and benchmark-version maintenance

**Goal:** make registry refresh and version changes repeatable without treating stale evidence as newly verified.

**Dependencies:** provenance audit, source timestamps, `research.json` eligibility/expiry rules.

**Acceptance:** a documented refresh records checked/expiry dates and evidence URLs; expired or mismatched evidence loses eligibility predictably; changed versions cannot silently inherit incompatible scores; fixture checks cover expiry boundaries and effort-specific estimates.

## 5. Retrieval efficiency and observability

**Goal:** reduce redundant requests and quota use while retaining accurate coverage and source-fetch times.

**Dependencies:** component-level health, cache timestamps, configurable budgets, saved paginated/failure fixtures.

**Acceptance:** repeated bounded runs demonstrate lower request counts without changing completeness claims; pagination interruptions remain partial; cache hits retain original times; quota/detail limits are visible and respected; fixture validation never spends API quota. Add concurrency or conditional requests only with measured benefit and deterministic failure handling.

## 6. Dependency reproducibility and CI

**Goal:** make a clean checkout reproducibly installable and validate reliability on supported platforms.

**Dependencies:** explicit supported Python/platform policy, dependency version strategy, network-free test fixtures, bundle-aware smoke checks.

**Acceptance:** clean-environment installation and the documented validation commands run in CI without secrets/network retrieval; Windows and non-Windows writer-lock/publication behavior are covered; dependency updates have a repeatable verification path. Artifact generation and smoke selection use one pinned bundle.

## 7. Scalable browsing and output size

**Goal:** preserve access to every model as catalogs grow without making the local site or workbook impractical.

**Dependencies:** stable model identity, complete directory/pages, measured generation time, bundle size, and browser interaction cost.

**Acceptance:** representative large fixtures have no broken links or missing non-router pages; displayed/total counts stay accurate; search reaches the full catalog; explicit performance budgets guide pagination/indexing or compact-data changes; offline use and machine-readable full exports remain available.

## Ordering

Start with identity and provenance because alternative matching, evidence maintenance, and cross-view consistency depend on them. Reproducible CI and accessibility improvements can proceed alongside those audits. Optimize retrieval and browsing against measurements after preserving the reliability contracts. Each item should land with scoped fixtures and acceptance evidence, without requiring a live-provider run for ordinary validation.
