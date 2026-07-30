# Changelog

## 0.5.0 — Public Draft

- Added a bounded, separately runnable MCP Web Research adapter with exactly five authenticated,
  tenant-scoped tools, central mode/server limits, stable structured outputs and conservative handoff.
- Added public/packaged MCP schemas, protocol/RBAC/isolation/security E2E coverage and a non-root MCP
  image/Compose process.
- Added the validated `conduct-assured-web-research` personal-skill source template for later,
  separately approved ChatGPT Work installation.
- Hardened Worker execution with periodic current-time lease heartbeats and fail-closed cancellation
  checks at every provider and persistence boundary.
- Routed production MCP retries through the durable queue and added atomic MCP idempotency
  reservation for concurrent duplicate requests.
- Bound release gates to the current GitHub Actions run, commit, required successful steps and
  checksummed package/SBOM/restore artifacts instead of preassigning `PASS`.

- Added PostgreSQL adapters, tenant-composite keys, forced RLS, checksummed migrations and
  least-privilege runtime roles.
- Added production OIDC/JWKS, strict claim mapping and human-only approval controls.
- Added durable asynchronous Research jobs with atomic submission, leases, retries, cancellation,
  dead-letter state, concurrency limits and stale-lease recovery.
- Added typed production configuration, external secrets, exact HTTPS egress, redacted telemetry,
  readiness and immutable build metadata.
- Added non-root images, backup/restore verification, SBOM and critical vulnerability scanning,
  checksums and computed release governance.
- Added a controlled two-tenant Sales Quote Review pilot with local OIDC and fake providers.

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
