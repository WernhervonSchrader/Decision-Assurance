# Decision Assurance v0.5 — Bounded MCP Web Research

**Status:** implementation specification approved by project owner

## Context and verified baseline

The branch point is `08287c2` on `feature/production-foundation-v0.5`, package version `0.5.0`.
After installing the declared project dependencies plus the test runner's undeclared Trio backend,
the unmodified suite produced 404 passes, 11 PostgreSQL skips and two OpenAPI snapshot-order failures.
Ruff format/lint and strict Mypy passed. Bandit reported only three pre-existing low-confidence B105
false positives when run without CI's `-s B105`. Dependency audit was polluted by unrelated global
packages and exposed vulnerable versions in the non-isolated host environment; the repository's
clean CI environment remains authoritative. Gitleaks is not installed locally. The isolated build
command requires Hatchling, which is installed by the normal PEP 517 build but not by
`--no-isolation`.

The implementation therefore uses an isolated project environment for completion evidence and
keeps the two historical REST OpenAPI documents semantically unchanged.

## Requirements matrix

| ID | Requirement | Implementation | Verification |
| --- | --- | --- | --- |
| MCP-01 | Exactly five bounded tools | `decision_assurance.mcp.server` | tool-list contract test |
| MCP-02 | Typed strict inputs and stable outputs | MCP contracts and JSON Schemas | schema and malformed-input tests |
| MCP-03 | No business logic in transport | application service plus injected ports | service unit tests |
| AUTH-01 | Authenticate every tool call | bearer authenticator at adapter boundary | missing/invalid-token tests |
| AUTH-02 | Central RBAC before access | existing `authorize` and permissions | role matrix tests |
| TEN-01 | Tenant only from verified identity | no tenant input field; `Identity.tenant` | schema and spoofing tests |
| TEN-02 | Cross-tenant access is non-enumerating | tenant-scoped repositories | E2E negative test |
| MODE-01 | Quick 5/2, Verified 10/5, Deep 20/10 | central mode policy | unit limit matrix |
| MODE-02 | Server policy can only reduce limits | minimum-of-three limit calculation | hostile client-limit tests |
| SAFE-01 | Preserve SSRF, redirect, DNS, scheme, port and size controls | existing providers and `PublicUrlPolicy` | existing plus MCP security suite |
| SAFE-02 | Web content remains untrusted | existing normalizer/evidence policy | prompt-injection E2E |
| SAFE-03 | No secret in inputs, outputs, errors or fixtures | server-side provider configuration | canary scan and contract tests |
| MUT-01 | Mutations require idempotency keys | Research idempotency repository | replay/conflict tests |
| RETRY-01 | Retry only failed permitted steps | existing orchestrator retry | retry-limit/domain/budget tests |
| HAND-01 | Handoff is existing conservative `DRAFT`-only path | compiler and handoff port | DRAFT/non-DRAFT tests |
| GOV-01 | MCP never emits assurance outcomes or approval | contracts and repository scan | forbidden-value tests |
| I18N-01 | DE/EN localized stable errors | MCP error mapper and existing i18n | parity tests |
| OPS-01 | Streamable HTTP is separately runnable | `decision-assurance-mcp` | protocol smoke test |
| SKILL-01 | Skill source contains only approved files and tools | `integrations/chatgpt-work/...` | Skill Creator validation/contract test |
| COMP-01 | Existing REST API remains compatible | no route removals/schema changes | OpenAPI and full regression suite |

## Tool contracts

All tool results contain `schema_version`, `ok`, `correlation_id` and either a typed result or a
stable error. Error messages are localized using the requested `locale`; codes remain language
neutral. Inputs forbid unknown fields and never contain `tenant_id`, provider keys or arbitrary
runtime configuration.

- `research_start` validates the Decision File and claims, applies mode/server caps, and submits the
  existing Research request. It returns the run and optional job identifiers.
- `research_get` returns bounded status metadata, source/extraction states, conflicts and a
  conservative evidence-bundle draft. It does not return full extracted page text.
- `research_retry` delegates to the existing retry lifecycle with the original request and limits.
- `research_cancel` delegates to the idempotent cancellation lifecycle and audit chain.
- `research_handoff` invokes or confirms the existing compiler/handoff path; only eligible evidence
  is attached and statuses remain `UNVERIFIED`, `OUTDATED` or `CONFLICTING`.

## Threat model

| Threat | Control | Residual risk |
| --- | --- | --- |
| Tool injection/over-broad capability | fixed five-tool registry; no URL/shell/file/config tools | compromised server code remains privileged |
| Client tenant spoofing | tenant absent from schemas and derived after token verification | trusted IdP/administrator compromise |
| Cross-tenant IDOR/inference | scoped repository queries, composite keys/RLS, generic not-found | database superuser remains privileged |
| Missing/forged authentication | bearer authentication on every call; OIDC production adapter | bearer token theft until expiry |
| Role escalation | centralized existing permission matrix | misconfigured IdP role mapping |
| Prompt injection in pages | content is data only; risk flag; never executed; no tool authority | semantic detector cannot identify every attack |
| SSRF/redirect/DNS rebinding | existing public-HTTPS URL policy, revalidation and egress controls | provider-side DNS timing remains residual |
| Cost/rate exhaustion | mode, server, budget, retry and provider caps | external provider billing remains operational risk |
| Replay/duplicate side effects | actor/tenant/operation-scoped idempotency and deterministic handoff | provider may bill an interrupted remote request |
| Secret exfiltration | keys stay in server runtime; bounded outputs/errors/logs | privileged host access |
| False assurance | no outcome fields; conservative evidence status; Engine-only evaluation | human may still over-trust weak evidence |
| Internal exception leakage | fail-closed generic localized errors with correlation ID | operators need protected logs for diagnosis |

## Acceptance criteria

1. Tool discovery exposes exactly the five named tools.
2. Quick, Verified and Deep caps are enforced and server policy always wins.
3. Authentication, RBAC and tenant isolation tests pass for every tool.
4. German Verified handoff and English Deep conflict E2E cases pass with fake providers.
5. Cross-tenant E2E returns non-enumerating not-found behavior.
6. Existing REST, Intake, Engine, Research and production tests remain compatible.
7. Ruff, Mypy, Bandit, audit, secret scan and build gates pass in a clean environment.
8. The repository skill source validates but is not installed or deployed.
