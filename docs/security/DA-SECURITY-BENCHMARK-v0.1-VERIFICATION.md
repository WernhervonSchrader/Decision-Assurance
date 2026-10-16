# Security benchmark v0.1 — verification record

Date: 2026-10-16. Environment: local Windows/Python, isolated PostgreSQL 16 container; no productive
systems or model credentials. Implementing Codex actor performed the following checks. This is
repository evidence, not independent review, deployment evidence or production authorization.

## Starting point and protected user changes

Base `499720f` on `feature/controlled-strategy-handoff`, open Strategy PR #12. Baseline full pytest:
736 passed, 33 skipped, 3 failed. Two failures lacked a PostgreSQL test DSN; one could not see three
tracked `.secrets/keycloak-*.example` files inside the restricted sandbox. Git outside the sandbox
confirmed those files are present: the apparent deletions were a visibility restriction, not user
changes. The untracked Odoo specifications were left untouched and excluded from commits. The draft PR is
stacked on the existing Strategy branch so it contains benchmark work only.

## Executed evidence

| Check | Result / evidence |
|---|---|
| Download and source integrity | All ten pinned files acquired; full raw and annotation SHA256/size checks passed; ignored `manifest.json` retained locally |
| Smoke provenance reconstruction | All 12 bundled wrappers match original contents; three complete source files reverified |
| Full raw content triage | 461,640 records scanned; 239 credential-shaped and 91 active-content-shaped records flagged; no bulk publication approved |
| Raw cardinality and derived index | 461,640 raw; 203,679 distinct subject/body payloads; 489 strata |
| Original annotations | 160,741 + 37,303 parsed; 148,347 exact attack joins, 11,948 benign joins, 43,384 unknown; one conflicting cross-phase label excluded |
| Additional benign corpus | 203 original emails; 160 unique strings; duplicates retained with distinct case IDs |
| New benchmark suite | 48 tests passed; JUnit `.cache/security-benchmark-final.xml` |
| Smoke | 27 total: 11 PASS, 4 SECURITY_FAILURE, 12 INCONCLUSIVE, zero skipped/test/infra errors |
| Standard | 1,315 total: 80 PASS, 32 SECURITY_FAILURE, 1,203 INCONCLUSIVE, zero skipped/test/infra errors |
| Offline CI-style regression | `regression_pass=true`, `security_pass=false`; known failures remain visible |
| Existing Golden/engine/Decision File/transitions | 61 tests passed; DATS Gold 10/10; original fixture files unchanged |
| Existing PostgreSQL integration/RLS/migrations/E2E | 28 passed against isolated loopback PostgreSQL 16; initial 26 passed + two temp-permission errors corrected by dedicated workspace basetemp |
| Full non-service Python suite after environment refresh and sandbox visibility correction | **785 passed**, 35 service/live tests deselected; JUnit `.cache/security-suite-unrestricted.xml` |
| Ruff | Repository formatting and lint passed for `src tests scripts/security scripts/strategy` |
| Mypy strict | All 155 source files passed |
| Bandit | No findings; existing explanatory-noqa warnings are not vulnerabilities |
| Package build | sdist and wheel built; report catalog and schema included by build configuration |
| Dependency audit | Initial local environment was stale; cryptography 49.0.0, mcp 1.29.0 and pip 26.1.2 flagged. Updated only local installed packages within declared bounds; final pip check and pip-audit report no known vulnerabilities |

The exact updated final command outputs and report metadata are retained in `.cache/` and
sanitized example reports under `benchmarks/security/reports/`. No raw datasets are published.
Benchmark security failures are discovered target behavior, not test-harness failures. They
deliberately prevent treating the outcome as a security proof or production-ready release.

Implementation commits: `f20f996` (source/contracts/design), `faa7164` (real governance and simulation), `7f3921e` (profiles/reports/regression). Final documentation/CI commit follows; example measurements identify the exact implementation commit.

## Separate reviews

Specification compliance: import/version/hash/raw preservation, original-vs-derived labels,
strict cases, A/B/C separation, positive controls, all 13 negative families, profile counts,
checkpoint identity, full JSONL comparison, localized reports and safe CI are implemented and
covered. The Burseg attribution is explicitly pending missing source input. No fresh external
model evaluation was authorized or performed. Full exhaustive profile execution is not required
to establish fresh resilience and is not claimed; streaming/resume/comparison are exercised with
bounded deterministic test batches.

Code quality/security: inspected schema strictness, safe relative paths and redirects, hash/size
verification before promotion, raw immutability, bounded retry/record/batch processing, conflicting
annotations, FP duplicate IDs, checkpoint code/input binding, missing-component error handling,
honest denominators, authorization ordering, atomic simulation recheck and Windows resource cleanup.
An initially expensive email-triage regex on long untrusted text was replaced with bounded token
matching before publication. No production engine/schema/lifecycle behavior was changed.

## Remaining checks and limits

The workstation lacks `node`/`npm` on PATH, so existing browser/UI checks were not rerun locally;
no UI code was changed. Live Keycloak/OIDC, full container scans, secret scanner, Linux actionlint,
backup/restore drills and commit-bound release evidence remain existing CI jobs and are not
asserted as locally passed. The restricted-sandbox missing-example failure is an environment visibility issue;
Git outside the sandbox and a fresh GitHub checkout retain the tracked examples.

The four discovered target weaknesses require independent remediation decisions (see methodology).
In particular, B3 is a real authenticated lifecycle admission bypass. Sandbox freshness cannot
substitute for the not-yet-implemented production executor. Missing Burseg source prevents the
requested exact eleven-principle mapping from being declared complete.

Final full local non-service run outside the restricted sandbox: **785 passed, zero failures, 35 deselected**. The earlier 784/1 result was caused solely by sandbox visibility of tracked placeholder examples. Final standard evidence is bound to implementation commit `7f3921e`, with 112 freshly invoked B/C components and zero reused checkpoints. All 64 original levels and all ten derived categories occur in the selection. Original Microsoft observations in this sample: 999 evaluable objective sets, 6 all-objective successes, 134 generated tool proposals; these are never fresh DA model measurements. Actionlint and exact original-content reconstruction passed.
