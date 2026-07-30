# Tenant Model

`TenantContext(tenant_id)` is established by the authentication adapter and is
never accepted from a Decision File, query string or request body. Every
repository method requires it explicitly. Tenant-owned tables and audit events
carry `tenant_id`; case identity is tenant-scoped.

Cross-tenant administration is absent from v0.2. Export, deletion, retention,
suspension and restore are future administrative workflows and must remain
tenant-scoped and audited. SQLite is the reference implementation; PostgreSQL
RLS is required before a production multi-tenant deployment claim.

Research runs, sources, snapshots, evidence, attempts, audit, budgets, idempotency and handoffs use
tenant-composite primary, foreign and unique keys. Snapshot cache lookup includes the authenticated
tenant. SQLite has no row-level security; production evolution requires PostgreSQL RLS,
least-privilege roles and migration tests before claiming database-enforced isolation.

