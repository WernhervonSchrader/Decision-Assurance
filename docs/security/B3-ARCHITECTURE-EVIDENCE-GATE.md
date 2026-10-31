# B3 Architecture & Evidence Gate — 2026-10-31

## 1. Decision note

Scope: close authenticated generator lifecycle mass assignment on create/import and preserve independently authenticated human approval. Base inspected: main `96b32da9e146b3b276c5fec4e636f67f6ea10889`. PR #16 head `06bce76e5029ea6aa6cc2ea2f8805bb314a18283` documents B3; PR #17 head `b80be3bd0d3ba54b7335eea54f2187d680f52aa6` remains DRAFT and B2 is excluded. CODE inspection, not production evidence. No external execution was observed or will be attempted.

Observed path: `api/routes/decisions.py:create_decision` authenticates and checks CREATE, schema and `validate_semantics`, creator/action tenant. It neither requires DRAFT nor calls `TransitionPolicy`. `document=deepcopy(body)` preserves APPROVED, approvals, evaluation and fake audit. Repositories insert document JSON unchanged. The new creation audit claims DRAFT independently of actual status. `approval_digest` is public deterministic content binding, not authentication. `transitions.py` correctly checks REVIEW, human APPROVER and actor separation, but is bypassed entirely by create. Existing evaluation can also rewrite terminal files; repository save lacks comparison to the read snapshot (PostgreSQL lock acquired only after reading does not fix this).

Approaches: (1) reject imported lifecycle authority and reuse the transition boundary plus snapshot CAS (recommended, no schema migration); (2) silently strip/reset imported approvals (hides caller intent, rejected); (3) introduce signed approval tokens and verification registry (more contracts/key operations, unnecessary for server-owned mutations). No novel cryptographic scheme.

## 2. State and evidence model

Decision: DRAFT -> VALIDATION -> REVIEW -> APPROVED/BLOCKED, terminal states immutable through evaluate. Engine outcome PASS/REVIEW/BLOCK is separate from lifecycle. Human identity and tenant come from injected verified authenticator, never document approval fields. Existing OIDC validates issuer/audience/signature/claims and maps actor kind/roles (`oidc/authenticator.py`, `docs/IDENTITY.md`). Static tokens only prove local test behavior.

External intake must be DRAFT, without approvals, outcome, validation history, satisfied reviews or audit history. Server compiler can create only an unapproved DRAFT (its provenance audit is server-generated). Client requested_by/current_owner remain descriptive, not authority. Transition endpoint derives actor and issues fresh nonce at the authorized request; snapshot binding in the persisted transition audit ties tenant, full pre-transition document, resulting document without its last audit event, actor and transition. Persistence CAS ties authorization to exactly the read document and writes document, event, report and idempotency together. Conflicting write rolls back and returns 409. No approval action or external execution occurs on replay.

Memory, Context and Runtime contracts unchanged. Evidence provenance remains B2's separate boundary. Execution is absent from this change; APPROVED grants no implemented external effect. Audit shares tenant/correlation/source and previous-event hash; DB-writer tamper resistance (B6) is NOT established by hashes.

## 3. Capability/contract matrix

| Capability | Evidence and coverage | Decision / owner / change | Acceptance |
| --- | --- | --- | --- |
| Authenticated actor, tenant | EXISTS_PROVEN CODE + existing auth tests, identity.py, OIDC, dependencies.py | REUSE identity/auth owner | wrong role/kind/tenant fail |
| Transition separation | EXISTS_PARTIAL transitions.py, TRANSITION_POLICY.md | EXTEND API boundary, reuse policy | generator/requester/validator cannot approve |
| Import lifecycle control | NOT_FOUND_IN_INSPECTED_SCOPE create route | EXTEND create validation and repository initial-state guard | supplied status/digest/history fail before insert |
| Approval integrity | EXISTS_PARTIAL decision_file.py, bind_approval | REUSE digest as integrity only; EXTEND server audit binding | exact actor/tenant/document/action hash in committed event |
| Atomic snapshot persistence | EXISTS_PARTIAL SQLite transaction, PG advisory lock; research compiler already uses CAS | EXTEND repository protocol and adapters, reuse transaction model | stale/concurrent write fails without partial audit/report/idempotency |
| Idempotency | EXISTS_PROVEN actor/tenant/operation/request hash scoped | REUSE; validate create before replay | same valid request safe, new-key replay terminal fails |
| DE/EN | EXISTS_PROVEN i18n error envelopes | REUSE stable INVALID_REQUEST/CONFLICT codes | DE/EN API journeys |
| Privacy/secrets/residency/retention | Existing profile contracts, no new data store/service/credential | REUSE; hashes only in existing audit retention | no request bodies/tokens added to logs |
| Browser/live identity/PG deployment | NOT_INSPECTED runtime | DEFER claim; run available CI/services, report omissions | no production claim |

## 4. Invariants and threat check

Assets: decision authority and exact evidence/action/policy snapshot. Actors: generator, independent validator, human approver, tenant admin, DB operator. Boundaries: untrusted JSON -> authenticated API -> deterministic policy -> tenant persistence. Spoofed human digest/status/history: reject initial authority. Vertical escalation: permission plus explicit APPROVER role, human kind and separation. Horizontal escalation: authenticated tenant + tenant-qualified CAS. Replay: existing scoped idempotency, terminal policy and atomic write. Tampering/TOCTOU: complete snapshot comparison; no post-approval evaluation. Failures: 409 on stale state; transaction rollback preserves audit/idempotency. Denial-of-service bounds and existing dependency controls unchanged. Residual risks: compromised issuer/admin, same effective person behind distinct IDs, DB operator rewriting audit, legacy malicious stored files; none resolved by a hash. Existing potentially compromised records require independent operational review, never automatic grandfathering. No new network provider or execution path.

## 5. Gate judgment and bounded implementation plan

PASS_FOR_IMPLEMENTATION_REVIEW under the user's explicit request to implement an independent draft. HUMAN_REVIEW_REQUIRED for normative contract changes and release; no merge/deployment authority. No extra component or migration: EXTEND existing owners.

1. Commit this design before production edits. Tests first: `tests/e2e/test_b3_approval_boundary.py` reproduces valid forged APPROVED import (expected rejection), other status/history/digest, role/kind/tenant/replay negatives and real human positive; SQLite CAS test covers concurrent winning write and rollback. Add optional PostgreSQL equivalent to existing service suite.
2. `decision_file.py`: reusable initial-authority validator, optional stricter untrusted-import check. `api/routes/decisions.py`: enforce import guard before idempotency; terminal evaluate rejection; explicit human APPROVER check; always issue approvals at transition; enrich audit hash; pass read snapshot to repository; conflict -> localized 409.
3. `repositories/protocols.py`, `sqlite.py`, `postgresql.py`: require expected_document keyword for save, initial guard on create, atomic tenant-qualified comparison, dedicated conflict type; update existing direct test callers. Preserve PG deletion advisory lock and RLS.
4. Existing `TransitionPolicy` retains normative state/evidence checks; digest is not upgraded into a credential. Update docs/TRANSITION_POLICY.md and security evidence. No B2 code, schema or dependency bounds changed. Commit implementation separately from plan.
5. Verify targeted failing/passing tests, full non-service pytest, Ruff, strict Mypy, Bandit, build, API contract tests and whitespace; service/browser/Keycloak/live-provider/container checks only claimed if actually run. Deterministic TestClient E2E uses tmp SQLite, two tenants/roles, DE/EN, synthetic static identities, no external credentials, no browser UX modification; browser/device/login/logout/session behavior remains in existing CI. Existing CI retains service, browser traces/artifacts and scanners.

Acceptance: forged approval cannot be stored through API, compiler creation remains DRAFT, normal independent human transition succeeds, terminal data cannot be reevaluated, stale snapshot cannot overwrite state or emit partial audit, exact scope binding is inspectable, no merge or external execution. Rollback: revert code only after blocking intake; no DB migration to reverse. Existing untrusted stored approvals require review before reuse. Separate spec compliance and quality reviews before publishing draft.
