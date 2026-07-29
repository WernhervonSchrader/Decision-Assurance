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

