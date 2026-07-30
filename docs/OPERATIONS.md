# Production operations runbook

Production telemetry, security logs, business events and tenant audit records are distinct. Never
log bearer tokens, complete Decision Files, Research queries, extracted text, raw provider responses
or unnecessary personal data.

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
