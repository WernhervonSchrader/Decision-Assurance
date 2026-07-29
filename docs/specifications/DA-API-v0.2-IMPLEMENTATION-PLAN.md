# API v0.2 Implementation Plan

## Task 1 — Foundations

- Update `pyproject.toml`; add `tenancy.py`, `identity.py`, `authorization.py`, `i18n.py`.
- First write unit tests for missing tenant, permissions, agent approval and locale fallback.
- Verify with `python -m pytest tests/unit -q`.
- Commit: `Add tenant identity and authorization foundations`.

## Task 2 — Persistence

- Add `migrations/001_api_v0_2.sql`, `repositories/protocols.py` and `repositories/sqlite.py`.
- Store cases, reports, audits and idempotency records transactionally with tenant-scoped keys.
- First write integration and two-tenant isolation tests.
- Verify with `python -m pytest tests/integration -q`.
- Commit: `Add tenant-safe persistence repositories`.

## Task 3 — HTTP API

- Add `api/app.py`, `api/dependencies.py`, `api/errors.py`, `api/schemas.py` and route modules.
- Enforce authentication, authorization, body limits, pagination and idempotency.
- First write API contract and negative security tests.
- Verify with `python -m pytest tests/contract tests/security -q`.
- Commit: `Expose authenticated Decision Assurance API`.

## Task 4 — E2E and CI

- Add `tests/e2e/test_decision_journeys.py` with two tenants and multiple roles.
- Expand CI with Ruff, mypy, build, Bandit, pip-audit and Gitleaks where stable.
- Verify with the full pytest, lint, type, build and security commands.
- Commit: `Add API end-to-end and security verification`.

## Task 5 — Operations and handoff

- Update `README.md`; add `docs/API.md`, `docs/SECURITY.md`, `docs/OPERATIONS.md` and `docs/DEPLOYMENT.md` describing implemented behavior only.
- Export deterministic OpenAPI JSON; review spec compliance and code quality separately.
- Commit: `Document and verify Decision Assurance API v0.2`.

Expected evidence: all legacy/new tests pass; 10/10 Gold Dataset; wheel includes
schemas/translations; OpenAPI artifact is stable; scans have no unresolved
critical finding.
