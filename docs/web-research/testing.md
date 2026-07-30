# Web Research Testing

Standard tests make no live Brave or Firecrawl calls. Adapter tests use `httpx.MockTransport`;
pipeline and API tests use deterministic fakes, clocks and resolvers with temporary SQLite files.
Coverage includes provider errors/schema/timeout, SSRF and IDNA, MIME and size limits, prompt
injection, active HTML, deduplication, lifecycle, audit hashes, budgets, retry/cancel, idempotency,
DRAFT-only handoff, two tenants, DE/EN, schema parity and eight approved API E2E scenarios.

CI runs pytest, both existing benchmarks, Ruff, strict mypy, Bandit, `pip-audit`, package build,
schema/migration checks, secret scanning and deterministic OpenAPI v0.4 drift detection. Real
provider-account testing is explicit operator-owned work outside the standard suite.

MCP adapter tests additionally cover official protocol discovery and bearer enforcement, strict
tool input/output contracts, role/tenant attacks, server-limit precedence, mutation replay, DE
Verified handoff, EN Deep conflicts and prompt-injection non-handoff. They use the same fake provider
ports and no live keys.
