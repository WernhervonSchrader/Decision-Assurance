# Threat Model — API v0.2

Assets are Decision Files, evidence references, approvals, reports, audit
history, tenant configuration and identities. Actors are tenant users, agents,
auditors, administrators and attackers. Trust boundaries exist at HTTP input,
authentication, tenant resolution, authorization, repository access and any
future identity provider.

| Threat | Likelihood / impact | Prevention and detection | Response / residual risk |
| --- | --- | --- | --- |
| Cross-tenant IDOR | medium / critical | tenant-scoped repository keys; non-enumerating 404; isolation tests | alert on denied probes; SQLite lacks RLS defense-in-depth |
| Tenant spoofing | high / critical | tenant only from verified identity context; body rejects tenant fields | revoke identity; IdP compromise remains material |
| Agent impersonates human | medium / high | identity `kind`; transition policy; role separation | audit and block; compromised human account remains |
| Role escalation | medium / high | centralized permission matrix and object authorization | security audit; bad upstream role mapping remains |
| Audit tampering | low / critical | append-only API and hash chain | integrity verification; DB administrator remains trusted in v0.2 |
| Replay/idempotency abuse | medium / medium | scoped keys plus payload hash | conflict event; storage exhaustion requires rate limits |
| Injection/mass assignment | medium / high | strict typed schemas; parameterized SQL; unknown fields forbidden | reject and correlate; dependency defects remain |
| Oversized/DoS input | high / medium | body, page and string limits; timeouts at deployment boundary | throttle/block source; distributed DoS external |
| Secret/token disclosure | low / high | header/body redaction; no secrets in repo; generic errors | rotate/revoke; operator logging mistakes remain |
| Supply-chain compromise | low / high | bounded dependencies, lock/build and vulnerability scans | pin/remediate; zero-day risk remains |

Production rollout remains blocked until OIDC, PostgreSQL RLS, edge limits and
operational monitoring are integrated.

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

