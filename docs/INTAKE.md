# Controlled Real-World Intake — Public Draft v0.3

Intake interprets untrusted input. The compiler translates verified intake state into a
Decision File. Only the Decision Assurance Engine evaluates that Decision File and produces
an assurance outcome.

The flow is `raw input → candidate facts → conflicts/gaps → verification or human confirmation
→ Decision File → DA Engine`. Intake uses its own contracts, lifecycle, repository protocol and
tenant-keyed tables. These tables share the v0.3 SQLite database with the existing engine; this
is logical separation, not a second database or service.

`tenant_id` is not part of the Intake Request contract. The API derives it only from the verified
identity. Raw policy, approval, role and outcome claims never replace the tenant Policy Registry,
authentication or governance engine. Extractor confidence describes parsing confidence, never
truth probability.

Compilation is fail-closed. Only `READY` reports whose used facts are `VERIFIED` or
`HUMAN_CONFIRMED` can be compiled. Missing mandatory data, conflicts and relevant unconfirmed
claims result in `NEEDS_CONFIRMATION`. The emitted Decision File has `decision_outcome: null`;
the existing evaluation path alone can produce `PASS`, `REVIEW` or `BLOCK`.

Corrections invalidate readiness until the complete tenant-policy verification has run again.
Approval thresholds count distinct authenticated human `APPROVER` identities, not repeated text
claims. Policy effective dates, evidence freshness, duration exceptions, approval completeness,
confirmed self-approval and governance-override attempts are deterministic derived findings.
Record, facts, confirmations, hash-linked Intake audit events and idempotency response are written
in one SQLite transaction. Compilation uses a deterministic decision ID so interrupted handoffs
converge safely on retry.

Contracts are versioned under `schemas/intake/`. Additive optional fields are permitted within a
compatible draft; new required fields, changed semantics or enum removals require a new schema
version. Public and packaged copies must stay byte-equivalent in meaning and are contract-tested.

Known limits: extraction is deliberately quote-focused and deterministic; it is not general
document understanding. Registry and Extractor are replaceable ports. The reference runtime uses
static development identities and SQLite, has no attachment ingestion, no external evidence
retrieval and no automatic retention/deletion job. Avoid real sensitive data unless deployment
controls provide an appropriate retention policy.
