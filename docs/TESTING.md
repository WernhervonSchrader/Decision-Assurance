# Testing Strategy — API v0.2

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

