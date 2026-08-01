# Recovery evidence and RPO/RTO

The recovery drill records environment, exact commit, data volume, backup/failure/restore timestamps,
latest restored record, audit/export/tenant-integrity checks and target versus observed RPO/RTO.
`recovery-evidence.schema.json` labels the result `TEST_OBSERVATION_NOT_SERVICE_COMMITMENT`.

CI creates a PostgreSQL custom-format backup, restores fresh infrastructure, checks migration, forced
RLS, safe roles and audit ordering, then emits the report. A real pilot must repeat this with
representative decisions, audit, Research, sessions and signed exports on actual infrastructure.
