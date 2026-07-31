# OpenAI Web Search and Firecrawl Provider Integration v0.7

Status: approved implementation basis for development and controlled pilot operation.

## Context and objective

Decision Assurance keeps one tenant-aware Research pipeline. OpenAI Responses API Web Search
replaces Brave for discovery, source-grounded summary and citation metadata. Firecrawl remains an
optional, separately guarded fetch/extraction step for selected public URLs. OIDC/Keycloak, export,
deletion, legal hold and retention remain outside this change.

The provider flow is:

```text
Research Request -> OpenAI Web Search -> source assessment -> URL selection
                 -> optional Firecrawl -> normalized content -> Evidence Records
                 -> Decision Assurance
```

Official OpenAI documentation checked on 2026-07-31 recommends Responses API with
`{"type":"web_search"}` for new integrations. Inline citations are returned as `url_citation`
annotations. `include: ["web_search_call.action.sources"]` returns all consulted URLs, which may be
more numerous than cited URLs. The implementation uses the configurable `gpt-5.6` default shown by
the current guide and never relies on a dynamically changing model alias without configuration.

## Requirements matrix

| ID | Requirement | Implementation | Verification |
| --- | --- | --- | --- |
| OW-01 | Reuse the existing provider-neutral pipeline | `SearchProviderPort`, orchestrator, policies and repositories | architecture/diff review |
| OW-02 | Responses API uses `web_search` and requests all sources | OpenAI adapter | exact request contract test |
| OW-03 | Preserve summary, cited URLs and consulted URLs | OpenAI normalization and Research run/source records | response contract tests |
| OW-04 | Firecrawl remains optional and selected-URL only | existing extractor/orchestrator | combined and degraded-flow tests |
| OW-05 | Every OpenAI and Firecrawl call passes the request-time guard | both adapters | audit-before-network zero-call tests |
| OW-06 | Restrictive profiles remain evidence-gated | residency guard/profile config | negative configuration tests |
| OW-07 | Development exception cannot authorize production | explicit dev mode and expected profile pin | downgrade tests |
| OW-08 | `OPENAI_API_KEY` and `FIRECRAWL_API_KEY` use `SecretProviderPort` | runtime wiring and `.secrets` templates | missing/file-provider tests |
| OW-09 | Missing connectors fail independently | optional key resolution | runtime and adapter tests |
| OW-10 | 401/403/404/429/5xx, timeout and retry are bounded | adapters and existing attempts/backoff | table-driven tests |
| OW-11 | URL, redirect, host, DNS and private address rules remain fail-closed | `PublicUrlPolicy` before selection and after extraction | SSRF/rebinding tests |
| OW-12 | Size and content types remain bounded | Firecrawl adapter/normalizer | negative tests |
| OW-13 | Canonical URLs and duplicates converge | URL policy/orchestrator | combined pipeline tests |
| OW-14 | Evidence chain has explicit artifact stages | contracts and orchestrator | schema/persistence assertions |
| OW-15 | Citation-only fallback never claims fetched full text | source status and partial completion | Firecrawl failure tests |
| OW-16 | Prompt injection remains untrusted data | OpenAI prompt boundary and Firecrawl risk policy | injection tests |
| OW-17 | Logs contain bounded connector metadata only | provider telemetry | exact-field/secret-canary tests |
| OW-18 | Tenant isolation and DE/EN behavior remain unchanged | repositories/RLS/localization | full regression/E2E |
| OW-19 | Live tests are explicit and key-gated | `live_provider` tests | safe skip/live execution |
| OW-20 | CI security and build gates remain blocking | existing CI | PR checks |

## Artifact and trust model

The chain is explicit and monotonic:

```text
SEARCH_RESULT -> SELECTED_SOURCE -> FETCHED_CONTENT -> DERIVED_CLAIM
```

- `SEARCH_RESULT`: cited or consulted URL plus OpenAI-generated, untrusted search context.
- `SELECTED_SOURCE`: canonical public URL selected by deterministic local policy.
- `FETCHED_CONTENT`: Firecrawl response validated, normalized, timestamped and content-hashed.
- `DERIVED_CLAIM`: Decision Assurance evidence candidate linked to a fetched snapshot and claim refs.

If Firecrawl is missing, denied or fails, a selected source becomes `CITATION_ONLY`. It remains a
search/citation record and may be displayed with its source URL, but it does not create a snapshot,
content hash, full-text assertion or compiled Decision evidence. The run becomes
`PARTIALLY_COMPLETED` and may be retried later.

OpenAI output and every consulted web page are untrusted data. Search summaries, citations and page
instructions cannot change authorization, provider selection, policy, prompts or workflow state.
Only deterministic application code chooses URLs and produces evidence candidates.

## Provider boundary

OpenAI uses `POST https://api.openai.com/v1/responses`, Bearer authentication, a configurable model,
`tools: [{"type":"web_search"}]`, `tool_choice: "auto"` and
`include: ["web_search_call.action.sources"]`. Allowed/blocked domains are passed to supported tool
filters and are independently re-enforced locally. Firecrawl remains `POST /v2/scrape`.

Retries remain explicit orchestration attempts. Each attempt consumes budget, passes the guard,
records egress before transport and respects bounded `Retry-After`. No adapter blindly retries.

Development uses `development-provider-integration` with `external-unspecified` and
`EGRESS_ALLOWED_DEVELOPMENT`. This is not residency evidence. Staging and production reject the
development mode and require independently verified evidence for OpenAI and Firecrawl.

## Threat model

| Threat | Likelihood / impact | Controls | Residual risk / response |
| --- | --- | --- | --- |
| Development downgrade | low / critical | pinned profile; dev mode rejected outside development | compromised config authority; stop egress |
| API key disclosure | medium / critical | secret port/files, ignore rules, Gitleaks, bounded logs | operator/process exposure; rotate key |
| Guard/audit bypass | low / critical | adapter guard immediately before transport; audit-before-send | compromised runtime; isolate network |
| SSRF/DNS rebinding/redirect | medium / critical | local canonical/public-IP checks before and after extraction | provider-side timing; reject source |
| Search prompt injection | high / high | untrusted summary/source model; fixed system boundary; no external instructions | semantic detection incomplete; human review |
| Search summary treated as full text | medium / high | explicit artifact types; citation-only partial state | UI misuse; audit and correct record |
| Provider schema drift | medium / high | strict required output parsing and stable errors | incompatible response blocks run |
| Cost/retry amplification | medium / medium | budgets, circuit breaker, attempts, backoff/Retry-After | outage; disable connector |
| Cross-tenant inference | low / critical | tenant context, composite keys/RLS, tenant audit | privileged operator risk; incident response |

## Acceptance criteria

1. Actual OpenAI and Firecrawl adapters complete a mocked Research run through the existing ports.
2. OpenAI request and response handling preserve all citations and consulted URL sources.
3. Artifact types prove `SEARCH_RESULT -> SELECTED_SOURCE -> FETCHED_CONTENT -> DERIVED_CLAIM`.
4. Firecrawl failure produces citation-only partial completion without snapshot/content hash/claim.
5. Missing/invalid keys and required HTTP classes fail with stable secret-free errors.
6. Residency denial and audit failure produce zero network calls.
7. SSRF, DNS changes, redirects, size/MIME and prompt-injection paths fail conservatively.
8. Development configuration cannot be used by staging or production.
9. Standard and PostgreSQL tests, Ruff, strict Mypy, scans, audits and builds pass.
