# ADR-007: Odoo-orchestrated deterministic expense assurance boundary

**Status:** Proposed for technical review and owner acceptance — `SOLO_OWNER` process update 2026-10-01

## Context

Decision Assurance already separates Controlled Intake, deterministic governance, lifecycle,
identity, tenant isolation and audit. The first Odoo expense use case adds probabilistic receipt
extraction, submitter confirmation, an externally approved RIF Rule Package and an Odoo-owned
business workflow. Without an explicit boundary, untrusted input could assign its own authority
class, OCR confidence could be mistaken for fact authority, a `PASS` could be mistaken for payment
approval, or incomplete evaluation bindings could be presented as reproducible.

This ADR resolves the Phase 0 architecture decisions and the findings from the first independent
review. It does not select tax rules, an OCR provider, an Odoo deployment model or the governance
treatment of completed bookings after later rule revocation. It also does not introduce distributed
locking between DA and Odoo.

The normative repository baseline is
`96b32da9e146b3b276c5fec4e636f67f6ea10889`. It includes Decision File v0.2, its Canonical Action,
Action Digest, Approval Digest, single-use nonce and terminal lifecycle contracts.

## Alternatives

### A. Odoo orchestrates through the Decision Assurance API

Odoo owns receipt upload, OCR initiation, user interaction and business workflow. It submits
untrusted candidate values, obtains a deterministic DA assurance result and later records an Odoo
action as post-action evidence. DA has no generic Odoo administrator credential and makes no
outbound Odoo callback in Phase 1.

### B. Decision Assurance calls Odoo through a worker and outbox

This supports asynchronous notification but adds Odoo credentials, guarded egress, retries,
dead-letter recovery and additional partial-failure states before the first use case needs them.

### C. Embed the Decision Assurance engine in Odoo

This reduces network calls but duplicates runtime, identity, schema, audit and release boundaries.
It would make contract and engine-version drift difficult to detect and could bypass DA controls.

## Decision

Choose A and adopt the following normative decisions.

### 1. Authority-relevant provenance is server-owned

OCR- or LLM-derived values never gain fact authority from confidence, normalization, field type,
source quality, model or provider. They remain extracted candidate facts until an authenticated human
explicitly confirms or corrects them.

Untrusted input must never establish the authority class of its own facts. Odoo and other clients may
submit observations about origin, but request fields such as `source_class`, `extraction_method`,
`trusted_extractor`, `verification_class`, `confirmation_required` or semantic equivalents cannot
grant authority and are rejected or ignored for authority decisions.

Authority-relevant provenance is assigned only through a trusted server-side ingestion binding that
records at least the source-document hash, ingestion path, extractor identity and version, extraction
method, server-assigned source class and a deterministic provenance binding. Only a known,
server-authorized deterministic ingestion method may remain eligible for existing automatic
verification. Unknown, missing, untrusted, unsupported, unattested or inconsistent provenance fails
closed to mandatory human confirmation. OCR and LLM always require human confirmation.

> No OCR-derived value may become an authoritative case fact without explicit authenticated human
> confirmation or correction, even if a client claims that the source is deterministic or trusted.

### 2. Identity and company mapping precede own-case confirmation

The Phase 1 order is:

```text
verified delegated identity
-> authoritative company-to-tenant resolution
-> immutable object ownership
-> object authorization
-> INTAKE_CONFIRM_OWN
```

A submitter may confirm only eligible facts in their own same-tenant case and an allowed Intake
state. Confirming transcription is not validation, rule approval, expense approval, booking approval,
payment approval or authorization. `GENERATOR` receives only `INTAKE_CONFIRM_OWN`, never unrestricted
`INTAKE_CONFIRM`. Client-supplied actor, tenant, company, owner or confirmer identifiers grant no
authority.

The preferred federation is an authenticated Odoo human represented by a DA-verifiable delegated
token. If direct verification is unavailable, Phase 1 must approve a standard token-exchange or
trusted identity-broker profile before ownership or confirmation is implemented. A service credential
plus a client-supplied user ID is never an authenticated human.

A generic `CompanyTenantResolver` maps a verified external organization identity and source-system
identity to exactly one DA Tenant. Its authority source, uniqueness, tenant binding, validity,
revocation, change authorization and mapping-change audit are server-controlled and versioned.
Ambiguous, missing, expired or revoked mappings fail before domain repository access.
`odoo_company_id` is context to validate, never tenant authority.

### 3. Outcome, lifecycle, artifact version and execution validity are separate

Governance outcomes remain exactly `PASS`, `REVIEW` and `BLOCK`. Decision lifecycle remains the
existing `DRAFT -> VALIDATION -> REVIEW -> APPROVED | BLOCKED` contract. Execution validity is a
separate dimension with `ACTIVE`, `INVALIDATED` and `SUPERSEDED`. Historical outcomes and artifacts
are not rewritten.

`COMPILED` Intake is terminal. A material fact change creates a new Intake version, a new Confirmed
Facts Snapshot and a new Decision/evaluation. There is no transition out of the old `COMPILED`
artifact. The previous evaluation becomes `INVALIDATED` when its binding is no longer current and
`SUPERSEDED` when a replacement becomes current; its historical outcome remains unchanged.

Every evaluation binds a canonical `evaluation_context_digest`. The digest covers, directly or by a
documented nested digest:

- confirmed-facts hash, schema version and canonicalization version;
- Rule Package identity, version, hash, schema version and canonicalization version;
- expense evaluator identity and version;
- DA engine identity and version;
- applicability-context hash;
- authoritative evaluation instant;
- numeric, currency and rounding policy versions.

Two evaluations may be claimed reproducible only when their complete normative evaluation context is
identical. A timestamp recorded merely for audit is not a substitute for the bound authoritative
evaluation instant.

### 4. RIF packages use one explicit versioned authority path

Phase 1 chooses a versioned successor port, `RulePackageRegistry`, with an explicit adapter from the
existing tenant-scoped `PolicyRegistry`. The existing sales-specific `PolicyContext` and its
`get_active(tenant_id)` behavior remain unchanged for legacy flows. They are not silently
reinterpreted as RIF contracts. The adapter/deprecation boundary is versioned and contract-tested;
there are no competing authority ports for the same package selection.

The registry contract binds registry identity, tenant, package identity/version, jurisdiction,
structured applicability, validity, authenticated approval authority, author identity, approval
time, source provenance, machine-readable rule identifiers, integrity provenance, conflicts,
revocation and supersession.

DA does not trust a package merely because it declares `APPROVED`. Registry provenance must be
authenticated by a reviewed signature or an equivalent authenticated channel and immutable registry
record. The approval authority must itself be authenticated and authorized for the tenant,
jurisdiction and package class. For the pilot, Rule Author and Rule Approver must be different human
identities unless a future governance ADR explicitly accepts an exception.

Selection is server-controlled and deterministic over tenant, jurisdiction, applicability context,
authoritative evaluation instant and normative package lineage. It must resolve exactly one eligible
package. Missing, unknown, multiple-applicable, conflicting, unapproved, expired, future, revoked,
hash-mismatched, provenance-invalid or authority-invalid packages stop before evaluation. A package
that is normatively superseded cannot be selected merely because its former time interval remains
otherwise valid. `supersedes`, `superseded_by`, `revoked_at`, `effective_from` and `effective_until`
or equivalent versioned fields define downgrade-resistant lineage.

An LLM must not interpret authoritative tax or policy prose at runtime. Build-time assistance has no
normative effect until the artifact is validated, tested, authenticated, approved, versioned and
hash-bound.

### 5. Missing and unknown semantics are total and fail closed

The expense domain distinguishes `VALUE`, `NOT_SUPPLIED`, `NOT_AVAILABLE`, `NOT_APPLICABLE` and
`UNKNOWN`. Omission, `null` and empty string have no implicit fachlich meaning. Known compliant facts
contribute compliance; a known violation yields `BLOCK`; decision-relevant unknown or incomplete
information yields `REVIEW` only when the applicable rule permits review and otherwise yields
fail-closed `BLOCK` or an explicitly defined control stop. Authority, integrity, authentication and
authorization failures are control failures and never become epistemic `REVIEW`.

A versioned Bootstrap Fact Set defines the minimum facts needed to determine jurisdiction, expense
profile and package applicability without consulting the final Required Fact Set. The order is:
Bootstrap Facts -> Rule Package candidate selection -> Rule Package validation -> applicability
determination -> versioned Required Fact Set -> collection/confirmation of remaining required facts
-> final Confirmed Facts Snapshot -> evaluation_context_digest -> deterministic evaluation.
Unresolved bootstrap facts that prevent unique applicable package selection cause a control stop;
they never authorize a guessed selection. The existing total unknown/missing semantics remain
authoritative. The final snapshot is complete only after the selected, validated applicable package
and profile have supplied all fact requirements.

### 6. Phase 1 is advisory expense assurance

The Controlled Intake compiler continues to emit Decision File v0.2 with
`canonical_action = null`. Therefore DA provides an assurance result only and authorizes no external
action. `DA PASS` is not DA lifecycle approval and is not an Odoo business permission.

The absence of external action authority does not remove existing Decision Assurance lifecycle
approval-binding requirements. With `canonical_action = null`, an existing DA lifecycle approval uses
`action_digest = null` but still requires all existing approval fields, Approval Digest and single-use
nonce semantics under Decision File v0.2. DA lifecycle approval binding is distinct from external
execution authorization and from an Odoo execution token/reservation. Phase 1 introduces no new
external execution token and does not weaken existing DA approval contracts.

A later DA-bound external action authority would additionally require Canonical Action and its Action
Digest, with a separately approved execution protocol, ADR and threat model; it is outside Phase 1.

Odoo independently performs its own business approval and workflow action. The Odoo Action Receipt
is post-action audit evidence only. It is not an execution authorization, lock, reservation or
stale-action prevention mechanism. Receipt validation can detect and record a mismatch but cannot
undo or claim to have prevented an action already performed by Odoo.

Phase 1 explicitly does not guarantee that Odoo cannot use a stale result between its last DA read
and external execution. That integration race is a documented residual risk and non-goal. A later
assurance level may define a pre-action intent/reservation, single-use nonce, Canonical Action digest,
compare-and-set, short validity window and execution acknowledgement; none is implemented in Phase 1.

### 7. Odoo remains the business system of record

Odoo owns authenticated UI, receipt storage, OCR initiation and display, user interaction, expense
approval, accounting, reimbursement and downstream accounting integration. DA owns Controlled
Intake, identity/tenant enforcement, confirmation integrity, authenticated Rule Package validation,
deterministic evaluation, governance outcome, evaluation-context binding and audit evidence.

Phase 1 includes no DA-to-Odoo callback, embedded DA engine, generic Odoo administrator credential,
direct booking, direct payment, DATEV integration or LLM workflow orchestration.

The following remain distinct:

`DA PASS != DA APPROVED != Odoo Expense Approval != Booking Authorization != Payment Authorization`.

### 8. Actor independence

Expense Submitter, Odoo Expense Approver, Rule Author, Rule Approver, DA Engine, DA Reviewer and Odoo
Workflow are distinct responsibilities. Fact confirmation, rule approval, assurance evaluation,
exception review, business approval and execution remain separate. A submitter's confirmation of
their own receipt facts is allowed and is not self-approval. Rule Author and Rule Approver are
separate authenticated humans for the pilot.

### 9. Audit enforcement terminology

Phase 1 audit structures are append-only for regular runtime roles and tamper-evident through hash
linkage; they are not absolutely immutable against PostgreSQL owner, migration, recovery or DBA
authority. Regular application roles lack `UPDATE`, `DELETE` and `TRUNCATE`. Migration and recovery
authority remains separate, least-privileged, operationally audited and unavailable to normal
runtime identities.

The audit chain reconstructs authenticated actor, trusted source provenance, candidates,
corrections, confirmations, versioned snapshot, Required Fact Set, authenticated Rule Package,
complete evaluation-context digest, outcome, artifact/validity transitions and post-action receipt.

## Deterministic-first principle

> Decision Assurance uses probabilistic systems only where uncertainty is unavoidable or
> productivity materially benefits. Decision authority remains deterministic wherever the governing
> facts and rules permit deterministic evaluation.

OCR is probabilistic; confirmation and unresolved review are human; identity, tenant enforcement,
provenance classification, package selection/validation, expense evaluation and
`PASS/REVIEW/BLOCK` are deterministic. No runtime LLM decides provenance authority, rule validity,
tax compliance, outcome, authorization, audit truth, booking or payment.

## Consequences

- Existing Identity, TenantContext, Controlled Intake, Decision File v0.2, lifecycle, engine, RLS,
  idempotency and audit contracts remain authoritative.
- Changed trust semantics use explicit new contract versions and migrations; legacy meanings are not
  silently changed.
- Generic federation, company/tenant resolution, provenance, Rule Package and expense-evaluation
  contracts belong in DA Core. Odoo routes and receipts remain a thin adapter boundary.
- `COMPILED` Intake remains terminal; material mutation creates versioned successor artifacts.
- Missing knowledge may reach `REVIEW` only under an applicable rule; authority and integrity failures
  never degrade into review or pass.
- The post-action receipt improves reconstruction but does not strengthen external execution control.
- Retrospective treatment of completed bookings after later package revocation remains an open
  governance decision outside Phase 1.

## Review gate

This ADR requires a documented architecture/security/contract assessment under
[DA-IRP-001 v0.3](../governance/DA-INDEPENDENT-REVIEW-POLICY.md), section 6, before Phase 1.
The adopted mode is `SOLO_OWNER`: a separate human, model or session is recommended but not
mandatory. The author/remediator may assess the final primary artifacts in a distinct review step
with disclosed non-independence; the accountable owner may accept their own repository artifacts.
A technical verdict, substantive finding closure, exact artifact binding and explicit owner
authorization remain required. Missing personnel separation alone is not a publication or
implementation-readiness blocker. Rule Author/Rule Approver and DA/Odoo runtime/business role
separation remain unchanged. Publication follows the separate owner release gate in policy
section 6.3; this amendment does not itself approve a release or Phase 1 implementation.
Acceptance authorizes planning only. It is repository evidence, not deployment, tax-content,
organizational or production authorization.
