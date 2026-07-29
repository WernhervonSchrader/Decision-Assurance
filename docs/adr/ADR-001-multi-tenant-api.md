# ADR-001: Hexagonal multi-tenant reference API

**Status:** Accepted — 2026-07-29

## Decision

Keep governance and transitions framework-independent. Add an HTTP adapter,
central authorization service, explicit request-scoped identity/tenant context,
and repository protocols. Use FastAPI/Pydantic for the reference transport and
SQLite for deterministic local/in-CI integration tests. Preserve a PostgreSQL
target contract for production-grade row-level security.

## Alternatives

Extending only the filesystem engine would not demonstrate authentication,
authorization or tenant isolation. Building a complete web UI would multiply
surface area before the secure service boundary exists. A service API therefore
provides the strongest next increment with bounded complexity.

## Consequences

SQLite cannot provide PostgreSQL RLS; isolation is enforced and tested in the
repository layer for v0.2. Production claims require a later PostgreSQL adapter,
RLS policies, migration verification and operational OIDC integration. The
domain engine remains reusable by CLI and future UI adapters.

