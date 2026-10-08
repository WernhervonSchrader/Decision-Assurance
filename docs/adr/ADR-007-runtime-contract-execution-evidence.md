# ADR-007: Runtime Contract and execution evidence

**Status:** Proposed; prior review amendments retained, independence unverified — current self-review 2026-10-08

**Issue:** [#10](https://github.com/WernhervonSchrader/Decision-Assurance/issues/10)

**Operating profile:** Development

**Scope:** Architecture and contract mapping only; no runtime implementation is authorized.

## Context

Decision File v0.2 binds an independently approved human decision to one canonical action. It does
not authorize a runtime to execute that action and does not describe what actually happened after an
approval. Treating `APPROVED`, a successful tool response or a confidence score as proof of task
completion would collapse governance, authorization, execution, evidence and organizational
acceptance into one unsafe assertion.

Issue #10 uses research concepts such as an agent trajectory, preventive runtime controls and
evidence-gated completion as design prompts. Research papers and external schemas are informative
inputs only, not normative authority. The project contract, approved ADRs and tested schemas remain
authoritative.

The architecture preserves this separation:

`Assurance Decision != Execution Authorization != Verified Execution Outcome != Human Acceptance`

## Decision drivers

- Do not silently change the published Decision File v0.2 contract.
- Bind every execution record to one tenant, Decision File version, canonical action, approval and
  policy/constraint set.
- Make successful completion deterministic and dependent on checkable mandatory evidence.
- Preserve actor independence and keep human review distinct from technical verification.
- Store only minimized, redacted execution metadata; do not create a general tracing system.
- Fail closed on missing audit, invalid evidence, replay, concurrency conflicts or unavailable
  mandatory dependencies.
- Keep normative codes locale-neutral while supporting equivalent German and English displays.

## Alternatives

### A. Add optional execution fields to Decision File v0.2

This is a small syntactic diff, but v0.2 rejects unknown fields and promises that documentation will
not change the meaning of an existing valid document. Optional execution fields would create two
assurance meanings under one version and could make an old approval appear to grant new authority.

**Rejected:** silent normative change and ambiguous migration semantics.

### B. Publish Decision File v0.3 immediately

Version 0.3 could add a forward reference without mutating v0.2. It would be appropriate if the
binding had to travel inside every Decision File exchange. It would also force every producer and
consumer to migrate before the independent Runtime Contract has been implemented and validated.

**Deferred:** valid future option, but larger than the minimum consistent boundary for Issue #10.

### C. Introduce a separate Runtime Contract v0.1 bound to Decision File v0.2

The Runtime Contract is a separate, versioned aggregate. It references an immutable Decision File by
ID, exact version and a Runtime-owned reference digest over explicitly selected v0.2 fields. It does
not claim that Decision File v0.2 defines a full-document digest. It also binds the canonical action, approvals,
policy/constraint set and expected execution evidence. Attempts and verification outcomes live in a
separate append-only ledger.

**Selected:** v0.2 remains unchanged; a later Decision File v0.3 requires a separate ADR, schema and
explicit migration.

## Decision

### 1. Separate lifecycle concepts

| Concept | Normative meaning | What it does not mean |
| --- | --- | --- |
| Planned action | `canonical_action` in Decision File v0.2: effect, target, parameters, tenant, context and reversibility, protected by `canonical_digest`. | Approval, authorization, execution or success. |
| Assurance Decision | Deterministic `decision_outcome` and reasons; the Transition Policy separately controls the resulting Decision File lifecycle transition. | Lifecycle status by itself, permission for runtime I/O or proof that an effect occurred. |
| Execution Authorization | Immutable, short-scope server decision that all bindings and preventive controls passed for one contract and action. | Reusable bearer credential, evidence of execution or organizational approval. |
| Execution Attempt | One uniquely identified invocation under one consumed authorization, with explicit start and terminal state. | Successful effect or evidence verification. |
| Evidence Verification | Deterministic evaluation of artifacts against requirements, digests, freshness, tenant and verifier rules. | Human approval or truth beyond the evidence scope. |
| Completion Decision | Deterministic `PASS` or `FAIL` for one attempt after mandatory evidence checks and required audit writes. | Pilot, production, regulatory or business acceptance. |

An authorization is consumed by at most one attempt. An attempt has only one effective terminal
completion. A later correction is a new superseding event; it never edits history.

### 2. Relationship to Decision File v0.2

Decision File v0.2 remains byte-for-byte and semantically unchanged. Runtime Contract v0.1 is a new
contract family, not a v0.2 extension. It binds:

- `decision_id`, exact `decision_file_version` and `runtime_decision_reference_digest` over the
  explicitly mapped v0.2 fields defined by Runtime Contract v0.1;
- `canonical_action_digest`;
- ordered unique lossless approval references containing exactly the v0.2 fields
  `requirement_ref`, `approver`, `decision`, `decided_at`, `action_digest`, `nonce` and
  `approval_digest`;
- `constraint_set_digest` over effective policies, constraints and evidence requirements;
- Runtime Contract version/ID and actor-independence policy.

An action-less Decision File cannot create an execution authorization. Existing v0.2 records require
no migration. An authorized service may create a new Runtime Contract from a validated v0.2 snapshot,
but cannot infer missing action or approval authority. A future v0.3 forward reference is a separate
normative decision. No v0.2 record may be relabelled as v0.3.

### 3. Binding invariants

The immutable binding chain is:

```text
tenant_id
  -> decision_id + decision_file_version + runtime_decision_reference_digest
  -> canonical_action_digest
  -> lossless v0.2 approval fields including approval_digest + nonce
  -> constraint_set_digest
  -> runtime_contract_id + version + digest
  -> authorization_id
  -> attempt_id
  -> evidence requirement/artifact digests
  -> completion_decision
```

Every record and lookup carries `tenant_id`. Client input never establishes tenant context. The
authenticated server identity supplies it; database RLS is defense in depth.

The constraint-set digest covers the exact ordered, versioned policy and constraint inputs evaluated
at authorization time, including evidence and independence rules. Canonical serialization is
versioned. A changed policy, action, approval, execution context or requirement needs a new Runtime
Contract or authorization. Digest equality proves integrity and binding only; it does not authenticate
an actor or prove an external effect.

### 4. Runtime boundary and non-bypassability claim

The reference ordering is:

```text
authenticate -> resolve tenant -> authorize -> validate bindings
-> persist authorization event -> reserve attempt and persist reservation event
-> persist attempt-started event -> protected I/O
-> observe evidence -> reconcile if effect unknown -> verify -> persist completion
```

Rejected paths must make zero protected-adapter calls. Repository tests can prove reference-adapter
behavior only. They do not prove production non-bypassability. A deployment must separately show
that no alternate credential, network route, tool or operator path reaches the protected target.

### 5. Append-only execution ledger

Decision File events retain governance history. Runtime events use a separate tenant-scoped
append-only ledger so execution data does not mutate the Decision File.

Normative event types are:

- `runtime_contract.bound`;
- `execution.authorization_decided` with `ALLOWED` or `BLOCKED`;
- `execution.authorization_revoked` with a reason and revocation-effective time;
- `execution.attempt_reserved` as the durable consume-once boundary before protected I/O;
- `execution.attempt_started`;
- `execution.attempt_finished` with observed transport outcome, never inferred completion;
- `execution.evidence_observed`;
- `execution.evidence_availability_changed` for deletion, expiry or loss of reachability;
- `execution.evidence_verified`;
- `execution.reconciliation_decided` for `EFFECT_UNKNOWN`;
- `execution.completion_decided` with `PASS` or `FAIL`;
- `execution.evidence_hold_applied` and `execution.evidence_hold_released`;
- `execution.evidence_delete_requested` and `execution.evidence_delete_completed`;
- `execution.assertion_superseded` for correction without deletion.

Each event uses a separate Runtime Event `0.1.0` envelope with exactly `event_type`,
`schema_version`, `event_id`, `timestamp`, `tenant_scope_ref`, `actor_ref`, `correlation_id`,
`source_component`, `payload`, `sequence`, `previous_event_hash` and `event_hash`. Existing v1
`tenant_id`/`actor_id` slots are unchanged, not aliased; existing readers cannot ingest these records.
Explicit version dispatch/registration is required before runtime ingestion/export.
Reversible identity mappings remain outside the immutable ledger. Runtime payloads add contract,
authorization, attempt and artifact references where applicable, stable reason codes and a payload
digest. `previous_event_hash` links to the canonical hash of the preceding complete event; the first
event uses `null`. The chain is scoped to one tenant and Runtime Contract. Event IDs, monotonic
sequence positions and idempotency keys are unique within tenant/operation scope. Unknown event
versions are rejected under [Event versioning and migration](../EVENT-VERSIONING.md).

Authorization consumption, attempt creation and `execution.attempt_reserved` are atomic. An
`ALLOWED` authorization may be revoked only while it is unconsumed. Revocation and reservation race
under one tenant-scoped compare-and-swap: if revocation commits first, reservation fails with
`AUTHORIZATION_REVOKED` and makes zero protected-adapter calls; if reservation commits first, the
authorization is consumed and later revocation cannot cancel or rewrite that attempt. Cancellation
of a reserved or started attempt is a separate, future policy operation and must not be represented
as authorization revocation. A stale reader must re-check the committed authorization state in the
reservation transaction.

After `execution.attempt_reserved`, `execution.attempt_started` is persisted before the adapter call.
If the process cannot prove that protected I/O was not accepted, the attempt enters
`EFFECT_UNKNOWN`. It is terminal for automatic execution: neither the original authorization nor its
idempotency key authorizes a blind retry. Reconciliation is a distinct, audited operation performed
by an actor with `execution:reconcile`. It may query an adapter using the original idempotency key or
use independently observed evidence. The immutable Reconciliation Record binds the attempt, result,
supporting evidence and deciding actor. A proven effect emits new observation/verification events and
may proceed to completion; a proven no-effect may authorize a new attempt only through a new
authorization; unresolved uncertainty remains `EFFECT_UNKNOWN` and completion is `FAIL`. Reconciliation
never edits the original transport observation or converts uncertainty directly into `PASS`. When
reconciliation is required, its digest is bound by the resulting verification and completion records,
so the chain `attempt -> reconciliation -> verification -> completion` is reconstructable.

Completion uses
compare-and-swap or an equivalent transaction lock; verification, completion event and terminal state
commit atomically. Identical duplicates replay the committed result. Reuse with a changed digest
fails. Concurrent losers get a conflict or committed replay. A failure before protected I/O rolls
back state and cannot return success. A failure after an adapter may have accepted an effect records
an uncertain terminal transport outcome, forbids blind automatic re-execution and requires
reconciliation by adapter idempotency or independently observed evidence. Audit or mandatory
evidence-store failure blocks authorization/completion.

### 6. Actor independence and least privilege

Actor identity, role and actor kind remain separate and server-authorized. The Runtime Contract
actor/capability matrix is the single normative source of truth for Runtime capabilities. Existing
roles map to it exactly as follows; all unlisted assignments are denied:

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

No role aggregation implies capabilities not listed. Service identities cannot impersonate humans;
break-glass access, if introduced, requires a separate decision and is not authorized by v0.1.
Generator, Validator and Approver have no direct Protected-I/O execution capability. Approval and
execution are always distinct capabilities. The specification repeats this matrix only as an exact
copy; if copies differ, this ADR denies the disputed capability.

The verifier is distinct from generator, execution actor and evidence producer. A required
post-execution human review is a separate decision, never synthesized from
technical completion. Successful completion does not grant pilot or production acceptance.

### 7. Evidence, privacy and operations

`trajectory_ref` is opaque and bounded, not a raw trajectory. It is tenant-bound through the contract
and ledger, normalized before policy evaluation and accompanied by type, integrity digest,
source/verifier metadata, observation time, availability, data class, retention class and
residency/egress decision.

Decision Assurance does not store prompts, chain-of-thought, tokens, credentials, complete request
bodies or unfiltered screenshots as trajectory evidence. Metadata is minimized and redacted before
durable storage. External content is untrusted data and cannot provide verifier instructions.

The Runtime Ledger is an audit record and is never physically deleted, rewritten, replaced or
pseudonymized by a tenant delete operation. Immutable ledger fields contain only pseudonymous
`tenant_scope_ref`, `subject_ref` and `actor_ref` values from creation. Reversible identity mappings
are stored outside the ledger under separate access control and may be deleted or access-blocked by
approved policy without changing any event or hash. Evidence metadata and artifact bytes have separate
policy-bound retention classes. Expiry or authorized deletion removes artifact bytes and live
locators, then appends an availability event; it preserves the minimum provenance tuple
`tenant_scope_pseudonym`, artifact/requirement/attempt IDs, type, digest algorithm/digest,
observation time, source class, verifier ID/version, deletion time/reason and ledger-event hashes.
The tuple cannot re-establish artifact content and remains only until its ledger retention expires.

A legal hold is tenant-, subject-, purpose-, authority- and time-bound, blocks expiry/deletion of the
covered mappings and artifact bytes, appends hold applied/released events, and never grants new
read or egress authority. Delete requests during hold are recorded as pending and execute after
release if still valid. Backups inherit retention, hold, encryption, residency and access controls;
expired/deleted data is removed through documented backup ageing rather than in-place backup edits.
Restore occurs only into an isolated environment, re-applies holds and deletion tombstones before
general access, verifies tenant isolation plus ledger hash continuity, and must not resurrect live
artifact access. Failed restore verification leaves the service unavailable and emits no success.
All concrete periods come from an approved, versioned Retention Policy bound to tenant, data class,
retention class, legal basis, owner and effective interval. Without that policy, automatic retention
and deletion remain disabled. Store admission is a `PROJECT_CONTRACT` architecture/deployment
control; activating a named store additionally requires matching `DEPLOYMENT_EVIDENCE`. Without both,
external storage remains disabled.

### 8. Multilingual behavior

Contract versions, enums, hashes, IDs and reason codes are locale-neutral and alone affect hashes,
authorization and gates. German and English catalogs render equivalent explanations outside the
normative record. Locale selection/fallback cannot change a digest, tenant, policy or authorization.
Audit stores stable codes; localized display is derived separately. Missing translations use the
documented visible fallback and are tested.

## Contract mapping

| External concept (informative) | Existing DA artifact | Necessary addition | Effect | Decision register | Planned test evidence |
| --- | --- | --- | --- | --- | --- |
| Agent Trajectory Schema | Research attempts/audit | Opaque tenant-bound `trajectory_ref`; no raw trace | DA reference semantics normative; external schema informative | DR-02 `RESOLVED` | schema, cross-tenant and redaction negatives |
| Evidence Chain | Decision evidence, approvals, deployment evidence | Runtime chain from Decision snapshot to completion | Normative | DR-01 `DEFERRED_CAPABILITY_DISABLED` | tampering, wrong-action and chain tests |
| Evidence-gated completion | Governance/release gates | Attempt-level deterministic mandatory gate | Normative | DR-03/DR-04 `RESOLVED` | missing/stale/unavailable evidence |
| Preventive runtime control | Authorization, Transition and egress guards | Authorization/attempt boundary before target I/O | Normative for reference implementation | DR-08 `REQUIRES_DEPLOYMENT_EVIDENCE` | zero-I/O spies on rejected paths |
| Trajectory with checkable evidence | Provenance and artifact digests | Typed artifact, verifier, freshness, digest and availability | Metadata normative; external content informative | DR-02 `RESOLVED`; DR-06 `REQUIRES_DEPLOYMENT_EVIDENCE`; DR-07 `DEFERRED_CAPABILITY_DISABLED` | substitution, availability and independence tests |
| Human acceptance | Approval and pilot acceptance | Optional distinct post-execution review | Separate existing authority | DR-03 `RESOLVED` | independent-human and agent-denial E2E |

## Consequences

- Decision File v0.2 remains compatible and unchanged.
- Runtime Contract v0.1 is a separate contract, service and persistence boundary.
- Execution evidence can have a retention lifecycle distinct from governance records.
- Later work needs database tables/RLS, permissions, APIs, localization and E2E paths.
- The extra digest boundary requires canonicalization and migration/version tests.
- Repository evidence is not deployment or organizational authorization.

## Decision register

| ID | Classification | Resolution / deactivation | Status |
| --- | --- | --- | --- |
| DR-01 portable signature | `ASSUMPTION_OR_RISK` | Runtime v0.1 trusts tenant-local canonical digests and the hash-linked ledger. Portable exchange remains disabled until a separate ADR selects asymmetric signing and key lifecycle. | DEFERRED_CAPABILITY_DISABLED |
| DR-02 artifact types | `PROJECT_CONTRACT` | Runtime v0.1 uses only the closed artifact-type allowlist and exact field profiles in the specification. Unknown types fail closed. | RESOLVED |
| DR-03 human post-review | `PROJECT_CONTRACT` | Any change to a field covered by an Approval, Action, Constraint or Authorization digest invalidates the prior binding and requires the applicable new authorization and, where the original transition required it, new human approval. `EFFECT_UNKNOWN` reconciliation also requires independent human review before `PASS`. | RESOLVED |
| DR-04 deletion provenance | `PROJECT_CONTRACT` | The minimum pseudonymous tuple in section 7 survives artifact deletion until ledger-retention expiry; no raw content or reusable locator survives. | RESOLVED |
| DR-05 Decision File v0.3 | `ASSUMPTION_OR_RISK` | Not required for v0.1. Interoperable forward references require a separate ADR/version/migration; no v0.2 change is permitted. | DEFERRED_CAPABILITY_DISABLED |
| DR-06 external stores | `PROJECT_CONTRACT` | Store selection/admission is an architecture/deployment control. Activation also requires store-specific evidence for delete, hold, residency, availability and restore. | REQUIRES_DEPLOYMENT_EVIDENCE |
| DR-07 concrete retention periods | `PROJECT_CONTRACT` | No period is invented. Automatic retention/deletion requires an approved versioned Retention Policy; otherwise those capabilities remain disabled. | DEFERRED_CAPABILITY_DISABLED |
| DR-08 adapter inventory/non-bypassability | `PROJECT_CONTRACT` | Repository design covers registered adapters only. Each deployment must inventory credentials/routes and prove protected I/O cannot bypass the gate. | REQUIRES_DEPLOYMENT_EVIDENCE |

No unresolved item above authorizes implementation, Controlled Pilot, production use or a `PASS`.
All future control and test evidence remains `NOT TESTED`.

## Verification before acceptance

- Review against Issue #10, Decision File v0.2, Transition Policy, OIDC, localization, deployment
  evidence and audit conventions.
- Confirm no artifact or verifier derives authority from its own completion result.
- Confirm technical completion is not organizational acceptance.
- Confirm denied prerequisites stop before protected I/O and success audit.
- Run repository Markdown/link checks and `git diff --check`.

The proposed v0.1 numeric interoperability subset and unchanged imported timestamps are defined
field-exactly in specification §4.3/4.4. Valid v0.2 data outside that subset is preserved and refused
with RUNTIME_SOURCE_NOT_CANONICALIZABLE, not coerced or promoted to execution authority.
