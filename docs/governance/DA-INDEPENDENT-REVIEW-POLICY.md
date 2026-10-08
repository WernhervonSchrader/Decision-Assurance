# Decision Assurance Review and Owner Release Policy

**Policy ID:** DA-IRP-001
**Version:** 0.3
**Process amendment prepared:** 2026-10-01
**Explicit owner ratification:** 2026-10-08 — current project-owner instruction approving the review-obligation changes; no retroactive release approval
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

`AGENTS.md` is the binding repository-wide engineering context for every reviewer. This policy
supplements it and MUST NOT replace, narrow or weaken it. A reviewer MUST apply both; where their
requirements differ, the stricter requirement governs. This obligation is part of the shared policy
and does not depend on a Claude, Codex or other tool adapter.

Section 6 explicitly replaces earlier project-process requirements that demanded a different
human or author-independent review for software/document publication or implementation readiness
in the adopted `SOLO_OWNER` mode. This is a scoped normative change, not an inferred exception.
The stricter-rule principle still applies to substantive engineering controls, domain/runtime
approvals, external obligations and explicit third-party commitments. An older process-only
independence requirement MUST NOT silently reinstate the superseded publication block.

## 3. Review types

A review MUST declare one primary review type:

- **ARCHITECTURE REVIEW** — evaluates boundaries, invariants, trust, state and control design.
- **SECURITY REVIEW** — evaluates abuse paths, authorization, isolation, integrity, confidentiality, race conditions and fail-closed behavior.
- **CONTRACT REVIEW** — evaluates normative compatibility between specifications, schemas, events, digests, enums and referenced contracts.
- **IMPLEMENTATION-READINESS REVIEW** — determines whether production implementation can begin without requiring the implementer to invent normative behavior.
- **IMPLEMENTATION REVIEW** — evaluates whether code conforms to the approved specification.
- **EVIDENCE REVIEW** — evaluates whether a claimed control or deployment state is supported by admissible evidence.

A combined review MAY cover several types, but each conclusion MUST remain traceable to the applicable review type.

A review MUST also declare one review lifecycle:

- **FRESH REVIEW** — no authoritative earlier findings are being closed. Use the New Findings Matrix;
  if a shared matrix requires `Prior status`, record `NOT APPLICABLE`.
- **REMEDIATION-CLOSURE REVIEW** — authoritative earlier findings exist. Use the Findings Closure
  Matrix and preserve each finding's original severity and identity.

The choice of review type MUST NOT suppress a dependent review family. The following minimum families
apply; additional families remain mandatory when dependency analysis makes them relevant:

| Primary review type | Mandatory review families |
|---|---|
| Architecture | source authority, cross-contract dependencies, trust/tenant boundaries, actor independence, state/events, threat model |
| Security | source authority, authentication/authorization, least privilege, tenant isolation, secrets/privacy/residency, abuse/races, audit/evidence |
| Contract | source authority, cross-contract fields/enums, canonicalization/digests, predecessor binding, state/events, actor/tenant semantics |
| Implementation readiness | all Architecture, Security and Contract families plus traceability, disabled capabilities and implementation-blocking unknowns |
| Implementation | approved-contract conformance, negative paths, tenant/security/E2E, migrations, auditability and Definition of Done |
| Evidence | evidence admissibility, binding, freshness, tenant/deployment scope, verifier independence and acceptance hierarchy |

A narrow label cannot make an otherwise dependent Security, Tenant, Cross-Contract, Evidence or
Actor-Independence family disappear.

## 4. Required review basis

Before evaluating findings, the reviewer MUST record:

- repository and worktree or checkout,
- branch,
- base commit or tag,
- head commit or explicit uncommitted diff basis,
- exact files in scope,
- exact files explicitly out of scope,
- confirmation that `AGENTS.md` was read and applied, per section 2 and section 5.1,
- canonical specification or contract version,
- canonical source of the findings being remediated, if remediation closure is being reviewed,
- tests or evidence that were actually observed,
- tests or evidence that were not observed.
- review mode: `SOLO_OWNER` or `INDEPENDENT`;
- independence result: `ESTABLISHED`, `NOT ESTABLISHED` or `NOT ASSESSABLE`;
- accountable human owner and the requested action/scope.

A review basis that omits confirmation that `AGENTS.md` was read and applied is incomplete. Section 12
requires `FAIL` whenever the review basis is insufficient for the requested authorization; an
independent reviewer, including a generic reviewer with no tool-specific adapter, MUST treat a missing
`AGENTS.md` confirmation as exactly this case and MUST NOT issue `PASS`, `PASS WITH MINOR FINDINGS` or
`AUTHORIZE IMPLEMENTATION = YES` without it.

For an independence claim, the Review Record MUST additionally contain:

- remediation actor identity and capability;
- remediation session, agent or run identifier;
- reviewer actor identity and capability;
- reviewer session, agent or run identifier;
- model, provider or review system used for each activity;
- exact repository, commit/diff and artifact basis for remediation and review.

If remediation provenance cannot be established, independence is `NOT ASSESSABLE`; the reviewer MUST
NOT claim an independent acceptance. A fresh session, context reset, agent name or different model is
helpful evidence but never sufficient by itself. The actor that performed the remediation cannot
issue an independent `PASS` for it, even after changing model, provider, session or context.
A technical `PASS` in `SOLO_OWNER` is permitted under section 6.2 and MUST be reported as an
owner-accountable assessment, never as independent acceptance. Missing author/reviewer separation
alone does not invalidate that mode; missing primary artifacts or substantive evidence still do.

If the canonical source of previous findings cannot be located, the reviewer MUST say so.

A reviewer MAY reconstruct likely findings for a fresh assessment, but MUST NOT report reconstructed findings as the authoritative closure status of the original findings.

## 5. Normative authority and artifact classes

### 5.1 Repository and governance rules

`AGENTS.md` supplies the repository-wide Engineering Standard. This policy supplies the shared review
contract. They govern process, required engineering properties and review method; they do not invent
domain fields or behavior absent from an approved normative contract. Reviewers MUST cover Security
by Default, Least Privilege, Multi-Tenancy, multilingual behavior, privacy/data protection, secrets,
data residency, threat modelling, deterministic state transitions, auditability, E2E testing,
Definition of Done and design-before-implementation whenever applicable.

### 5.2 Approved normative contracts

Versioned specifications, contracts and ADR decisions define product behavior only when `approved`.
For this policy, `approved` means an authorized project authority has produced an immutable approval
record that identifies:

- approving actor/role and authority source;
- exact artifact ID, version and normative scope;
- exact commit and artifact digest;
- approval result and timestamp;
- any conditions, expiry or supersession relationship.

The approval record MAY be a repository governance record or a protected Git-hosting review/decision,
but it MUST be retrievable and bound to the exact artifact. Draft status, existence on a branch,
implementation, test success, recency or greater detail is not approval. If authority, version, scope
or binding is absent, the artifact is not proven approved and the gap remains a finding or
implementation-blocking unknown.

An approved artifact remains authoritative for its bound version and scope until an equally
authorized record explicitly supersedes it. A newer, more detailed or implemented artifact MUST NOT
silently override it.

### 5.3 Conformance artifacts

Schemas, event contracts and interface contracts are conformance artifacts. They are normative only
to the extent an approved contract explicitly incorporates their exact version and scope. They MUST
NOT add or resolve behavior omitted by the approving contract.

### 5.4 Implementation and evidence artifacts

Code and migrations implement; tests, fixtures and examples check or illustrate; repository,
integration and deployment evidence record observations. None may define, supplement or repair
missing normative contract behavior. A passing test proves only the tested claim against its exact
basis. A normative gap remains a finding even when code, a migration, fixture or example chose a
plausible behavior.

### 5.5 Planning and communication artifacts

Implementation plans, issues, pull-request discussions, prompts, summaries and chat transcripts are
non-normative unless an approved contract explicitly incorporates a versioned artifact. They provide
context but cannot authorize behavior.

When applicable artifacts conflict, the reviewer MUST use these classes and explicit approval/
incorporation records rather than recency. A conflict between authoritative artifacts remains a
finding until an authorized normative decision resolves it.

### 5.6 Evidence is not specification

Runtime observations and deployment evidence prove properties of a concrete implementation or environment. They do not redefine the contract.

Likewise, a project requirement or control is not itself `DEPLOYMENT_EVIDENCE`. A traceability matrix MUST distinguish at least:

- requirement/control classification,
- required evidence class,
- observed evidence,
- test or gate result.

### 5.7 No silent contract upgrade

A new runtime contract MUST NOT invent fields, enums, canonicalization rules or digest semantics and attribute them to an unchanged referenced contract.

If a runtime layer requires a derived representation that does not exist in the referenced contract, it MUST define:

- a new, separately named runtime record or digest,
- an exact lossless mapping from source fields,
- its own canonicalization and version,
- its relationship to the unchanged source contract.

## 6. Review modes and owner release authority

For the current single-maintainer operation, `SOLO_OWNER` is the adopted default for Decision
Assurance repository architecture, contracts, implementation readiness, code and software/document
publication. `INDEPENDENT` remains available when separation is established or explicitly required
for the requested scope. Record the mode before judging findings. Independence is a disclosed
assurance attribute; it is not a universal prerequisite for publishing software or documentation.

### 6.1 `INDEPENDENT`

An independent reviewer MUST NOT approve its own remediation as an independent review.

Independence is capability- and object-specific, not a role-label assertion. The reviewer MUST compare
authenticated actor identity, capability, tenant, reviewed object/decision and concrete action across
generation, validation, approval, execution, evidence production, remediation and review:

- a Generator MUST NOT independently validate or approve its own material decision;
- an Executor MUST NOT independently verify its own execution evidence;
- an Evidence Producer MUST NOT be the sole independent verifier of that evidence;
- a Remediator MUST NOT independently approve its own change;
- matching or different role names alone prove nothing;
- actor aliases, service accounts, delegated sessions and shared principals MUST be resolved far
  enough to detect the same controlling actor.

An exception is valid only when an approved normative rule identifies the exact capability, object,
tenant, action, authorizing actor and required compensating evidence. The reviewer MUST cite that
authority; exceptions MUST NOT be inferred from convenience or missing provenance.

For AI-assisted work:

- remediation and independent review SHOULD use separate sessions or agents;
- the review session MUST begin from the declared repository state rather than relying on conclusions remembered from the remediation session;
- use of a different model or provider is desirable for high-risk changes but is not sufficient by itself to establish independence;
- if the same model family is used, the reviewer MUST disclose this and use a fresh context;
- the reviewer MUST inspect primary artifacts and MUST NOT rely only on a remediation summary.

Independence concerns the review process and evidence chain, not merely the model name.

When required remediation provenance is missing, record independence and any dependent closure as
`NOT ASSESSABLE`. `NOT ASSESSABLE` cannot yield independent `PASS` or
`AUTHORIZE IMPLEMENTATION = YES` in `INDEPENDENT` mode. This restriction MUST NOT be applied to
the separately authorized `SOLO_OWNER` mode solely because personnel separation is unavailable.

### 6.2 `SOLO_OWNER`

The same human owner MAY author, remediate, technically review and authorize publication of their
own repository artifacts. The same AI actor/session MAY perform a later assessment after its
remediation. It MUST inspect the final primary artifacts, changes and relevant evidence in a
distinct review step and disclose its earlier contribution. It MUST NOT claim independent review.
A separate context, second model or external reviewer SHOULD be used when practical; none is a
mandatory solo publication gate. The owner remains the accountable decision maker.

The following compensating controls are mandatory:

1. Record the exact repository, final commit or uncommitted diff plus artifact hashes, scope,
   author/remediator/reviewer identities and available session/model provenance.
2. Perform the applicable architecture/security/contract or code review against primary artifacts;
   keep specification compliance and code quality assessments identifiable.
3. Record findings, actual checks and `NOT TESTED` accurately. Mandatory applicable checks for the
   requested action must pass; no unresolved substantive Major Finding or critical/high defect
   may be waived merely because the maintainer is alone.
4. Disclose `INDEPENDENCE = NOT ESTABLISHED` for known self-review, or `NOT ASSESSABLE` if provenance
   is insufficient. Record the concentration of author, reviewer and release authority as an
   accepted residual risk. It is not itself a blocking finding in this mode.
5. Obtain and retain the accountable owner's explicit, scope-bound release decision. AI checks,
   CI success and a technical verdict do not supply human release authority.
6. Bind the decision to the final immutable release commit and artifact digests before publication;
   re-check the head immediately before the action. Material changes require renewed technical
   review and owner authorization for the changed scope.

An uncommitted diff/hash basis is sufficient for a local review recommendation, not for executing
a release. Required evidence is proportional to the requested action: documentation publication
does not require runtime tests for unimplemented features or production evidence; executable
software publication requires its applicable build, test and security evidence. Draft/source
publication MAY disclose incomplete implementation and future gates as `NOT TESTED`, provided
known exploitable defects, secrets and false operational claims are absent and no functioning or
production-approved capability is claimed. Missing mandatory evidence for the claimed capability
remains blocking. No full threat model or additional review bureaucracy is required for an
editorial-only change unless its scope affects a material contract or security claim.

### 6.3 Publication decision and boundaries

Use separate fields:

- `REVIEW MODE = SOLO_OWNER | INDEPENDENT`
- `INDEPENDENCE = ESTABLISHED | NOT ESTABLISHED | NOT ASSESSABLE`
- `VERDICT: PASS | PASS WITH MINOR FINDINGS | FAIL`
- `AUTHORIZE IMPLEMENTATION = YES | NO` (technical readiness recommendation)
- `OWNER RELEASE DECISION = APPROVE | REJECT | PENDING`
- `PUBLICATION ELIGIBLE = YES | NO`

`PUBLICATION ELIGIBLE = YES` requires a non-blocking technical verdict, the applicable checks,
a bound `APPROVE` decision by the accountable human owner, no overriding requirement for the
requested scope, and the immutable final release basis. Otherwise use `NO`. A review result MUST
identify what is being published: documentation, draft/source, package/release or another explicit
artifact. Record owner identity/authority, policy ID/version/mode, commit and artifact hashes,
review/evidence references, remaining minor findings, independence limitation, accepted residual
risk, action/destination, decision timestamp and any conditions. A protected PR comment or
versioned decision record MAY hold this evidence. This is repository-process evidence, not a new
DA runtime record or approval schema.

Solo owner release does not grant business, expense, booking, payment, tax-rule, tenant, runtime
execution or deployment authority. It does not replace legal, contractual or customer-required
separation, or a separately promised independent assessment. Those requirements remain binding
for their scope. The Odoo pilot's separate authenticated Rule Author/Rule Approver requirement and
DA creator/reviewer runtime restrictions remain unchanged. Public documentation MUST accurately
state that review was owner-accountable, not independently certified or audited. RIF/RRS
conformance requiring independent assessment cannot be claimed from this mode.

There is no arbitrary expiry or mandatory second-person checkpoint for this solo mode. Reassess
it when ownership, staffing, risk or an external commitment changes. A fresh reviewer is an
improvement path, not a condition that indefinitely prevents a solo release.

### 6.4 Transition from earlier review gates

Preserve earlier review records and original finding severity. If an earlier blocker concerns
only the now-superseded process requirement for a different author/reviewer, retain its historical
status and record `CURRENT GATE = SUPERSEDED BY DA-IRP-001 v0.3 section 6.2` with owner authority,
affected object/scope and compensating controls. Do not mark it technically `CLOSED` or disguise
it as Minor. A current assessment uses the new gate. All substantive original findings still
require actual closure; a combined finding MUST separate its substantive part from its obsolete
personnel gate. Past verdicts, hashes and independent-review claims MUST NOT be rewritten.

## 7. Review invariants

Every applicable review MUST test the following invariants.

### 7.0 Applicability and coverage matrix

Before judging findings, the reviewer MUST create a Coverage Matrix. Every policy criterion and every
mandatory family for the declared review type receives exactly one applicability status:

- `APPLICABLE`; or
- `NOT APPLICABLE`.

`NOT APPLICABLE` requires all of: a concrete reason, relation to the declared scope, and citation of
the primary artifact or normative rule that establishes non-applicability. Missing implementation,
missing evidence, inconvenience, a narrow review label or `NOT TESTED` does not establish
non-applicability. An unjustified or omitted security-relevant criterion is a Major Finding.

| Criterion | Applicability | Scope reason | Primary artifact/rule | Review action/result |
|---|---|---|---|---|
| Source authority and approval | `APPLICABLE` or `NOT APPLICABLE` | required | required | required |
| Cross-contract compatibility | `APPLICABLE` or `NOT APPLICABLE` | required | required | required |
| Authentication and authorization | `APPLICABLE` or `NOT APPLICABLE` | required | required | required |
| Actor independence and least privilege | `APPLICABLE` or `NOT APPLICABLE` | required | required | required |
| Tenant isolation | `APPLICABLE` or `NOT APPLICABLE` | required | required | required |
| Multilingual behavior | `APPLICABLE` or `NOT APPLICABLE` | required | required | required |
| Privacy, data protection and residency | `APPLICABLE` or `NOT APPLICABLE` | required | required | required |
| Secrets and external services | `APPLICABLE` or `NOT APPLICABLE` | required | required | required |
| Threat model and abuse cases | `APPLICABLE` or `NOT APPLICABLE` | required | required | required |
| States, events, replay and races | `APPLICABLE` or `NOT APPLICABLE` | required | required | required |
| Canonicalization and integrity binding | `APPLICABLE` or `NOT APPLICABLE` | required | required | required |
| Auditability and lifecycle | `APPLICABLE` or `NOT APPLICABLE` | required | required | required |
| Tests, E2E and Definition of Done | `APPLICABLE` or `NOT APPLICABLE` | required | required | required |
| Traceability and evidence semantics | `APPLICABLE` or `NOT APPLICABLE` | required | required | required |
| Design-before-implementation gate | `APPLICABLE` or `NOT APPLICABLE` | required | required | required |

The reviewer MAY add criteria but MUST NOT remove these rows. Security-relevant dependent criteria
remain `APPLICABLE` even when they are secondary to the primary review type.

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

`Requirement -> Risk -> Control -> Required Evidence -> Observed Evidence -> Test/Gate -> Deployment Evidence -> Review Result -> Responsible Role -> Status`

For high-risk execution paths this traceability is mandatory.

The reviewer MUST distinguish design intent from observed evidence.

The normative traceability record uses separate fields:

| Requirement | Risk | Control | Required Evidence | Observed Evidence | Test/Gate | Deployment Evidence | Review Result | Responsible Role | Status |
|---|---|---|---|---|---|---|---|---|---|

`Required Evidence` states what would be admissible. `Observed Evidence` records only evidence actually
inspected. `Deployment Evidence` is empty or explicitly absent unless bound observations for a
concrete deployment were inspected. A Requirement, Risk, Control, plan or expected test MUST NOT be
copied into either observed-evidence field. `Review Result` reports the review judgment; `Status`
reports the control/evidence lifecycle and MUST retain values such as `NOT TESTED` accurately.

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

Every newly identified finding starts `OPEN`. For remediation reviews, each original finding MUST
retain its stable identity and Original Severity and receive exactly one Closure Status:

- **CLOSED** — every material aspect is resolved in the primary artifacts and the reviewer can cite the exact normative location.
- **PARTIALLY CLOSED** — some aspects are resolved but at least one material ambiguity, conflict or dependency remains.
- **OPEN** — the material finding remains unresolved.
- **NOT ASSESSABLE** — required review basis or primary artifact is unavailable.

A finding MUST NOT be marked `CLOSED` merely because the new text discusses the topic.

Original Severity is immutable review history. Current Residual Severity MAY additionally describe
the remaining impact after remediation, but it MUST NOT replace Original Severity or bypass Closure
Status. A reviewer MUST NOT reclassify an original Major Finding as Minor to remove the PASS block.
An original Major Finding remains blocking while `OPEN`, `PARTIALLY CLOSED` or `NOT ASSESSABLE`, even
if its Current Residual Severity is lower, except for a solely superseded personnel gate recorded
exactly as section 6.4 requires. This exception cannot close or waive a substantive finding.

`Original Severity` is exactly `Major` or `Minor`. `Current Residual Severity` is exactly `Major`,
`Minor` or `None`; `None` is permitted only with Closure Status `CLOSED` and does not erase history.

For a Fresh Review, use a New Findings Matrix and set every new finding to `OPEN` when identified.
There is no prior closure status; if a common schema requires the field, use
`Prior status = NOT APPLICABLE`.

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

Evaluate the conditions below against current applicable requirements. A process-only legacy
personnel gate explicitly superseded under section 6.4 is retained as history, not counted as a
current substantive Major Finding. `NOT ASSESSABLE` independence alone is not a solo `FAIL`;
unassessable substantive evidence remains blocking. No verdict implies independent acceptance
unless the declared `INDEPENDENT` mode actually establishes it.

### `PASS`

Permitted only when:

- the declared mode satisfies section 6; `SOLO_OWNER` does not require established independence,
- no Major Finding is `OPEN` or `PARTIALLY CLOSED`,
- no original Major Finding is `NOT ASSESSABLE`,
- no implementation-blocking unknown remains for the reviewed scope,
- no required primary artifact is missing,
- no material contradiction remains.

### `PASS WITH MINOR FINDINGS`

Permitted only when all `PASS` conditions above hold and remaining findings are genuinely Minor and non-blocking.

### `FAIL`

Required when:

- any Major Finding remains `OPEN` or `PARTIALLY CLOSED`,
- any original Major Finding is `NOT ASSESSABLE`,
- an implementation-blocking unknown remains,
- a required normative conflict is unresolved,
- the review basis is insufficient for the requested authorization.

## 13. Implementation authorization

The review verdict and implementation authorization MUST be stated separately.

Use exactly:

`AUTHORIZE IMPLEMENTATION = YES | NO`

`YES` requires:

- the declared review mode meets section 6 and the accountable owner is identified,
- `PASS` or `PASS WITH MINOR FINDINGS`,
- no implementation-blocking unknowns for the authorized scope,
- no higher-level project gate prohibiting implementation,
- explicit identification of any capabilities that remain disabled.

`YES` is prohibited whenever any original Major Finding is not fully `CLOSED`, regardless of Current
Residual Severity or attempted reclassification, except for the explicitly superseded process-only
gate in section 6.4. `YES` is a technical recommendation; the human owner's implementation
decision remains separate, and AI cannot sign that decision for the owner.

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

Every reviewer, including a `SOLO_OWNER` self-reviewer, MUST perform the following sequence:

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

The reviewer MUST NOT remediate files during a read-only review unless remediation is authorized.
After remediation, re-assess the final artifacts in a subsequent review step. `INDEPENDENT` requires
an independent actor; `SOLO_OWNER` permits the same actor with the disclosure and controls in
section 6.2. A remediation summary alone never substitutes for reviewing the final artifacts.

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
- review lifecycle (`FRESH REVIEW` or `REMEDIATION-CLOSURE REVIEW`),
- remediation/reviewer actor, capability, session/run and model/review-system provenance,
- declared review mode: `SOLO_OWNER` or `INDEPENDENT`,
- independence result: `ESTABLISHED`, `NOT ESTABLISHED` or `NOT ASSESSABLE`,
- accountable human owner; publication decision and exact scope when requested.

### Coverage matrix

Include every row required by section 7.0 with exactly one applicability status and the required
reason/artifact citation for each `NOT APPLICABLE` row.

### Controls

Report relevant checks such as:

- diff scope,
- whitespace/conflict checks,
- referenced-contract integrity,
- unchanged artifacts that were required to remain unchanged,
- future gates still marked `NOT TESTED` where applicable.

### Findings closure matrix

For a Remediation-Closure Review:

| Finding | Original Severity | Current Residual Severity | Prior status | Closure Status | Primary artifact and section | Reason |
|---|---|---|---|---|---|---|

For a Fresh Review, use instead:

| Finding | Original Severity | Current Residual Severity | Prior status | Current status | Primary artifact and section | Reason |
|---|---|---|---|---|---|---|
| newly assigned ID | Major or Minor | same as Original Severity | NOT APPLICABLE | OPEN | citation | reason |

### Evidence traceability matrix

Use the ten separate fields required by section 7.9. Do not collapse required, observed or deployment
evidence into Requirement or Control text.

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

Also report the mode, independence and, for a publication assessment, the separate owner decision
and publication eligibility defined in section 6.3. Use `PENDING`/`NO` when owner sign-off or the
final immutable publication basis has not been observed. Do not invent owner approval.

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

## 19. Policy conformance negative tests

These cases are normative interpretation fixtures. A conforming reviewer MUST resolve each as shown;
an adapter MUST NOT change the outcome.

| # | Negative case | Required deterministic resolution | Result |
|---|---|---|---|
| 1 | Referenced field is absent from the approved source contract | Record a cross-contract finding; do not infer the field or mapping. | DETERMINISTICALLY RESOLVED |
| 2 | Actor matrices grant contradictory rights | Major Finding; disputed capability is denied until normative reconciliation. | DETERMINISTICALLY RESOLVED |
| 3 | A required control is `NOT TESTED` | Observed test evidence is absent; never convert to `PASS`. | DETERMINISTICALLY RESOLVED |
| 4 | An external store has not been approved | Store capability remains disabled; documentation or implementation cannot approve it. | DETERMINISTICALLY RESOLVED |
| 5 | A capability requires missing Deployment Evidence | Capability remains disabled; unrelated explicitly separable scope may continue. | DETERMINISTICALLY RESOLVED |
| 6 | A transformation is plausible but undefined | Major Finding or implementation-blocking unknown; implementer cannot choose it. | DETERMINISTICALLY RESOLVED |
| 7 | Independent reviews conflict on `PASS`/`FAIL` | Use the disputed-claim procedure and primary authority; never vote or average. | DETERMINISTICALLY RESOLVED |
| 8 | Remediation actor reviews its own remediation | `INDEPENDENT`: no independent `PASS`. `SOLO_OWNER`: disclose `NOT ESTABLISHED`; technical verdict is possible under section 6.2, owner release remains separate. Unknown provenance is `NOT ASSESSABLE`. | DETERMINISTICALLY RESOLVED |
| 9 | Digest input fields are undefined | Major Finding; digest-dependent scope is not implementation-ready. | DETERMINISTICALLY RESOLVED |
| 10 | New specification conflicts with an approved existing contract | Existing approved scope remains authoritative until explicit approved supersession; conflict is a finding. | DETERMINISTICALLY RESOLVED |
| 11 | A new Major Finding has no prior closure status | Fresh Review: `Prior status = NOT APPLICABLE`, Current status `OPEN`, Original Severity Major. | DETERMINISTICALLY RESOLVED |
| 12 | Reviewer reclassifies an original Major as Minor | Preserve Original Severity Major; non-`CLOSED` status blocks `PASS` and implementation authorization. | DETERMINISTICALLY RESOLVED |
| 13 | Security criterion is marked `NOT APPLICABLE` without reason/citation | Invalid Coverage Matrix and Major Finding; review cannot `PASS`. | DETERMINISTICALLY RESOLVED |
| 14 | Generic reviewer applies this policy without `AGENTS.md` | Review basis is incomplete; required repository context is missing and review cannot `PASS`. | DETERMINISTICALLY RESOLVED |
| 15 | Solo owner has no second reviewer, all substantive controls pass | No personnel-only block; mode `SOLO_OWNER`, truthful non-independent verdict and bound owner release decision may permit publication. | DETERMINISTICALLY RESOLVED |
| 16 | AI issues `PASS` but owner has not approved release | Owner decision `PENDING`; publication eligibility `NO`. | DETERMINISTICALLY RESOLVED |
| 17 | Solo owner attempts to waive an open substantive Major/security defect | Technical verdict `FAIL`; publication eligibility `NO`. | DETERMINISTICALLY RESOLVED |
| 18 | Owner release approval refers to another commit or changed artifact | Stale binding; publication eligibility `NO` until renewed review and owner decision. | DETERMINISTICALLY RESOLVED |
| 19 | Independent certification/customer commitment is required for the action | Solo mode cannot satisfy that commitment; affected action remains blocked. | DETERMINISTICALLY RESOLVED |
| 20 | Documentation publication has no runtime implementation evidence | Future runtime checks may remain `NOT TESTED`; truthful documentation can pass its own applicable gates. No production claim. | DETERMINISTICALLY RESOLVED |
| 21 | Solo release is used to bypass DA/Odoo runtime role separation | Deny the runtime bypass; repository publication approval grants no such capability. | DETERMINISTICALLY RESOLVED |
| 22 | Earlier finding consists solely of the replaced personnel requirement | Preserve original severity/history; explicitly supersede current gate under section 6.4, never fabricate technical closure. | DETERMINISTICALLY RESOLVED |
| 23 | Existing Git-hosting rules still require another person's approval | Policy does not alter hosting settings; disclose the operational blocker, never bypass it with admin privileges. | DETERMINISTICALLY RESOLVED |
| 24 | A mixed legacy finding contains personnel and unresolved integrity defects | Only the personnel gate can be superseded; the integrity defect remains a blocking substantive finding. | DETERMINISTICALLY RESOLVED |
| 25 | Same AI actor reviews its final changes without a new session | Allowed in `SOLO_OWNER` with a distinct final-artifact assessment and full disclosure; not an independent review. | DETERMINISTICALLY RESOLVED |
| 26 | Unknown remediation provenance but final primary artifacts are assessable | Independence `NOT ASSESSABLE`; solo technical review can proceed if its substantive basis and owner authority are sufficient. | DETERMINISTICALLY RESOLVED |

Acceptance requires all twenty-six rows to remain `DETERMINISTICALLY RESOLVED` under the current policy
and every supported adapter.

## 20. Adoption, alternatives and verification

**Authority:** The project owner explicitly requested on 2026-10-01 that the review contract be
adapted for single-maintainer work so publication is possible without absolutely independent review.
This authorizes adopting the scoped process change, not an automatic release of every artifact.
Record the resulting policy commit/digest when committing; no immutable commit is claimed for the
current working-tree revision. Existing approval/binding rules still apply to release artifacts.

Alternatives considered: mandatory external human review preserves personnel separation but
blocks current solo work; removing review entirely loses technical scrutiny; `SOLO_OWNER` retains
technical gates, truthful disclosure and human accountability. The owner-directed third approach
is adopted. Its residual risk is correlated author/reviewer error and concentrated release control.
Primary-artifact review, applicable deterministic checks, recorded findings and exact release
binding reduce that risk without claiming to eliminate it.

Verification: apply section 19's fixtures, check adapter consistency, confirm that the Odoo/RIF
publication gates reference this mode, and verify substantive security and runtime approval rules
remain unchanged. This documentation change neither implements a release validator nor changes
Git-hosting branch protection. A hosting rule that still mandates another person's approval must
be reported separately; any hosting change needs an explicitly authorized, scoped configuration
update. No admin bypass is authorized by this policy.
