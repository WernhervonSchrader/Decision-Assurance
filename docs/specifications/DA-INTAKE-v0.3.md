# DA Public Draft v0.3 — Controlled Real-World Intake

**Status:** implementation specification approved by project owner  
**Positioning:** Public Draft; no standard, certification, compliance, medical or legal approval claim

## Context and objective

v0.2 accepts a fully structured Decision File. It cannot prove that fields such
as evidence status, constraint satisfaction or approvals were derived from
trusted information. v0.3 adds a distinct controlled intake pipeline:

`raw input → candidates → gaps/conflicts → verification/human confirmation → compilation → Decision File → existing engine`

The Intake extracts possible facts. It does not decide truth, import policies or
authority from user text, or select a governance outcome.

## Trust model and boundaries

| Level | Meaning | May drive deterministic findings? |
| --- | --- | --- |
| `RAW_INPUT` | Untrusted user text retained by hash and object reference. | No |
| `CANDIDATE` | Extracted possible fact with span, method and confidence. | No |
| `VERIFIED` | Matched by a deterministic verifier against tenant trusted context. | Yes |
| `HUMAN_CONFIRMED` | Confirmed/corrected by an authenticated authorized human. | Yes |
| `REJECTED` | Explicitly rejected; original candidate remains immutable. | No |
| `UNRESOLVED` | Missing, ambiguous or conflicting. | No; creates review need |
| `DERIVED_FINDING` | Deterministic rule output with fact/policy/calculation references. | Yes |

Extraction confidence is only confidence that text was parsed as intended, not
truth probability. Text commands, claimed roles, approvals, policies and
outcomes remain candidates. Missing evidence is not negative evidence; an
unresolved registry reference is not labelled fabricated.

## Components

> Intake interprets untrusted input. The compiler translates verified intake
> state into a Decision File. Only the Decision Assurance Engine evaluates that
> Decision File and produces an assurance outcome.

- `intake/contracts.py`: typed records and stable enums.
- `intake/extractor.py`: replaceable `Extractor` protocol and deterministic DE/EN quote extractor.
- `intake/policies.py`: tenant-scoped trusted Policy Pack protocol and in-memory reference registry.
- `intake/verification.py`: deterministic normalization, conflicts, gaps and derived findings.
- `intake/lifecycle.py`: separate Intake state machine.
- `intake/confirmation.py`: immutable human confirm/correct/reject/unresolved actions.
- `intake/compiler.py`: fail-closed compilation into a Decision File without invented values.
- `intake/service.py`: orchestration, idempotency and audit.
- dedicated Intake repository protocol/tables in the same v0.3 database, using
  migration `002_controlled_intake_v0_3.sql`; physical database separation is
  explicitly deferred.
- API/CLI adapters: transport only; no extraction or governance rules.

## Contracts and evolution

Normative schemas live under `schemas/intake/` and packaged copies under
`src/decision_assurance/schemas/intake/`. Every object has `schema_version:
"0.3.0"`; unknown fields and future versions fail closed. Patch versions may add
optional fields without changing existing semantics. New required fields,
changed enums or changed trust meaning require a new schema version and explicit
migration.

Contracts are Intake Request, Intake Record, Candidate Fact, Source Reference,
Extraction Report, Ambiguity/Conflict, Verification Requirement, Human
Confirmation/Correction, Compilation Report and Intake Audit Event. Candidate
facts contain stable ID, semantic type, raw/normalized value, optional unit or
currency, source/span, extractor method/version, extraction confidence,
verification status, conflict references and confirmation requirement.

Untrusted request schemas contain no accepted `fabricated`, `outdated`,
`satisfied`, `approved`, tenant, actor, policy result or outcome fields.

## Intake lifecycle

`RECEIVED → EXTRACTED → NEEDS_CONFIRMATION → READY → COMPILED`

Additional terminal transition: any non-terminal state may become `REJECTED` by
an authorized human. `EXTRACTED → READY` is allowed only when all required facts
are verified or human-confirmed and no blocking ambiguity remains. `COMPILED`
and `REJECTED` are terminal. Retries with the same scoped idempotency key and
payload hash replay; changed payload conflicts. Every transition records tenant,
actor, source/target, correlation, reason codes and hash linkage.

All Intake primary and foreign keys include `tenant_id`; cross-tenant
relationships are structurally impossible in the reference schema. Intake owns
no `PASS`, `REVIEW`, `BLOCK` or `APPROVED` value. Unresolved mandatory facts
force `NEEDS_CONFIRMATION` and reject compilation.

## Extraction and deterministic verification

The deterministic extractor supports DE/EN amounts/currencies, percentages,
discount, margin, min/max thresholds, payment terms, durations, dates, policy
and exception references, claimed approvals/roles, explicit missing values and
conflicting repeated values. Locale parsing distinguishes German and English
separators. Extraction never contacts a network and never loads benchmark
expectations.

Trusted Policy Packs are tenant-scoped inputs supplied outside raw text through
an interchangeable `PolicyRegistry` port. Extractors also use an interchangeable
port and their outputs remain untrusted candidates. v0.3
rules cover discount maximum, minimum margin, evidence freshness, duration
exceptions, required approvals, role independence and conflicts. Findings cite
fact IDs, policy ID/version, rule ID, calculation, result and uncertainty.

## Human confirmation

Only authenticated human `VALIDATOR` or `APPROVER` roles may confirm, correct,
reject or mark unresolved as permitted by centralized authorization. Agent kind
is rejected. Corrections create a new action containing old/new value, reason,
actor and time; candidates are not overwritten. Tenant, identity and role come
from authentication. Idempotency prevents duplicate actions/events.

## Compilation

Compilation is the only component allowed to construct a Decision File and is
allowed only in `READY`. It uses verified or human-confirmed
facts plus trusted Policy Pack records. Missing values remain missing and are
represented as review requirements/limitations; no plausible defaults are
invented. The compiler never writes final `APPROVED`, verified approvals not in
trusted context, or an outcome. The existing engine evaluates the compiled
Decision File without incompatible contract changes.

## API and CLI

API resources under `/v1/intakes`: create, extract/inspect, confirm, readiness,
compile, evaluate and audit. Authentication, tenant isolation, 1 MiB request
limit, JSON content type, idempotency and localized error contract reuse v0.2.
CLI adds nested `intake create|inspect|confirm|compile|evaluate|benchmark` using
the same service contracts.

## Requirements matrix

| Requirement | Implementation | Verification evidence |
| --- | --- | --- |
| Trust separation | intake contracts/service/compiler | contract and compiler negative tests |
| DE/EN and locale numbers | extractor + i18n catalog | locale extraction and fallback tests |
| Multi-tenancy | intake tables/repository require `TenantContext` | two-tenant same-ID E2E |
| Authentication | existing injected authenticator | missing/invalid token API tests |
| Authorization | new intake permissions in centralized matrix | role and human-kind negative tests |
| Tenant isolation | scoped SQL keys and queries | raw/candidate/action/file/audit isolation assertions |
| Input validation | strict schemas, content-type/body limits | malformed/mass-assignment/security tests |
| Audit logging | hash-linked Intake events with tenant/correlation | lifecycle/action/idempotency tests |
| Data protection | raw text minimized, no body logging, documented retention | repository and documentation review |
| Deterministic extraction | replaceable protocol + regex/locale extractor | span/normalization/metamorphic tests |
| Trusted policies | tenant-scoped registry separate from raw text | raw-only vs trusted-context tests |
| Human confirmation | immutable actions; verified actor | confirmation/correction/idempotency tests |
| Decision compilation | READY-only compiler, no invented values/outcome | compiler/engine regression tests |
| E2E | FastAPI TestClient + CLI subprocess-free entry calls | complete two-tenant and CLI journeys |
| CI security | Ruff, mypy, pytest, Bandit, pip-audit, Gitleaks, build | workflow and local command output |

## Objective acceptance criteria

1. All ten Intake contracts validate examples and reject invalid/mass-assigned fixtures with stable DE/EN errors.
2. The extractor produces exact provenance spans and normalized values for DE/EN formats without assigning truth.
3. Raw-only claims never produce `PASS`; trusted context/human confirmation is required.
4. Thirteen required corpus cases and raw/trusted variants produce documented deterministic results.
5. Confirmation is human-only, immutable, idempotent and tenant-scoped.
6. Compilation cannot occur before `READY` and never invents missing values or an outcome.
7. API and CLI complete intake→compile→existing-engine journeys.
8. Existing 77 tests and DATS remain green; new unit/contract/integration/E2E/security/metamorphic tests pass.
