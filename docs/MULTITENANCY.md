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

Operating Profiles v0.6 are deployment-wide immutable policy, never tenant configuration. OIDC still
establishes tenant identity; provider host/location, country declarations and mode are absent from
API and MCP schemas. Unknown fields such as `tenant_id` in provider egress configuration fail
startup. One tenant therefore cannot choose a different provider, country, secret, cache namespace,
job route, backup or support boundary.

Retention, export and deletion schedules may differ by tenant only through a separately authorized
operator workflow. An export must establish one transaction-local tenant context, verify that every
record and manifest entry has that tenant ID, and use a destination allowed by the active profile.
Deletion must preserve isolation and cover tenant-owned domain, Intake, Research, job, cache and
provider data plus documented backup expiry. Cross-tenant bulk export/deletion and administrative
bypass remain unsupported and are a production `BLOCK` until explicit authorization, audit and
two-tenant negative tests exist.

Keycloak's admin-managed `tenant_id` token claim is the only local OIDC tenant authority. A differing
`X-Tenant-ID`, path tenant or top-level JSON `tenant_id` produces `AUTH_TENANT_MISMATCH` before a
handler, database or external provider is called. `da_admin` has no implicit bypass; an attempted
cross-tenant assertion is denied as `AUTH_CROSS_TENANT_DENIED` and audited.
