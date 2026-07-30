# Changelog

## 0.4.0 — Public Draft

- Added a provider-neutral Web Research domain with isolated lifecycle, ports, policies and tables.
- Added Brave discovery and guarded Firecrawl scrape adapters with no live standard tests.
- Added a tenant-safe, idempotent Research API, bounded retry/cancel, cache, budgets and audit.
- Added conservative DRAFT-only handoff that never verifies evidence or emits outcomes.
- Added eight Research schemas, OpenAPI v0.4, DE/EN errors and eight API E2E scenarios.

## 0.3.0 — Public Draft

- Added controlled raw-text Intake contracts, lifecycle and deterministic DE/EN quote extractor.
- Added tenant-scoped Policy Registry and Extractor ports, verification and immutable human confirmation.
- Added the exclusive verified-state Decision File compiler; governance remains in the existing engine.
- Added shared-database Intake tables with tenant-composite keys and a separate repository boundary.
- Added REST and CLI Intake flows, OpenAPI v0.3, 13-case Intake corpus and security/E2E tests.
- Added correction re-verification, authenticated distinct-approver counting, Intake audit access,
  transactional idempotency and strict nested Intake contract validation.

## 0.2.0 — Public Draft

- Added authenticated tenant-aware API, SQLite persistence, lifecycle operations and audit access.
