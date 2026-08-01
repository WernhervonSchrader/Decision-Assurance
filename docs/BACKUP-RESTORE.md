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

## Operating-profile placement and disaster recovery

The backup manifest must also record operating mode, reviewed configuration hash, tenant set,
storage country/boundary, encryption-key reference, retention expiry and restore target. For `local`,
backup storage, key custody, support access and the fresh restore target remain `local`. For
`eu-managed`, primary, replica/PITR, backup and restore locations must be declared EU country codes
with current evidence. Replication or emergency copies outside the active profile are forbidden;
there is no automatic cross-jurisdiction disaster-recovery fallback.

Before restore, compare the backup profile/configuration hash with the intended target. A profile or
country change requires a separately approved migration, not a routine restore. After technical
verification, reapply the protected tenant deletion ledger so expired or erased tenant data is not
silently reactivated, then run two-tenant isolation, OIDC, queue, provider-egress and DE/EN smoke
tests. Switch traffic only with recorded operator and independent approver sign-off.

Disaster response prioritizes confidentiality and tenant isolation over RTO. If no compliant target
is available, remain unavailable and declare the recovery incident rather than restoring to an
undeclared region. Record actual RPO/RTO, lost job window, provider side effects, config/evidence
hashes and corrective action. Quarterly drills must exercise both selected profile placement and a
negative restore to a prohibited location, which must fail closed.

The local Keycloak PostgreSQL volume is a separate backup domain. Never merge it into the Decision
Assurance application database or reuse application credentials. Back it up in PostgreSQL custom
format to encrypted restricted storage and restore only into a fresh isolated Keycloak database;
then run realm contracts, PKCE/JWKS authentication, tenant denial, role/actor-independence and
restart-persistence tests. Restore never replays initial bootstrap automatically. If administrator
recovery is required, keep all regular Keycloak nodes stopped, run the profile-gated
`bootstrap-admin user` service once, canary-scan its captured output without displaying it, restore
permanent administration, delete the temporary identity and start the regular service without
bootstrap secret mounts. Production Keycloak RPO/RTO, PITR and geographic placement require a
separate approved service design.

For controlled-pilot data, restore only into an isolated fresh PostgreSQL 16 database, apply roles,
verify migration `003`, validate forced RLS for every tenant table, verify lifecycle event chains and
reapply the protected deletion ledger before reconnecting edge/worker traffic. Prove one retained case,
one completed deletion tombstone and one legal hold, then repeat cross-tenant export/read/delete denial.
Record archive hash, operator, verifier, start/end time and RPO/RTO; repository tests do not constitute
a measured deployment restore.
