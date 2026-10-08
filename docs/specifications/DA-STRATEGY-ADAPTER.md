# Optional controlled strategy handoff — design

PROJECT_CONTRACT; Unreleased additive development capability. Authorized scope: user request of 2026-10-08 and supplied v2 implementation prompt. No production import, publication or deployment. Normative Decision File remains 0.2.0; package version stays 0.5.0 until a separately reviewed release (existing Unreleased convention).

## Context assessment
DA HEAD 96b32da9e146b3b276c5fec4e636f67f6ea10889; RIF HEAD e6e90e9dcd65db433a8fb7da92a8bb13dea75745. RIF handoff 3.4-rc3 is present. Existing local .gitignore edits, locally inaccessible .secrets examples (Git reported D; actual deletion is not established), .review-pr11 and Odoo design files are outside this change. Python baseline: 679 passed, 28 skipped, 3 failed: two PostgreSQL deployment tests lack DA_TEST_POSTGRES_DSN; Keycloak example-secret test fails because fixtures were already inaccessible in this sandbox. Preserve them. Existing authorization, tenant repositories, audit hash chains and DRAFT-only research handoff supply the patterns. No Superpowers plugin is available; follow repository workflow manually.

## Approaches and decision
1. Attach only original JSON: small, but material uncertainty bypasses DA validation.
2. Add normative strategy fields: rich expressiveness, but violates requested first-stage boundary and requires migration.
3. Separately validate, store original documents and mapping; append conservative DA fields transactionally. Recommended and selected: bounded, opt-in, no new strategic router or calculations. No import elevates verified status.

## Requirements matrix
| Requirement | Location | Verification / evidence |
|---|---|---|
| Three artifact types / exact RIF version | strategy/contracts.py; packaged rif schemas | valid/invalid handoff fixtures, parity hashes |
| Multilingual | existing api errors/i18n; strategy CLI | DE/EN and fallback E2E; content language stored separately |
| Multi-tenancy | strategy/store.py; migration composite keys/RLS | two-tenant reads/writes, wrong tenant negative tests |
| Authentication | existing get_identity / injected Identity | missing/expired token E2E; no role in payload |
| Authorization | existing DECISION_READ / DECISION_CREATE | generator import, readonly/approver denial; no changed permissions |
| Tenant isolation | tenant-bound transactions | horizontal and missing context tests; PostgreSQL CI |
| Input validation | pinned schemas plus DA semantic validator | references, weights, scales, periods, finite numbers, field injection |
| Audit logging | existing audit event shape + sidecar ledger | hash chain, correlation, rollback on audit failure |
| Data protection | bounded JSON, no network, tenant retention | no execution of locators; operator export/deletion guide |
| DRAFT-only and concurrency | locked transaction / expected hash | stale and concurrent writes; replay convergence |
| Immutable baseline / separate observations | strategy store | overwrite/correction/terminal case tests |
| Imported test limitations | typed provenance companion | six v2 acceptance cases; no VERIFIED/PASS/APPROVED |
| E2E testing | tests/strategy/test_e2e.py | import -> independent evaluation -> separate observation |
| CI security checks | existing verify / PostgreSQL jobs | pytest, ruff, mypy, bandit, pip-audit, secret scan, build |
| Existing governance unchanged | engine/transitions not edited | regression suite and source diff evidence |

## Architecture and boundaries
Untrusted RIF JSON + versioned DA envelope -> bounded schema validation -> semantic reference/number checks -> authenticated tenant Identity -> existing permissions -> decision read under same tenant -> immutable provenance/mapping + append-only original storage. Preview builds a copy without persistent writes. Mutation uses SQLite BEGIN IMMEDIATE or PostgreSQL tenant connection/FOR UPDATE and one transaction for case, original, baseline, mapping, audit and replay. API routes are installed only when an explicit strategy store is injected; CLI offers read-only preview, never role-asserted writing. No new tool server, provider or runtime RIF dependency.

Envelope binds tenant_id, decision_id, expected_document_hash, content_language, source provenance, selected_option_id, mode (draft/observation/baseline), and artifact. Identity is not part of the envelope. Baselines bind to an exact stored DA document and preserve whether that state was DRAFT, APPROVED or reconstructed. Baseline correction uses a new ID, predecessor and reason, preserving original decision/analysis references. Later observations bind to the stored baseline and cannot change historical case JSON. A DRAFT expectation never becomes an approved expectation automatically. A new material fact yields only a new-case proposal.

Original RIF IDs, plans, counterevidence, rankings/scenarios, attribution and unknown values remain in original JSON. DA claims/evidence/assumptions use deterministic namespaced IDs; evidence is UNVERIFIED or CONFLICTING; assumptions UNVERIFIED. Material uncertainty maps to unresolved risk plus an unsatisfied REVIEW_REQUIRED adapter-completeness constraint (STRATEGY_FULL_REPLAY_NOT_PERFORMED). The actual engine considers MEDIUM unresolved risk only in combination with high impact, so risk alone is insufficient. The constraint represents missing independent analysis validation using the existing engine path; it creates no policy or human review requirement. Hard conditions for the selected option map to MANDATORY unsatisfied constraints when violated or unknown. Positive imported compliance also remains independently unverified, hence unsatisfied; normative boolean cannot express unknown. Nonselected options remain in the sidecar and contribute uncertainty, without making all rejected alternatives mandatory constraints. No new policies or review requirements. Evidence-state ACCEPTED and eligible/winner never authorize.

DA performs structural validation and bounded semantic checks, not the complete RIF evidence pipeline or scoring replay. Full result replay is a documented contract gap, always represented as unresolved DA risk and reported as not performed. Claimed rankings are checked for reference integrity and eligibility, never called substantively verified. External locators are retained as inert strings, never opened. Imported test reports preserve method, subject, expected/observed outcome, execution state, source commit, actual file hashes and local modifications independently. Missing data stays null. Expected rejection is distinct from ERROR; NOT_REPRODUCED is inconclusive. Every imported report remains unverified even when internally complete.

Localization uses existing EN/DE error catalogs, Accept-Language detection and EN fallback; machine audit/error codes stay stable, RFC3339/JSON numbers stay machine-readable. content_language is independent of user locale and tenant default; no new UI or locale-sensitive display is introduced.

## Threat model
| Threat (likelihood / impact) | Prevention | Detection / response | Residual risk |
|---|---|---|---|
| Spoofed roles / cross-tenant IDs (medium/high) | trusted Identity, existing RBAC, composite FK, forced RLS | deny and security event | compromised identity provider |
| Tampered artifact/status/approval (high/high) | strict schemas, allowlisted mapping, no transitions | invalid request / original retained | source semantic truth unverified |
| Stale updates/replay (medium/high) | locks, expected hash, immutable IDs/digests | conflict, rollback | existing unrelated writers may need separate concurrency hardening |
| Baseline rewriting (medium/high) | append-only API, predecessor binding | conflict | database owner can tamper; protected backups required |
| Hidden uncertainty / forged PASS (high/high) | unresolved risk, mandatory conditions, unverified evidence | independent DA evaluation | no scoring/evidence-pipeline replay |
| Prompt injection/SSRF (high/high) | inert data; zero external fetch or code tools | preserved for human review | analyst can still misunderstand text |
| DoS (medium/medium) | existing 1MiB HTTP limit; JSON depth/count bounds | 413/422; bounded failure | operator rate limits remain existing perimeter responsibility |
| Repudiation/audit loss (medium/high) | transactional original/hash-linked audit and identity | fail closed rollback | hash does not authenticate human review |
| Supply chain/data leakage (low/high) | pinned local schema snapshots, no RIF runtime deps, minimized logs | existing CI scans and schema parity | scans not production certification |

## Acceptance criteria
Preview has zero persistence mutation. Only authorized DRAFT imports append DA business fields; protected fields remain identical. All invalid/stale/mismatched operations roll back. Identical retries converge without duplication; altered same IDs conflict. Six v2 reports retain uncertainty. Chosen violated/unknown hard condition cannot win governance. Baseline history survives corrections and observations; terminal cases remain byte-equivalent. Existing engine, role permissions, transitions and normative schemas are unchanged. Full local relevant checks are reported including unavailable infrastructure and preexisting failures. RIF compatibility is described by exact tested contract and bounded scope, not semantic truth.

## Design review
No full strategy router/calculator, no normative schema changes, no generic tool execution. Conservative unknown-as-unsatisfied is an explicit representation limit, not a new policy. Optional routes preserve existing OpenAPI snapshots when not injected. Implementation approval is within the user's explicit request to execute the supplied task; no new human governance approval is synthesized.

## Final review refinement

An explicit regression proved a source-free assumption import could otherwise produce PASS because MEDIUM risk is not independently actionable in the engine. Every draft mapping therefore also projects the documented missing full replay into one REVIEW_REQUIRED constraint. This changes no engine, role, transition or approval rule and imposes no external mandatory policy. Acceptance requires source-free uncertainty to yield REVIEW from the existing engine.
