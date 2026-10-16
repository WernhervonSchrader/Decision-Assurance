# Security benchmark v0.1 — implementation plan

Design: `DA-SECURITY-BENCHMARK-v0.1-DESIGN.md`. Owner's implementation instruction authorizes
this isolated benchmark; production target behavior and configuration are not changed.

1. **Source and contracts** — `benchmarks/security/datasets/llmail/source-lock.json`,
   `benchmarks/security/schemas/security-case.schema.json`, packaged copy under
   `src/decision_assurance/schemas/security-benchmark/`, `security_benchmark/contracts.py`,
   `dataset.py`, `tests/security_benchmark/test_dataset.py` and `test_contracts.py`.
   Start with failing tests for checksum corruption, unsafe paths/redirects, schema rejection,
   byte preservation and deterministic stratification. Implement bounded stream import with
   `.part` staging, verified promotion, raw manifests, derived index and seeded selection.
   Interface: locked source → raw manifest; raw manifest/profile/seed → fixture JSONL.
   Commit: `feat(security-benchmark): add pinned LLMail import and strict contracts`.

2. **Adapters and fixtures** — `security_benchmark/cases.py`, `adapters.py`, `execution.py`,
   `benchmarks/security/fixtures/`, `tests/security_benchmark/test_adapters.py`,
   `test_execution.py`. Fail first on missing B1–B6/C1–C7, fabricated authority, wrong tenant,
   stale evidence, changed price/vendor/bank/version, retries and generator-owned validation.
   Actual engine/Decision File/API controls return observed outcomes; simulated execution
   records attempted, blocked and committed events independently. Include allowed controls.
   Commit: `feat(security-benchmark): exercise real governance and simulated execution boundaries`.

3. **Runner, metrics and comparison** — `security_benchmark/runner.py`, `metrics.py`,
   `reporting.py`, `__main__.py`, `locales.json`, `tests/security_benchmark/test_runner.py`,
   `test_metrics.py`, `test_e2e.py`, `benchmarks/security/baselines/smoke-v0.1.json`.
   Failing tests: zero denominator produces null, source results never become current ASR,
   missing adapter never passes, altered audit/outcome/evidence/freshness regresses, changed
   dataset/profile cannot silently compare, no payloads in reports. Implement checkpoint identity
   and prefix integrity, deterministic output, safe report writing and explicit failure exits.
   Commit: `feat(security-benchmark): add reports checkpoints and regression gates`.

4. **CI and documentation** — `.github/workflows/ci.yml`, `README.md`, `docs/TESTING.md`,
   `benchmarks/security/README.md`, `docs/security/DA-SECURITY-BENCHMARK-v0.1.md`,
   `docs/security/SECURITY-COVERAGE-MATRIX-v0.1.md`, example reports and verification record.
   Add offline smoke + regression check to existing verify job, preserve existing security scans
   and release evidence job names. Standard/full runs explicit local opt-in, no PR-path downloads.
   Commit: `docs(security-benchmark): record coverage findings and offline CI evidence`.

## Verification and expected results

Use `.venv/Scripts/python.exe` locally (`python` in CI).

* `-m pytest tests/security_benchmark -q`: all contract/unit/integration/E2E tests pass;
  tests of known target weaknesses assert truthful failed observations, never safe outcomes.
* `-m decision_assurance.security_benchmark run --profile smoke --output .cache/security-smoke`:
  deterministic reports; security finding exit differs from infrastructure/invalid-input exit.
* `... compare --baseline benchmarks/security/baselines/smoke-v0.1.json --report ...`:
  no new regressions; known security failures remain visible.
* `-m pytest tests/test_benchmark.py tests/test_dats.py tests/test_dats_gold_dataset.py
  tests/test_engine.py tests/test_decision_file.py tests/test_transitions.py -q`: existing Gold passes.
* `-m pytest -m 'not postgresql and not keycloak_e2e and not live_provider' -q`:
  baseline failures documented; investigate any new failure. Run PostgreSQL/browser checks if
  isolated services are available; otherwise explicitly record unexecuted checks.
* `-m ruff format --check src tests scripts/security scripts/strategy`, `-m ruff check ...`,
  `-m mypy src`, `-m bandit -q -r src -s B105`, `-m build`: pass.
* `-m pip_audit`, existing UI build/test/E2E, secret/container scans where tools/network exist:
  report results and environment limitations, no major upgrades.

E2E environment: pytest, real in-process FastAPI TestClient and temporary SQLite per test,
CLI subprocesses, fixed seed/clock, two tenants, generator/validator/human approver/auditor;
German/English, authorized/prohibited actions, persisted audit and duplicate requests. No external
services or production dependencies. New scope has no browser UI; browser/device coverage remains
the existing Chromium pilot suite. Fresh temporary data cleaned by pytest; no retries; hashes bind
selection and checkpoints. CI retains sanitized JSON/Markdown/JUnit for 14 days; no raw payload
attachments or screenshots/traces from adversarial data. Existing browser trace policy unchanged.

Separate final reviews: specification compliance including all acceptance criteria; code quality
including path safety, memory bounds, errors, provenance and honest denominators. Inspect staged
diffs, commit only authorized files, push feature branch and create draft PR with exact evidence.

## Source clarification received 2026-10-16

The owner supplied the eleven numbered principles as a transcript. Map that ordering in
`docs/security/SECURITY-COVERAGE-MATRIX-v0.1.md`, retaining explicit production/simulation
boundaries and remaining gaps. Remove the now-obsolete `BURSEG_SOURCE_PENDING` report limitation
in `src/decision_assurance/security_benchmark/runner.py`; do not change any target behavior.
Run `tests/security_benchmark`, fresh smoke and standard profiles, regenerate sanitized examples
and the known-gap baseline, and compare unchanged outcomes. Commit source/mapping first and
bind subsequent fresh evidence to that commit. No new runtime control is implied by this update.
