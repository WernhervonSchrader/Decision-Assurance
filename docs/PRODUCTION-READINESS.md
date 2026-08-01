# Production readiness — v0.5

Status: **controlled-pilot candidate**. A CI `PASS` proves the repository's technical gates; it is not
a certification or permission to deploy real customer data.

Implemented and continuously verified:

- PostgreSQL migration, tenant-composite keys, forced RLS and least-privilege runtime roles;
- strict OIDC/JWKS authentication, server-side authorization and human-only approval;
- durable asynchronous Research jobs, idempotency, budgets, cancellation and recovery;
- external secrets, exact HTTPS egress, redacted logs, bounded metrics and readiness;
- non-root API/Worker containers, native backup/restore verification and rollback guidance;
- dependency/secret/static/container scans, CycloneDX SBOM, checksums and computed release report;
- two-tenant DE/EN controlled pilot with no live provider dependency.

Deployment owners must still supply and validate managed OIDC, PostgreSQL with backups/PITR and
encryption, network egress enforcement, secret rotation, TLS edge controls, monitoring/on-call,
branch/environment protection, retention/deletion/export/legal-hold processes, capacity/load evidence,
disaster-recovery objectives and regulatory approval. Any missing mandatory CI or operational evidence
is `BLOCK`; no unavailable check is treated as a pass.

## Controlled-pilot v0.8 boundary

Repository evidence now covers the Caddy/UI images, BFF PKCE/session contracts, deterministic
two-tenant browser tests, portable export validation and physical deletion with legal-hold checks.
This closes repository implementation gates only. Real DNS/certificates, managed secrets, MFA,
external monitoring, measured backup/restore, load tests, on-call readiness, provider residency and
organizational approval remain deployment evidence and therefore block production release.
