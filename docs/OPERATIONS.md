# Operations and Incident Notes

`/health/live` verifies process availability; `/health/ready` verifies database
access. Back up the SQLite database only from a quiesced service or through a
SQLite-consistent backup mechanism. Restore into an isolated environment,
verify `PRAGMA integrity_check`, run the full tests/smoke journey, then switch
traffic. Backup encryption, retention and restore drills belong to the operator.

On suspected tenant leakage, token compromise or audit inconsistency: stop
writes, revoke affected identities upstream, preserve database and logs, record
the incident correlation IDs, assess tenant scope, notify accountable owners,
restore only from verified state and document corrective controls. Never edit
audit rows to conceal an incident.

Operational logs, security logs, business events and audit records are distinct.
Do not log bearer tokens, complete Decision Files or unnecessary personal data.

