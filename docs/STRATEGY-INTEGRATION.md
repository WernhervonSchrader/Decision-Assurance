# Controlled strategy handoff (Unreleased)

PROJECT_CONTRACT. Optional adapter version `rif-3.4-rc3/da-1`; pinned RIF contract `3.4-rc3`. Package release remains 0.5.0 and normative Decision File 0.2.0. No runtime RIF installation, provider, network access, new strategy router, tool server or financial calculator is required.

## Start with a read-only preview

From the repository, using the installed Python environment:

```powershell
.\.venv\Scripts\python.exe -m decision_assurance.cli strategy-preview examples/strategy/decision.json examples/strategy/envelope.json --locale de
.\.venv\Scripts\python.exe -m scripts.strategy.synthetic_journey
.\.venv\Scripts\python.exe -m pytest tests/strategy -q
```

The CLI emits the conservative proposed document, mapping, original test-method distinctions and reason codes. It never writes case files and cannot assert a role for an import. Its tenant is an offline preview label, not authenticated write authority. On error it emits the existing DE/EN INVALID_REQUEST message. The examples are synthetic and contain inert source locators.

For application use, inject `strategy_store=SqliteStrategyStore(database_path)` or `PostgresStrategyStore(connections)` into the existing `create_app`. SQLite requires `store.initialize()` after `SqliteDecisionRepository.initialize()`; PostgreSQL requires migration 005 under the existing migration role. The adapter is disabled when no store is supplied. Existing runtime constructors do not enable it automatically; deployments must deliberately wire the store only after their integration acceptance. No new environment flag or credentials are added.

## Bounded authenticated API

| Operation | Path | Existing permission |
|---|---|---|
| Preview, no case/artifact writes | POST /v1/strategy/preview | decision:read |
| Atomic record / DRAFT content import | POST /v1/strategy/imports | decision:create |
| Read original, provenance, binding and mapping | GET /v1/strategy/artifacts/{artifact_id} | decision:read |

Existing Bearer authentication establishes Identity, tenant, roles and kind. Do not build Identity from source documents or request roles. The Python library assumes Identity is supplied by a trusted caller, just like existing domain services. API authentication/authorization security events can be written during preview; no decision or strategy data is mutated.

The strict envelope schema is [import-envelope.schema.json](../schemas/strategy/import-envelope.schema.json). Mandatory fields: adapter_version, tenant_id (assertion checked against authenticated tenant), decision_id, expected_document_hash, mode, content_language, selected_option_id (nullable), provenance and artifact. The exact full current DA document is hashed by `decision_assurance.audit.payload_hash`. A stale hash fails. Once evaluated, a DRAFT with a stored outcome must use a new case rather than hiding stale validation. No case status, approval, validation result, governance outcome or canonical action is supplied by the adapter envelope.

Modes:

- `draft`: validates a RIF StrategyArtifact, adds conservative claims/evidence/assumptions/risks/conflicts and selected-option hard constraints only to an unevaluated DRAFT. Existing arrays are appended, never replaced. A selected option is mandatory when option analysis is supplied. An embedded baseline is fixed separately in the same transaction.
- `baseline`: validates a RIF Baseline and stores it without changing the case. Its original_decision.id must equal the DA decision_id. Captures exact DA document hash/state/time. A DRAFT expectation stays a DRAFT expectation. Attachment to an APPROVED case does not establish that those forecasts were approved; binding records `case_attachment_unverified`.
- `observation`: validates a RIF StrategyArtifact with value data against an already stored, identical baseline. Stores a separate immutable version and a new-case proposal flag. No historical case JSON changes, reopening, new approval or external execution occurs.

An artifact ID is immutable and tenant-scoped across cases. An exact envelope retry by the same trusted principal (actor ID, kind and client ID) returns the original receipt, even after later transitions; it performs no write. Same ID with changed payload, case, provenance, expected hash or importing principal conflicts. Use new artifact IDs for later observations. Baseline corrections require new id + previous_id + correction_reason, same original decision/analysis references and nondecreasing creation time; branches and overwrites fail. Corrections preserve the predecessor's DA binding and original version. A missing baseline causes observation rejection; an export/hash alone does not establish prior fixation in DA.

## Exact mapping and limitations

| RIF / companion information | DA representation |
|---|---|
| Claims | Namespaced claims; submitted statements remain unconfirmed |
| Linked sources | UNVERIFIED or CONFLICTING evidence; inert strategy source_ref; canonical metadata hash |
| Assumptions / proposed tests | UNVERIFIED assumptions; test plans, IDs, uncertainty and counterevidence retained in original |
| Counterevidence | Unresolved MEDIUM conflicts plus unresolved risk; no invented claim-source links |
| Selected option's hard conditions | MANDATORY, satisfied=false; violations explicitly identified; positive/unknown imported compliance remains unverified |
| Other options, scale, weights, scenarios, rank changes | Original artifact + mapping; unresolved risk represents missing independent full replay |
| Open findings / imported evidence_state | Original artifact + unresolved risk + unsatisfied REVIEW_REQUIRED completeness condition; never imported validation_results |
| Execution, actuals, causal evidence, competing explanations | Separate observation original; no success or causal-certainty upgrade |
| Baseline | Immutable separately stored original + DA snapshot binding; reconstructed flag preserved |
| Test reports | Typed provenance companion preserving individual methods, source identity and outcomes |

No policies or new review roles are introduced. Existing DA engine decides all outcomes. Because normative constraints have a boolean satisfaction field, the adapter cannot express unknown as an independently satisfied condition: an option with any imported hard condition stays blocked until a separately controlled verification/new-case process supplies verified conditions. DA currently has no strategy-specific field-verification endpoint. Independent DA evaluation is a governance assessment of submitted material, not substantive verification of a RIF model.

DA validates pinned JSON structure, unknown-field rejection, references/duplicates, finite and bounded numbers, exact nonnegative weight sum, scales, measurement unit/period compatibility, alternatives/exclusion reasons, selected-option references, eligibility/ranking consistency, baseline matching and time ordering. It does **not** replay the complete RIF EvidencePipeline, source credibility/citation algorithms, model scores, result deltas or semantic truth. `complete_semantic_replay=false` and unresolved risk always disclose that gap. Numeric parsed values and claimed rankings are not independently verified. Every draft also carries STRATEGY_FULL_REPLAY_NOT_PERFORMED as an unsatisfied REVIEW_REQUIRED constraint: MEDIUM risk alone is not actionable for every case in the existing engine. This ensures source-free uncertainty yields REVIEW without inventing a mandatory external policy or a new human-review role. No unrestricted URL or filesystem resolver is provided: locators, source text and embedded instructions are inert untrusted data. Full test acceptance must not be claimed from structure alone.

## Test provenance v2

The companion belongs to the adapter, not the normative Decision File. Each report records method (cli/function/static/manual), subject, source_ref, source_commit, actual file_hashes, local_modifications (nullable), execution_status, exit_code, checked_objects and individual required checks with status, subject_ref and expected_rejection. Unknown fields are rejected. Missing actual identity stays unknown; an imported commit name is never substituted for file hashes. Stored original_hash hashes canonical JSON, not the original file bytes, and authenticates neither author nor approver.

Exit 0 with a mandatory ERROR/SKIP/FAIL is incomplete. Zero objects/no required checks is empty. NOT_REPRODUCED is inconclusive. Missing references and execution aborts stay incomplete. A demonstrated expected input rejection is distinguished from an ERROR and remains reported-but-unverified. Mixed reports retain separate methods and do not imply CLI execution of original scripts. Even an internally complete report yields only TEST_REPORTED_COMPLETE_UNVERIFIED. Test reports are bound to the immutable imported original/hash. Check subject_ref must identify an unambiguous original ID, explicit original JSON object path (for example /request/assumptions/0), DA case ID or named file_hashes entry. Bare IDs shared by differing baseline/request versions remain ambiguous. test_subject_bindings records the matched canonical subject hash or null; missing or ambiguous references prevent reported completion. No imported assumption result is elevated to verification. F01 is withdrawn and not propagated as a defect; ambiguous memo text cannot independently establish a financial conclusion.

## Audit, storage and operations

DRAFT case writes, original/mapping, baseline and audit inserts share one locked transaction (SQLite BEGIN IMMEDIATE; PostgreSQL row lock under tenant-scoped transaction/RLS). A write failure rolls back everything. Standard case audit records preserve the case chain; baseline/observation sidecar audit is a separate per-tenant/case hash chain and does not rewrite terminal case chains. Original/provenance remains only in tenant-scoped storage; logs contain no source bodies. The caller actor ID/kind and effective roles are retained; the normative audit role denotes the existing decision:create mapping role, not a new privilege.

The PostgreSQL application role has SELECT/INSERT only on strategy tables; forced RLS denies absent/wrong tenant context. SQLite is a reference boundary with explicit predicates, not database-enforced multi-user isolation. Protect database files/backups from administrators who could replace data or schema. This adapter adds no encryption claim; existing deployment encryption, backup protection and retention obligations apply.

Tenant export: authorized callers read each stored artifact by known ID; no new signed-export claim or automatic incorporation into existing pilot exports. Backup/restore must include strategy_records and strategy_events with decisions and existing audit. Existing controlled case deletion cascades both tables; tenant retention, legal holds and deletion authority remain governed by existing lifecycle service. There is no adapter update/delete API. Operators must include these tables in restoration/isolation acceptance before enabling the optional PostgreSQL integration. To roll back enablement, remove store injection first; leave additive tables intact for retention. Never roll back a migration by deleting historical originals.

## Verification

Use `python -m scripts.strategy.export_contract` for public/packaged envelope drift. Regular pytest automatically includes deterministic strategy unit/integration/API-E2E tests in existing CI. PostgreSQL tests use `DA_TEST_POSTGRES_DSN`, existing role migration and cleanup of strategy-pg-a/b tenants. They fail in CI when the DSN is missing and skip locally when unavailable. These are API journeys, no new browser/device feature; existing desktop Chromium DE/EN UI journeys remain unchanged. CI JUnit artifacts retain failure details for 14 days, without source bodies or screenshots; existing browser traces are unchanged.

See [design](specifications/DA-STRATEGY-ADAPTER.md), [implementation plan](specifications/DA-STRATEGY-IMPLEMENTATION-PLAN.md) and [execution evidence](STRATEGY-VERIFICATION.md). Repository tests, pinned-contract compatibility, RIF-side full replay, model evaluation and production authorization are distinct evidence classes.
