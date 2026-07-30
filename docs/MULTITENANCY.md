# Multi-tenancy — v0.5

The normative implementation overview is [TENANCY.md](TENANCY.md). In v0.5, the tenant originates
only from a validated OIDC identity and is carried explicitly through API, Intake, Research, jobs,
handoffs, audit and persistence. Client bodies and query parameters cannot select a tenant.

Production PostgreSQL uses tenant-composite primary and foreign keys plus forced row-level security.
Application transactions set tenant context locally. Missing context returns no tenant rows. A
separate Worker role can claim queue records across tenants but cannot read Decision or Intake data;
tenant-domain processing returns to the application role. CI uses two tenants to prove read/write,
cache, audit, evidence and idempotency isolation. SQLite is development-only.

Cross-tenant administration, export, deletion, suspension and legal hold are not pilot features.
They require explicit authorization, tenant-scoped audit and a reviewed retention workflow before
real regulated data is admitted.
