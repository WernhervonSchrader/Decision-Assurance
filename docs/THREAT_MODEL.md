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

OIDC, PostgreSQL RLS, redacted observability and release gates are implemented. Rollout remains
blocked until the deployment owner supplies managed identity/database/secrets, edge controls,
monitoring/on-call, retention/deletion and regulatory evidence described in Production Readiness.

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
include repeated URL validation, public-only addressing, fixed scrape options, normalization,
composite tenant keys, atomic budgets, bounded attempts and human-review markers. DNS changes
between adapter validation and remote provider retrieval remain an upstream/provider risk.

The asynchronous v0.5 boundary adds job theft, duplicate cost, stale leases and cross-tenant Worker
privilege. Controls are hashed lease tokens, periodic current-time heartbeats, conditional
transitions, atomic budget/job submission, provider-boundary cancellation, bounded retries, stale
recovery and a database role limited to queue tables. Lease loss prevents later domain or terminal
writes by the old Worker. Residual risk is an in-flight provider-side effect that cannot be recalled
after the remote provider accepted it; reconcile provider request IDs and stop on unexplained budget
anomalies.

