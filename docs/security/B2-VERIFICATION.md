# B2 correction — local verification and review record

Date: 2026-10-30 (Europe/Berlin). Proposed change; HUMAN_REVIEW_REQUIRED.
No merge, deployment or production acceptance. Evidence classes: CODE and local TEST only.

## Evaluated source

Base main: `96b32da9e146b3b276c5fec4e636f67f6ea10889`.
Local implementation commit: `9f7460927d7354ebe37ff0da383629ab411076b5`.
Tested implementation Git tree: `61e2a33d2f5d474b51bc740b1fd0accf1f2b399d`.
Later additions are this verification note and release Decision File only. Publishing
through GitHub may create different commit IDs; the implementation tree is the source
comparison anchor, not a claim of CI execution at a later documentation commit.

Inspected PR #16: open/draft, head `06bce76e5029ea6aa6cc2ea2f8805bb314a18283`.
The B2 assertion is confirmed by its code path and benchmark documentation. Its complete
LLMail benchmark was NOT run here, and its eight source variants are NOT claimed to be
fresh Microsoft-model measurements. Eight new deterministic B2 regressions exercise
spoofed email source metadata through the actual local engine.

## Actual path and correction

`API create -> authenticated creator/tenant-bound storage -> evaluate_decision_file ->
normalize -> engine validation -> report + audit; lifecycle unchanged`.

Previously evaluate_decision_file discarded provenance fields and the engine defaulted
verifiable to true for claimed VERIFIED. Now it retains complete evidence and claims.
The engine needs an independent server record matching tenant, generator, decision,
evidence identity, full evidence/source/content hash, claims and full policies/version.
It checks TTL, revocation and validator != generator. Unknown status and positive client
flags cannot substitute for authority; explicit negative statuses cannot be overridden.
Missing/malformed/outdated authority or adapter errors yield REVIEW. Mandatory BLOCK
findings still take precedence. Records are lookup-only application dependencies, never
created from a request, model output, embedded signature or source text.

Gate outcome: REUSE API identity, lifecycle and audit; EXTEND engine, evaluator and
provenance contract; NEW minimal registry port/immutable record because inspected
source/export/intake contracts lack arbitrary external-origin authentication.
Full rationale: B2-ARCHITECTURE-EVIDENCE-GATE.md.

## Executed checks

Commands below ran in the isolated development venv with this repository as cwd.
Python 3.12.14; pytest 9.2.0, FastAPI 0.162.0, Starlette 1.10.0, httpx 0.28.1,
Pydantic 2.14.2, cryptography 50.0.2, Ruff 0.17.3, Mypy 1.20.2, final pip 26.2.2.
No declared dependency bounds were changed. Installed socksio locally because the
host SOCKS proxy otherwise prevents httpx client construction in two existing tests.

| Command / check | Observed result | Scope / limit |
|---|---|---|
| Before production edit: `python -m pytest tests/test_engine.py tests/test_decision_file.py tests/test_dats.py tests/test_benchmark.py -q` | 50 passed | original behavior baseline |
| TDD new tests before implementation | collection failed: missing provenance.evidence module | design-first red state, not a passing security test |
| Unchanged main full non-service suite, same initial venv | 678 passed, 2 failed, 30 deselected | both failures: missing socksio in local proxy environment |
| First full candidate before expectation migration | 711 passed, 23 failed, 30 deselected | 21 deliberate provenance-contract differences plus same 2 environment failures; not hidden |
| `python -m pytest tests/test_evidence_provenance.py tests/e2e/test_b2_evidence_provenance.py -q` | **64 passed** | eight new B2 variants, source/proof/hash/claim/policy tamper, tenant/creator/decision switch, expiry/revocation/self-validator, unavailable authority, bad status/flags, mixed sources, positive independent record, DRAFT preserved, DE/EN/API roles/audit |
| Final `python -m pytest -m 'not postgresql and not keycloak_e2e and not live_provider' --tb=short -q` | **745 passed, 30 deselected**, 11 deprecation warnings; exit 0 | entire local non-service suite after final code/test changes |
| `decision-assurance benchmark benchmarks/dats/v0.2.0/catalog.json` | **10/10 matched**, exit 0 | new explicit DRAFT expectations; not accepted/certified |
| DATS v0.1.0 / original scenarios diff vs main | no changes | all ten historical provenance-policy differences are asserted by a dedicated regression test |
| `ruff format --check src tests scripts/security` | 282 files formatted, exit 0 | local |
| `ruff check src tests scripts/security` | passed, exit 0 | local |
| `mypy src` | passed, 137 source files | local strict typing |
| `bandit -q -r src -s B105` | exit 0, no findings | pre-existing nosec-comment parser warnings; B105 excluded as in CI |
| `python -m build` | wheel and sdist built | local packaging, not deployment |
| OpenAPI generation + diff for 0.4.0 and 0.5.0 | both unchanged, exit 0 | server dependency injection did not expand wire API |
| Initial `pip-audit` | failed on local pip 25.0.1 vulnerabilities | installer refreshed within CI's existing minimum |
| Final `pip-audit` | no known vulnerabilities found | editable project itself absent from PyPI, explicitly skipped by tool; source checked separately |
| `git diff --check` | passed | whitespace |

Full-suite deprecation warnings concern Starlette TestClient's httpx compatibility and
pre-existing MCP AuthSettings resource-default behavior. They are not resolved by B2.

## Remaining assumptions, non-executed checks and release blockers

1. **NOT VERIFIED: actual independent source authentication.** Positive tests provision
   synthetic records outside generator/API control. They prove acceptance/binding, not
   a real mailbox connector, source-signature chain or enterprise verifier's truthfulness.
   No production registry or provisioning route is implemented. Default runtime therefore
   keeps evidence-dependent cases in REVIEW until a separately reviewed integration exists.
2. **NOT VERIFIED: effective-principal separation and registry-write security.** Comparing
   independent actor IDs is only a local guard. The adapter/operator must prove disjoint
   effective permissions, tenant authorization/RLS, validator authentication, alias handling,
   secure provisioning, revocation freshness, time integrity, write audit, retention/deletion,
   residency and recovery. Server/registry-write compromise is outside this patch's boundary.
3. **NOT RUN: PostgreSQL, live Keycloak/OIDC, browser E2E, live-provider, container/secret/
   Actionlint/restore jobs and exact-head CI.** Thirty service/live tests were deselected.
   The PostgreSQL positive fixture was adapted to explicit synthetic verification, but its
   service execution is not claimed. Existing workflow jobs remain enabled and required.
4. **Historical output != current authority.** Old stored reports/approval data are not
   migrated. Same-key idempotency returns historical output; current source revalidation
   requires a fresh evaluation key. This patch grants no execution permit and supplies no
   production approval invalidation/execution recheck service.
5. **B1/B3/B6 remain separate.** B2 PASS was not evidence of external action or lifecycle
   escape. B3's forged APPROVED admission is not fixed here. No global security/production
   readiness claim follows from local green checks or a future green CI run.
6. DATS v0.2.0 changes mandatory expected reasons and the no-provenance positive case to
   REVIEW. The dataset is explicitly DRAFT; owner acceptance is outstanding. All original
   BLOCK conditions remain BLOCK; original source fixtures remain immutable.
7. Independent code/specification review remains required. Implementing actor performed
   both separate review passes; no independent reviewer/agent/human approval is claimed.

Release decision: **BLOCKED** pending independent contract review and the applicable
operational/integration evidence. The branch is suitable for a separate **DRAFT PR**
against main; it has no dependency on merging PR #16. Local success is not merge approval.
