# Recovery evidence and RPO/RTO

The recovery drill records environment, exact commit, data volume, backup/failure/restore timestamps,
latest restored record, audit/export/tenant-integrity checks and target versus observed RPO/RTO.
`recovery-evidence.schema.json` labels the result `TEST_OBSERVATION_NOT_SERVICE_COMMITMENT`.

CI creates a PostgreSQL custom-format backup, restores fresh infrastructure, recomputes audit hash
links, exercises application-role tenant isolation, verifies an Ed25519 export built from restored
tenant data and decrypts pre-backup sessions through the shared store. The report generator consumes
that exact verifier JSON and binds its SHA-256 digest; it cannot assert the checks independently.
The verifier report has an exact field set and is bound to the CI head, named environment, distinct
source/restore databases, PostgreSQL 16, schema 004, all forced-RLS tables, drill row counts,
post-backup data absence and completion timestamp. Minimal or relabeled `PASS` JSON is rejected. A
real pilot must repeat this with representative scale on actual infrastructure.

The verifier enumerates all 28 tables declared with `FORCE ROW LEVEL SECURITY` across migrations
001-004, including private browser sessions, Intake/Research/idempotency/budget/handoff/runtime-limit
tables and the acceptance ledger. Database names, PostgreSQL version number, counts, booleans,
environment, timestamps and commit identifiers are type- and format-checked rather than coerced.
