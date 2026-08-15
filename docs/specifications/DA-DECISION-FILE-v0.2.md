# Decision File v0.2 — Canonical Action and Approval Binding

**Status:** Implementation draft
**Operating profile:** Development
**Decision:** Extend the vendor-neutral Decision File without weakening v0.1 semantics.

## 1. Context and objective

Decision File v0.1 records claims, evidence, reviews, approvals and lifecycle events but cannot
prove that a human approved the same concrete action later presented for execution. Version 0.2
adds a canonical action, explicit requester identity, reversibility classification, action binding,
single-use approval nonce and deterministic approval digest.

The maximum credible harm is execution of a different, cross-tenant, irreversible or higher-impact
action than the independently reviewed action. The public contract remains provider-neutral; the
reference engine supplies deterministic digest and semantic validation.

## 2. Considered approaches

1. **Change v0.1 in place.** Smallest diff, but silently changes the meaning of already valid
   records and violates the published versioning rule. Rejected.
2. **Add optional extension fields to v0.1.** Backward compatible syntax, but permits action-bearing
   approvals without binding and creates two assurance meanings under one version. Rejected.
3. **Publish v0.2 with explicit migration.** Required fields and fail-closed validation are
   unambiguous; unapproved v0.1 records can migrate while existing approvals require re-approval.
   Selected.

## 3. Normative requirements

| Requirement | Implementation | Verification | Status |
| --- | --- | --- | --- |
| Version separation | schema ID and `schema_version` `0.2.0` | contract tests reject unsupported versions | Implemented |
| Canonical action | `canonical_action` with effect, target, parameters, tenant, context and reversibility | schema and semantic tests | Implemented |
| Action integrity | deterministic SHA-256 over canonical JSON | parameter-tampering negative test | Implemented |
| Requester identity | required `requested_by` actor | schema and digest-binding tests | Implemented |
| Independent human approval | `approver` actor; requester/generator collision denied | negative actor-independence test | Implemented |
| Replay resistance | 128-bit-or-stronger base64url-style nonce, unique per Decision File | duplicate-nonce test | Implemented |
| Approval integrity | digest binds case, requester, approver, action, decision, time and nonce | approval-tampering test | Implemented |
| Reversibility gate | non-read-only action requires mandatory `APPROVER` review | fail-closed semantic test | Implemented |
| Migration | unapproved v0.1 to v0.2; approvals are not synthesized | migration tests | Implemented |
| Multilingual behavior | stable machine codes only; human display is outside the contract | existing locale/UI E2E remains applicable | No behavioral change |
| Multitenancy | `tenant_id` is digest-bound and must match the authenticated API tenant | negative cross-tenant API E2E plus existing storage isolation E2E | Local implemented; deployment evidence unchanged |
| Authentication | identity provider remains authoritative; digest is not authentication | existing Keycloak E2E | No behavioral change |
| Authorization | Transition Policy and runtime authorization remain authoritative | transition and role-negative tests | Updated contract gate |
| Input validation | JSON Schema rejects unknown/malformed fields; semantic layer verifies relationships | contract tests | Implemented |
| Audit logging | hash-linked APPROVED transition binds all stored approval digests | transition and API E2E tests | Implemented |
| Data protection | parameters may contain sensitive data; minimization and retention policy still apply | documentation and existing export/redaction tests | No new collection required |
| E2E testing | authenticated API approval generates nonce and binds the canonical action | local API E2E plus controlled-pilot E2E | Local implemented; deployment evidence pending |
| CI security | existing Ruff, Mypy, Bandit, dependency, secret and container gates | repository CI | Pending CI run |

## 4. Architecture and trust boundaries

The generator creates a Decision File but cannot grant approval. `requested_by` identifies the
principal asking for the decision. The validator recomputes the action digest from canonical JSON.
An independently authenticated human approver approves the digest; the API generates a single-use
nonce server-side and rejects approval records before REVIEW. The Transition Policy verifies schema
and semantics before `APPROVED`, and the transition event binds the approval digests; the execution layer must compare
the approved action digest with the candidate action immediately before execution.

Tenant identity is carried inside the canonical action and therefore changes its digest. The API
also rejects an action whose tenant differs from the authenticated request tenant. Equivalent
request-bound authorization remains mandatory at every service, job and database boundary.

No user-facing text is added. Stable values such as `IRREVERSIBLE` and reason codes remain
machine-readable; German and English display labels belong to the localization layer.

## 5. Threat model

| Threat | Control | Detection / response | Residual risk |
| --- | --- | --- | --- |
| Parameters changed after approval | recomputed canonical digest | reject before transition/execution | compromised verifier/runtime |
| Approval replay | bounded-format unique nonce | semantic rejection and audit reason | cross-record replay requires persistent nonce registry at execution boundary |
| Requester self-approval | requester/generator and approver separation | fail-closed semantic validation | compromised or colluding human identities |
| Cross-tenant action substitution | tenant included in action digest | mismatch rejection plus existing tenant authorization | incorrect authorized tenant context upstream |
| Higher-impact wrapper action | semantic effect and reversibility are digest-bound | mandatory approval and pre-execution comparison | incomplete action canonicalization adapter |
| Approval record tampering | deterministic approval digest | validation failure | hash alone is not a digital signature |
| Sensitive parameters exposed | data minimization, existing export/redaction controls | security tests and review | schema cannot classify domain-specific secrets |
| Legacy approval silently trusted | migration blocks v0.1 records containing approvals | explicit re-approval | operational migration workload |

## 6. Acceptance criteria

1. Both public and packaged schemas are byte-identical and validate Draft 2020-12.
2. All valid examples and compiler output conform to v0.2.
3. Parameter, requester, approver, digest, action binding and nonce manipulation fail closed.
4. Existing decision evaluation and lifecycle tests remain green.
5. Unapproved v0.1 records migrate deterministically; approved legacy records require re-approval.
6. Ruff, Mypy and the full non-external test suite pass locally and in CI.
7. No merge, deployment or production-policy change occurs without separate authorization.
