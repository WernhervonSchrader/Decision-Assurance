# ADR-005: Bounded MCP adapter for Web Research

**Status:** Accepted for implementation — 2026-07-30

## Context

Decision Assurance v0.4 already owns Web Research contracts, Brave and Firecrawl adapters,
tenant-scoped persistence, source safety policy, evidence assessment, audit and conservative
`DRAFT`-only handoff. ChatGPT Work and Codex need a narrow MCP interface to those capabilities.
The MCP boundary must not become a second Research implementation or a general browsing surface.

## Alternatives

### A. Mount MCP routes directly in the REST API

This minimizes process count, but couples MCP sessions, authentication failures and transport
upgrades to the public REST lifecycle. It also makes it easier to leak REST-specific concerns into
tool contracts.

### B. Add `decision_assurance.mcp` to the same Python distribution

The MCP server runs as its own process and reuses the existing authenticator, authorization matrix,
Decision and Research repositories, submission/orchestration services, compiler and handoff port.
It can be deployed beside the API and Worker while retaining a small, independently testable
transport boundary.

### C. Build a separate MCP service

This offers the strongest deployment isolation, but creates another artifact, configuration model,
version boundary and operational surface before independent scaling or regulatory isolation requires
it. It also increases the risk of duplicating Research policy.

## Decision

Choose alternative B. The distribution exposes a `decision-assurance-mcp` entry point using the
official MCP Python SDK 1.x line and stateless Streamable HTTP at `/mcp`. MCP 2.x is intentionally
outside this v0.5 compatibility range because it is a major SDK transition.

The transport registers exactly five tools: `research_start`, `research_get`, `research_retry`,
`research_cancel` and `research_handoff`. Tool handlers authenticate the bearer token and call a
transport-independent application service. The service derives `TenantContext` only from the
verified identity and calls the centralized authorization function before repository access.

Quick, Verified and Deep modes centrally cap search/extraction counts at 5/2, 10/5 and 20/10. The
effective value is the minimum of the client request, mode cap and server policy. Retry cannot change
the original request, domain rules, cost budget or limits. Handoff uses only the existing compiler
and handoff port and remains idempotent, tenant-scoped and `DRAFT`-only.

MCP returns bounded structured metadata and evidence candidates. It never returns provider keys,
raw credentials or an assurance outcome. Web content remains untrusted data; no extracted text is
interpreted as an instruction. The Decision Assurance Engine remains the only component that can
produce governance findings or an assurance outcome.

## Consequences

- MCP and REST remain separately deployable processes from one wheel.
- Existing REST routes and v0.4 Research contracts remain compatible.
- Authentication configuration and provider secrets are shared by runtime construction, not copied
  into tool arguments or the personal skill.
- A later split into a dedicated service remains possible behind the same application-service API.
- A reachable production-like endpoint still requires TLS termination, OIDC registration, network
  policy, PostgreSQL/RLS, external secrets and operational controls; the local server is not a
  production deployment.

## Explicit exclusions

No arbitrary URL fetch, unrestricted crawler, shell, filesystem tool, provider configuration tool,
Decision evaluation tool or approval tool is exposed. The repository skill template is source only
and is not installed into ChatGPT Work by this change.
