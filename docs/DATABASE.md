# PostgreSQL operations

Production uses PostgreSQL 16 with explicit SQL and psycopg v3. Migrations `001` and `002` are applied
out of band under an advisory lock and recorded with SHA-256 checksums. A changed applied migration,
sequence gap or unknown target fails closed.

Every business table carries `tenant_id`; primary, unique and foreign keys include the tenant where a
relationship exists. Row-level security is enabled and forced. Application sessions set the tenant
transaction-locally. Missing context sees no rows. The queue Worker role is a narrow exception: an
explicit policy grants cross-tenant scheduling access only to Research job, job-event and limit
tables; domain work uses a separate tenant-scoped application connection.

Roles are non-login capability groups: migration, application, Worker, operations-read and
audit-export. Deployment-created login roles inherit one group. None is superuser or has
`BYPASSRLS`, `CREATEDB` or `CREATEROLE`; the application cannot modify the migration ledger.

Monitor connection saturation, transaction age, locks, replication/PITR lag, storage growth, stale
worker leases and migration version. Vacuum/analyze, HA, TLS, encryption at rest, PITR and regional
failover remain platform responsibilities and must be evidenced before pilot use.
