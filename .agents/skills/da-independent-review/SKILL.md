---
name: da-independent-review
description: Perform a Decision Assurance architecture, security, contract, remediation-closure, implementation-readiness, implementation, evidence or owner-release review in SOLO_OWNER or INDEPENDENT mode. Use for PASS/FAIL, finding closure, implementation readiness, publication eligibility and cross-contract validation. Follow the shared policy and disclose actual independence.
---

# Decision Assurance Review — Solo Owner or Independent

This skill is an operational adapter only. It defines no material review rule.

Before any review, read and apply in full:

- repository-root `AGENTS.md`;
- `docs/governance/DA-INDEPENDENT-REVIEW-POLICY.md`;
- the primary artifacts required by the policy's declared scope and Coverage Matrix.

If this adapter and the shared policy differ, follow the policy's explicit scoped precedence and
report adapter drift. Do not reinstate a process-only independence gate superseded by section 6.
Do not treat this file as authority for fields, severity, independence,
coverage, evidence or verdict semantics.

## Operational sequence

1. Validate and record the exact repository, branch, revision/diff and artifact scope.
2. Load `AGENTS.md`, the shared policy and primary artifacts directly.
   Declare the policy's adopted `SOLO_OWNER` mode unless `INDEPENDENT` is required for the scope.
3. Execute the policy's Required Review Procedure in order.
4. Produce every matrix and output field required by the policy for the declared review lifecycle.
5. Return the policy-defined verdict and implementation-authorization statement separately.
   For publication, also report owner decision, exact release basis and publication eligibility.

Review work is read-only unless remediation is authorized. After remediation, assess the final
primary artifacts in a distinct review step. `SOLO_OWNER` permits the same actor/session with
disclosure; a separate session or model is recommended but not mandatory. `INDEPENDENT` requires
the policy's actual separation. A technical `PASS` never supplies human owner release authority.
