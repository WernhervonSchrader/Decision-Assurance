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

