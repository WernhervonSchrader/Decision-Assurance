# Web Research Testing

Standard tests make no live Brave or Firecrawl calls. Adapter tests use `httpx.MockTransport`;
pipeline and API tests use deterministic fakes, clocks and resolvers with temporary SQLite files.
Coverage includes provider errors/schema/timeout, SSRF and IDNA, MIME and size limits, prompt
injection, active HTML, deduplication, lifecycle, audit hashes, budgets, retry/cancel, idempotency,
DRAFT-only handoff, two tenants, DE/EN, schema parity and eight approved API E2E scenarios.

CI runs pytest, both existing benchmarks, Ruff, strict mypy, Bandit, `pip-audit`, package build,
schema/migration checks, secret scanning and deterministic OpenAPI v0.4 drift detection. Real
provider-account testing is isolated under the `live_provider` marker. It runs only when
`DA_RUN_LIVE_PROVIDER_TESTS=1` and both required local `.secrets` files are available. Example:

```text
DA_RUN_LIVE_PROVIDER_TESTS=1 python -m pytest -m live_provider -s
```

Live output is bounded to status, HTTP result class, duration, result count and correlation ID. It
must never print credentials, URLs, provider bodies or extracted content.

MCP adapter tests additionally cover official protocol discovery and bearer enforcement, strict
tool input/output contracts, role/tenant attacks, server-limit precedence, mutation replay, DE
Verified handoff, EN Deep conflicts and prompt-injection non-handoff. They use the same fake provider
ports and no live keys.
