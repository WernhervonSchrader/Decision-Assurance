# Decision Assurance v0.8 — Controlled Pilot Edge, UI and operational evidence

**Status:** implementation specification approved by project owner on 2026-08-01

**Branch point:** `af06fc84e5e9d9ed2a490f6d8d8442d8741394df`
**Scope:** one bounded Sales Quote Review pilot; not a SaaS or production approval

## A. Context assessment

PR #6 established the OIDC and tenant boundary. The branch baseline has 575 passing non-live tests;
21 PostgreSQL, Keycloak and live-provider tests are deliberately separate. The repository already
contains the deterministic Engine, controlled Intake, asynchronous Research, PostgreSQL 16 with
forced RLS, hash-linked audit records, OpenAI Web Search, optional Firecrawl, request-time egress
gates, five MCP Research tools and Keycloak Authorization Code/PKCE test infrastructure.

The existing production-like E2E proves an API-only Sales Quote journey for two tenants. It does not
provide a browser session, externally usable HTTPS edge, case listing, portable export, executable
retention/delete/legal-hold behavior or complete pilot operations evidence. Those are the only new
capability boundaries in v0.8. Existing REST, MCP, Research, Engine, OIDC and persistence contracts
remain authoritative.

Users are a bounded set of German- or English-speaking pilot participants: generator, human
validator, different human approver and auditor. The pilot tenant is configured, never selected by
the browser. No real customer data, general tenant onboarding, billing, email/SMS or external
administration is in scope.

Primary risks are token leakage, reverse-proxy trust confusion, cross-tenant IDOR, accidental local
governance logic, incomplete deletion, audit loss, export tampering and mistaking CI evidence for a
production release. The implementation must fail closed on identity, tenant, audit, legal hold,
configuration and provider/residency uncertainty.

## B. Requirements matrix

Evidence is `planned` until the named gate has run on the final commit.

| ID | Requirement | Implementation location | Verification | Completion evidence |
| --- | --- | --- | --- | --- |
| EDGE-01 | HTTPS-only public edge, redirect, allowlisted hosts and trusted proxy boundary | `deploy/edge/Caddyfile`, `compose.controlled-pilot.yaml`, edge tests | Caddy validation and TLS/header integration | `pilot-edge` CI job |
| EDGE-02 | Bounded bodies and fixed UI/API/MCP/identity routes | Caddy and existing API middleware | oversized, route and smuggling negative tests | edge contract tests |
| UI-01 | Minimal DE/EN Sales Quote UI without governance computation | `ui/`, `src/decision_assurance/pilot_ui/` | unit and browser E2E | UI build/test artifacts |
| I18N-01 | Stable DE/EN keys, explicit locale selector, English fallback, locale-aware display | `ui/src/i18n.ts`, BFF locale cookie | parity/fallback/format tests | UI unit and browser tests |
| AUTH-01 | Keycloak Authorization Code with S256 PKCE, state and nonce | `pilot_ui/oidc.py`, `pilot_ui/routes.py` | positive and negative OIDC tests | browser-auth gate |
| AUTH-02 | Tokens stay server-side; browser receives only an opaque secure session | `pilot_ui/session.py` | storage, cookie, log and error canary tests | token-leakage gate |
| AUTH-03 | Logout, short expiry, fixation defense and IdP outage fail closed | BFF session/auth routes | replay, fixation, expiry and outage tests | browser-auth gate |
| AUTHZ-01 | Existing server permissions remain the only authorization source | BFF REST client and existing API | role escalation and prohibited-action tests | pilot E2E |
| TENANT-01 | Actor and tenant come only from validated OIDC; no client override | existing API OIDC plus BFF `/session` projection | body/header/query/URL manipulation tests | tenant-boundary gate |
| TENANT-02 | UI, REST, direct IDs, export and deletion deny Tenant B access to Tenant A | all new repositories/routes | two-tenant browser/API/PostgreSQL tests | tenant-isolation gate |
| DATA-01 | Intake text/upload is bounded, validated and treated as untrusted | BFF upload parser and existing Intake contracts | type/size/injection tests | input-security gate |
| GOV-01 | Only Engine emits PASS/REVIEW/BLOCK; Research and UI never do | existing Engine, thin UI/BFF | forbidden-symbol/dependency scan and E2E | governance-boundary gate |
| GOV-02 | APPROVED requires authorized distinct human; generator/validator/approver SoD | existing transitions and new journey orchestration | same-actor/agent/role negative tests | actor-independence gate |
| EXP-01 | Versioned portable Decision File export with checksummed manifest | `export/`, API export route, schemas | schema, checksum, tamper and offline validator tests | export-validation gate |
| EXP-02 | Export excludes secrets, tokens and unnecessary PII | export allowlist/redaction | canary scan and schema assertions | export-redaction gate |
| RET-01 | Tenant retention policy and physical deletion order are executable | `lifecycle/`, PostgreSQL migration/repository, API routes | unit, PostgreSQL and E2E | lifecycle gate |
| HOLD-01 | Active legal hold blocks physical delete and is audited | lifecycle service/repository | hold/replay/race tests | lifecycle gate |
| AUDIT-01 | Request, block, execution and result events are hash-linked and persisted | lifecycle/export services and existing audit chain | failure injection and chain verification | audit-integrity gate |
| OBS-01 | Correlation spans browser, BFF, API, worker, Research and audit | BFF/API headers and existing telemetry | trace E2E | correlation gate |
| OBS-02 | Low-cardinality metrics cover auth, API, jobs, providers, outcomes and approvals | existing/new observability adapters | metric-name/label allowlist tests | metrics-safety gate |
| PRIV-01 | No token, secret, prompt or sensitive body in logs/errors/browser/export | structured allowlists and redaction | multi-surface canary scan | secret/privacy gate |
| CFG-01 | `controlled-pilot` starts only with PostgreSQL, OIDC, HTTPS, non-loopback URLs, secret refs, hosts, audit, backup, retention, probes and tenant | production config/runtime | complete negative startup matrix | profile gate |
| CFG-02 | `local` and `eu-managed` remain compatible and provider gates remain fail closed | existing config/egress | regression suites | legacy regression |
| API-01 | Strict schemas, idempotency and consistent localized errors | new API schemas/routes | contract/OpenAPI/negative tests | API contract gate |
| RES-01 | Provider failure affects Research only and never fabricates PASS | existing Research plus journey UI | fake-provider failure E2E | resilience gate |
| E2E-01 | Complete Tenant A browser journey reaches APPROVED and validates export offline | `tests/pilot/e2e/` | Playwright with local Keycloak/PostgreSQL/fake providers | browser E2E artifact |
| E2E-02 | Tenant B is denied every Tenant A surface | same | UI/REST/direct-ID manipulation | tenant E2E artifact |
| CI-01 | Legacy Ruff, Mypy, tests, PostgreSQL, Keycloak, scans, builds and OpenAPI remain | `.github/workflows/ci.yml` | CI | existing jobs green |
| CI-02 | UI build/unit/browser, npm audit, SAST, actionlint, edge/UI image scan/SBOM and Compose gates | CI and scripts | CI | new jobs green |
| OPS-01 | Pilot start/abort/recovery, alerts, backup/restore and rollback are executable | `docs/` and scripts | doc contracts and local drills | operations evidence |

## C. Architecture decision

### Alternatives considered

1. **Server-rendered BFF with a small TypeScript enhancement layer — selected.** A dedicated
   FastAPI BFF owns OIDC state and access tokens, renders one localized shell and calls the existing
   REST API. TypeScript modules provide progressive interaction and are built/tested with a minimal
   Node toolchain. This minimizes browser authority and frontend supply-chain surface while still
   enabling a real browser journey.
2. **React/Vite SPA plus BFF.** It provides mature component ergonomics but adds a large runtime and
   dependency surface for a single bounded workflow. The pilot does not justify that complexity.
3. **Pure SPA with browser-held OAuth tokens.** It is operationally simple but conflicts with the
   server-side token preference and materially increases token theft exposure. Rejected.

The selected UI is not a second API or governance implementation. The BFF forwards authenticated
operations to the existing API with bearer token, correlation ID, locale and idempotency key. It
does not accept tenant or actor fields and never constructs PASS/REVIEW/BLOCK outcomes.

### Components and trust boundaries

```text
Internet browser
  -> Caddy HTTPS edge (host/path/body/header policy)
     -> Pilot UI/BFF (OIDC transaction, opaque session, CSRF, locale)
        -> existing REST API (OIDC authentication, authorization, TenantContext)
           -> PostgreSQL 16 forced RLS / hash-linked audit
           -> existing async Research job + worker -> guarded providers
     -> Keycloak public OIDC paths
     -> MCP public path (OAuth resource server)
```

Caddy trusts no client `Forwarded`/`X-Forwarded-*` values. It removes them and sets a fixed proxy
chain. The BFF accepts forwarded scheme/host only from the configured edge network and validates the
effective host against an allowlist. Internal API, worker, database and management health endpoints
are not published.

### Browser authentication and session model

The BFF generates 256-bit `state`, `nonce` and PKCE verifier values and stores a single-use bounded
login transaction server-side. The callback verifies exact state, exchanges the code at the
configured HTTPS token endpoint, validates the ID token via the existing OIDC policy/JWKS adapter,
checks nonce, and rotates the pre-authentication identifier. A random opaque session identifier is
placed in a `__Host-da_session` cookie (`Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`, no Domain).
Access tokens remain only in a bounded, expiring server-side session store. The controlled pilot is
single-BFF-instance by design; restart invalidates sessions. No refresh token is requested or
persisted. This deliberate limitation is safer and smaller than introducing a new token database.

Every unsafe BFF request requires a per-session CSRF token supplied in a header and checked with a
constant-time comparison. Login state is independent of the application session. Return paths are
relative allowlisted UI paths, never arbitrary URLs. Logout deletes the server session, expires the
cookie and invokes the allowlisted Keycloak end-session endpoint when available.

### Tenant, authorization and localization flow

The BFF derives the displayed actor, tenant and role from the API `/v1/session` response produced
after bearer validation. It never reads identity claims without API validation and never forwards a
client tenant identifier. Existing role permissions and PostgreSQL forced RLS authorize every
operation. Machine codes and audit events remain stable English identifiers. UI strings have DE and
EN catalogs, browser preference plus explicit selection, tenant-default hook, and English fallback.
Content language and audit display locale remain separate.

### New API contracts

- `GET /v1/session`: safe projection of actor ID, tenant ID, kind, effective roles and expiry class.
- `GET /v1/decisions?limit=&cursor=`: bounded tenant-scoped case list.
- `GET /v1/decisions/{id}/pilot-view`: composed read model from existing Decision/Report/Research
  contracts; no newly computed outcome.
- `GET /v1/decisions/{id}/export`: deterministic ZIP with fixed relative names.
- `POST /v1/decisions/{id}/deletion-requests`: idempotent tenant-scoped request.
- `GET /v1/decisions/{id}/deletion-requests/{request_id}`: status without existence leakage.
- `PUT/DELETE /v1/decisions/{id}/legal-hold`: tenant-admin/audited pilot control.

### Export structure

`pilot-export-v1.zip` contains only fixed names:

```text
manifest.json
decision/decision-file.json
decision/assurance-report.json
intake/intake-record.json
research/research-runs.json
research/sources.json
research/evidence.json
audit/decision-events.json
audit/intake-events.json
audit/research-events.json
lifecycle/events.json
```

The manifest declares schema `0.8.0`, export ID, tenant-scoped case ID, generated timestamp, software
version, commit SHA, policy/schema versions and SHA-256 plus byte length for every member. ZIP member
names are compile-time constants; no object ID becomes a path. JSON is canonical UTF-8. The offline
validator rejects extra, missing, duplicate, absolute or traversal names, decompression excess,
schema mismatch, checksum mismatch and broken audit links.

### Retention, deletion and legal hold

PostgreSQL migration `003_controlled_pilot_v0_8.sql` adds tenant-scoped policy, legal-hold, deletion
request and lifecycle-audit tables with forced RLS and composite keys. A per-case advisory lock
serializes approval and deletion. Requests are idempotent by `(tenant, actor, key)` and transition
`REQUESTED -> BLOCKED_BY_HOLD | EXECUTING -> COMPLETED | FAILED`. Active hold always wins.

Execution physically removes provider attempts, evidence, sources, handoffs, Research jobs/runs,
Intake facts/confirmations/records, reports, idempotency payloads and Decision document in declared
foreign-key order. A minimized tombstone and lifecycle audit remain with tenant, salted case digest,
timestamps, policy/reason codes and actor pseudonymous digest; no source content, quote text or token
remains. Hash-linked Decision/Intake/Research audit records are exported before deletion when policy
requires, then removed; the lifecycle ledger records the verified result. Backups expire under the
documented schedule and are not selectively rewritten. Legal hold retains all case data until
released by an authorized tenant administrator. No SQLite or soft-delete implementation can satisfy
the controlled-pilot profile.

### Observability and failure behavior

Correlation IDs are generated at the edge/BFF boundary and forwarded unchanged to API, jobs,
Research and audit. Metrics labels are allowlisted to route template, method, status class, connector,
job state, outcome enum and reason code; tenant, actor, URL, claim and object IDs are forbidden.
Failures return stable localized codes and correlation IDs. OIDC, audit persistence, legal-hold
lookup, export integrity and controlled-pilot configuration fail closed. Provider failure degrades
Research only. Readiness covers database/schema, OIDC discovery/JWKS freshness, audit persistence,
configured pilot tenant and worker health; liveness is process-only.

### Deployment profile

`controlled-pilot` is a new explicit operating profile, not an alias for production. Startup rejects
SQLite/static auth, HTTP or loopback issuer/redirect/public URL, missing host allowlists, inline
secrets, disabled audit persistence, missing backup/retention/probes/pilot tenant, placeholder
credentials and unspecified edge trust. `local` and `eu-managed` semantics do not change. Tunnel and
DNS configuration live outside core code and may target the fixed edge port.

## D. Threat model

| Threat | Likelihood / impact | Prevention | Detection/response | Residual risk |
| --- | --- | --- | --- | --- |
| Code/state/nonce replay | medium / critical | single-use expiring transaction; exact comparisons; PKCE S256 | auth denial metric; invalidate transaction/session | compromised IdP remains trusted |
| Session theft/fixation | medium / critical | rotated random cookie, Secure/HttpOnly/SameSite, short TTL, TLS | session denial/logout; restart invalidates all | endpoint compromise can use live token |
| CSRF/open redirect | medium / high | bound token on unsafe methods; relative return allowlist | security event and correlation | browser extension risk remains |
| Token leakage | medium / critical | server-only token, no refresh, structured allowlists, no-store | canary scans; revoke sessions/clients | BFF memory is sensitive |
| Host/forwarded spoofing | medium / critical | edge strips headers; BFF trusts configured proxy CIDR and host allowlist | rejected-host metric; pilot abort | edge compromise remains critical |
| Cross-tenant IDOR | medium / critical | OIDC tenant, no overrides, API authz, forced RLS | negative probes and alerts; pilot stop | privileged DBA is trusted |
| Role escalation/SoD bypass | medium / critical | existing exact role allowlist and transition policy | denied action audit; disable identity | compromised approver account |
| UI fabricates outcome | low / critical | UI displays server fields only; forbidden dependency/symbol tests | E2E compare API/UI | malicious browser can alter its own display only |
| Malicious upload/prompt injection | high / high | strict type/size, plain text, untrusted marker, no instruction authority | injection finding/audit; human review | semantic attacks are imperfectly detectable |
| SSRF/redirect rebinding | medium / critical | existing request-time egress guard and redirect revalidation | provider denial metrics; disable Research | provider-side resolution race |
| Export tampering/zip slip/bomb | medium / high | fixed names, canonical JSON, checksums, size/member bounds | offline validator rejects; regenerate | verifier host remains trusted |
| Incomplete/replayed delete | medium / critical | transactional state machine, FK order, idempotency, verification | lifecycle FAILED/alert; retry bounded | backups retain until expiry |
| Hold/delete/approval race | medium / critical | per-case lock, hold recheck in delete transaction | race tests/security event | database outage blocks all three safely |
| Audit failure/tampering | low / critical | atomic writes, hash chain, fail closed | verifier/readiness/alert; pilot abort | DB owner compromise |
| Metric/log cardinality or PII leak | medium / high | label/event allowlists and redaction | schema/canary tests; purge and rotate | operators see permitted identifiers |
| Edge DoS | high / medium | body/rate/time limits and resource caps | latency/5xx alerts; shed load | volumetric protection is deployment-specific |
| Supply-chain compromise | low / critical | pinned lockfiles/images/actions, audits, SBOM, Trivy, non-root | block PR/rebuild | upstream signing trust |
| Misread CI as production approval | medium / high | explicit evidence classes and Draft gate | acceptance checklist | organizational misuse remains possible |

## E. Specification review

The review found and resolved five ambiguities:

1. “Extern testable” does not authorize deployment; PR #7 supplies deployment configuration and
   local evidence only.
2. “One tenant” is the operational pilot limit, while tests still require two tenants to prove
   isolation.
3. The existing profile names are environment profiles (`development/staging/production`) plus
   operating modes (`local/eu-managed`). `controlled-pilot` is introduced as an operating mode with
   stricter startup invariants, not as a production claim.
4. The portable export is deterministic ZIP, not a filesystem directory or arbitrary archive path.
5. Physical deletion and immutable audit conflict unless retention is classified. The selected
   contract removes case content and domain audit, retains only a minimized lifecycle tombstone, and
   documents backup expiry and legal-hold precedence.

No requirement authorizes weakening provider residency gates, exposing internal health endpoints,
adding productive credentials or changing Engine outcomes.

## F. Acceptance criteria

1. The branch remains based on `af06fc84…`; `main` is unchanged and no deployment occurs.
2. All 575 baseline tests and every PostgreSQL/Keycloak regression pass.
3. Caddy offers only approved routes over HTTPS, redirects HTTP, rejects invalid hosts/forwarded
   spoofing and sets the documented security headers.
4. Browser login proves S256 PKCE, state/nonce single use, fixation resistance, CSRF, secure cookies,
   short expiry and no token in storage/logs/errors.
5. Tenant A completes Intake, guarded Research, Engine evaluation, distinct human validation and
   approval, and offline-valid export through the UI.
6. Tenant B cannot infer or operate Tenant A objects via UI, REST, direct IDs, manipulated payloads,
   export, approval or deletion.
7. The export schema, member allowlist, hashes, audit links and manifest validate offline; mutation,
   traversal and excess input are rejected.
8. Retention, request replay, physical deletion, legal hold and concurrent delete/approval are
   deterministic and audited; active hold never deletes.
9. `controlled-pilot` fails startup for every missing prerequisite and never implies production
   approval.
10. UI/edge images run non-root; lockfiles, audits, SAST, Gitleaks, actionlint, SBOM and Trivy pass.
11. Documentation separates repository CI, local integration, deployment, organizational and
   production evidence and records remaining operational risks.
12. The final commit has green CI and a Draft PR; readiness, merge and deployment remain separate
   independent decisions.
