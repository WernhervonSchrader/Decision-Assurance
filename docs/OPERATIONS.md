# Production operations runbook

Production telemetry, security logs, business events and tenant audit records are distinct. Never
log bearer tokens, complete Decision Files, Research queries, extracted text, raw provider responses
or unnecessary personal data.

## Operating-profile preflight

For every rollout, compare the reviewed config hash with the deployed read-only file. Confirm exactly
one mode, complete storage/processing/backup/support/external-processing locations, exact
`provider_egress`/allowlist host equality, provider-location membership, OIDC issuer/audience/JWKS,
separate PostgreSQL roles, retention owner and restore target. `local` requires every core and
provider location to be `local`; `eu-managed` requires EU country codes and current HTTPS residency
and subprocessor evidence. Run two-tenant DE/EN smoke tests after migrations and before traffic.

Missing or contradictory residency, provider, identity, database or secret configuration is not a
degraded mode. Keep API, Worker and MCP out of readiness; do not fall back to SQLite, static tokens,
environment secrets, another provider, region or operating mode.

The SQLite reference profile is not a production datastore. If it is used for local evaluation,
back it up only from a quiesced process or through a SQLite-consistent backup, verify
`PRAGMA integrity_check`, and restore only into an isolated test environment.

## Database or migration failure

Remove the API and Worker from readiness, stop migration retries, preserve the failing migration and
ledger evidence, and verify role/RLS state. Restore only into a fresh target. Never grant the
application migration ownership or `BYPASSRLS` to recover service.

## Provider outage or backlog

Keep the Engine and existing evidence readable. Allow bounded retries to enter `RETRY_WAIT`; do not
increase tenant budgets automatically. Pause new Research submission when oldest-job age or dead
letters exceed the pilot limit. Resume after a controlled synthetic request succeeds.

## Residency or provider-egress incident

Immediately pause Research submission and disable the affected outbound route. Preserve the config
file and hash, image digest, DNS resolution, provider/access/support logs, job IDs, audit correlation
IDs and evidence review record without copying tenant content into operational logs. Identify all
affected tenants, data classes, provider calls, countries and time windows. Revoke provider secrets
and privileged sessions when exposure is possible; do not redirect traffic to an undeclared backup
provider or country.

For `local`, verify endpoint ownership and that storage, computation, backup and support stayed in the
operator boundary. For `eu-managed`, verify every observed country remains in the EU declaration and
review DPA/subprocessor/control-plane evidence. The incident owner performs contractual and legal
notification assessment. Resume only after corrected read-only configuration, credential rotation,
provider synthetic probes, configuration contracts, two-tenant RLS tests and deployment approval.

## MCP authentication or tool failure

Keep MCP out of readiness when OIDC metadata, exact Host/Origin policy, PostgreSQL, Worker or schema
compatibility fails. Compare correlation IDs with protected API/Worker logs without recording bearer
tokens or tool payloads. A missing role remains a denial, not an operations override. If tool
discovery exposes anything beyond the five approved tools, remove the process from service and treat
it as a release-security incident.

## Secret rotation

Publish the new reference version, invalidate controlled caches, restart affected processes and
verify authentication/provider/database probes. Retain the prior reference only for the documented
overlap window; revoke it after successful verification.

## Worker recovery

The Worker renews a running lease every one third of its configured lease duration and uses a fresh
UTC timestamp for every heartbeat, completion and failure write. Heartbeat rejection or an
unavailable cancellation check is treated as lost ownership: the Worker stops before the next
provider or persistence boundary and must not write a terminal job state. Confirm heartbeat loss,
stop the old instance, then run stale-lease recovery. Conditional lease ownership guarantees that
only the current token can complete a job. Investigate repeated dead letters before replay;
cancellation must remain effective between search, each extraction, compilation and handoff.

## Tenant isolation or audit suspicion

Stop the pilot immediately, preserve database/audit/log evidence, revoke affected credentials and
test RLS with both tenants. Do not export cross-tenant rows for diagnosis. Any confirmed isolation or
audit-integrity failure is a release/pilot `BLOCK` condition.

## Retention, export and deletion operations

Maintain an approved tenant schedule covering live domain data, Intake/Research evidence, jobs,
audit, provider copies and backups. General automated tenant export/deletion is not implemented.
Requests that cannot be satisfied by a reviewed tenant-scoped procedure remain blocked. A permitted
manual export uses a dedicated role, one tenant context, encrypted destination, record counts and
hash manifest plus independent approval; verify a second tenant is absent before release.

Deletion uses the same tenant boundary and records authorization, scope, counts, provider deletion
receipt, backup-expiry date and verifier. Do not edit immutable backups or audit chains. Prevent a
later restore from reactivating deleted data by maintaining a protected deletion ledger and running
the approved suppression/re-deletion step after restore. Any cross-tenant result stops the operation
and triggers the tenant-isolation incident procedure.
