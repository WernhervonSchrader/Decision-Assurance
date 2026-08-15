# Decision File Contract — Public Draft v0.2.0

The Decision File is the normative, vendor-neutral exchange contract for one
Decision Assurance case. The JSON Schema at
[`schemas/decision-file.schema.json`](../schemas/decision-file.schema.json) is
authoritative for syntax; this document defines field semantics.

All top-level fields are required so that tools cannot silently confuse an
omitted value with an empty or unresolved value. Arrays may be empty where the
schema permits it. Unknown fields and unsupported `schema_version` values are
rejected. A newer version must be migrated explicitly; readers must never guess
its meaning. Patch releases may clarify documentation but must not change the
meaning of an existing valid document.

| Field | Type / values | Meaning and validation |
| --- | --- | --- |
| `schema_version` | `"0.2.0"` | Contract version; exact match required. |
| `decision_id` | stable identifier | 1–128 safe filename characters; immutable. |
| `title`, `description`, `use_case` | non-empty strings | Human title, scope and domain profile. |
| `status` | `DRAFT`, `VALIDATION`, `REVIEW`, `APPROVED`, `BLOCKED` | Lifecycle state, changed only by the Transition Policy. |
| `assurance_level` | `BASIC`, `STANDARD`, `HIGH` | Declared rigor; not a certification. |
| `created_at`, `updated_at` | RFC 3339 date-times | Creation is immutable; update time advances on transitions. |
| `created_by`, `current_owner` | actor | Actor identity, role and kind (`HUMAN`, `AGENT`, `SERVICE`). |
| `requested_by` | actor | Principal requesting the decision or action; included in every approval digest. |
| `canonical_action` | action or `null` | Canonical execution intent. `null` means that the Decision File authorizes no external action. |
| `claims` | non-empty claim array | Statements being assessed; IDs are case-local references. |
| `evidence` | evidence array | Sources mapped to claims with explicit verification status. |
| `assumptions` | assumption array | Accepted, unverified or rejected premises. |
| `constraints` | constraint array | Mandatory, review-required or advisory rules and satisfaction state. |
| `policies` | policy array | Versioned policy references and review requirements. |
| `risks` | risk array | Impact and unresolved uncertainty used by governance. |
| `conflicts` | conflict array | Explicit contradictions; unresolved critical conflicts block approval. |
| `validation_results` | validation array | Versioned actor result, reasons and timestamp. |
| `review_requirements` | requirement array | Human roles that must act before approval. |
| `approvals` | approval array | Human decisions bound to requester, approver, case, action digest and single-use nonce. |
| `decision_outcome` | `PASS`, `REVIEW`, `BLOCK`, or `null` | Deterministic governance result, distinct from lifecycle status. |
| `outcome_reasons` | unique reason-code array | Complete machine-readable explanation of the outcome. |
| `audit_events` | audit-event array | Ordered, hash-linked material lifecycle events. |

Referential integrity and role separation are semantic validations performed by
the engine and Transition Policy in addition to JSON Schema validation. Examples
are in [`examples/decision-cases`](../examples/decision-cases).

## Canonical action

An action-bearing Decision File records `action_id`, `action_type`, semantic
`effect`, complete `target`, typed JSON `parameters`, `tenant_id`, an
`execution_context_hash`, and one of these reversibility classes:

- `READ_ONLY`
- `REVERSIBLE`
- `EXTERNALLY_REVERSIBLE`
- `IRREVERSIBLE`

`canonical_digest` is the SHA-256 digest of JSON serialized with UTF-8,
lexicographically sorted object keys, no insignificant whitespace and the
`canonical_digest` field omitted. The reference function is
`canonical_action_digest`. A changed parameter, target, tenant, context or
reversibility class invalidates the digest. Every non-read-only action requires
a mandatory `APPROVER` review requirement.

## Approval binding and replay protection

An approval records the independently attributable `approver`, decision time,
the matching `action_digest` or `null`, and a 128-bit-or-stronger base64url-style
single-use `nonce`. `approval_digest` binds the following canonical payload:

`decision_id`, `requested_by`, `requirement_ref`, `approver`, `decision`,
`decided_at`, `action_digest`, `nonce`.

The engine rejects reused nonces, requester/approver or generator/approver role
collisions, non-human approval, mismatched requirement roles, stale action
digests and modified approval payloads. Verification of these fields proves
integrity and binding; it does not by itself prove that the named human
controlled the identity provider. Deployment evidence must establish that
separately.

## Migration from v0.1.0

`migrate_decision_file_v0_1_to_v0_2` migrates only Decision Files without
approvals. It sets `requested_by` to the existing `created_by` identity and
`canonical_action` to `null`; it never invents action authority. A v0.1.0 file
containing approvals requires independent re-approval under v0.2.0 because no
nonce or cryptographic binding existed in the older record.
