# OpenAI Web Search and Firecrawl Provider Integration v0.7 implementation plan

## 1. Contract-first artifact chain

- Paths: `web_research/contracts.py`, `codec.py`, research JSON schemas and contract tests.
- Add backward-compatible artifact markers: `SEARCH_RESULT`, `SELECTED_SOURCE`,
  `FETCHED_CONTENT`, `DERIVED_CLAIM`; persist OpenAI summary and response ID on the run.
- First tests: schema parity, codec round trip, chain invariants and absence of a derived claim without
  fetched content.
- Expected: old stored fields remain readable; new writes expose an unambiguous evidence stage.

## 2. OpenAI Web Search adapter

- Replace `providers/brave.py` with `providers/openai_web_search.py` inside `SearchProviderPort`.
- Request: `POST /v1/responses`, configurable model, `web_search`, domain filters, tool choice and
  complete source include.
- Response: strict parsing of `web_search_call.action.sources`, output text and `url_citation`
  annotations; citations rank before consulted-only URLs; canonical deduplication stays local.
- Tests: exact request, summary/citations/all sources, schema drift, missing/invalid key,
  401/403/404/429/all 5xx, timeout and secret-free telemetry.
- Expected: no response body, URL, header or credential reaches logs/errors.

## 3. Optional Firecrawl and degraded citation flow

- Paths: orchestrator, existing Firecrawl adapter, pipeline/control tests.
- Mark a source selected before extraction. On unavailable/denied/failed extraction, retain it as
  `CITATION_ONLY`, finish partially and allow explicit retry. Never synthesize fetched content.
- Tests: OpenAI-only citation fallback, combined full-content flow, hash/provenance, duplicate URLs,
  prompt injection, audit/residency zero-call and tenant isolation.

## 4. Runtime, profile and secrets

- Paths: runtime, development profile, `.env.example`, `.gitignore`, `.gitleaks.toml`,
  `.secrets/*.example` and configuration tests.
- Replace Brave host/key/rules with `api.openai.com` and `OPENAI_API_KEY`; retain Firecrawl.
- Pin the expected runtime profile and load both keys independently through `SecretProviderPort`.
- Expected: restrictive profiles remain blocked without provider-specific verified evidence.

## 5. Live smoke and documentation

- Replace Brave live smoke with OpenAI Responses Web Search; keep Firecrawl and combined tests.
- Require `DA_RUN_LIVE_PROVIDER_TESTS=1` and local secret files. Emit only status, HTTP class,
  duration, result count and correlation ID.
- Update active provider, architecture, security, threat and testing documentation. Historical specs
  may retain historical context but no active configuration may reference Brave.

## 6. Verification and publication

- Ruff format/check; strict Mypy; full non-PostgreSQL and PostgreSQL 16 suites.
- Bandit, staged Gitleaks, isolated dependency audit and `git diff --check`.
- Python packages and API/Worker/MCP images; non-root smoke and critical scans.
- OpenAPI drift and Gold benchmark.
- If both keys exist, run OpenAI, Firecrawl and combined live smoke tests with bounded output.
- Commit the architecture replacement, push the existing feature branch and update Draft PR #5.
- Do not merge or deploy.
