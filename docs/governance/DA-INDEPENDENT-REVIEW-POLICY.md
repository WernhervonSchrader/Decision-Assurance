# Decision Assurance Independent Review Policy

**Policy ID:** DA-IRP-001  
**Version:** 0.1  
**Status:** PROJECT GOVERNANCE STANDARD  
**Scope:** Architecture, security, contract, implementation-readiness and evidence reviews for Decision Assurance  
**Applies to:** Human reviewers and AI-assisted reviewers, independent of model or vendor

## 1. Purpose

Decision Assurance reviews must produce reproducible judgments from primary artifacts rather than model-specific interpretation.

This policy defines a single review contract for Codex, Claude Code, ChatGPT and human reviewers. A reviewer may use different tools or models, but the evidence rules, finding semantics and authorization gates are the same.

The governing principle is:

> A reviewer may identify ambiguity. A reviewer may not silently resolve ambiguity on behalf of the specification.

A review is successful only when another qualified reviewer can reproduce the verdict from the same repository state, review basis and evidence.

## 2. Normative language

The terms **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT** and **MAY** are normative within this project policy.

This policy does not replace a versioned Decision Assurance contract, schema or ADR. It defines how those artifacts are reviewed.

## 3. Review types

A review MUST declare one primary review type:

- **ARCHITECTURE REVIEW** — evaluates boundaries, invariants, trust, state and control design.
- **SECURITY REVIEW** — evaluates abuse paths, authorization, isolation, integrity, confidentiality, race conditions and fail-closed behavior.
- **CONTRACT REVIEW** — evaluates normative compatibility between specifications, schemas, events, digests, enums and referenced contracts.
- **IMPLEMENTATION-READINESS REVIEW** — determines whether production implementation can begin without requiring the implementer to invent normative behavior.
- **IMPLEMENTATION REVIEW** — evaluates whether code conforms to the approved specification.
- **EVIDENCE REVIEW** — evaluates whether a claimed control or deployment state is supported by admissible evidence.

A combined review MAY cover several types, but each conclusion MUST remain traceable to the applicable review type.

## 4. Required review basis

Before evaluating findings, the reviewer MUST record:

- repository and worktree or checkout,
- branch,
- base commit or tag,
- head commit or explicit uncommitted diff basis,
- exact files in scope,
- exact files explicitly out of scope,
- canonical specification or contract version,
- canonical source of the findings being remediated, if remediation closure is being reviewed,
- tests or evidence that were actually observed,
- tests or evidence that were not observed.

If the canonical source of previous findings cannot be located, the reviewer MUST say so.

A reviewer MAY reconstruct likely findings for a fresh assessment, but MUST NOT report reconstructed findings as the authoritative closure status of the original findings.

## 5. Source-of-truth hierarchy

### 5.1 Normative claims

Unless a versioned contract explicitly defines another precedence rule, use this order for normative interpretation:

1. approved versioned specifications, contracts and ADR decisions explicitly scoped to the reviewed version;
2. versioned schemas, event contracts and interface contracts explicitly referenced by those normative documents;
3. implemented code and migrations;
4. tests, fixtures and examples;
5. implementation plans, issues, pull-request discussions, prompts and chat transcripts.

A lower-ranked artifact MUST NOT silently amend a higher-ranked normative artifact.

If two applicable normative artifacts at the same level conflict, the conflict is a finding until the specification establishes precedence or reconciles them.

### 5.2 Evidence is not specification

Runtime observations and deployment evidence prove properties of a concrete implementation or environment. They do not redefine the contract.

Likewise, a project requirement or control is not itself `DEPLOYMENT_EVIDENCE`. A traceability matrix MUST distinguish at least:

- requirement/control classification,
- required evidence class,
- observed evidence,
- test or gate result.

### 5.3 No silent contract upgrade

A new runtime contract MUST NOT invent fields, enums, canonicalization rules or digest semantics and attribute them to an unchanged referenced contract.

If a runtime layer requires a derived representation that does not exist in the referenced contract, it MUST define:

- a new, separately named runtime record or digest,
- an exact lossless mapping from source fields,
- its own canonicalization and version,
- its relationship to the unchanged source contract.

## 6. Independent-review requirement

An independent reviewer MUST NOT approve its own remediation as an independent review.

For AI-assisted work:

- remediation and independent review SHOULD use separate sessions or agents;
- the review session MUST begin from the declared repository state rather than relying on conclusions remembered from the remediation session;
- use of a different model or provider is desirable for high-risk changes but is not sufficient by itself to establish independence;
- if the same model family is used, the reviewer MUST disclose this and use a fresh context;
- the reviewer MUST inspect primary artifacts and MUST NOT rely only on a remediation summary.

Independence concerns the review process and evidence chain, not merely the model name.

## 7. Review invariants

Every applicable review MUST test the following invariants.

### 7.1 Fail closed

Unknown, stale, conflicting, missing or unverifiable security-relevant state MUST NOT be converted into approval, execution or `PASS` by default.

An explicitly disabled capability is acceptable when:

- the disabling condition is normative,
- the capability cannot be reached through another path,
- the disabled state is visible and testable,
- documentation does not simultaneously claim the capability is active.

A deliberately disabled capability is not automatically an implementation blocker for unrelated capabilities.

### 7.2 Actor independence and least privilege

Generator, validator, approver, executor, reviewer and governance roles MUST have unambiguous responsibilities.

If multiple actor or capability matrices exist, they MUST be provably consistent or one MUST be declared the single normative source of truth.

A reviewer MUST treat contradictory execution rights, approval rights or bypass capabilities as a Major Finding.

### 7.3 Cross-contract field compatibility

For every record that references another versioned contract, the reviewer MUST verify:

- referenced fields actually exist,
- field meanings are compatible,
- required fields are not lost,
- transformations are explicit and deterministic,
- enums are either reused exactly or explicitly mapped,
- identifiers and tenant bindings remain intact.

A plausible-looking runtime field list is not sufficient evidence of compatibility.

### 7.4 Canonicalization and digest compatibility

For each digest or signature dependency, the reviewer MUST determine:

- exact input fields,
- canonicalization algorithm,
- encoding and timestamp rules,
- array ordering rules,
- domain separation where applicable,
- hash/signature algorithm,
- versioning,
- parent or predecessor bindings.

A new canonicalization rule MUST NOT be retroactively attributed to a referenced contract that did not define it.

### 7.5 Cryptographic dependency binding

If a downstream result is normatively valid only because an upstream decision, reconciliation, verification, authorization or evidence record exists, the downstream integrity chain MUST bind that dependency by digest or another equally deterministic, tamper-evident mechanism.

A reviewer MUST ask:

> Can an attacker substitute, remove or mix-and-match this required predecessor while preserving the downstream result?

If yes, the dependency is not closed.

### 7.6 State and event completeness

Normative state diagrams, event lists, architecture overviews and implementation plans MUST agree on security-relevant transitions.

Events required for authorization, reservation, execution, reconciliation, revocation, hold, deletion, acceptance or audit MUST have sufficiently defined names, payloads, actors and transition semantics for the stated scope.

An overview MUST NOT omit a security checkpoint that detail sections require before a protected action.

### 7.7 Concurrency and race behavior

Security-relevant competing transitions MUST define atomicity or conflict behavior.

At minimum, the reviewer MUST inspect relevant races involving:

- authorize vs revoke,
- reserve vs revoke,
- retry vs unknown external effect,
- hold vs delete,
- tenant or actor context changes,
- duplicate or replayed requests.

If an implementer must choose the race winner semantics, the contract is not implementation-ready.

### 7.8 Append-only integrity

Audit-critical append-only or hash-chained records MUST NOT be mutated in place.

If privacy obligations require deletion, pseudonymization or restriction, the design MUST preserve the append-only invariant through an explicit compatible mechanism, such as pseudonymous references, side mappings, lifecycle events or tombstones.

A document that simultaneously requires immutable events and in-place rewriting contains a Major Finding.

### 7.9 Traceability

Every material requirement SHOULD be traceable through:

`Requirement -> Risk -> Control -> Required Evidence -> Test/Gate -> Responsible Role -> Status`

For high-risk execution paths this traceability is mandatory.

The reviewer MUST distinguish design intent from observed evidence.

## 8. Evidence semantics

### 8.1 `NOT TESTED`

`NOT TESTED` means exactly that no test result has established the control.

It MUST NOT be interpreted as:

- `PASS`,
- partial evidence,
- implementation completion,
- pilot acceptance,
- deployment verification.

A pre-implementation design review MAY legitimately contain future gates marked `NOT TESTED` if the implementation is not yet claimed to exist.

### 8.2 Self-declaration

A statement in documentation that a control exists is not independent runtime or deployment evidence that the control is effective.

Where the project requires concrete deployment evidence, the reviewer MUST verify the evidence against the exact deployment, tenant, commit and applicable artifact bindings.

### 8.3 Evidence freshness and scope

Evidence MUST be evaluated only for the object, tenant, commit, deployment and time window to which it is bound.

Evidence from another version or environment MUST NOT be silently reused.

## 9. Finding severity

### 9.1 Major Finding

A finding is **Major** when at least one of the following is true:

- an implementer must invent a security-relevant or normative behavior;
- two applicable contracts or matrices prescribe incompatible behavior;
- authorization, tenant isolation or actor independence is ambiguous or bypassable;
- a required evidence or cryptographic dependency is not bound;
- canonicalization or digest semantics allow incompatible implementations;
- a race condition can change authorization, execution or evidence outcome without defined semantics;
- append-only or audit integrity is contradicted;
- a required fail-closed condition can become fail-open;
- a claimed `PASS`, acceptance or authorization is unsupported by required evidence.

### 9.2 Minor Finding

A finding is **Minor** only when the correction does not require choosing between materially different security, authorization, evidence, state or compatibility behaviors.

Examples include a missing cross-reference, naming clarification or an invariant already uniquely determined by the normative artifacts but not stated in the clearest location.

### 9.3 Editorial observation

Pure wording, formatting or non-normative readability issues SHOULD be reported separately and MUST NOT inflate security severity.

## 10. Finding closure status

For remediation reviews, each original finding MUST receive exactly one status:

- **CLOSED** — every material aspect is resolved in the primary artifacts and the reviewer can cite the exact normative location.
- **PARTIALLY CLOSED** — some aspects are resolved but at least one material ambiguity, conflict or dependency remains.
- **OPEN** — the material finding remains unresolved.
- **NOT ASSESSABLE** — required review basis or primary artifact is unavailable.

A finding MUST NOT be marked `CLOSED` merely because the new text discusses the topic.

## 11. Implementation-blocking unknowns

An **implementation-blocking unknown** is an unresolved choice that an implementer must decide in order to implement the authorized scope correctly.

Examples include undefined:

- field mappings,
- canonicalization,
- role-to-capability assignments,
- state transitions,
- race semantics,
- mandatory artifact schemas,
- predecessor bindings,
- authorization requirements.

A deferred capability is not an implementation-blocking unknown when the contract unambiguously keeps it disabled and the authorized implementation does not depend on it.

Deployment evidence that can only exist after implementation is not by itself an implementation-blocking unknown, provided the contract already specifies what evidence is required and the affected deployment capability remains inactive until evidence exists.

## 12. Review verdicts

Review verdicts are distinct from Decision Assurance runtime/business outcomes such as `PASS`, `REVIEW` and `BLOCK`.

A review MUST use one of:

### `PASS`

Permitted only when:

- no Major Finding is `OPEN` or `PARTIALLY CLOSED`,
- no implementation-blocking unknown remains for the reviewed scope,
- no required primary artifact is missing,
- no material contradiction remains.

### `PASS WITH MINOR FINDINGS`

Permitted only when all `PASS` conditions above hold and remaining findings are genuinely Minor and non-blocking.

### `FAIL`

Required when:

- any Major Finding remains `OPEN` or `PARTIALLY CLOSED`,
- an implementation-blocking unknown remains,
- a required normative conflict is unresolved,
- the review basis is insufficient for the requested authorization.

## 13. Implementation authorization

The review verdict and implementation authorization MUST be stated separately.

Use exactly:

`AUTHORIZE IMPLEMENTATION = YES | NO`

`YES` requires:

- `PASS` or `PASS WITH MINOR FINDINGS`,
- no implementation-blocking unknowns for the authorized scope,
- no higher-level project gate prohibiting implementation,
- explicit identification of any capabilities that remain disabled.

`NO` is mandatory after `FAIL`.

Implementation authorization does not authorize deployment, Controlled Pilot, production use or regulatory approval.

## 14. Conflicting independent reviews

Conflicting reviewer verdicts MUST NOT be resolved by majority vote, model reputation or averaging confidence scores.

Create a disputed-claim table containing:

- claim,
- reviewer A position,
- reviewer B position,
- authoritative primary artifact,
- exact field/section/event/digest under dispute,
- resolved fact,
- resulting finding status.

For each disputed claim, inspect the primary artifact directly.

If the primary artifacts themselves conflict, the conflict remains a finding. Do not choose the interpretation that makes the implementation easier.

## 15. Required review procedure

An independent reviewer MUST perform the following sequence:

1. Establish exact review basis and scope.
2. Confirm the diff or artifact set actually reviewed.
3. Locate the canonical source of any previous findings.
4. Identify applicable normative contracts and their versions.
5. Build cross-contract mappings for referenced fields, enums, events and digests.
6. Check state/event ordering and security checkpoints.
7. Check actor/capability consistency and least privilege.
8. Check canonicalization, digest and predecessor bindings.
9. Check tenant binding, authorization, replay and race behavior.
10. Check append-only, retention, deletion, hold and recovery invariants where applicable.
11. Check traceability and evidence-class semantics.
12. Distinguish disabled capabilities from unresolved behavior.
13. Record all remaining implementation-blocking unknowns.
14. Assign finding closure status and severity.
15. Issue verdict and separate implementation-authorization decision.

The reviewer MUST NOT remediate files during an independent read-only review unless the task explicitly changes from review to remediation. If remediation occurs, a later independent review is required.

## 16. Required output format

Every implementation-readiness or remediation-closure review MUST contain these sections:

### Review basis

- repository/worktree,
- branch,
- base/head or diff basis,
- files in scope,
- files out of scope,
- canonical findings source,
- observed tests/evidence.

### Controls

Report relevant checks such as:

- diff scope,
- whitespace/conflict checks,
- referenced-contract integrity,
- unchanged artifacts that were required to remain unchanged,
- future gates still marked `NOT TESTED` where applicable.

### Findings closure matrix

| Finding | Severity | Prior status | Current status | Primary artifact and section | Reason |
|---|---|---|---|---|---|

### New findings

Separate Major, Minor and editorial observations.

### Implementation-blocking unknowns

List each unknown explicitly. If none remain, state `None`.

### Disabled capabilities

List capabilities intentionally disabled and the activation condition for each.

### Verdict

Use exactly:

`VERDICT: PASS | PASS WITH MINOR FINDINGS | FAIL`

and

`AUTHORIZE IMPLEMENTATION = YES | NO`

## 17. Anti-patterns

A Decision Assurance reviewer MUST NOT:

- infer missing contract fields because they would be convenient;
- declare a finding closed solely because a topic is now mentioned;
- treat `NOT TESTED` as evidence;
- treat a requirement as the evidence that satisfies itself;
- accept two contradictory actor matrices as "complementary" without proving equivalence;
- invent canonicalization for a referenced unchanged contract;
- omit a required predecessor from an integrity chain;
- rewrite an append-only invariant through prose without defining a compatible mechanism;
- downgrade a security ambiguity to Minor merely because implementation has not started;
- approve its own remediation as an independent review;
- resolve conflicting reviews by voting rather than checking primary artifacts.

## 18. Model and tool neutrality

This policy is the shared review contract. Agent-specific instruction files SHOULD reference it rather than reproduce divergent copies.

A model-specific adapter MAY define how a tool loads the policy, but MUST NOT weaken its review criteria.

The policy is intentionally independent of OpenAI, Anthropic or any other model provider.
