# Backup and restore

`scripts/postgres/backup.ps1` creates a PostgreSQL custom-format logical backup plus a manifest with
schema version, size and SHA-256 checksum. The destination must be an access-controlled,
platform-encrypted store with immutable retention. The script does not make local disk encrypted.

Restore is permitted only into a fresh isolated database. `restore.ps1` verifies the manifest and
checksum before `pg_restore --single-transaction --exit-on-error`, then runs `verify_restore.py`.
Verification blocks on migration mismatch, missing/disabled/unenforced RLS, unsafe database roles or
audit ordering anomalies. Afterward, run the full two-tenant RLS, OIDC, queue recovery and controlled
pilot smoke suites before any traffic switch.

Pilot targets are RPO 24 hours and RTO 4 hours unless the deployment owner documents stricter
platform-backed PITR objectives. Run a restore drill before pilot start and at least quarterly;
record backup reference, checksum, timings, verifier report, operator and approver. Corrupt or
unverifiable backups are `BLOCK`, not `REVIEW`.
