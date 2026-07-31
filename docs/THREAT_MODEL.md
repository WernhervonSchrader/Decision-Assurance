# Threat Model — Production Foundation v0.5

Assets are Decision Files, evidence references, approvals, reports, audit
history, tenant configuration and identities. Actors are tenant users, agents,
auditors, administrators and attackers. Trust boundaries exist at HTTP input,
authentication, tenant resolution, authorization, repository access and any
future identity provider.

| Threat | Likelihood / impact | Prevention and detection | Response / residual risk |
| --- | --- | --- | --- |
| Cross-tenant IDOR | medium / critical | tenant-composite keys; forced PostgreSQL RLS; non-enumerating 404; isolation tests | stop pilot and investigate; privileged database operator remains trusted |
| Tenant spoofing | high / critical | tenant only from verified identity context; body rejects tenant fields | revoke identity; IdP compromise remains material |
| Agent impersonates human | medium / high | identity `kind`; transition policy; role separation | audit and block; compromised human account remains |
| Role escalation | medium / high | centralized permission matrix and object authorization | security audit; bad upstream role mapping remains |
| Audit tampering | low / critical | append-only API, hash chain, role restrictions and restore verification | block release and restore verified copy; DB administrator remains trusted |
| Replay/idempotency abuse | medium / medium | scoped keys plus payload hash | conflict event; storage exhaustion requires rate limits |
| Injection/mass assignment | medium / high | strict typed schemas; parameterized SQL; unknown fields forbidden | reject and correlate; dependency defects remain |
| Oversized/DoS input | high / medium | body, page and string limits; timeouts at deployment boundary | throttle/block source; distributed DoS external |
| Secret/token disclosure | low / high | header/body redaction; no secrets in repo; generic errors | rotate/revoke; operator logging mistakes remain |
| Supply-chain compromise | low / high | bounded dependencies, pinned Trivy action, SBOM, dependency/secret/container scans and checksums | block release and rebuild; zero-day risk remains |
| Undeclared or changed provider processing | medium / critical | startup equality plus central request-time guard re-reading profile, policy, tenant, host and connector | persist `BLOCKED` event, stop request and disable route; config/control-plane compromise remains a residual risk |
| Unverified, stale or mismatched provider attestation | medium / critical | structured evidence class, issuer, validity window, verification status, host/provider binding; self-declaration never authorizes | `EGRESS_EVIDENCE_*` event and no socket call; contractual truth still requires operator/provider review |
| Non-EU provider in EU-managed | medium / critical | EU country allowlist and request-time location check for every external-processing declaration | reject configuration/request; revoke route/key and assess exposure |
| Remote processing labeled local | medium / critical | local accepts only `local`; provider attestation must be verified and location-bound | stop Research and investigate endpoint ownership and evidence |
| Tenant-selected jurisdiction or scope mismatch | low / critical | deployment-only profile, explicit provider tenant scope and request-time tenant check | `EGRESS_TENANT_MISMATCH`, no network call, incident review |
| Residency/config tampering | low / high | read-only reviewed config, exact allowlist equality and configuration hash in release evidence | remove from readiness, rotate credentials and redeploy reviewed config; host/CI administrator remains privileged |
| Regional outage or denial of service | medium / high | bounded retry, approved in-profile backup/restore and no automatic cross-region fallback | degraded operation or reviewed in-boundary recovery; correlated regional failure remains |

OIDC, PostgreSQL RLS, redacted observability and release gates are implemented. Rollout remains
blocked until the deployment owner supplies managed identity/database/secrets, edge controls,
monitoring/on-call, retention/deletion and regulatory evidence described in Production Readiness.

## Operating Profiles v0.6 trust boundaries

Assets added by v0.6 are the reviewed configuration, residency declarations, provider host/location
mappings, external evidence references and deployment audit evidence. Entry points are configuration
delivery and the two provider base-URL environment overrides. The config parser, runtime startup,
HTTPS egress allowlist, DNS/provider boundary and operator control plane are distinct trust
boundaries. Tenant boundaries remain OIDC identity plus forced PostgreSQL RLS; residency is global
deployment policy and cannot grant cross-tenant access.

Detection uses startup reason codes, request-time egress events, readiness, configuration hashes, provider access logs, DNS and
support-access review, two-tenant probes and periodic evidence review. Response is fail-closed:
disable provider egress and new Research jobs, preserve audit/configuration evidence, identify
affected tenants and jurisdictions, rotate credentials, correct the profile and repeat release and
restore verification. There is no automatic fallback to another provider, country or operating
mode.

## Controlled Intake v0.3 extension

New assets are raw business text, candidate provenance, trusted Policy Packs,
human corrections and compiled Decision Files. The raw-input boundary is
hostile: prompt injection, claimed authority/policy/approval, locale ambiguity,
oversized content, cross-tenant references and forged verification status are
expected abuse cases.

Controls are strict Intake schemas without governance flags; extraction that
only creates candidates; tenant-scoped trusted registries; authenticated
human-only confirmation; immutable corrections; READY-gated compilation;
content-type/body limits; parameterized tenant-scoped storage; hash-linked audit
and raw/trusted/metamorphic security tests. A deterministic regex extractor may
miss linguistic variants (medium likelihood/medium impact); this remains
visible as missing/unresolved information and therefore fails toward review,
not pass. Raw text retention creates privacy exposure; v0.3 stores only the
minimum case text and documents tenant-controlled retention/deletion as an
operational prerequisite.

Web Research adds SSRF, DNS/IP rebinding assumptions, hostile markup, prompt injection, poisoned
provenance, provider compromise, cost exhaustion and cross-tenant cache/handoff threats. Controls
include a request-time residency transport guard, repeated URL validation, public-only addressing, fixed scrape options, normalization,
composite tenant keys, atomic budgets, bounded attempts and human-review markers. DNS changes
between adapter validation and remote provider retrieval remain an upstream/provider risk.

The provider-integration development profile adds a configuration-downgrade threat: an operator
could otherwise mistake unverified `external-unspecified` egress for production residency evidence.
The runtime pins the startup profile, reloads it before each call, emits the distinct
`EGRESS_ALLOWED_DEVELOPMENT` code, and rejects this operating mode in staging and production. The
residual risk is compromise of process/configuration authority; response is to stop provider egress,
rotate credentials and review tenant-scoped egress audit records.

The asynchronous v0.5 boundary adds job theft, duplicate cost, stale leases and cross-tenant Worker
privilege. Controls are hashed lease tokens, periodic current-time heartbeats, conditional
transitions, atomic budget/job submission, provider-boundary cancellation, bounded retries, stale
recovery and a database role limited to queue tables. Lease loss prevents later domain or terminal
writes by the old Worker. Residual risk is an in-flight provider-side effect that cannot be recalled
after the remote provider accepted it; reconcile provider request IDs and stop on unexplained budget
anomalies.

