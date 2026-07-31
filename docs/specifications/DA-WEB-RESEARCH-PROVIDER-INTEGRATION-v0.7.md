# Web Research Provider Integration v0.7

Status: approved implementation basis for development and controlled pilot provider operation.

## Context and objective

Decision Assurance already has one tenant-aware Research pipeline, Brave and Firecrawl adapters,
bounded source selection, URL policy, normalization, evidence compilation, persistence and the
request-time residency guard. This change completes the technical provider integration without a
parallel architecture. It does not add OIDC/Keycloak, export, deletion, legal hold or retention.

Brave discovery returns title, URL, description, rank and an available publication/page age. A
selected public URL is submitted to Firecrawl for Markdown extraction. Provider output is validated,
normalized, hashed and retained as separate source, snapshot and evidence records. External content
is untrusted data and cannot change agent instructions, policy or authorization.

Official provider contracts checked for this design are Brave Web Search v1 at
`GET /res/v1/web/search` with `X-Subscription-Token`, and Firecrawl Scrape v2 at
`POST /v2/scrape` with Bearer authentication.

## Requirements matrix

| ID | Requirement | Implementation | Verification |
| --- | --- | --- | --- |
| PI-01 | Reuse the existing pipeline and domain contracts | current providers, orchestrator, normalizer and compiler | architecture/diff review |
| PI-02 | Brave preserves title, URL, description, rank and available date | Brave adapter | response contract tests |
| PI-03 | Firecrawl returns bounded normalized text and metadata | Firecrawl adapter and normalizer | adapter and integration tests |
| PI-04 | Every network attempt passes the request-time guard | provider adapters and egress context | zero-call spies and audit tests |
| PI-05 | Restrictive profiles remain evidence-gated | residency guard | production negative tests |
| PI-06 | Development use is explicit and cannot authorize production | development provider profile and pinned runtime profile | downgrade tests and audit code |
| PI-07 | Provider keys use `SecretProviderPort` and local files by preference | runtime provider factory and `.secrets` templates | missing/invalid/file-provider tests |
| PI-08 | Connector failures are controlled and independent of unrelated functions | optional provider key resolution and existing error model | missing-key API tests |
| PI-09 | Timeout, retry, backoff and 429 are bounded | existing Research attempts, job policy and Retry-After | provider/orchestration tests |
| PI-10 | 401/403/404/429/5xx have stable classifications | provider adapters | table-driven tests |
| PI-11 | SSRF, redirect and DNS changes fail closed | `PublicUrlPolicy` before and after extraction | hostile resolver/metadata tests |
| PI-12 | Size and content type are bounded | Firecrawl adapter and normalizer | negative tests |
| PI-13 | Canonical URLs and duplicates converge | URL policy and orchestrator | combined pipeline tests |
| PI-14 | Provenance, retrieval time and content hash are immutable | source/snapshot/evidence contracts | persistence assertions |
| PI-15 | Prompt injection is marked and cannot drive handoff | normalizer and evidence policy | injection E2E |
| PI-16 | Logs contain only connector, status, duration, correlation and reason | provider telemetry and structured logger | secret-canary tests |
| PI-17 | Tenant isolation and DE/EN behavior remain unchanged | repositories, RLS and API localization | full regression and E2E |
| PI-18 | Live tests are explicit, local-key-gated and output-minimal | marked live smoke module | opt-in execution |
| PI-19 | CI retains all security and build gates | existing CI | successful PR checks |

## Architecture

```text
Research Request
      |
      v
ResearchOrchestrator -- tenant/actor/correlation --> ResidencyEgressGuard
      |                                                   |
      v                                                   v
BraveSearchProvider -------------------------------> Brave Search
      |
      v
PublicUrlPolicy -> canonical selection/deduplication
      |
      v
FirecrawlContentExtractor -------------------------> Firecrawl Scrape
      |
      v
PublicUrlPolicy (post-response) -> EvidenceNormalizer -> Snapshot/Hash -> Evidence
```

Provider retries remain orchestration attempts. Each retry consumes budget, creates an attempt and a
new egress decision, and respects job backoff or bounded `Retry-After`. Firecrawl POST requests are
not blindly repeated inside the adapter.

Development is represented by `development-provider-integration`. Its external location is recorded
as `external-unspecified`, and its egress decision uses `EGRESS_ALLOWED_DEVELOPMENT`. That reason is
not residency evidence. Staging and production reject the development mode and continue to accept
only independently verified admissible evidence.

`BRAVE_API_KEY` and `FIRECRAWL_API_KEY` are secret references. Local operation prefers mounted files
under `.secrets/`; environment resolution is permitted only for development/test. Missing or unsafe
values become `PROVIDER_NOT_CONFIGURED` and never appear in logs, audit or exceptions.

## Threat model

| Threat | Likelihood / impact | Prevention and detection | Residual risk / response |
| --- | --- | --- | --- |
| Production profile downgraded to development | low / critical | pin startup profile; reject development mode in staging/production | compromised process/config authority; stop service |
| Key disclosure | medium / critical | secret ports, ignored files, redacted structured logs, Gitleaks | operator terminal/process exposure; rotate key |
| Guard or audit bypass | low / critical | adapter-level guard immediately before transport; audit-before-send | compromised runtime; isolate egress |
| SSRF, metadata access or DNS rebinding | medium / critical | HTTPS/public-IP policy before selection and after provider result | provider-side DNS timing; block source/provider |
| Redirect to prohibited target | medium / high | post-response canonical URL and same-domain validation | provider metadata may be incomplete; reject result |
| Poisoned or instructional content | high / high | active-content stripping, secret redaction, injection risk, no policy authority | semantic detection incomplete; human review |
| Retry amplification/rate-limit abuse | medium / medium | bounded attempts, budget, circuit breaker, backoff and capped Retry-After | provider outage; disable connector |
| Cross-tenant inference | low / critical | tenant context, tenant repositories/RLS and tenant-scoped audit | privileged operator risk; incident response |
| Provider schema drift | medium / high | strict required fields and stable errors | additive fields ignored; block incompatible response |

## Acceptance criteria

1. Actual Brave and Firecrawl adapter instances complete a mocked end-to-end Research run.
2. Source candidates, snapshots and evidence retain separate provenance, retrieval time and hashes.
3. Missing/invalid keys and all required HTTP classes fail with stable secret-free errors.
4. Residency denial and mandatory audit failure produce zero network calls.
5. Private, loopback, link-local, metadata, DNS-change and prohibited redirect targets are rejected.
6. Unsupported/oversized content and prompt-injection patterns cannot become trusted evidence.
7. Development calls are explicitly marked and cannot be configured in staging/production.
8. Live smoke tests require explicit opt-in and both local secret files; output is bounded metadata.
9. Ruff, strict Mypy, complete non-PostgreSQL/PostgreSQL tests, scans, audits and builds pass.
