# Runtime Contract v0.1 — Execution Evidence Binding

**Status:** Architecture draft for independent review

**Operating profile:** Development

**ADR:** [ADR-007](../adr/ADR-007-runtime-contract-execution-evidence.md)

**Issue:** [#10](https://github.com/WernhervonSchrader/Decision-Assurance/issues/10)

## 1. Objective and scope

Runtime Contract v0.1 connects an immutable Decision File v0.2 snapshot and its approved canonical
action to one controlled execution trajectory and a deterministic evidence-gated completion decision.
It defines a future contract boundary. It does not add fields to Decision File v0.2, execute an
action, create general tracing or grant organizational acceptance.

Research papers and external trajectory schemas are `ASSUMPTION_OR_RISK` inputs until mapped and
approved locally. The requirements below are proposed `PROJECT_CONTRACT` rules. Future test or
environment observations are `DEPLOYMENT_EVIDENCE`; they cannot authorize production.

## 2. Context assessment

At base `96b32da9e146b3b276c5fec4e636f67f6ea10889`:

- Decision File v0.2 binds canonical action, tenant, requester, approval digest and nonce.
- Transition Policy separates generator, validator and human approver and hash-binds approvals to
  the `APPROVED` transition.
- OIDC establishes tenant, actor, roles and actor kind; UI state is not authorization.
- PostgreSQL uses tenant context and forced RLS for material business records.
- Audit records are ordered/hash-linked; deployment acceptance has a separate append-only ledger.
- Deployment evidence distinguishes repository, integration, deployment and organizational gates.
- No execution authorization, `trajectory_ref`, attempt ledger or completion gate exists.

The principal risk is falsely reporting success for an action that differs from its approval, ran in
the wrong tenant or lacks valid execution evidence.

## 3. Requirements matrix

| ID | Requirement | Planned location | Test method | Completion evidence |
| --- | --- | --- | --- | --- |
| RC-01 | Standalone versioned contract; Decision File v0.2 unchanged | future runtime schemas | version/unknown-field tests | schema mirror and v0.2 hash checks |
| RC-02 | Bind tenant, Decision snapshot, action, approvals/nonces and constraints | canonicalization/policy | field-by-field tampering | deterministic fixtures |
| RC-03 | One authorization is consumed by at most one attempt | service/repository | replay and parallel reservation | one owner plus replay/conflict |
| RC-04 | Completion requires all mandatory checkable evidence | completion policy | missing/stale/unavailable/mismatch | stable `FAIL` reasons |
| RC-05 | State, idempotency and audit writes are atomic/append-only | ledger/repository | audit failure and partial transaction | no false success |
| RC-06 | Actor independence is server-enforced | authorization policy | role/actor-kind negatives | self-verification denied |
| RC-07 | Every reference, key and query is tenant-scoped | API/service/PostgreSQL | two-tenant API and SQL | no cross-tenant inference |
| RC-08 | Authentication supplies tenant/actor from verified identity only | OIDC/new routes | Keycloak wrong/missing claims | denial before DB/adapter |
| RC-09 | Input and artifact references are strict and bounded | schemas/resolver | unknown field, SSRF, size/content tests | zero egress on invalid input |
| RC-10 | Reason codes are stable; DE/EN display is equivalent | localization/UI | catalog, fallback, browser E2E | same normative codes |
| RC-11 | Prompts, CoT, secrets and unnecessary PII are excluded | schemas/redaction | canary scans in all outputs | no disclosure |
| RC-12 | Retention, hold, deletion and availability are explicit | evidence lifecycle | expiry/hold/delete/reverify | append-only availability history |
| RC-13 | Residency/egress is checked immediately before retrieval | egress guard | mismatch/stale and zero-transport | blocked policy event |
| RC-14 | E2E covers success and prohibited journeys | API/PostgreSQL/Keycloak/browser | two tenants, roles, DE/EN | sanitized failure artifacts |
| RC-15 | CI preserves security/release gates | existing workflow | exact-head full workflow | commit-bound evidence |

## 4. Contract model

### 4.1 Runtime Contract

Logical fields, subject to independent field-name review:

| Field | Required semantics |
| --- | --- |
| `runtime_contract_version` | Exact supported version, initially `0.1.0`. |
| `runtime_contract_id` | Stable tenant-local identifier. |
| `tenant_id` | Equals authenticated tenant and canonical action tenant. |
| `decision_ref` | Decision ID, Decision File version and full snapshot digest. |
| `canonical_action_digest` | Recomputes to the approved v0.2 action. |
| `approval_refs` | Ordered unique approval digests plus explicit nonce digests/references; the raw nonce remains in its Decision File approval and is not copied as runtime authority. |
| `constraint_set_digest` | Versioned policies, constraints, evidence and independence rules. |
| `execution_context_digest` | Protected-adapter context evaluated at authorization time. |
| `evidence_requirements` | Mandatory/advisory requirements, verifier, freshness and artifact policy. |
| `actor_independence` | Required unequal actors and human-review requirements. |
| `created_at`, `expires_at` | Bounded eligibility; expiry never extends implicitly. |

The complete Runtime Contract has its own canonical digest. Unknown fields, versions, algorithms,
enums and silent field dropping are rejected.

### 4.2 Authorization, attempt, evidence and completion

An Execution Authorization records tenant, contract/action/constraint digests, authenticated actor,
decision/expiry, result and reasons. `ALLOWED` is useful only through atomic consumption; it is not a
bearer token. Required blocked decisions are audited before returning denial.

An Execution Attempt records a unique ID, consumed authorization, contract/action binding, execution
actor, adapter, idempotency request digest, time and explicit state. Proposed states are `RESERVED`,
`STARTED`, `EFFECT_REPORTED`, `EFFECT_UNKNOWN`, `VERIFYING`, `COMPLETED` and `FAILED`. Transport
success maps only to `EFFECT_REPORTED`; a timeout or crash after possible target acceptance maps to
`EFFECT_UNKNOWN`, never to success and never to an automatic unbounded retry.

An Evidence Requirement declares stable ID/type, mandatory flag, action/attempt binding, accepted
artifact types, freshness, verifier class, independence, data class, retention and residency policy.
An Artifact Reference contains no unrestricted payload: it binds artifact ID/type, opaque
`trajectory_ref`, tenant, attempt, content digest, source, observation time, availability, redaction,
data/retention class and egress decision.

Evidence Verification records requirement/artifact digests, verifier identity/kind/version, time,
result and reasons. A verifier cannot finally verify its own mandatory evidence. Completion is a pure
function of immutable contract, terminal attempt facts and accepted verification records. Result is
`PASS` or `FAIL`; uncertainty, missing data or internal error cannot become `PASS`. Post-execution
human review, when required, is a separate gate.

## 5. Deterministic invariants and failure codes

| Invariant | Failure code |
| --- | --- |
| Identity, contract, action, attempt and artifact tenants match | `EXECUTION_TENANT_MISMATCH` |
| Decision version/snapshot digest matches source | `DECISION_BINDING_MISMATCH` |
| Action digest recomputes and matches approval/contract | `ACTION_BINDING_MISMATCH` |
| Approval and nonce reference are valid/not incompatibly reused | `APPROVAL_BINDING_MISMATCH`, `APPROVAL_REPLAYED` |
| Effective policies/constraints match digest | `CONSTRAINT_SET_MISMATCH` |
| Runtime Contract version/digest is valid | `RUNTIME_CONTRACT_UNSUPPORTED`, `RUNTIME_CONTRACT_TAMPERED` |
| Authorization is current and consumed once | `AUTHORIZATION_EXPIRED`, `AUTHORIZATION_REPLAYED` |
| Attempt and idempotency request are unique | `ATTEMPT_REPLAYED`, `IDEMPOTENCY_KEY_REUSED` |
| Mandatory evidence is present/current/reachable/bound | `EVIDENCE_MISSING`, `EVIDENCE_STALE`, `EVIDENCE_UNAVAILABLE`, `EVIDENCE_BINDING_MISMATCH` |
| Artifact content matches digest | `EVIDENCE_TAMPERED` |
| Verifier satisfies independence | `EVIDENCE_VERIFIER_NOT_INDEPENDENT` |
| Required persistence succeeds | `AUDIT_PERSISTENCE_FAILED`, `EVIDENCE_STORE_UNAVAILABLE` |
| Exactly one effective terminal completion wins | `COMPLETION_CONFLICT` |

Reason codes are normative identifiers, not localized prose. Authorization denial uses `BLOCKED`;
attempt-level Completion Decision uses `PASS` or `FAIL`. Missing or uncertain evidence therefore
cannot be mislabeled as a successful completion, while neither result changes the separate Decision
File lifecycle or constitutes organizational acceptance.

## 6. State and event flow

```text
Decision File APPROVED
  -> Runtime Contract bound
  -> Authorization ALLOWED | BLOCKED
  -> Attempt RESERVED -> STARTED -> EFFECT_REPORTED | FAILED
  -> Evidence OBSERVED -> VERIFIED | REJECTED
  -> Completion PASS | FAIL
  -> optional independent post-execution human review
```

Every arrow has an append-only event. Invalid transitions fail. A superseding event identifies the
old assertion and preserves both chain positions.

Normative Runtime Contract v0.1 event types are:

| Event type | Required meaning |
| --- | --- |
| `runtime_contract.bound` | Immutable contract-to-decision binding accepted. |
| `execution.authorization_decided` | `ALLOWED` or `BLOCKED`, with stable reasons and evaluated binding digest. |
| `execution.attempt_started` | Consumed authorization and reserved attempt entered protected execution. |
| `execution.attempt_finished` | Observed transport result, including `EFFECT_UNKNOWN`; never inferred completion. |
| `execution.evidence_observed` | Artifact reference and subject digest recorded. |
| `execution.evidence_availability_changed` | Artifact expired, was deleted or became unreachable; history remains intact. |
| `execution.evidence_verified` | Independent verification result for one requirement/artifact binding. |
| `execution.completion_decided` | Deterministic attempt-level `PASS` or `FAIL`. |
| `execution.assertion_superseded` | A later assertion supersedes, but does not mutate or erase, an earlier one. |

Every event uses the existing v1 envelope from [Event versioning](../EVENT-VERSIONING.md), a strict
versioned payload, a tenant/contract-local monotonic sequence and `previous_event_hash`. The event
hash covers the canonical complete event excluding only its own derived hash field. Unknown versions
or broken sequence/hash links fail closed. Authorization consumption plus attempt reservation is one
transaction. Verification plus effective completion is one compare-and-swap transaction. Identical
idempotent duplicates return the committed result; changed payload digests, concurrent losing writes
and replay across tenant, actor or operation are rejected.

## 7. Trust boundaries and tenant flow

1. OIDC validates signature, issuer, audience, algorithm, lifetime and claims.
2. Server identity resolves tenant, actor, roles and kind.
3. Central authorization checks permission and object-level tenant membership.
4. Strict schemas validate requests before persistence/external access.
5. Binding and independence policies use server-loaded records.
6. Required authorization/audit decision persists.
7. Authorization is consumed and attempt reserved atomically.
8. Only then may the protected adapter perform target I/O.
9. Artifact retrieval passes current egress/residency controls before secrets or transport.
10. Verification and completion persist atomically in the tenant ledger.

RLS, composite tenant keys, idempotency, caches and jobs preserve tenant identity. Cross-tenant object
access returns non-enumerating denial.

## 8. Actor-independence matrix

| Actor | Validate | Approve | Execute | Finally verify mandatory evidence | Human acceptance |
| --- | --- | --- | --- | --- | --- |
| Generator | not own case | not own case | policy-dependent | never own case/evidence | no implicit authority |
| Validator | if independent | not same case | policy-dependent | only if not producer/executor | no implicit authority |
| Approver | not same path | independent human | policy-dependent | only if not producer/executor and policy permits | separate authorized review only |
| Execution Actor | no implicit authority | no implicit authority | yes | never its own material evidence | no implicit authority |
| Evidence Verifier | technical verification | no implicit authority | must not execute verified effect | if role/kind/version/separation match | technical result is not acceptance |
| Auditor | integrity checks only | no | no | offline integrity only | no mutation/acceptance |

Material effects default to distinct generator, execution actor and final verifier. Human review is
fulfilled only by an authenticated human with the required server-authorized role.

## 9. Data protection, retention and external artifacts

- Prohibited durable content: prompts, chain-of-thought, tokens, keys, passwords, unnecessary PII and
  unfiltered bodies/screenshots.
- `trajectory_ref` is opaque, bounded and cannot be dereferenced without tenant, authorization,
  egress, residency and content controls.
- Logs use allowlisted metadata and sanitized codes.
- Retention, expiry, legal-hold scope and deletion status are explicit per artifact.
- Deletion preserves only approved minimum provenance; legal hold never crosses tenants.
- Missing/deleted evidence creates a new event and fails mandatory reverification.
- Redirect, DNS, IP range, content type/size, timeout and retry controls apply. External content is
  never executed as instruction.
- Evidence/audit outage prevents success; bounded retry cannot duplicate uncertain target I/O.

## 10. Localization

Interface language, user locale, tenant default, content language, audit code and display language
remain distinct. Contract values, bytes and reasons are never translated. DE/EN catalogs contain
equivalent explanations. Fallback cannot change authorization, tenant or digest. Dates/numbers are
formatted only for display.

## 11. Threat model

Likelihood/impact are project assessments, not certification.

| Threat | Likelihood / impact | Invariant | Control | Failure reason | Planned verification | Residual response |
| --- | --- | --- | --- | --- | --- | --- |
| Action/approval manipulation | medium / critical | Decision, action and approval chain exactly match | Recompute all canonical digests from server-loaded records | `ACTION_BINDING_MISMATCH`, `APPROVAL_BINDING_MISMATCH` | parameter, actor, nonce and digest tampering | revoke authorization and require re-approval |
| Authorization replay | medium / high | one authorization creates at most one attempt | atomic consume, expiry and tenant-scoped unique key | `AUTHORIZATION_REPLAYED` | sequential and parallel replay | stop execution and inspect ledger |
| Attempt/evidence replay | medium / high | attempt and artifact remain bound to their original subject | request, attempt and artifact subject digests | `ATTEMPT_REPLAYED`, `EVIDENCE_BINDING_MISMATCH` | reuse across action, attempt and tenant | independent source for material evidence |
| Cross-tenant reference | medium / critical | all records equal authenticated tenant | server tenant, composite keys and forced RLS | `EXECUTION_TENANT_MISMATCH` | API, service and direct-SQL negatives | incident response for privileged compromise |
| Self-verification | medium / high | final verifier differs from prohibited actors | actor IDs/kinds and separation policy | `EVIDENCE_VERIFIER_NOT_INDEPENDENT` | generator/executor/service/human matrix | organizational anti-collusion controls |
| Forged evidence | high / high | bytes, subject and provenance match the artifact record | content digest and verifier/source binding | `EVIDENCE_TAMPERED` | byte substitution and relabeling | signatures if portable trust is approved |
| Stale evidence | high / high | evidence is within requirement freshness | observation/retrieval/expiry times and policy clock | `EVIDENCE_STALE` | boundary-clock tests | re-observe |
| Unreachable/deleted evidence | medium / high | mandatory evidence remains policy-verifiable | availability events and conservative gate | `EVIDENCE_UNAVAILABLE` | timeout, 404, deletion and hold | preserve minimum provenance; fail reverification |
| Race/double completion | medium / high | one effective terminal completion wins | transaction lock/CAS and unique completion key | `COMPLETION_CONFLICT` | parallel PASS/FAIL and lease loss | recover only from committed ledger |
| Ledger manipulation | low / critical | history is append-only, ordered and hash-linked | database privileges/triggers plus offline chain verification | `AUDIT_CHAIN_INVALID` | update/delete/gap/reorder tests | restore verified copy and incident response |
| Credential/PII leakage | medium / critical | prohibited data is absent from durable outputs | allowlist schemas, redaction and canary scans | `SENSITIVE_DATA_REJECTED` | logs, events, API, export and CI scans | privacy response and deletion workflow |
| Malicious artifact reference | high / high | only approved public destinations/content are accessed | HTTPS allowlist plus DNS/redirect/IP/content controls | `ARTIFACT_REFERENCE_BLOCKED` | SSRF, redirect, DNS and size tests | sandbox parsing and incident response |
| Audit store outage | medium / high | required audit precedes target I/O and success | transactional audit write, health gate and zero-I/O ordering | `AUDIT_PERSISTENCE_FAILED` | fault injection and adapter spy | accept outage over lost traceability |
| Evidence store outage | medium / high | mandatory evidence is available before PASS | bounded retry, circuit breaker and fail-closed completion | `EVIDENCE_STORE_UNAVAILABLE` | timeout, partial write and circuit tests | delayed completion only |
| Circular evidence | medium / critical | evidence authority originates outside its own result | distinct source, artifact, verifier and gate graph | `EVIDENCE_PROVENANCE_INVALID` | self-referencing graph | independent source for high impact |

## 12. Contract mapping

| External concept | Existing DA artifact | Necessary addition | Effect | Open decision | Test evidence |
| --- | --- | --- | --- | --- | --- |
| Agent Trajectory Schema | Research attempts/events | minimized `trajectory_ref` and provenance | DA rules normative; external shape informative | schemes and lifetime | schema, redaction, tenant tests |
| Evidence Chain | Decision evidence/approvals/deployment bundle | execution binding graph | normative | portable signature | cycle, tampering, digest tests |
| Evidence-gated completion | release/governance gates | pure attempt-level completion policy | normative | requirement taxonomy | complete/missing/stale matrix |
| Preventive runtime control | authorization/egress guards | consume-once authorization before target port | normative for reference adapters | adapter inventory | zero target calls on denial |
| Checkable trajectory evidence | provenance/artifact digests | requirements, artifact and verifier records | metadata normative; content informative | source trust profiles | substitution/availability/independence |
| Task completion | no current execution outcome | technical attempt completion | normative technical result | domain success requirements | adapter contract tests |
| Organizational acceptance | controlled-pilot acceptance | optional linked post-execution review | separate authority | deployments requiring it | independent-human E2E |

## 13. Acceptance criteria for future implementation

1. Decision File v0.2 remains unchanged.
2. Runtime schemas reject unknown versions, fields and algorithms.
3. Every binding component is tamper-tested.
4. Missing evidence, uncertainty or internal error cannot yield `PASS`.
5. Authorization, attempt and completion are replay/concurrency safe.
6. Two-tenant API/service/RLS tests prove isolation.
7. Actor-independence negatives cover every prohibition.
8. DE/EN display identical normative codes and tested fallback.
9. Secret/PII canaries do not appear in durable/test artifacts.
10. PostgreSQL 16, Keycloak, API and browser E2E cover success and blocks.
11. Audit/evidence failures stop before target I/O or success.
12. CI is exact-head evidence, not deployment or organizational approval.

## 14. Non-goals and open decisions

Non-goals are general tracing, prompts/CoT, DATS v0.2, SAFE Incident Record, trust scores, automatic
execution of all approvals, silent v0.2 mutation, production non-bypassability claims, deployment and
organizational authorization.

Independent review must resolve or explicitly defer ADR-007's six open questions before schema or
security implementation. Field names, length limits, artifact profiles and signature scope remain
provisional.
