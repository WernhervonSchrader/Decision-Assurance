# Incident response

New pilot-stop triggers include signature/key failure, suspected key disclosure, MFA downgrade,
shared-session compromise, evidence replay/tampering and failed recovery or alert delivery. Revoke
keys/sessions, block review, preserve redacted evidence and require independent re-approval.

1. Declare severity, incident lead, time and affected environment; stop the controlled pilot for any
   suspected secret disclosure, tenant crossover, audit corruption or unbounded provider spend.
2. Contain with credential revocation, egress disablement, queue cancellation or service removal from
   readiness. Preserve immutable evidence before restarting or restoring.
3. Determine scope using correlation IDs and tenant-local audit exports. Logs and metrics may locate
   the interval but cannot substitute for audit records.
4. Eradicate the cause through reviewed configuration, code, migration or provider controls. Rotate
   every potentially exposed credential and verify old references fail.
5. Recover into a verified state: migrations current, RLS negative tests passing, stale jobs handled,
   audit chains contiguous, backups restorable and required providers bounded.
6. Obtain human operational and governance approval before resuming. Record timeline, impact,
   evidence, decisions, residual risk and preventive actions.

Rollback uses the prior immutable image and compatible schema only. Forward-only database changes
require a tested compensating migration or restore into a fresh instance; never rewrite the migration
ledger or delete audit evidence.

The pilot-abort triggers are any tenant crossover, token/secret disclosure, broken audit persistence,
unexplained approval, deletion despite hold, provider egress bypass, sustained job backlog or TLS/private
key compromise. Disable external edge reachability first, revoke sessions/credentials as appropriate,
preserve redacted correlation IDs and immutable audit/export hashes, and avoid logging request bodies.
Reopening requires fresh negative isolation tests, audit-chain verification, restore evidence and a
separate human decision by security and pilot owners.
