# Retention, deletion and legal hold

Migration `003` stores a tenant-scoped retention policy, active legal holds, deletion requests and a
hash-linked lifecycle audit. The pilot policy is configuration, not a scheduler: an authorized tenant
administrator requests and explicitly executes deletion. Idempotency is bound to pseudonymized actor,
tenant and key; reuse for another case or reason is rejected.

Execution acquires the same tenant/case PostgreSQL advisory lock used by decision writes, rechecks the
hold inside the transaction, and physically removes research jobs/events/content, intake facts and
records, reports, decision audit/idempotency data and the decision. An active hold returns
`BLOCKED_BY_HOLD`; no covered row is removed. The minimized tombstone retains only HMAC case/actor/key
references, reason/status/timestamps and hash-linked request/block/execute/result events. Raw case IDs,
actor IDs, tokens, content and provider payloads are not retained there.

Backups are immutable and expire under the separately approved backup retention schedule. Restore must
reapply completed deletions before service. Legal/audit retention, delayed backup expiry and the HMAC
key lifecycle require deployment-owner approval. There is no silent soft delete.
