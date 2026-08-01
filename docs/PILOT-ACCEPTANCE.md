# Controlled pilot acceptance checklist

## Repository CI evidence

- [ ] Ruff, Mypy strict, Python tests, PostgreSQL 16, OpenAPI drift and package builds pass.
- [ ] UI typecheck/unit/build, Chromium two-tenant E2E and npm audit pass.
- [ ] Secret/SAST/dependency scans, Compose/Caddy checks, image non-root checks, Trivy and SBOM pass.
- [ ] Export validates audit chains offline; atomic delete/audit, append-only hold history,
  lifecycle concurrency, similarly named IDs and tenant-isolation tests pass.
- [ ] OIDC callback is initiating-browser bound; callback query credentials are absent from logs.
- [ ] The identity edge exposes only allowlisted realm OIDC/login resource paths, never admin/account.

## Local integration evidence

- [ ] Real Keycloak PKCE login/logout, rotation/restart and Research regression pass.
- [ ] TLS/header smoke proves HTTP redirect, hostname allowlist and fixed routes.
- [ ] Two different human actors complete validation and approval; second tenant receives only 404.

## Deployment evidence

- [ ] Controlled DNS/TLS, managed secrets/rotation, MFA, encrypted PostgreSQL and provider residency are approved.
- [ ] Monitoring/on-call alerts, capacity, immutable backups, measured restore and rollback are witnessed.
- [ ] Retention, deletion ledger, legal hold, incident contacts and pilot-abort authority are assigned.

## Organizational and production gates

- [ ] Security/architecture independently reviews the exact commit with no blocking finding.
- [ ] Pilot owner accepts the named tenant/users/data class and residual risks.
- [ ] Production approval is separately signed. CI, local integration or pilot approval alone is never production approval.
