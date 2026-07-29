# DA Web Research v0.4 — Implementation Plan

1. Add provider-neutral contracts, lifecycle, URL policy, evidence policy and
   deterministic fake providers with tests.
2. Add migration 003, tenant-aware repository, hash-linked audit, semantic
   idempotency, snapshots, budgets and conservative Decision File handoff.
3. Add isolated Brave REST adapter with mocked HTTP contracts.
4. Add guarded Firecrawl v2 scrape adapter with mocked HTTP contracts.
5. Expose authenticated `/v1/research-runs` endpoints with bounded pagination,
   retries, cancellation, DE/EN errors and generated OpenAPI.
6. Run pytest, Ruff, strict mypy, Bandit, pip-audit, benchmarks, build and
   OpenAPI drift verification after every vertical slice.

Commit boundaries are specification, research core, persistence/handoff,
Brave, Firecrawl, orchestration/API and documentation/release verification.

Each task starts with a failing unit, contract, integration, security or E2E
test. Slice verification is `pytest`, Ruff format/lint, strict mypy and Bandit.
Final verification additionally runs dependency audit, both benchmarks, build,
schema-copy equality, fresh and upgraded SQLite migrations, OpenAPI drift,
secret scan when available and `git diff --check`.

The first slice uses deterministic fake providers, clock, IDs and resolver. It
must prove all lifecycle edges, semantic idempotency, tenant isolation,
provider-budget accounting and a DRAFT-only unverified evidence handoff before
real adapter code is introduced.
