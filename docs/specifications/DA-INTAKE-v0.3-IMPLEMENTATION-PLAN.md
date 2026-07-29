# Controlled Intake v0.3 Implementation Plan

## Stage 1 — Contracts, lifecycle, extractor and verification

- Files: `schemas/intake/*.schema.json`, packaged copies, `intake/contracts.py`,
  `intake/lifecycle.py`, `intake/extractor.py`, `intake/verification.py`.
- First failing tests: `tests/intake/unit/test_contracts.py`,
  `test_lifecycle.py`, `test_extractor.py`, `test_verification.py`.
- Expected: exact spans/normalized DE/EN values; no truth/outcome fields;
  allowed/prohibited transitions; injected clock.
- Verify: `pytest tests/intake/unit -q`, Ruff, mypy.
- Commit: `Add controlled intake contracts and deterministic extraction`.

## Stage 2 — Confirmation, policies, compiler and persistence

- Files: `intake/policies.py`, `confirmation.py`, `compiler.py`, `service.py`,
  `migrations/002_controlled_intake_v0_3.sql`, repository protocols/SQLite.
- First failing tests: human/agent role tests, raw/trusted policy tests,
  compiler missing-value tests, transaction/idempotency/isolation tests.
- Expected: immutable actions, tenant policy lookup, READY-only compilation,
  atomic state/audit/idempotency.
- Verify: unit plus `tests/intake/integration -q`.
- Commit: `Add trusted intake verification and compilation`.

## Stage 3 — API and CLI

- Files: `api/routes/intakes.py`, API schemas/app, `cli.py`, OpenAPI artifact.
- First failing tests: auth, permission, content type, tenant IDOR, replay,
  confirmation and end-to-end compile/evaluate.
- Expected: all required operations and response state distinctions.
- Verify: `pytest tests/intake/contract tests/intake/e2e -q`.
- Commit: `Expose tenant-safe controlled intake workflows`.

## Stage 4 — Corpus and metamorphic benchmark

- Files: `benchmarks/intake/cases/01..13/`, `intake/benchmark.py`, benchmark tests.
- Each case contains raw input, request, trusted context and expectations. Raw
  and trusted variants are separate executions where applicable.
- Verify 13 cases, per-case reason/status/outcome/audit plus six metamorphic
  properties; production code is scanned for case IDs/expected outputs.
- Commit: `Add controlled intake open benchmark`.

## Stage 5 — Documentation, CI and release verification

- Update README, architecture, API, trust boundary, threat model, security,
  testing, retention, changelog, version 0.3.0, OpenAPI and CI benchmark step.
- Run formatting, Ruff, strict mypy, full pytest, old/new benchmarks, Bandit,
  pip-audit, build, installed-wheel CLI and generated OpenAPI comparison.
- Review specification compliance and code quality separately.
- Commit: `Document and verify Controlled Intake v0.3`.

E2E uses FastAPI TestClient and direct CLI `main(argv)` in isolated temporary
SQLite databases with deterministic seeds, injected clocks, two tenants and
human/agent roles. No browser exists, so browser/device/screenshots are not
applicable; CI retains benchmark/OpenAPI/pytest artifacts on failure. Tests do
not retry and use no external service, network, key or LLM.

