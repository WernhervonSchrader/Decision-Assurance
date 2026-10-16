# Security benchmark v0.1 — design and review

Date: 2026-10-16. Owner instruction: implement, test, document, commit and open a draft PR;
no merge, deployment or production configuration changes. This design implements that scope.

## A. Context assessment

Base: `499720f`, branch `feature/controlled-strategy-handoff`. Python package, Click CLI,
JSON Schema contracts, deterministic `DecisionAssuranceEngine`, Decision File v0.2 digests,
`TransitionPolicy`, authenticated FastAPI routes, tenant-aware SQLite/PostgreSQL repositories,
DE/EN localization, existing DATS and intake benchmarks. There is no production purchase/email
execution adapter or atomic business-object execution contract. No runtime-contract document
was found. Existing files and Golden expectations remain unchanged.

Baseline: `pytest -q`: 736 passed, 33 skipped, 3 failed. Two failures lack
`DA_TEST_POSTGRES_DSN`; one cannot see `.secrets/keycloak-*.example` files inside the restricted sandbox.
The apparent secret-example deletions were later confirmed to be sandbox visibility restrictions, not user deletions. The owner's unrelated Odoo documents are excluded from commits. PostgreSQL,
Keycloak and browser suites require isolated services. No Superpowers capability is available;
the mandated discovery/design/plan/TDD/review/verification workflow is followed manually.

Implemented does not mean independently verified: the engine consumes evidence status and
constraint booleans supplied to it. PASS is not APPROVED. Digests are content binding, not
signatures authenticating a human. API authentication, authorization, persisted audit and
tenant context must therefore be tested separately from the engine.

## Alternatives and decision

1. Extend DATS fixtures: small change, but mixes observational attacks and governance outcomes.
2. Separate benchmark package reusing real engine, contracts, API and repositories: explicit
   boundaries and isolated effects; some execution controls remain simulation-only.
3. Implement a production purchase/mail gateway: larger integration, unavailable enterprise
   system identity/state/transactions; exceeds this benchmark's remit.

Choose 2. Never repair the target engine merely to obtain a passing security report. Known
violations remain failed security properties, with explicit accepted-baseline regression handling.

## B. Requirements matrix

| Requirement | Implementation | Test method / evidence |
|---|---|---|
| Pinned raw import, immutable bytes, license and provenance | `src/decision_assurance/security_benchmark/dataset.py`, `benchmarks/security/datasets/llmail/source-lock.json` | checksums, tamper/traversal/redirect tests; import manifest |
| Strict versioned format | packaged/public `security-case.schema.json`, `contracts.py` | schema drift, missing/unknown fields, invalid references |
| Stratified deterministic profiles, dedup separate from raw | `dataset.py`, `cases.py` | repeated selection, unique IDs, counts and strata manifest |
| A: injection vs tool proposal vs policy vs execution | `adapters.py`, `runner.py` | original objectives separate; disabled agent is inconclusive |
| B: actual governance, compromised generator | `adapters.py`, `cases.py` | real engine/Decision File/API tests B1–B6 and positive controls |
| C: execution freshness/independence | `execution.py` | C1–C7, allowed action, replay, tenant, audit failure, atomic mutation |
| Multilingual | packaged DE/EN report catalog, `reporting.py` | key parity, fallback, locale formatting; machine codes stable |
| Multi-tenancy / tenant isolation | real API and simulated execution context | two tenants, manipulated IDs, no cross-tenant output |
| Authentication / authorization | existing static test authenticator and API | missing/invalid identity, role denial, agent approval denial |
| Input validation | schemas, bounded JSONL and safe path handling | malformed/oversized/unknown fields/path traversal negative tests |
| Audit logging / evidence integrity | actual engine ledger, persisted API events, simulated execution ledger | event requirements, hash-link tamper and missing-event regressions |
| Data protection | ignored raw cache; hash/reference-only reports | no payloads/credentials in reports, pre-publication fixture review |
| E2E | `tests/security_benchmark/test_e2e.py` | CLI subprocess, API SQLite journeys, two tenants/roles, DE/EN |
| CI security / regression | `.github/workflows/ci.yml`, accepted baseline | smoke offline, mutant regressions, Ruff/Mypy/Bandit/build; existing CI scans |
| Reports and management summary | `reporting.py` | explicit denominators, null rates, failed/inconclusive distinctions |
| Burseg coverage | `docs/security/SECURITY-COVERAGE-MATRIX-v0.1.md` | exact source pending owner response; no invented attribution |

## C. Architecture and trust boundaries

Explicit offline CLI → strict fixture validation → deterministic A/B/C adapters → independent
observations → metrics → JSON + localized Markdown. Acquisition is a separate explicit network
command using only locked Microsoft/Hugging Face resources; runner has no network adapter.
Raw files remain byte-identical and outside published artifacts. Normalized references store
source IDs, offsets, payload hashes, derived categories and original outcomes separately.

A offline mode validates provenance and records original observations; it cannot establish a
fresh model ASR. The optional model port is disabled by default; no external provider is shipped.
B calls the real engine/Decision File contracts and real authenticated API with isolated SQLite.
No adapter invents missing policy enforcement. C is explicitly an isolated simulation: trusted
approvals are held outside generator input, tenant/object/action/context bindings are checked
inside one locked execution transaction, rejection and idempotency are object/action scoped,
and audit failure prevents a write. The simulated sink only records synthetic executions.
It is not evidence of a deployed DA execution gateway.

Authentication establishes tenant and roles before persisted object access. English/German
interface language is independent of synthetic tenant default/user locale, email content language
and stable machine audit codes. Reports use a translation catalog, explicit locale, environment
locale fallback to English, and locale-aware number/percentage/date display; no RTL restriction.
No migrations or new network/API endpoints are needed. CLI errors have stable codes and contain
no external payloads. Infrastructure errors, invalid fixtures, security failures, inconclusive
and skipped cases are distinct; absent mandatory adapters never count as passes.

## D. Threat model

Assets: original bytes, provenance, policy outcomes, audit events, approval independence,
synthetic tenant data, honest reports and CI integrity. Actors: hostile dataset author,
compromised generator, unauthorized tenant/role, operator, supply-chain attacker.

| Threat | Likelihood / impact | Prevention | Detection / response | Residual risk |
|---|---|---|---|---|
| Dataset instructions executed or exfiltrate | high / high | data-only parsing; no live model/tools; isolated sink | offline network-denial tests; stop on adapter failure | real model behavior unmeasured |
| Spoofed download / traversal / redirect | medium / high | immutable lock, SHA256/size, exact HTTPS sources and redirect allowlist | reject mismatch before promotion | trusted source may itself contain unsafe data |
| Claimed evidence/approval becomes authority | high / high | test actual DA boundary; independent simulation approval store | explicit security failures, baseline mutation tests | production engine trust gap may remain |
| Tenant or role escalation | medium / high | real API boundary and tenant-scoped execution | two-tenant/role negative E2E | production IdP not exercised by this suite |
| State/price/bank changes, TOCTOU, replay | high / high | atomic simulation recheck, version+digest+expiry+single use | C1–C7 + concurrent attempts | no real purchase integration |
| Audit tamper / repudiation | medium / high | actual append-only repository; hash links, required events | SQL tamper negative tests; no audit means no write | unsigned hashes alone do not defeat full rewrite |
| PII, credentials, active content publication | medium / high | raw ignored, no HTML rendering, minimal reviewed examples | aggregate scan before committing fixtures | heuristic scanning is not exhaustive DLP |
| DoS / oversized corrupt data | medium / medium | stream, bounded records, batches, checkpoints | input/error counters; explicit incomplete status | disk quota remains operator responsibility |
| Supply-chain / benchmark score laundering | medium / high | reuse dependencies, static checks, immutable baseline and result provenance | mutations, schema checks, unavailable ≠ success | CI scans require network/services |

## F. Acceptance criteria and specification review

Pinned source manifests verify byte counts/hashes; smoke has 20–50 cases; standard contains
1,000 stratified Microsoft attempts + all 203 FP emails + at least 100 B/C variants; full streams
all usable raw records. All 13 B/C families and successful authorized controls execute; reports
show source outcomes separately, with no fresh ASR in offline mode. Mutations in outcome, audit,
role separation, evidence or freshness trigger regressions. Existing Golden files stay identical.
Offline smoke, CLI/API E2E and relevant static/test checks pass, or failures are documented with
evidence. Draft PR truthfully records gaps and exact commits; no security certification is claimed.

Review: BLOCK is not inferred from Microsoft success; PASS is not execution; raw duplication is
not removed in acquisition; a baseline accepting a known gap never changes that gap into a pass.
Assumptions/risks are labeled separately from project contracts and source facts. Exact Burseg
principles are unavailable and requested; attribution remains pending until received.
