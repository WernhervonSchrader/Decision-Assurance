# Testing Strategy — Public Draft v0.5

Controlled Intake v0.3 adds contract, extraction/provenance, verification, confirmation,
compiler, SQLite isolation, CLI/API E2E, prompt-injection and metamorphic tests under
`tests/intake/`. The separate 13-case corpus under `benchmarks/intake/cases/` executes both
raw-only and trusted-context variants. READY variants are compiled and evaluated by the existing
engine; unresolved variants assert `NEEDS_CONFIRMATION` and do not manufacture an outcome.

Unit tests cover domain, permission and localization functions. Integration
tests use a temporary SQLite database. Contract tests exercise OpenAPI requests
and responses. E2E tests use FastAPI's in-process HTTP client, deterministic
seed data, two tenants, human and agent identities, English and German, and
create their own isolated database.

Material journeys are DRAFT→VALIDATION→REVIEW→APPROVED and deterministic
BLOCKED evaluation. Negative coverage includes unauthenticated, unauthorized,
wrong tenant, missing tenant, manipulated ID, invalid state, malformed and
oversized input, unsupported locale fallback, agent approval, replay conflict
and duplicate request.

No browser UI exists in v0.2, so browser/device screenshots and traces are not
applicable. CI retains pytest output and generated OpenAPI/build artifacts on
failure. Tests contain no retry; deterministic data and fresh databases control
flakiness.

Web Research v0.4 adds unit, provider-contract, SQLite integration, security, schema and eight
FastAPI E2E scenarios under `tests/research/`. All provider traffic is mocked or faked. Public and
packaged schemas and OpenAPI are drift-checked; fresh and upgraded SQLite migrations are tested.

Production Foundation v0.5 adds real PostgreSQL integration and a controlled API/service E2E under
`tests/production/`. CI provisions PostgreSQL 16, applies roles and checksummed migrations, exercises
forced-RLS isolation, two-Worker lease races, current-time heartbeat renewal, durable manual requeue,
concurrent idempotency and job recovery, and restores a native backup into a fresh database. The pilot
uses two tenants, locally signed OIDC identities, human and agent actors, a fixed clock, deterministic
IDs and fake Brave/Firecrawl adapters. No live provider or production identity/database is used.
API-only scope makes browser/device screenshots inapplicable; sanitized workflow evidence is retained.

The MCP v0.5 suite lives under `tests/mcp_adapter/`. It covers strict inputs and schemas, Quick/
Verified/Deep limits, server-limit precedence, exact tool discovery, Streamable-HTTP authentication,
RBAC, idempotency, tenant isolation, conservative DRAFT handoff, prompt injection, German Verified
success, English Deep conflict and cross-tenant denial. All providers are deterministic fakes. The
suite also proves running cancellation between provider calls, production retry queueing and a
single owner for concurrent idempotency keys. The repository skill source is structurally checked
and also validated with the official Skill Creator.

## Operating Profiles v0.6 evidence

Configuration contract tests load both repository profiles and cover missing residency, unknown
fields, incomplete location categories, non-EU countries, missing HTTPS evidence and local-boundary
violations. Provider-residency regression tests prove:

- local provider hosts are declared as `local` and EU-managed provider hosts use declared EU codes;
- provider hosts and the HTTPS allowlist have identical normalized sets;
- every provider processing location occurs in `external_processing_locations`;
- request-time guard re-reads the profile and policy after a configuration change;
- missing, unverified, expired or mismatched provider evidence fails before the transport call;
- Brave and Firecrawl block without a network call and persist secret-free `ALLOWED`/`BLOCKED`
  egress events;
- undeclared runtime URLs, extra allowlisted hosts, region conflicts and tenant-specific provider
  fields fail closed;
- those runtime conflicts fail before secret resolution or database/OIDC/provider construction.

`tests/production/e2e/test_operating_profiles.py` loads both checked-in profiles with deterministic
fake secrets, a mocked JWKS client and no live provider. It asserts the shared PostgreSQL/OIDC
runtime types and the early failure boundary. Existing production E2E supplies two tenants, at least
two roles and German/English behavior; existing PostgreSQL tests prove forced-RLS isolation. Profile
configuration is deployment-wide, so the negative `tenant_id` provider-field test proves no tenant
can select a separate region or egress route.

Local and CI commands are `ruff format --check src tests`, `ruff check src tests`, `mypy src`, the
targeted configuration/E2E tests, `pytest -m "not postgresql" -q` and `pytest -m postgresql -q`
against isolated PostgreSQL 16. CI additionally runs Bandit, dependency audit, secret scan, container
scan, build/OpenAPI verification, backup/restore verification and commit-bound release evidence.
Tests use fresh temp directories/databases and deterministic fakes without retry; no browser UI means
device screenshots/traces remain inapplicable. Sanitized pytest, build and release evidence is
retained by CI on failure.

