# B2 independent evidence trust — Architecture & Evidence Gate

Date: 2026-10-30 (Europe/Berlin). Status: PROPOSED / HUMAN_REVIEW_REQUIRED.
Operating profile: development; no merge, deployment or production acceptance.

## 1. Decision note and execution scope

The user authorizes inspection, a minimal server-side B2 fix, tests and evaluation of a
separate PR. Scope is this repository and a new draft branch/PR only. No external
messages, mail, live model calls, production data, merge or deployment. Implementing
actor is also the specification/code reviewer; independent review is outstanding.
Normative changes are PROJECT_CONTRACT proposals. Owner/reviewer: repository owner.

Inspected base: `main` at `96b32da` (resolve full SHA in verification report).
PR #16 is open/draft, head `06bce76e5029ea6aa6cc2ea2f8805bb314a18283`,
base `feature/controlled-strategy-handoff`. This fix branches independently from main.
PR #16 benchmark `adapters.run_governance` changes source_ref to
`untrusted/attacker-email.txt`, sets VERIFIED, calls the real Decision File evaluator,
and records PASS separately from DRAFT. Eight variants are reported in its pinned
benchmark documentation. No B2 external effect or lifecycle bypass is established.
B1/B3/B6 and a production execution gateway are outside this fix.

CODE evidence at inspected base:
- `adapters.normalize`: evidence dictionaries are forwarded unchanged, no origin check.
- `decision_file.evaluate_decision_file`: evidence is reduced to id/status/fabricated;
  source_ref, content_hash, claim_refs and observed_at are lost before evaluation.
- `engine.DecisionAssuranceEngine._validate`: default `verifiable` is
  `status != UNVERIFIED`; VERIFIED (and even missing status) can pass without authentication.
  Client flags can override UNVERIFIED/freshness/support findings.
- `api/routes/decisions.evaluate`: authenticated tenant controls repository lookup,
  but evaluator receives no independent evidence verification authority.
- `schemas/evidence-contract.schema.json` and `schemas/decision-file.schema.json`:
  provenance/source/status are declarations; schema validation proves shape only.
- `intake/verification.IntakeVerifier` independently checks objective extraction and
  tenant policy; this is not authentication of an arbitrary external source.
- `web_research/evidence_policy` and compiler deliberately leave external evidence
  UNVERIFIED. Do not reinterpret extraction confidence as provenance authentication.
- `export/signing.py` + `export/validator.py`: Ed25519 authenticates export bytes and
  key validity. Signed export != independently authenticated embedded source.
- `audit.AuditLedger` and Decision File evaluation event already hash results and
  preserve lifecycle state. Hash chaining alone is not tamper-proof storage.

No RUNTIME or PRODUCTION evidence was inspected. Local test results are recorded
separately after execution; no historical CI result is attributed to this change.

## 2. State and evidence model

| Layer | Existing/relevant transition | Authority and binding | Failure path |
|---|---|---|---|
| Memory | no memory transition | no memory data is authoritative | not added |
| Context | Decision File snapshot -> evaluation request | retain exact evidence and claims, decision ID, policy version | changed snapshot invalidates verification match |
| Evidence | submitted assertion -> independently matched verification / unresolved | server-owned read-only registry; exact tenant, generator, decision, evidence ID, payload digest, verified_at/valid_until, independent validator ID, revocation | missing/malformed/stale/revoked/mismatched record -> REVIEW |
| Runtime | authenticated evaluate request -> bounded local lookup -> report | tenant from authenticated Identity; generator from authenticated creation binding | registry error -> REVIEW, no retry or fallback trust |
| Decision | evaluation appends outcome and validation audit event | engine findings; lifecycle stays exactly as received | B2 never confers approval |
| Execution | unchanged | separate authorization contract required | no side effect implemented |

Existing event/correlation envelope is reused: engine ledger findings/report hashes,
Decision File `decision.evaluated`, and API tenant/correlation/source_channel enrichment.
Verification records carry an opaque reference; findings use evidence ID and stable
reason codes, without copying raw source content into a new log or store.

## 3. Capability / contract matrix and alternatives

| Requirement | Existing evidence / coverage | Decision | Owner / delta / compatibility |
|---|---|---|---|
| Source identity, integrity, claim binding | schemas + payload_hash: EXISTS_PARTIAL (CODE) | EXTEND | provenance owner: bind full evidence, claims, policy, decision and generator to server record |
| Independent tenant verification lookup | NOT_FOUND_IN_INSPECTED_SCOPE | NEW minimal port/immutable record in existing provenance package | provenance owner: read-only protocol and in-memory development adapter; no client write endpoint |
| Authenticated tenant / creator binding | API Identity + create actor check: EXISTS_PROVEN (CODE; tests pending) | REUSE | API owner passes trusted tenant/creator, ignores payload tenant claims |
| Independent verification before PASS | engine: EXISTS_PARTIAL | EXTEND | engine owner: no evidence item is trusted from status or flags alone; REVIEW when not verified |
| Source transport signatures | signed export exists, source verification absent | DEFER | export signature cannot authenticate arbitrary source; no custom crypto or new signing keys |
| Decision lifecycle / execution separation | existing evaluator + transition policy: EXISTS_PROVEN (CODE) | REUSE | no automatic transition/side effect; B3 remains separate |
| DE/EN reason displays | i18n catalogs: EXISTS_PROVEN (CODE) | EXTEND | stable new reason code localized in both languages |
| Persistent verifier provisioning, RLS, permissions and revocation operations | NOT_INSPECTED / not implemented for this new port | DEFER / release HOLD | owner must provide independently authorized adapter and operations evidence before production |

Alternatives: (1) reject every VERIFIED assertion permanently: smallest containment,
but no supported positive verification path. (2) reuse export signatures: proves who
packaged assertions, not independent source authentication; rejected. (3) recommended:
exact-match server verification registry, default absent/deny. No external verifier is
invented; its provisioning is an explicit trust boundary and outstanding integration.
A new minimal port is necessary because neither IntakeVerifier nor export validation
has a read-only tenant/decision/evidence-bound external-origin verification contract.

Compatibility: existing documents remain schema-valid; their VERIFIED value remains a
submitted assertion, never silently rewritten. Legacy PASS without independent evidence
becomes REVIEW, including CLI/benchmark callers. Golden fixtures must not be silently
rewritten or exempted. Report baseline divergences explicitly. No database migration,
public attestation endpoint, outbound traffic, secrets, UI or dependency change.

## 4. Invariants, threats and requirements

- Generator cannot populate registry through request/document fields. Registry is
  dependency-injected by server composition only; records must originate in a real
  independent validator workflow, not from generated VERIFIED data.
- Bind tenant, decision, generator, evidence identity, source_ref, content_hash,
  observed_at, claim refs/claims and policy. Reuse only exact digest match before TTL.
  This digest authenticates nothing by itself: authority is trusted server storage.
- Missing status, `verifiable=true`, embedded fake proof, changed source/content/claim,
  tenant switching, self-validation, expiry/revocation and provider errors cannot yield PASS.
- A trusted record cannot promote UNVERIFIED/CONFLICTING/OUTDATED/FABRICATED/UNAVAILABLE
  evidence; strict status and existing negative checks apply independently of flags.
- Registration/provisioning privilege is an explicit operational assumption. An attacker
  with server-code/registry-write access is outside this patch's defended boundary.
- Replay of an unchanged, unexpired record within its exact scope is permitted; other
  decisions/claims/tenants are not. Evaluation is not execution authority.
- Availability failure -> REVIEW. No external calls/retries are added. A remote adapter
  needs timeout/availability policy before adoption. Audit uses existing chains and events.
- Privacy/residency/retention: record stores digests/IDs/times only, no source bodies;
  local synthetic fixtures only. Production location, retention/deletion and write audit
  remain operator review requirements, not claims of compliance.
- Authorization/authentication: reuse existing evaluate permission/Identity. No new
  generator capability. Tenant isolation is checked on lookup AND returned record.
- Multilingual: no new UI; stable reason code in EN/DE and fallback checked.
- E2E: pytest + FastAPI TestClient, isolated temporary SQLite, static test identities,
  two tenants, generator/validator roles, DE/EN. No live IdP/browser/production database
  is substituted by those tests. Existing CI service/browser/security checks retained;
  their execution at the candidate head must be reported separately.
- Supply chain/secrets/container/residency/retention/backup: no dependency, image,
  secret or persistent schema change. Existing CI checks remain required for release.

## 5. Gate and bounded implementation plan

Gate: PASS_FOR_IMPLEMENTATION_REVIEW for this local, reviewable fix. User's explicit
instruction authorizes its implementation; human acceptance of the proposed contract,
independent review, merge and production release remain pending.

Before implementation: record this design/plan; separately review specification for
scope/contradictions (done by implementing actor; no independent review claimed).

1. `tests/test_evidence_provenance.py`: failing tests for eight B2 source variants,
   forged source/proof, changed fields/claims/policy, wrong tenant/generator/decision,
   self-validation, stale/revoked/invalid records, no registry/errors, status escalation,
   positive independent record and unchanged DRAFT. Command: pytest this file; expect red.
2. `src/decision_assurance/provenance/evidence.py`: frozen verification record, read-only
   lookup protocol, bounded in-memory snapshot adapter; existing payload_hash reused.
3. `engine.py`, `adapters.py`, `decision_file.py`: keep full evidence and claim bindings;
   enforce default-deny provenance plus explicit negative statuses, no client boolean bypass.
4. `api/app.py`, `api/routes/decisions.py`: optional server registry dependency; instantiate
   per-request scoped engine from authenticated tenant and bound creator. Never accept
   registry/proof/tenant authority from body or source text.
5. `i18n.py`: EN/DE message; API E2E negatives/positive, audit and lifecycle assertions.
6. Run focused tests, lint/type/security checks, then relevant full non-service suite.
   Preserve baseline fixtures; record intentional divergences and unrelated environment
   failures rather than claiming a green regression gate. Commit design separately, then fix.
7. Independently review specification compliance and code quality as separate passes
   (same actor only). Prepare separate DRAFT PR against main with results, limitations,
   baseline migration needs and B1/B3/B6 exclusions. Never auto-merge or deploy.

Rollback: revert this isolated commit/branch; this reopens B2 and requires explicit owner
risk acceptance. Safer containment is to retain default REVIEW until verifier integration.
Done for review: targeted negatives and positive pass, no lifecycle mutation/side effects,
new trust boundary documented, exact commands/results recorded. Production Done is HOLD.
