# Decision Assurance v0.5 — MCP Web Research implementation plan

This plan implements ADR-005. Each stage ends with focused tests. Commit, push, Draft PR,
deployment and ChatGPT Work installation require separate owner approval.

## Stage 1 — Architecture and contracts

- Record baseline, alternatives, decision, requirements and threat model.
- Add strict tool contracts, mode policy and public/packaged JSON Schemas.
- Verify schemas, mode caps and forbidden tenant/outcome fields.

## Stage 2 — Transport-independent application service

- Reuse Decision and Research repositories, submission/orchestration, compiler and handoff ports.
- Authenticate outside the service; authorize centrally inside every operation.
- Implement start/get/retry/cancel/handoff, bounded summaries, localized stable errors and
  actor/tenant-scoped idempotency.
- Verify unit, tenant, RBAC, retry, cancellation, audit and DRAFT-only handoff cases.

## Stage 3 — MCP transport and runtime

- Pin official MCP Python SDK `>=1.29,<2`.
- Register exactly five typed tools on stateless Streamable HTTP `/mcp`.
- Construct the MCP runtime from the same protected runtime configuration and services as the API.
- Verify protocol discovery, typed invocation, per-call authentication and fail-closed exceptions.

## Stage 4 — Personal skill source

- Run the official Skill Creator initializer at
  `integrations/chatgpt-work/conduct-assured-web-research`.
- Keep only `SKILL.md`, `agents/openai.yaml` and the four requested references.
- Generate `openai.yaml` with the official helper and validate with `quick_validate.py`.
- Verify trigger guidance, five-tool allowlist, source/evidence policy and absence of installation
  claims.

## Stage 5 — E2E, documentation and release evidence

- Add provider-independent German Verified success, English Deep conflict and cross-tenant cases.
- Update README, architecture, security, deployment, operations, testing, Web Research, changelog,
  version notes and key-free configuration examples.
- Run full pytest, Ruff format/lint, strict Mypy, Bandit, dependency audit, Gitleaks when available,
  build, schema/OpenAPI checks and installed-wheel smoke tests.
- Stop with a complete report and request approval before the first commit.
