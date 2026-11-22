# Transition Policy — Public Draft v0.2.0

The executable policy is implemented in
[`transitions.py`](../src/decision_assurance/transitions.py). No other component
may change `status`.

| From | To | Actor | Preconditions | Audit event | Rejection examples |
| --- | --- | --- | --- | --- | --- |
| DRAFT | VALIDATION | separate `VALIDATOR` | actor is not generator | `status.transitioned` | unauthorized role, role collision |
| DRAFT | BLOCKED | `VALIDATOR` | a recorded blocking reason exists | `status.transitioned` | missing block reason |
| VALIDATION | REVIEW | `VALIDATOR` | outcome is not `BLOCK` | `status.transitioned` | block must remain blocked |
| VALIDATION | BLOCKED | `VALIDATOR` | blocking outcome/reason | `status.transitioned` | missing block reason |
| REVIEW | APPROVED | human, separate `APPROVER` | `PASS`; mandatory constraints satisfied; no unresolved critical conflict; mandatory reviews satisfied; approval digest and nonce valid; action digest matches | `status.transitioned` | missing authority/evidence/review, replay, digest mismatch, role collision |
| REVIEW | BLOCKED | human `APPROVER` | rejection/block reason | `status.transitioned` | unauthorized role |

`APPROVED` and `BLOCKED` are terminal in v0.2.0. Reopening is intentionally not
defined: a changed material fact starts a new versioned Decision File. This
prevents a blocked result from being silently converted into approval. Every
authorized transition records actor, source, target, time, reasons, payload hash
and the hash of the previous event.


## B3 server-owned lifecycle boundary (proposed security correction)

`POST /v1/decisions` creates only an unapproved `DRAFT`: no approvals, engine outcome,
validation results, outcome reasons, satisfied reviews or caller-supplied audit history.
These assertions are rejected with 422 before an idempotent create replay is returned.
They are never silently converted into authority. Server-side compilers may supply their
own provenance audit but the repository initial-authority guard also requires an
unapproved DRAFT. Parsing/validating an exported historical file does not authorize import.

An API approval requires an authenticated HUMAN with the explicit APPROVER role and
`decision:approve` permission, independent of generator, requester and prior validator.
The server generates the nonce, approver identity and approval time during that request;
`approval_digest()` is a public integrity hash, not a credential or human signature.
No request body may supply actor/approval fields to the transition endpoint.

The API transition audit reason `DECISION_SNAPSHOT_BOUND_V1` selects this payload hash:
`{tenant_id, from, to, actor, after_document_hash}`. `after_document_hash` hashes the
complete resulting Decision File with its final transition event removed from
`audit_events`. This binds all claims, evidence, action, policy versions, reviews and
approvals and can be recomputed from the stored result. The existing previous-event
hash links the prior event; it does not independently prevent a database writer from
rewriting history (B6). Offline TransitionPolicy audit format is unchanged.

Repository `save_result` requires the exact `expected_document` read by the caller.
A tenant-qualified atomic compare-and-set commits document/report/audit/idempotency
only while that snapshot remains current; mismatch/deletion returns 409 through the
API with `DECISION_DOCUMENT_CHANGED`. Internal repositories are trusted server ports,
not authenticated approval APIs. All untrusted approval requests must use the API.
APPROVED and BLOCKED cannot be evaluated again through the API, including old-key
replays. Repeated approval with the same valid actor/key returns the historic response
without issuing a new nonce/event; a fresh-key repeat is rejected by terminal policy.

No stored legacy approval is retroactively authenticated. Before production use,
operators must review/quarantine potentially affected legacy records and verify the
real OIDC, database and audit deployment. This draft binds the server-time snapshot;
it does not add a client-reviewed-version precondition or attest what a human read.
An APPROVED Decision File still does not implement external execution authority.
