# Decision Assurance v0.10 — Odoo Expense Assurance

**Status:** Proposed implementation specification for technical review and owner acceptance — `SOLO_OWNER` process update 2026-10-01

This specification defines the normative target behavior for Phase 1. It does not authorize
implementation, deployment, productive Odoo configuration, tax-rule approval, booking or payment.
The architecture decision is [ADR-007](../adr/ADR-007-odoo-expense-assurance-boundary.md).

Repository review and publication follow [DA-IRP-001 v0.3](../governance/DA-INDEPENDENT-REVIEW-POLICY.md)
section 6, in the adopted `SOLO_OWNER` mode. The same owner may author, technically review and
accept these repository artifacts; the same AI actor/session may re-assess final primary artifacts
with disclosed self-review. A second person/model/session is recommended but not mandatory.
Substantive review, applicable evidence and explicit owner authorization remain required. This
process change does not alter Rule Package authority, separate pilot Rule Author/Rule Approver,
DA lifecycle approval, Odoo business approvals or any runtime capability.

## A. Context assessment

The normative repository baseline is
`96b32da9e146b3b276c5fec4e636f67f6ea10889`. It provides Controlled Intake candidate facts and human
confirmations, a sales-oriented tenant-scoped `PolicyRegistry`, deterministic compilation to Decision
File v0.2, `PASS/REVIEW/BLOCK`, separate lifecycle approval, OIDC identity, centralized
authorization, PostgreSQL forced RLS, scoped idempotency and hash-linked audit.

Decision File v0.2 requires an explicit `canonical_action`. `canonical_action = null` means the file
authorizes no external action. A future action-bearing file must use the existing Canonical Action,
Action Digest, Approval Digest and single-use nonce contract. `APPROVED` and `BLOCKED` Decision Files
and `COMPILED` Intake artifacts are terminal; material change creates a new versioned artifact.

The current contracts do not yet provide server-owned source-authority provenance, own-case
confirmation, a Company/Tenant Resolver, an immutable confirmed-facts snapshot, a RIF Rule Package,
a complete evaluation-context digest, execution validity or Odoo post-action receipts. Existing
normalized objective facts may become `VERIFIED` without human confirmation. Existing audit tables
are not all protected from regular runtime update/delete privileges below application logic.

Scope is an isolated, testable advisory assurance contract. Excluded are concrete German tax rules,
BMF packages, DATEV, reimbursement, production configuration, OCR provider selection, a RIF
authoring engine, DA-bound external action authority, distributed DA/Odoo execution locking and
retrospective treatment of completed bookings after later rule revocation.

## B. Normative language and assurance classification

`MUST`, `MUST NOT`, `SHOULD` and `MAY` are `PROJECT_CONTRACT` terms, not external standards.
Repository and CI results are repository/integration evidence only. Unverified Odoo federation,
registry deployment and external execution behavior remain `ASSUMPTION_OR_RISK` until concrete
deployment evidence exists.

Governance outcome remains exactly `PASS`, `REVIEW` or `BLOCK`. Decision lifecycle, artifact version
and execution validity are separate:

```text
historical outcome != current execution validity
historical artifact != successor artifact
DA PASS != DA APPROVED != Odoo Expense Approval
DA PASS != Booking Authorization != Payment Authorization
```

Phase 1 is advisory. Its Decision File has `canonical_action = null`; DA authorizes no Odoo action.

## C. Requirements matrix

| Requirement | Implementation boundary | Test method | Completion evidence |
| --- | --- | --- | --- |
| Trusted source provenance | server ingestion/provenance contract | spoofed source-class contract tests | no auto-`VERIFIED`, compiler/evaluator not called |
| OCR confirmation | Intake verification/compiler | 99.9% and provider variants | all OCR/LLM facts remain confirmation-required |
| Identity federation | existing OIDC/Identity plus approved federation profile | forged-user/service-token negatives | immutable human subject from verified token |
| Company/Tenant resolution | generic `CompanyTenantResolver` | missing/ambiguous/revoked/cross-tenant tests | denial before domain repository access |
| Own-case confirmation | central RBAC and object authorization | owner/role/kind/state negatives | `INTAKE_CONFIRM_OWN` only for eligible own case |
| Confirmed facts | immutable snapshot and canonical SHA-256 | ordering/Unicode/decimal/mutation tests | stable versioned snapshot digest |
| Required Fact Set | expense profile plus authenticated package | bootstrap/completeness matrix | no implicit or circular required-field logic |
| RIF authority | versioned successor registry and adapter | forged approval/signature/author collision | exactly one authenticated eligible package |
| Package selection | tenant/jurisdiction/applicability/time/lineage | ambiguity/downgrade/revocation tests | no automatic `PASS` on invalid selection |
| Deterministic evaluation | pure expense evaluator plus existing DA Engine | permutation and repeated-run tests | stable results for identical full context |
| Evaluation binding | canonical `evaluation_context_digest` | change every normative component | every semantic drift changes digest |
| Outcome separation | Decision File/lifecycle/validity contracts | enum and authority-negative tests | no `INVALIDATED` outcome; no Odoo permission |
| Versioned mutation | new Intake/snapshot/Decision/evaluation | reopen-terminal negative test | v1 retained; v2 created and linked |
| Odoo boundary | thin inbound adapter | dependency/runtime graph tests | no callback, admin secret or embedded engine |
| Action receipt | post-action evidence service | authorization non-effect and replay tests | receipt changes no Odoo/DA authority state |
| Input validation | strict versioned schemas | unknown fields, mass assignment, size tests | authority fields rejected or ignored fail closed |
| Audit | append-only runtime grants plus hash chain | effective-role update/delete/truncate tests | DB denial and full reconstruction |
| Data protection | minimal reference/hash storage | canary, retention/export/delete tests | no receipt body/token leakage |
| Multilingual | stable codes plus DE/EN display | locale/fallback/formatting tests | German and English journeys pass |
| Multi-tenancy | identity-derived tenant, resolver, composite keys, RLS | two-company/two-tenant E2E | no read, write, inference or replay across tenants |
| E2E | isolated API/Odoo fake/PostgreSQL | positive and prohibited journeys | commit-bound Golden Evidence Set |
| CI security | existing gates extended | schema, migration, RLS, SAST/SCA/secret/container checks | mandatory checks available and green |

## D. Proposed architecture and trust boundaries

```text
Odoo authenticated human                              EXTERNAL IDENTITY
  -> DA-verifiable delegation/broker token            TRUST BOUNDARY
  -> existing immutable DA Identity                   DETERMINISTIC
  -> CompanyTenantResolver                            DETERMINISTIC/AUTHORITATIVE
  -> trusted server-side receipt ingestion            TRUST BOUNDARY
  -> server-owned Provenance Binding                  DETERMINISTIC
  -> OCR/LLM candidate values                         PROBABILISTIC/UNTRUSTED
  -> own-case authorization                           DETERMINISTIC
  -> explicit correction/confirmation                 HUMAN
  -> Bootstrap Facts                                 CONFIRMED/EXPLICIT
  -> Rule Package candidate selection                 SERVER-CONTROLLED
  -> package and approval validation                  DETERMINISTIC/AUTHORITATIVE
  -> applicability determination                      DETERMINISTIC
  -> versioned Required Fact Set                      DETERMINISTIC
  -> collection/confirmation of remaining facts        HUMAN WHERE REQUIRED
  -> final Confirmed Facts Snapshot                    DETERMINISTIC
  -> evaluation_context_digest                        DETERMINISTIC
  -> pure expense-rule evaluation                     DETERMINISTIC
  -> existing DA Engine                               DETERMINISTIC
  -> PASS | REVIEW | BLOCK                            ADVISORY GOVERNANCE RESULT
  -> Odoo-owned approval and execution                EXTERNAL/HUMAN AUTHORITY
  -> post-action receipt                              AUDIT EVIDENCE ONLY
```

Protected commands enforce:

```text
authenticate
-> resolve identity and tenant
-> resolve/validate company mapping
-> authorize role, actor kind, ownership and object
-> validate request, provenance and state
-> persist required audit/policy decision
-> perform domain mutation
-> return result
```

Failure in an earlier gate prevents later repository, registry, evaluator or adapter work. Phase 1
contains no DA outbound Odoo I/O.

## E. Identity federation, company mapping and ownership

Before own-case confirmation is implemented, Phase 1 MUST select and document exactly one supported
test/deployment profile:

1. a DA-verifiable delegated user token; or
2. a reviewed standard token-exchange/trusted identity-broker flow.

The profile records issuer, audience, authorized party/client, subject mapping, actor kind, tenant
claim, external organization claim, token lifetime, replay control, revocation and session behavior.
A service token MAY authenticate the Odoo application but MUST NOT turn payload `user_id`,
`confirmed_by`, `tenant_id`, `company_id` or owner fields into human authority.

`CompanyTenantResolver.resolve(identity, source_system, external_organization_ref, at_time)` returns
one authoritative tenant-bound mapping or fails. The mapping contract includes mapping ID/version,
authority source, source-system identity, external organization reference, DA tenant, `valid_from`,
optional `valid_until`, revocation state/time, created/changed-by authorized identity and audit
reference. The tuple `(authority source, source system, external organization reference, effective
time)` MUST resolve to at most one DA tenant. Missing, multiple, expired, revoked or identity-conflict
mappings fail before case lookup or domain processing.

Case creation records immutable owner actor, tenant, mapping reference and external company reference
from the verified context. `INTAKE_CONFIRM_OWN` requires human kind, matching owner, matching tenant,
matching authoritative mapping and an allowed non-terminal Intake state. `GENERATOR` receives no
global `INTAKE_CONFIRM`. Existing Validator/Approver global behavior remains unchanged and grants no
expense, rule, booking or payment authority.

## F. Trusted Source Provenance and candidate facts

Candidate values supplied by Odoo are untrusted. Authority fields are not writable contract inputs.
The server creates a versioned Provenance Binding containing at least:

- provenance-binding ID and schema version;
- tenant, case/intake and source-document reference;
- source-document SHA-256;
- trusted ingestion-path identity and version;
- extractor identity and version;
- extraction method;
- server-assigned source class;
- ingestion timestamp and correlation ID;
- canonical provenance digest.

The server derives the source class from a case-sensitive allowlist of trusted ingestion/extractor
registrations. Client claims such as `source_class`, `trusted_extractor`, `verification_class` and
`confirmation_required` are rejected as unknown/mass-assignment fields or retained only as untrusted
observations that cannot influence authority.

Only a server-authorized deterministic retrieval/verification method MAY use the legacy automatic
verification policy. Unknown, missing, untrusted, unsupported, unattested or inconsistent provenance
sets `mandatory_human_confirmation=true`. OCR and LLM always set it to true. No verifier may clear it
automatically; normalization and confidence never affect it. The compiler independently verifies the
trusted provenance binding and rejects every OCR/LLM-derived or fail-closed candidate without an
authenticated confirmation/correction.

Candidate facts retain original raw/normalized values, immutable source/provenance references,
confidence, verification state and correction history. Original extraction is never overwritten.

## G. Presence, Required Fact Set and Confirmed Facts Snapshot

Every fact requirement has one explicit presence representation:

- `VALUE`: typed value present;
- `NOT_SUPPLIED`: no assertion supplied;
- `NOT_AVAILABLE`: authenticated actor confirms it cannot be obtained;
- `NOT_APPLICABLE`: authenticated actor asserts non-applicability, subject to deterministic rule;
- `UNKNOWN`: value cannot presently be established.

Omission, `null` and empty string MUST NOT silently map to a presence state.

Stage 1 uses a versioned Bootstrap Fact Set: the bounded minimum facts needed to determine
jurisdiction, expense profile and package applicability. Its definition is available before final
package selection and is independent of the final Required Fact Set. Bootstrap facts must be
confirmed or explicitly represented. They support server-side Rule Package candidate selection,
followed by package/approval validation and deterministic applicability determination.

Stage 2 derives the complete versioned Required Fact Set only after selecting and validating the
uniquely applicable Rule Package. The canonical Required Fact Set is the deterministic union of:

```text
expense-profile base requirements
+ applicability bootstrap requirements
+ selected Rule Package requirements
```

It records profile/package versions, requirement IDs, types, conditional applicability expressions
and a canonical digest. If bootstrap requirements are unresolved such that exactly one package cannot
be selected, package selection stops fail closed; the system does not guess a package or a Required
Fact Set. This is the control-stop branch of section I; unresolved bootstrap information cannot
become a guessed selection or an implicit outcome. Once a package is validly selected, remaining
unknown/incomplete facts follow section I's REVIEW/BLOCK rules.

Remaining required facts are collected and confirmed after Required Fact Set derivation.
DA creates a final Confirmed Facts Snapshot only after every applicable requirement has an allowed typed
representation and every mandatory confirmation is present. The immutable snapshot contains schema
and canonicalization versions, predecessor reference where applicable, case/intake version,
Required-Fact-Set digest, ordered facts/presence states, source-document/provenance digests,
confirmation references/actors/times and tenant persistence binding.

## H. RIF Rule Package authority and selection

Phase 1 introduces `RulePackageRegistry` as a versioned successor port and a legacy adapter from the
existing `PolicyRegistry`. Legacy `PolicyContext` behavior is not changed. The new port owns only RIF
package resolution; the adapter relationship, supported versions and deprecation path are explicit
and contract-tested.

The Rule Package schema includes:

- schema/canonicalization version, registry identity and registry-record reference;
- tenant scope, package ID/version, jurisdiction and structured applicability;
- `effective_from`, optional `effective_until`, `revoked_at` and revocation reason;
- `supersedes` and optional `superseded_by` lineage;
- author identity and authenticated approval identity, authority scope and `approved_at`;
- source references/provenance digests;
- deterministic rule IDs, definitions and Required Fact Set contributions;
- conflict declarations/resolution references;
- package hash and authenticated provenance/signature metadata.

Registry provenance MUST be authenticated through a reviewed signature with key identity/status or
an equivalently authenticated, integrity-protected registry channel and immutable record. A package
self-assertion of `APPROVED` is insufficient. DA validates that the approval identity is a human
authorized for the tenant, jurisdiction and package class and differs from the Rule Author for the
pilot.

The server, never the client, selects a package from tenant, jurisdiction, canonical applicability
context, authoritative evaluation instant and lineage. Selection must produce exactly one current
eligible package. Zero or multiple candidates, unresolved conflicts, unknown registry/schema/rule
versions, invalid provenance/signature, unauthorized/self approval, future/expired/revoked packages,
hash mismatch or a requested downgrade stop before evaluator invocation. A normatively superseded
package is ineligible even if its former validity interval would otherwise match.

## I. Total fact/control result semantics

| Fact/control state | Review permitted by applicable rule? | Required result |
| --- | ---: | --- |
| Known compliant | irrelevant | compliant contribution |
| Known violation | irrelevant | `BLOCK` |
| Unknown/incomplete | yes | `REVIEW` |
| Unknown/incomplete | no | fail-closed `BLOCK` |
| Deterministically not applicable | irrelevant | excluded with stable reason and rule reference |
| Authority failure | irrelevant | control failure; stop before domain evaluation |
| Integrity/provenance failure | irrelevant | control failure; stop before domain evaluation |
| Authentication/authorization/tenant failure | irrelevant | reject before domain evaluation |
| Package selection ambiguity/failure | irrelevant | control failure; no evaluator call or outcome |
| Mandatory audit failure | irrelevant | operation fails; no successful transition |

No state has an implicit outcome. Control failures are not converted into fachlich `REVIEW` or
`BLOCK`; the protected operation fails with a stable control reason before the DA Engine is invoked.

The pure expense evaluator consumes only a Confirmed Facts Snapshot, Required Fact Set and validated
Rule Package. It emits evaluated rule IDs, stable reasons, fact references, calculations and
compliant/non-compliant/unresolved contributions. The existing DA Engine alone produces
`PASS/REVIEW/BLOCK`.

## J. Complete executable evaluation context

An evaluation records an immutable versioned Evaluation Context. Its canonical digest binds directly
or through explicitly documented nested digests:

```text
confirmed_facts_hash
confirmed_facts_schema_version
confirmed_facts_canonicalization_version
required_fact_set_digest
rule_package_id
rule_package_version
rule_package_hash
rule_package_schema_version
rule_package_canonicalization_version
expense_evaluator_identity
expense_evaluator_version
da_engine_identity
da_engine_version
applicability_context_hash
authoritative_evaluation_instant
numeric_policy_version
currency_policy_version
rounding_policy_version
```

Canonical JSON uses the approved versioned algorithm: UTF-8, Unicode normalization defined by the
canonicalization version, lexicographically sorted object keys, no insignificant whitespace, exact
typed decimal/date/currency representations and omission of the digest field itself. Nested digests
may replace duplicated content only when their schema, canonicalization and covered fields are
normatively documented.

The authoritative evaluation instant is an input used for package validity and time-dependent rules;
it is distinct from an audit-record creation timestamp. Two evaluations may be claimed reproducible
only when the complete normative Evaluation Context is identical. Changing any covered component
changes `evaluation_context_digest`.

## K. Versioned mutation and execution validity

`COMPILED` Intake and terminal Decision Files are never reopened. A material correction after v1
creates Intake v2 linked to v1, obtains new confirmations where required, creates Snapshot v2 and
then Decision/evaluation v2. It does not mutate v1.

An evaluation begins `ACTIVE` only after its context and audit writes succeed. Discovery of a binding
change marks v1 `INVALIDATED` through compare-and-set. A successful current v2 marks v1
`SUPERSEDED`; the transition preserves the prior outcome and context. There is no transition from
`SUPERSEDED` back to `ACTIVE`. Duplicate or racing transitions are idempotent or conflict
deterministically and append audit evidence.

Execution validity indicates whether DA considers an evaluation current for advisory retrieval. It
does not grant or revoke external Odoo execution authority.

## L. Decision File v0.2 and Odoo receipt boundary

Phase 1 uses advisory Decision File v0.2 with `canonical_action = null`. `PASS` therefore means only
that the defined assurance checks passed. It does not authorize an Odoo action. Odoo independently
authenticates, authorizes and performs its business workflow.

The absence of external action authority does not remove existing Decision Assurance lifecycle
approval-binding requirements. Existing DA approval entries retain all mandatory fields, Approval
Digest and single-use nonce semantics, including when `canonical_action = null` and their
`action_digest = null`. DA lifecycle approval binding is separate from external execution
authorization and Odoo execution tokens/reservations. Phase 1 introduces no new external execution
token and does not bypass existing approval validation.

After an Odoo action, Odoo MAY submit an idempotent Action Receipt containing stable external
action/object reference, action type, occurred-at time, observed evaluation/context references and
the authenticated actor/mapping context. Actor and tenant authority come only from verified identity
and `CompanyTenantResolver`, never receipt fields.

> The Odoo Action Receipt is post-action audit evidence only. It is not an execution authorization,
> lock, reservation, validity check, or stale-action prevention mechanism.

Receipt acceptance validates schema, identity, tenant/case association and idempotency and records
what DA observed. A mismatched or stale referenced evaluation produces explicit discrepancy evidence;
it must not be relabelled as proof that the external action was prevented. Same idempotency key and
payload replay; changed payload conflicts. Receipt handling changes no governance outcome, Decision
lifecycle, external permission, booking or payment state.

Phase 1 does not guarantee prevention of a stale Odoo action between result retrieval and external
execution. This is an explicit residual risk/non-goal. A future separately approved assurance level
may add Canonical Action and Action Digest plus a pre-action reservation, execution nonce,
compare-and-set, short validity and acknowledgement. Phase 1 introduces none of that external
execution protocol; existing DA lifecycle Approval Digest and nonce requirements remain unchanged.

## M. Audit, persistence, localization and data protection

Tenant-owned records, keys, references and idempotency scopes include the DA tenant. PostgreSQL
forced RLS remains defense in depth. Same external IDs in two tenants remain isolated.

Relevant audit structures are append-only for regular runtime roles and tamper-evident, not absolutely
immutable against PostgreSQL owner, migration, recovery or DBA authority. Regular roles lack
`UPDATE`, `DELETE` and `TRUNCATE`; privileged roles are separate, unavailable to runtime, monitored
and operationally audited. Audit persistence failure blocks the corresponding DA transition.

Audit reconstructs identity/federation, company mapping, trusted provenance, candidates/corrections,
confirmations, artifact lineage, Required Fact Set, snapshot/context digests, authenticated package
and approval, evaluated rules, outcome/validity changes and post-action receipt/discrepancy.

Machine contracts and reason codes are locale-independent. User-facing text uses German and English
with English fallback. Locale formatting never enters canonical digests. Odoo remains the document
system of record; DA stores the minimum immutable references, hashes and facts. Receipt bodies,
tokens, credentials and unnecessary personal data do not enter logs, metrics, errors or CI artifacts.
Retention, export, deletion, legal hold and backup expiry remain tenant-scoped controlled workflows.

## N. Threat model

| Threat | Likelihood/impact | Prevention and detection | Response/residual risk |
| --- | --- | --- | --- |
| Client labels OCR deterministic | high/critical | server-owned provenance; reject/ignore authority fields; compiler test | deny compilation; compromised trusted ingestion remains |
| OCR confidence bypass | high/critical | unconditional OCR/LLM confirmation | block; compromised human remains |
| Service impersonates human | medium/critical | delegated subject, actor kind, party/replay checks | deny/revoke; IdP compromise remains |
| Company/tenant spoofing | high/critical | authoritative resolver before lookup; RLS | deny/non-enumerating response; resolver admin compromise remains |
| Submitter confirms foreign case | medium/critical | owner/tenant/state object policy | deny/audit; stolen human session remains |
| Forged package approval | medium/critical | authenticated registry provenance and approver authorization | stop selection; authority-key compromise remains |
| Rule author self-approves | medium/high | human author/approver separation | reject package; governance exception requires ADR |
| Package downgrade/ambiguity | medium/critical | server selection and lineage checks | no evaluator call; registry lineage defect remains |
| Evaluation drift | high/critical | complete context digest and component-version tests | re-evaluate; undeclared implementation change remains supply-chain risk |
| Unknown becomes pass | medium/critical | total result table and Required Fact Set | block/review/control stop; rule defects remain |
| Reopen terminal artifact | medium/high | successor versions and transition tests | reject mutation; linkage defect remains |
| PASS treated as action authority | high/critical | `canonical_action=null`, explicit advisory contract | block DA authority claim; Odoo configuration is external |
| Stale Odoo action race | medium/high | visible residual-risk test; receipt is evidence only | discrepancy/incident handling; prevention outside Phase 1 |
| Duplicate/forged receipt | medium/high | identity, tenant scope, strict schema, idempotency | conflict/audit; action already external |
| Audit mutation | low/critical | DB grants, RLS, hash chain and export verification | block release/restore; privileged DB operator remains |
| Sensitive-data leakage | medium/high | minimization, redaction, retention | incident/erasure; Odoo storage remains external |
| Runtime LLM authority | medium/critical | no LLM dependency in validator/evaluator graph | release block; build-time approval defect remains |

## O. Acceptance criteria

1. Client authority-class fields cannot create trusted provenance or automatic verification.
2. OCR/LLM facts cannot compile without authenticated human confirmation, including at 99.9%.
3. Federation and Company/Tenant resolution precede ownership and confirmation.
4. Service credential plus supplied user identity never satisfies a human gate.
5. A human confirms only eligible facts in their own same-tenant case.
6. Snapshot completeness uses a versioned non-circular Required Fact Set.
7. Exactly one authenticated, approved, applicable, current, non-revoked, non-superseded package may
   reach evaluation; forged approval, ambiguity and downgrade do not.
8. Rule Author and Rule Approver are different authorized humans for the pilot.
9. `evaluation_context_digest` covers every normative runtime input listed in section J.
10. Equal full contexts reproduce equal rule results/outcomes; changing any component changes digest.
11. Unknown/incomplete evidence follows the total table and never passes implicitly.
12. `COMPILED` v1 is never reopened; mutation produces linked v2 artifacts.
13. Historical outcome, artifact version and execution validity remain distinct.
14. Phase 1 Decision Files use `canonical_action=null` and grant no external action authority.
15. Receipt processing is post-action evidence only and has no authorization effect.
16. The stale external action race is visible as an explicit Phase 1 residual risk.
17. Regular PostgreSQL runtime roles cannot update/delete/truncate append-only audit structures.
18. Two tenants/companies cannot read, mutate, infer or replay each other's artifacts.
19. German and English behavior and stable machine codes pass.
20. The runtime performs no LLM call for provenance authority, package validation, evaluation,
   governance, authorization, audit truth or Odoo execution.
21. The complete Golden Evidence Set is bound to the exact implementation commit.

## P. Golden Case Evidence Set

One commit-bound set contains the positive flow and all negatives.

Positive flow:

```text
authenticated Odoo human
-> verified federation and company/tenant mapping
-> trusted server-side provenance
-> OCR candidate with incorrect amount
-> correction and explicit confirmation
-> Bootstrap Facts
-> Rule Package candidate selection
-> package and approval validation
-> applicability determination
-> versioned Required Fact Set
-> collection/confirmation of remaining required facts
-> final Confirmed Facts Snapshot
-> complete evaluation context digest
-> deterministic PASS | REVIEW | BLOCK
-> Odoo independently authorizes and performs its workflow
-> post-action receipt as evidence
-> complete audit reconstruction
```

Mandatory negatives:

- N1: 99.9% OCR confidence without confirmation -> no evaluation.
- N2: client claims OCR is deterministic/trusted -> claim rejected/ignored, confirmation mandatory.
- N3: material change after compiled v1 -> v1 not reopened, linked v2 required.
- N4: foreign/ambiguous/revoked company mapping -> rejection before domain processing.
- N5: forged, self-approved, revoked, expired, conflicted, ambiguous or downgraded package -> no
  evaluator call or automatic `PASS`.
- N6: changed evaluator, canonicalization, instant or numeric/currency/rounding policy -> different
  `evaluation_context_digest`.
- N7: evaluation changes after Odoo read but before Odoo action -> DA does not claim prevention;
  receipt remains evidence and discrepancy/residual risk is visible.

## Q. Open governance questions and residual risks

The retrospective treatment of bookings completed before later package revocation remains unresolved.
Phase 1 does not reverse, relabel or reopen completed Odoo transactions. Prevention of the external
stale-result race likewise remains outside Phase 1. Neither residual risk may be presented as closed
by Action Receipts, repository tests or successful CI.
