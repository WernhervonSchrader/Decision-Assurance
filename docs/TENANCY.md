# Tenant Model

`TenantContext(tenant_id)` is established by the authentication adapter and is
never accepted from a Decision File, query string or request body. Every
repository method requires it explicitly. Tenant-owned tables and audit events
carry `tenant_id`; case identity is tenant-scoped.

Cross-tenant business administration is absent from v0.5. Export, deletion, retention,
suspension and restore are future administrative workflows and must remain
tenant-scoped and audited. SQLite remains development-only. PostgreSQL uses tenant-composite keys,
transaction-local tenant context and forced RLS. A narrowly scoped Worker role may claim queue rows
across tenants but cannot read Decisions or Intake.

Research runs, sources, snapshots, evidence, attempts, audit, budgets, idempotency and handoffs use
tenant-composite primary, foreign and unique keys. Snapshot cache lookup includes the authenticated
tenant. CI proves RLS, missing-context failure, role boundaries and cross-tenant denial for all
material domains. Physical database separation remains a later option for regulatory isolation or
independent deployment needs.

