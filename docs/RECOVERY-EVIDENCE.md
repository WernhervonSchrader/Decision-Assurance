# Recovery evidence and RPO/RTO

The recovery drill records environment, exact commit, data volume, backup/failure/restore timestamps,
latest restored record, audit/export/tenant-integrity checks and target versus observed RPO/RTO.
`recovery-evidence.schema.json` labels the result `TEST_OBSERVATION_NOT_SERVICE_COMMITMENT`.

CI creates a PostgreSQL custom-format backup, restores fresh infrastructure, recomputes audit hash
links, exercises application-role tenant isolation, verifies an Ed25519 export built from restored
tenant data and decrypts pre-backup sessions through the shared store. The report generator consumes
that exact verifier JSON and binds its SHA-256 digest; it cannot assert the checks independently. A
real pilot must repeat this with representative scale on actual infrastructure.
