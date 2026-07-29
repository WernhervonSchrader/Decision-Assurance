# Decision File Contract — Public Draft v0.1.0

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
| `schema_version` | `"0.1.0"` | Contract version; exact match required. |
| `decision_id` | stable identifier | 1–128 safe filename characters; immutable. |
| `title`, `description`, `use_case` | non-empty strings | Human title, scope and domain profile. |
| `status` | `DRAFT`, `VALIDATION`, `REVIEW`, `APPROVED`, `BLOCKED` | Lifecycle state, changed only by the Transition Policy. |
| `assurance_level` | `BASIC`, `STANDARD`, `HIGH` | Declared rigor; not a certification. |
| `created_at`, `updated_at` | RFC 3339 date-times | Creation is immutable; update time advances on transitions. |
| `created_by`, `current_owner` | actor | Actor identity, role and kind (`HUMAN`, `AGENT`, `SERVICE`). |
| `claims` | non-empty claim array | Statements being assessed; IDs are case-local references. |
| `evidence` | evidence array | Sources mapped to claims with explicit verification status. |
| `assumptions` | assumption array | Accepted, unverified or rejected premises. |
| `constraints` | constraint array | Mandatory, review-required or advisory rules and satisfaction state. |
| `policies` | policy array | Versioned policy references and review requirements. |
| `risks` | risk array | Impact and unresolved uncertainty used by governance. |
| `conflicts` | conflict array | Explicit contradictions; unresolved critical conflicts block approval. |
| `validation_results` | validation array | Versioned actor result, reasons and timestamp. |
| `review_requirements` | requirement array | Human roles that must act before approval. |
| `approvals` | approval array | Human review decisions; an agent cannot create valid human authority. |
| `decision_outcome` | `PASS`, `REVIEW`, `BLOCK`, or `null` | Deterministic governance result, distinct from lifecycle status. |
| `outcome_reasons` | unique reason-code array | Complete machine-readable explanation of the outcome. |
| `audit_events` | audit-event array | Ordered, hash-linked material lifecycle events. |

Referential integrity and role separation are semantic validations performed by
the engine and Transition Policy in addition to JSON Schema validation. Examples
are in [`examples/decision-cases`](../examples/decision-cases).

