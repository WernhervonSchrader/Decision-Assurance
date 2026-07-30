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

## Secret rotation

Publish the new reference version, invalidate controlled caches, restart affected processes and
verify authentication/provider/database probes. Retain the prior reference only for the documented
overlap window; revoke it after successful verification.

## Worker recovery

Confirm heartbeat loss, stop the old instance, then run stale-lease recovery. Conditional lease
ownership guarantees that only the current token can complete a job. Investigate repeated dead
letters before replay; cancellation must remain effective.

## Tenant isolation or audit suspicion

Stop the pilot immediately, preserve database/audit/log evidence, revoke affected credentials and
test RLS with both tenants. Do not export cross-tenant rows for diagnosis. Any confirmed isolation or
audit-integrity failure is a release/pilot `BLOCK` condition.
