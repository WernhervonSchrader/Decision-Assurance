# Runtime Contract v0.1 — Execution Evidence Binding

**Status:** Architecture draft after self-review; implementation not authorized

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

## 3. Normative traceability matrix

All controls are future controls. Their status is `NOT TESTED`; a planned test or evidence type is
not evidence that the control exists or passed.

| Requirement | Classification | Risk | Control | Evidence | Test/Gate | Responsible role | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RC-01 standalone contract; Decision File v0.2 unchanged | `PROJECT_CONTRACT` | silent semantic migration | separate strict Runtime schema/version and byte-unchanged v0.2 schema/reference functions | schema mirrors and approved-base file hashes | unknown-field/version and byte-equality gate | contract owner | NOT TESTED |
| RC-02 field-exact tenant/decision/action/approval/constraint binding | `PROJECT_CONTRACT` | substitution or wrong action | lossless v0.2 mapping and canonical matrix in sections 4.3–4.4 | canonical fixtures and binding ledger event | mutate every covered field | contract owner | NOT TESTED |
| RC-03 consume-once reservation and revocation race | `PROJECT_CONTRACT` | replay or revoked execution | atomic CAS plus separate `attempt_reserved` event | committed authorization/reservation events | parallel revoke/reserve and replay gate | runtime service owner | NOT TESTED |
| RC-04 complete `EFFECT_UNKNOWN` reconciliation | `PROJECT_CONTRACT` | duplicate effect or false success | no automatic retry; audited independent reconciliation | original transport fact plus reconciliation evidence | crash boundaries, inquiry/no-effect/unresolved cases | runtime service owner | NOT TESTED |
| RC-05 mandatory evidence gates completion | `PROJECT_CONTRACT` | unsupported success | deterministic fail-closed completion policy | requirement/artifact/verification digests | missing, stale, unavailable and mismatch gate | verification policy owner | NOT TESTED |
| RC-06 append-only atomic ledger | `PROJECT_CONTRACT` | repudiation or split state | hash chain, unique sequence and transactional writes | ledger chain and transaction result | write-failure, gap, mutation and CAS gate | data platform owner | NOT TESTED |
| RC-07 actor/capability independence | `PROJECT_CONTRACT` | self-approval or privilege escalation | deny-by-default matrix in section 8 | authorization decisions with actor kind/role/capability | full positive/negative capability matrix | identity/security owner | NOT TESTED |
| RC-08 tenant isolation and authenticated identity | `PROJECT_CONTRACT` | cross-tenant disclosure/action | server tenant, composite keys and forced RLS | tenant-bound records and denial audit | two-tenant API/service/SQL/worker gate | identity/data owners | NOT TESTED |
| RC-09 strict inputs and guarded artifact retrieval | `PROJECT_CONTRACT` | injection, SSRF or secret exposure | strict bounded schemas and request-time egress policy | sanitized policy event | unknown fields, DNS/redirect/IP/size/content gate | security owner | NOT TESTED |
| RC-10 locale-neutral namespaces and DE/EN equivalence | `PROJECT_CONTRACT` | translated control semantics | closed namespaces in section 5.1; display-only catalogs | catalog parity report | schema and localization/E2E gate | localization owner | NOT TESTED |
| RC-11 data minimization and redaction | `PROJECT_CONTRACT` | credential/PII leakage | allowlisted durable fields; prohibited-content rejection | canary scan report | event/log/API/export/CI scan | privacy/security owner | NOT TESTED |
| RC-12 retention, deletion and legal hold | `PROJECT_CONTRACT` | unlawful deletion/retention or evidence loss | separate lifecycle, tombstones, minimum provenance and holds | lifecycle events and policy snapshot | expire/delete/hold/release/reverify gate | data owner/legal role | NOT TESTED |
| RC-13 backup and restore preserve semantics | `PROJECT_CONTRACT` | resurrected data or broken audit chain | inherited holds/deletions; isolated restore verification | commit/environment-bound recovery record | backup ageing, fresh restore, RLS/hash/tombstone gate | platform operator | NOT TESTED |
| RC-14 deployment storage/residency/non-bypassability | `PROJECT_CONTRACT` | design claim mistaken for deployed control | disable until named-adapter evidence is approved | expected class: `DEPLOYMENT_EVIDENCE`, bound to adapter/routes/store | independent deployment gate | deployment owner/reviewer | NOT TESTED |
| RC-15 end-to-end and exact-head release gate | `PROJECT_CONTRACT` | partial checks presented as readiness | required deterministic suite and exact revision binding | expected classes: repository, integration and deployment evidence | PostgreSQL, Keycloak, API, browser, security, CI | release owner/independent reviewer | NOT TESTED |
| RC-16 bind reconciliation into completion | `PROJECT_CONTRACT` | uncertain effect becomes unbound success | `attempt_digest -> reconciliation_digest -> verification_digest -> completion_digest` | immutable Reconciliation Record and bound downstream digests | effect/no-effect/unresolved, substitution, omission and blind-retry gates | verification policy owner | NOT TESTED |

## 4. Contract model

### 4.1 Runtime Contract

Logical fields are normative for v0.1; a later spelling or shape change requires a new contract
version:

| Field | Required semantics |
| --- | --- |
| `runtime_contract_version` | Exact supported version, initially `0.1.0`. |
| `runtime_contract_id` | Stable tenant-local identifier. |
| `tenant_id` | Equals authenticated tenant and canonical action tenant. |
| `decision_ref` | Decision ID, exact Decision File version and Runtime-owned `runtime_decision_reference_digest`; no v0.2 full-document digest is asserted. |
| `canonical_action_digest` | Recomputes to the approved v0.2 action. |
| `approval_refs` | Ordered unique lossless v0.2 approval records, exactly as in section 4.4; the copied nonce is a reference field and never bearer or execution authority. |
| `constraint_set_digest` | Versioned policies, constraints, evidence and independence rules. |
| `execution_context_digest` | Protected-adapter context evaluated at authorization time. |
| `evidence_requirements` | Mandatory/advisory requirements, verifier, freshness and artifact policy. |
| `actor_independence` | Required unequal actors and human-review requirements. |
| `created_at`, `expires_at` | Bounded eligibility; expiry never extends implicitly. |

The complete Runtime Contract has its own canonical digest. Unknown fields, versions, algorithms,
enums and silent field dropping are rejected.

### 4.2 Authorization, attempt, evidence and completion

An Execution Authorization records tenant, contract/action/constraint digests, authenticated actor,
decision/expiry, `authorization_result` and reasons. `ALLOWED` is useful only through atomic consumption; it is not a
bearer token. Required blocked decisions are audited before returning denial.

An unconsumed `ALLOWED` authorization may be revoked with a separate
`execution.authorization_revoked` event. Reservation and revocation use one compare-and-swap. A
committed revocation wins with `AUTHORIZATION_REVOKED` and zero target I/O; a committed reservation
wins consumption and cannot be retroactively revoked.

An Execution Attempt records a unique ID, consumed authorization, contract/action binding, execution
actor, adapter, idempotency request digest, time and explicit state. Normative states are `RESERVED`,
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

For an `EFFECT_UNKNOWN` attempt, a Reconciliation Record is mandatory and contains exactly
`reconciliation_id`, `tenant_id`, `attempt_id`, `attempt_binding_digest`, `reconciliation_result`,
sorted unique `evidence_refs`, `actor_ref`, `actor_kind`, `decided_at` and
`reconciliation_digest`. Allowed results are `PROVEN_EFFECT`, `PROVEN_NO_EFFECT` and `UNRESOLVED`.
Each evidence reference contains exactly `artifact_id`, `requirement_id` and `artifact_digest` and is
sorted by `(requirement_id, artifact_id, artifact_digest)`. The digest is recomputed from all
preceding fields except itself. `PROVEN_EFFECT` may support later
verification; `PROVEN_NO_EFFECT` requires a new authorization and attempt; `UNRESOLVED` requires
completion `FAIL`. Verification records created after uncertainty contain the exact
`reconciliation_digest`; Completion contains it as well. Omission, substitution, wrong tenant or
wrong attempt fails closed. Thus `attempt -> reconciliation -> verification -> completion` is
deterministically reconstructable and cannot authorize a blind retry.

### 4.3 Field-exact binding and canonicalization matrix

Every Runtime-owned digest uses UTF-8 RFC 8785 JSON Canonicalization Scheme bytes, SHA-256, lowercase hexadecimal,
no Unicode pre-normalization, integers within the exact IEEE-754 safe range for numeric contract
values, UTC timestamps normalized to `YYYY-MM-DDTHH:MM:SS.ffffffZ` only for new Runtime-owned
timestamp fields, RFC 8785 object-key ordering, and arrays in the order stated below. Imported
v0.2 timestamp strings remain exactly unchanged, including valid offsets. Unknown fields, duplicate
logical keys, floats, unsafe integers, non-canonical new Runtime timestamps and unsupported
algorithm/version identifiers are rejected before hashing. This is an explicitly bounded v0.2
interoperability subset: a valid v0.2 source containing a float or an integer outside
[-9007199254740991, 9007199254740991] remains valid v0.2 but is not admitted to Runtime v0.1.
Return `RUNTIME_SOURCE_NOT_CANONICALIZABLE`, preserve the original and perform no authorization
or target I/O; do not round, stringify, normalize or re-approve it implicitly. Domain separation is the ASCII prefix
`DA:<record-type>:<schema-version>\n` followed by canonical JSON bytes.

| Runtime record / digest | Exact canonical payload fields | Ordered/set rules | Bound parent fields |
| --- | --- | --- | --- |
| Runtime Contract / `runtime_contract_digest` | `runtime_contract_version`, `runtime_contract_id`, `tenant_id`, `decision_ref`, `canonical_action_digest`, `approval_refs`, `constraint_set_digest`, `execution_context_digest`, `evidence_requirements`, `actor_independence`, `created_at`, `expires_at` | `approval_refs` sorted by `(requirement_ref, approval_digest)` and unique; requirements sorted by `requirement_id`; all other arrays preserve declared order | Runtime decision reference, action, approvals, constraint set |
| Decision ref / `runtime_decision_reference_digest` | exact v0.2 values of `schema_version`, `decision_id`, `status`, `decision_outcome`, `requested_by`, `canonical_action`, ordered `constraints`, ordered `policies`, ordered `review_requirements`, ordered `approvals` | arrays retain their validated v0.2 order; nested objects retain every v0.2 field; Runtime canonicalization applies only to this new reference record | explicitly selected validated v0.2 fields; not a v0.2 full-document digest |
| Approval ref / `approval_ref_digest` | lossless exact v0.2 values `requirement_ref`, `approver`, `decision`, `decided_at`, `action_digest`, `nonce`, `approval_digest` | unique by `(requirement_ref, approval_digest)`; no renaming, derived actor ID, transition or timestamp | v0.2 approval and its action binding |
| Constraint set / `constraint_set_digest` | `constraint_set_version`, ordered `policy_refs`, ordered `constraints`, canonical `evidence_requirements`, `actor_independence` | policy precedence order is significant; requirements sorted by ID | policies effective at authorization time |
| Authorization / `authorization_binding_digest` | `authorization_id`, `tenant_id`, `runtime_contract_id`, `runtime_contract_digest`, `canonical_action_digest`, `constraint_set_digest`, `execution_context_digest`, `authorized_actor_id`, `authorized_actor_kind`, `authorization_result`, `reason_codes`, `decided_at`, `expires_at` | reason codes sorted/unique; no mutable state in digest | exact contract and actor decision |
| Attempt reservation / `attempt_binding_digest` | `attempt_id`, `tenant_id`, `authorization_id`, `authorization_binding_digest`, `runtime_contract_digest`, `canonical_action_digest`, `execution_actor_id`, `execution_actor_kind`, `adapter_id`, `adapter_version`, `idempotency_key_digest`, `request_digest`, `reserved_at` | scalar record; all fields required | consumed authorization and exact request |
| Evidence requirement / `requirement_digest` | `requirement_id`, `type`, `mandatory`, `subject_binding`, `accepted_artifact_types`, `freshness_seconds`, `verifier_classes`, `independence_rule`, `data_class`, `retention_class`, `residency_policy` | accepted types/verifier classes sorted/unique | contract, action and attempt subject |
| Artifact ref / `artifact_digest` | `artifact_id`, `tenant_id`, `attempt_id`, `requirement_id`, `artifact_type`, `trajectory_ref_digest`, `content_digest_algorithm`, `content_digest`, `source_id`, `source_version`, `observed_at`, `availability`, `redaction_profile`, `data_class`, `retention_class`, `residency_decision_digest` | scalar record; locator bytes are excluded and separately protected | attempt and requirement |
| Reconciliation / `reconciliation_digest` | `reconciliation_id`, `tenant_id`, `attempt_id`, `attempt_binding_digest`, `reconciliation_result`, sorted `evidence_refs` (each object: `artifact_id`, `requirement_id`, `artifact_digest`), `actor_ref`, `actor_kind`, `decided_at` | evidence refs sorted by `(requirement_id, artifact_id, artifact_digest)` and unique; required only after `EFFECT_UNKNOWN` | immutable attempt and reconciliation evidence |
| Verification / `verification_digest` | `verification_id`, `tenant_id`, `attempt_id`, `requirement_digest`, `artifact_digest`, `reconciliation_digest` (`null` only when reconciliation was not required), `verifier_actor_id`, `verifier_actor_kind`, `verifier_version`, `verification_result`, `reason_codes`, `verified_at` | reason codes sorted/unique | immutable requirement, artifact and required reconciliation |
| Completion / `completion_digest` | `completion_id`, `tenant_id`, `attempt_id`, `attempt_binding_digest`, `reconciliation_digest` (`null` only when reconciliation was not required), sorted `verification_digests`, `completion_result`, `reason_codes`, `decided_at`, `policy_version` | verification digests sorted/unique; reason codes sorted/unique | attempt, required reconciliation and all effective verifications |
| Pilot acceptance reference / `pilot_acceptance_digest` | `acceptance_id`, `tenant_id`, `deployment_scope_digest`, `runtime_contract_digest`, `completion_digest`, `reviewer_actor_id`, `deployment_evidence_status`, `reason_codes`, `decided_at` | status is copied from the existing Deployment Evidence contract; reason codes sorted/unique | separate named deployment and human review |

Event payload digests cover their strict payload; event hashes cover the complete canonical envelope
excluding only the derived `event_hash`. Timestamps and mutable availability never enter an earlier
record retroactively; they create new events.

Imported `canonical_action_digest` and `approval_digest` values are verified using the unchanged
Decision File v0.2 reference functions and then bound as opaque `sha256:` values. Runtime v0.1 never
recomputes them with RFC 8785 or domain separation and never calls its new reference digest a
`decision_file_digest`.

### 4.4 Lossless Decision File v0.2 mapping

The binder first validates the complete v0.2 document with the existing schema and semantic checks.
It then checks the explicit numeric interoperability subset in section 4.3. Only admitted sources
are copied into `decision_ref` without renaming or coercion. Lossless mapping applies to that subset;
this draft does not claim support for every otherwise valid v0.2 document. Each approval is
copied field-for-field:

| Decision File v0.2 source | Runtime approval reference | Transformation |
| --- | --- | --- |
| `requirement_ref` | `requirement_ref` | exact string |
| `approver` | `approver` | complete validated actor object |
| `decision` | `decision` | exact `APPROVE` or `REJECT` |
| `decided_at` | `decided_at` | exact validated timestamp string |
| `action_digest` | `action_digest` | exact digest or `null` |
| `nonce` | `nonce` | exact v0.2 nonce; never promoted to bearer authority |
| `approval_digest` | `approval_digest` | exact digest, verified by the existing v0.2 function |

No `approval_id`, `approver_actor_id`, `approved_transition` or `approved_at` is inferred. Any change
to a mapped Action, Approval, Constraint or Authorization digest input invalidates the old binding and
requires a new Runtime authorization; where the original Decision transition required human approval,
the modified Decision File requires that approval again.

### 4.5 Closed Runtime Artifact Type allowlist

Runtime v0.1 accepts exactly two `artifact_type` values. Common required fields for both are
`artifact_schema_version` (`0.1.0`), `artifact_id`, `tenant_id`, `attempt_id`, `requirement_id`,
`artifact_type`, `source_id`, `source_version`, `observed_at`, `content_digest_algorithm` (`sha256`),
`content_digest`, `trajectory_ref_digest`, `availability` (`AVAILABLE`), `redaction_profile`,
`data_class`, `retention_class` and
`residency_decision_digest`.

| `artifact_type` | Additional required fields | Closed values |
| --- | --- | --- |
| `DA_ADAPTER_EXECUTION_RECEIPT_V0_1` | `adapter_id`, `adapter_version`, `request_digest`, `external_operation_ref_digest`, `receipt_result` | `receipt_result`: `ACCEPTED`, `REJECTED`, `UNKNOWN` |
| `DA_TARGET_STATUS_OBSERVATION_V0_1` | `adapter_id`, `adapter_version`, `target_ref_digest`, `observation_query_digest`, `effect_status` | `effect_status`: `PRESENT`, `ABSENT`, `INDETERMINATE` |

Unknown types, versions, fields or enum values are rejected. These structured records contain no raw
provider body, prompt, trace, screenshot, credential or unrestricted metadata. A new artifact class
requires a new Runtime Contract version or explicit versioned extension decision; an implementer may
not invent a code.

## 5. Deterministic invariants and failure codes

| Invariant | Failure code |
| --- | --- |
| Identity, contract, action, attempt and artifact tenants match | `EXECUTION_TENANT_MISMATCH` |
| Decision version/snapshot digest matches source | `DECISION_BINDING_MISMATCH` |
| Action digest recomputes and matches approval/contract | `ACTION_BINDING_MISMATCH` |
| Approval and nonce reference are valid/not incompatibly reused | `APPROVAL_BINDING_MISMATCH`, `APPROVAL_REPLAYED` |
| Effective policies/constraints match digest | `CONSTRAINT_SET_MISMATCH` |
| Valid v0.2 source is representable without coercion | `RUNTIME_SOURCE_NOT_CANONICALIZABLE` |
| Runtime Contract version/digest is valid | `RUNTIME_CONTRACT_UNSUPPORTED`, `RUNTIME_CONTRACT_TAMPERED` |
| Authorization is current and consumed once | `AUTHORIZATION_EXPIRED`, `AUTHORIZATION_REPLAYED` |
| Authorization was not revoked before reservation committed | `AUTHORIZATION_REVOKED` |
| Attempt and idempotency request are unique | `ATTEMPT_REPLAYED`, `IDEMPOTENCY_KEY_REUSED` |
| Mandatory evidence is present/current/reachable/bound | `EVIDENCE_MISSING`, `EVIDENCE_STALE`, `EVIDENCE_UNAVAILABLE`, `EVIDENCE_BINDING_MISMATCH` |
| Artifact content matches digest | `EVIDENCE_TAMPERED` |
| Required reconciliation is present and bound through verification/completion | `RECONCILIATION_MISSING`, `RECONCILIATION_BINDING_MISMATCH`, `RECONCILIATION_UNRESOLVED` |
| Verifier satisfies independence | `EVIDENCE_VERIFIER_NOT_INDEPENDENT` |
| Required persistence succeeds | `AUDIT_PERSISTENCE_FAILED`, `EVIDENCE_STORE_UNAVAILABLE` |
| Exactly one effective terminal completion wins | `COMPLETION_CONFLICT` |

Reason codes are normative identifiers, not localized prose. Authorization denial uses `BLOCKED`;
attempt-level Completion Decision uses `PASS` or `FAIL`. Missing or uncertain evidence therefore
cannot be mislabeled as a successful completion, while neither result changes the separate Decision
File lifecycle or constitutes organizational acceptance.

### 5.1 Closed value namespaces

Names are field-qualified and MUST NOT be compared across namespaces even where labels coincide.

| Field namespace | Allowed values in v0.1 |
| --- | --- |
| `decision_outcome` | `null`, `PASS`, `REVIEW`, `BLOCK` — imported unchanged from Decision File v0.2 |
| `authorization_result` | `ALLOWED`, `BLOCKED`, `REVOKED` |
| `attempt_state` | `RESERVED`, `STARTED`, `EFFECT_REPORTED`, `EFFECT_UNKNOWN`, `VERIFYING`, `COMPLETED`, `FAILED` |
| `reconciliation_result` | `PROVEN_EFFECT`, `PROVEN_NO_EFFECT`, `UNRESOLVED` |
| `verification_result` | `VERIFIED`, `REJECTED`, `UNAVAILABLE` |
| `completion_result` | `PASS`, `FAIL` |
| `deployment_evidence_status` | `INCOMPLETE`, `TECHNICALLY_VERIFIED`, `PILOT_REVIEW_REQUIRED`, `PILOT_ACCEPTED`, `BLOCKED` — reused unchanged from the existing Deployment Evidence contract |

Runtime v0.1 defines no competing `pilot_acceptance_status`. A Runtime acceptance reference is a
snapshot of `deployment_evidence_status`; it does not add, rename or translate values.
`NOT TESTED` and `BLOCKED` in traceability/gate reporting are evidence-status labels, not runtime
enum values unless explicitly listed above.

## 6. State and event flow

```text
Decision File APPROVED
  -> Runtime Contract bound
  -> Authorization ALLOWED | BLOCKED -> optional REVOKED while unconsumed
  -> Attempt RESERVED -> STARTED -> EFFECT_REPORTED | EFFECT_UNKNOWN | FAILED
  -> EFFECT_UNKNOWN -> reconciliation PROVEN_EFFECT | PROVEN_NO_EFFECT | UNRESOLVED
  -> Evidence OBSERVED -> VERIFIED | REJECTED | UNAVAILABLE
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
| `execution.authorization_revoked` | Unconsumed authorization became `REVOKED`; it cannot reserve an attempt. |
| `execution.attempt_reserved` | Authorization was atomically consumed and the exact attempt/request binding became durable before target I/O. |
| `execution.attempt_started` | Consumed authorization and reserved attempt entered protected execution. |
| `execution.attempt_finished` | Observed transport result, including `EFFECT_UNKNOWN`; never inferred completion. |
| `execution.evidence_observed` | Artifact reference and subject digest recorded. |
| `execution.evidence_availability_changed` | Artifact expired, was deleted or became unreachable; history remains intact. |
| `execution.evidence_verified` | Independent verification result for one requirement/artifact binding. |
| `execution.completion_decided` | Deterministic attempt-level `PASS` or `FAIL`. |
| `execution.assertion_superseded` | A later assertion supersedes, but does not mutate or erase, an earlier one. |
| `execution.reconciliation_decided` | Independent inquiry concluded `PROVEN_EFFECT`, `PROVEN_NO_EFFECT` or `UNRESOLVED` for an `EFFECT_UNKNOWN` attempt. |
| `execution.evidence_hold_applied` | An authorized hold changed an eligible evidence subject from `UNHELD` to `HELD`. |
| `execution.evidence_hold_released` | An authorized release changed the same hold from `HELD` to `RELEASED`. |
| `execution.evidence_delete_requested` | An authorized delete request became `PENDING_HOLD` or `READY`. |
| `execution.evidence_delete_completed` | Bytes/live locator or external identity mapping were deleted or tombstoned; ledger events remained unchanged. |

Every Runtime event uses its separate Runtime Event envelope version `0.1.0`, with exactly
`event_type`, `schema_version`, `event_id`, `timestamp`, `tenant_scope_ref`, `actor_ref`,
`correlation_id`, `source_component`, `payload`, `sequence`, `previous_event_hash` and `event_hash`.
The existing v1 envelope in [Event versioning](../EVENT-VERSIONING.md) is unchanged and requires
`tenant_id`/`actor_id`; this Runtime envelope is not compatible with that reader and defines no aliases.
Registration and explicit version dispatch are required before runtime ingestion/export. Payloads
are strict and versioned; the sequence is tenant/contract-local and monotonic. Direct identity mappings remain
outside the ledger. The event
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
7. Authorization is consumed, attempt reserved and `execution.attempt_reserved` persisted atomically.
8. `execution.attempt_started` persists; only then may the protected adapter perform target I/O.
9. Artifact retrieval passes current egress/residency controls before secrets or transport.
10. Verification and completion persist atomically in the tenant ledger.

RLS, composite tenant keys, idempotency, caches and jobs preserve tenant identity. Cross-tenant object
access returns non-enumerating denial.

## 8. Actor and capability matrix

This table is an exact copy of ADR-007 and the sole Runtime capability model; ADR-007 prevails
fail-closed if the copies ever differ.

| Existing role or Runtime service identity | Exact allowed capabilities | Explicit denials |
| --- | --- | --- |
| Requester/Generator | `runtime_contract:request`; read own permitted case | every Runtime mutation and Protected I/O |
| Validator | existing validation only; read required case/validation records | every Runtime mutation and Protected I/O |
| Approver | existing Decision File approval only; read approved case | every Runtime mutation, Protected I/O and pilot acceptance |
| Runtime contract binder service | `runtime_contract:bind` from server-loaded approved records | approve, execute, verify, reconcile or accept |
| Authorization policy service | `execution:authorize`, `execution:revoke_unconsumed` | reserve/invoke, verify, reconcile or accept |
| Execution orchestrator service | `execution:reserve`, `execution:invoke` through the protected port; record its allowlisted receipt | authorize itself, revoke, verify its evidence, reconcile or accept |
| Evidence observer service | `evidence:record` for its attempt and allowlisted types | authorize, execute, finally verify its artifact or accept |
| Independent technical verifier | `evidence:verify` for permitted types and bound version | execute/produce the verified effect, mutate evidence or accept |
| Reconciliation operator/service | `execution:reconcile` using read-only target inquiry and allowlisted evidence | blind retry, rewrite observations, self-authorize or accept |
| Tenant auditor | `ledger:read`, `ledger:verify_integrity`, approved export | all domain mutation and acceptance |
| Independent human acceptance reviewer | existing `pilot_acceptance:decide` for eligible named scope | generate, execute or produce reviewed evidence |
| Data governance actor | `evidence:hold_apply`, `evidence:hold_release`, `evidence:delete_request` under approved policy | Protected I/O, verification, acceptance or ledger mutation |
| Evidence lifecycle service | `evidence:delete_complete` only for an authorized ready request | policy approval, hold release, Protected I/O or ledger mutation |
| Platform operator | health, backup and restore under separated operational identity | tenant-domain decisions, unrestricted content read or acceptance |

Capabilities are exact, case-sensitive, tenant/object scoped and deny-by-default. Generator,
Validator and Approver never receive `execution:reserve` or `execution:invoke`. Actor kind and role
remain separate; aggregation never waives independence, and a service cannot satisfy a human gate.

## 9. Data protection, retention, hold and recovery

- Prohibited durable content: prompts, chain-of-thought, tokens, keys, passwords, unnecessary PII and
  unfiltered bodies/screenshots.
- `trajectory_ref` is opaque, bounded and cannot be dereferenced without tenant, authorization,
  egress, residency and content controls.
- Logs use allowlisted metadata and sanitized codes.
- Runtime Ledger and artifact bytes use separate retention policies. Ledger events are never
  physically deleted, rewritten, replaced or pseudonymized. They contain pseudonymous
  `tenant_scope_ref`, `subject_ref` and `actor_ref` from creation. Reversible identity mappings live
  outside the ledger and may be deleted or blocked under policy without changing an event or hash.
- Artifact deletion removes bytes and live locators, appends a tombstone/availability event and keeps
  only: tenant-scope pseudonym, artifact/requirement/attempt IDs, artifact type, digest algorithm and
  digest, observation time, source class, verifier ID/version, deletion time/reason and ledger hashes,
  until ledger-retention expiry.
- A legal hold identifies tenant, subjects, purpose, authority, start/expiry and custodian. It blocks
  expiry/deletion but grants no read/egress authority. Requested deletion becomes pending and resumes
  after release. Hold application and release are append-only events.
- Backups inherit tenant isolation, encryption, residency, retention and hold. Deletion propagates by
  backup ageing; immutable backups are not silently edited. Restore into fresh isolated infrastructure
  reapplies hold state and deletion tombstones before access, then verifies tenant isolation, latest
  retained event, ledger hash continuity and absence of resurrected live artifact locators.
- Restore failure stays fail-closed. Observed RPO/RTO are deployment evidence, never commitments.
- Missing/deleted evidence creates a new event and fails mandatory reverification.
- Redirect, DNS, IP range, content type/size, timeout and retry controls apply. External content is
  never executed as instruction.
- Evidence/audit outage prevents success; bounded retry cannot duplicate uncertain target I/O.

Concrete periods come only from an approved versioned Retention Policy containing tenant scope, data
class, retention class, legal basis, owner, effective interval and policy digest. Without it,
automatic retention/deletion is disabled. Store selection/admission is a `PROJECT_CONTRACT` control;
external storage additionally requires store-specific `DEPLOYMENT_EVIDENCE`. Without both, external
storage, execution and restore acceptance remain disabled and `NOT TESTED`.

### 9.1 Legal-hold and delete event contract

All events include the standard envelope, tenant binding and prior hash. Payload fields below are
required and no additional fields are accepted.

| Event | Required payload | Actor/capability | Allowed transition and CAS rule | Effect |
| --- | --- | --- | --- | --- |
| `execution.evidence_hold_applied` | `hold_id`, `tenant_scope_ref`, `subject_ref`, `policy_digest`, `authority_ref`, `purpose_code`, `applied_at`, `expires_at`, `expected_subject_version` | Data governance actor / `evidence:hold_apply` | `UNHELD -> HELD`; one CAS winner; duplicate identical request replays | blocks byte, locator and identity-mapping deletion; ledger unchanged |
| `execution.evidence_hold_released` | `hold_id`, `tenant_scope_ref`, `subject_ref`, `policy_digest`, `authority_ref`, `release_reason_code`, `released_at`, `expected_hold_version` | Different authorized data governance actor / `evidence:hold_release` | `HELD -> RELEASED`; stale/wrong/expired authority fails closed | pending delete is re-evaluated; ledger unchanged |
| `execution.evidence_delete_requested` | `delete_request_id`, `tenant_scope_ref`, `subject_ref`, `retention_policy_digest`, `requester_ref`, `reason_code`, `requested_at`, `expected_subject_version` | Data governance actor / `evidence:delete_request` | eligible/no hold `-> READY`; active hold `-> PENDING_HOLD`; CAS prevents lost hold/delete races | no bytes removed yet; mandatory reverification treats pending/unavailable per policy |
| `execution.evidence_delete_completed` | `delete_request_id`, `tenant_scope_ref`, `subject_ref`, `retention_policy_digest`, `executor_ref`, `deleted_components`, `minimum_provenance_digest`, `completed_at`, `expected_delete_version` | Evidence lifecycle service / `evidence:delete_complete` | `READY -> COMPLETED`; forbidden from `PENDING_HOLD`; hold applied first wins and blocks, completion first wins only after atomic no-hold recheck | deletes/tombstones bytes, live locator or external mapping; appends availability change; ledger unchanged |

Tenant mismatch, missing policy, authorization failure, stale CAS or audit persistence failure makes no
lifecycle mutation and deletes nothing. Legal hold never grants read/egress authority. Identical
replays return the committed result; changed payloads conflict. Backup ageing applies completed
tombstones before restored data becomes accessible.

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

| External concept | Existing DA artifact | Necessary addition | Effect | Decision register | Test evidence |
| --- | --- | --- | --- | --- | --- |
| Agent Trajectory Schema | Research attempts/events | minimized `trajectory_ref` and provenance | DA rules normative; external shape informative | DR-02 `RESOLVED` | schema, redaction, tenant tests |
| Evidence Chain | Decision evidence/approvals/deployment bundle | execution binding graph | normative | DR-01 `DEFERRED_CAPABILITY_DISABLED` | cycle, tampering, digest tests |
| Evidence-gated completion | release/governance gates | pure attempt-level completion policy | normative | DR-03/DR-04 `RESOLVED` | complete/missing/stale matrix |
| Preventive runtime control | authorization/egress guards | consume-once authorization before target port | normative for reference adapters | DR-08 `REQUIRES_DEPLOYMENT_EVIDENCE` | zero target calls on denial |
| Checkable trajectory evidence | provenance/artifact digests | requirements, artifact and verifier records | metadata normative; content informative | DR-02 `RESOLVED`; DR-06 `REQUIRES_DEPLOYMENT_EVIDENCE`; DR-07 `DEFERRED_CAPABILITY_DISABLED` | substitution/availability/independence |
| Task completion | no current execution outcome | technical attempt completion | normative technical result | DR-08 `REQUIRES_DEPLOYMENT_EVIDENCE` | adapter contract tests |
| Organizational acceptance | controlled-pilot acceptance | optional linked post-execution review | separate authority | DR-03 `RESOLVED` | independent-human E2E |

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
13. An `EFFECT_UNKNOWN` completion binds the required reconciliation digest through verification and completion.
14. Hold/delete races preserve immutable ledger events and delete nothing without policy, authority and a winning CAS.

## 14. Non-goals and decision register

Non-goals are general tracing, prompts/CoT, DATS v0.2, SAFE Incident Record, trust scores, automatic
execution of all approvals, silent v0.2 mutation, production non-bypassability claims, deployment and
organizational authorization.

| ID | Classification | Normative result | State |
| --- | --- | --- | --- |
| DR-01 | `ASSUMPTION_OR_RISK` | Portable signing/export is outside v0.1 and disabled pending a separate ADR. | DEFERRED_CAPABILITY_DISABLED |
| DR-02 | `PROJECT_CONTRACT` | Only the two exact section 4.5 artifact types are admitted. | RESOLVED |
| DR-03 | `PROJECT_CONTRACT` | Digest-input changes invalidate prior authority; required human approval is repeated; `EFFECT_UNKNOWN` reconciliation requires independent human review before `PASS`. | RESOLVED |
| DR-04 | `PROJECT_CONTRACT` | Section 9 minimum pseudonymous provenance survives artifact deletion; raw content/live locator does not. | RESOLVED |
| DR-05 | `ASSUMPTION_OR_RISK` | Decision File v0.3 is not required; interoperable forward reference remains disabled pending separate ADR/version. | DEFERRED_CAPABILITY_DISABLED |
| DR-06 | `PROJECT_CONTRACT` | Store admission is a control and named-store activation requires matching deployment evidence. | REQUIRES_DEPLOYMENT_EVIDENCE |
| DR-07 | `PROJECT_CONTRACT` | Automatic retention/deletion is disabled until an approved versioned Retention Policy supplies periods. | DEFERRED_CAPABILITY_DISABLED |
| DR-08 | `PROJECT_CONTRACT` | Protected execution requires deployment-bound adapter/credential/route inventory and non-bypassability evidence. | REQUIRES_DEPLOYMENT_EVIDENCE |

These are the only permitted Decision Register states. No `RESOLVED` row leaves implementer-defined
semantics. Length limits outside the explicit artifact fields and deployment-specific profiles must
be approved before their capability is enabled. Every future control remains `NOT TESTED`.

Publication remediation and proposal limitations: [review](DA-RUNTIME-CONTRACT-v0.1-PUBLICATION-REVIEW.md). No implementation or runtime evidence is supplied by this document correction.
