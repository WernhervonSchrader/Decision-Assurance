# Transition Policy — Public Draft v0.1.0

The executable policy is implemented in
[`transitions.py`](../src/decision_assurance/transitions.py). No other component
may change `status`.

| From | To | Actor | Preconditions | Audit event | Rejection examples |
| --- | --- | --- | --- | --- | --- |
| DRAFT | VALIDATION | separate `VALIDATOR` | actor is not generator | `status.transitioned` | unauthorized role, role collision |
| DRAFT | BLOCKED | `VALIDATOR` | a recorded blocking reason exists | `status.transitioned` | missing block reason |
| VALIDATION | REVIEW | `VALIDATOR` | outcome is not `BLOCK` | `status.transitioned` | block must remain blocked |
| VALIDATION | BLOCKED | `VALIDATOR` | blocking outcome/reason | `status.transitioned` | missing block reason |
| REVIEW | APPROVED | human, separate `APPROVER` | `PASS`; mandatory constraints satisfied; no unresolved critical conflict; mandatory reviews satisfied | `status.transitioned` | missing authority/evidence/review, role collision |
| REVIEW | BLOCKED | human `APPROVER` | rejection/block reason | `status.transitioned` | unauthorized role |

`APPROVED` and `BLOCKED` are terminal in v0.1.0. Reopening is intentionally not
defined: a changed material fact starts a new versioned Decision File. This
prevents a blocked result from being silently converted into approval. Every
authorized transition records actor, source, target, time, reasons, payload hash
and the hash of the previous event.

