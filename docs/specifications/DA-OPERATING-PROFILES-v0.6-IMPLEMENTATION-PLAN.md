# Operating Profiles v0.6 implementation plan

This plan implements the approved `local` and `eu-managed` specification in independently testable
commits. No database migration is required because operating mode is deployment configuration, not
tenant-owned persisted state.

## E. Tasks and commit boundaries

### 1. Typed policy and failing tests

- Paths: `src/decision_assurance/production/contracts.py`,
  `src/decision_assurance/production/config.py`,
  `tests/production/configuration/test_operating_profiles.py`.
- Interfaces: `OperatingMode`; `DataResidencyPolicy`; `RuntimeConfig.operating_mode` and
  `RuntimeConfig.data_residency`.
- Data: immutable tuples for storage, processing, backup, support and external processing country
  codes; HTTPS evidence references.
- First tests: valid local/EU profiles; missing mode; non-EU location; incomplete location set;
  remote local support; invalid evidence URL; unknown fields.
- Implementation: parse strict mappings, normalize country codes to uppercase and validate by mode.
- Commands: `python -m pytest tests/production/configuration/test_operating_profiles.py -q`;
  `ruff check src tests`; `mypy src`.
- Expected: new tests fail before implementation and pass afterward; static checks clean.
- Commit: `feat(config): add local and EU managed operating profiles`.

### 2. Deployable examples and runtime E2E

- Paths: `config/deployment/local.example.json`,
  `config/deployment/eu-managed.example.json`,
  `tests/production/e2e/test_operating_profiles.py`, `.env.example`.
- Interfaces: existing `load_runtime`; fake external secret and OIDC adapters at test boundary.
- Tests: load each repository fixture, construct production app, assert PostgreSQL/OIDC/shared
  modules, run authenticated DE/EN health/error probes where applicable, and prove tenant/mode cannot
  be supplied by request input.
- Commands: targeted E2E plus `pytest -m "not postgresql" -q`.
- Expected: both fixtures construct the same runtime types; unsafe variants fail before construction.
- Commit: `feat(deployment): add local and EU managed profiles`.

### 3. Documentation and operational controls

- Paths: `README.md`, `docs/ARCHITECTURE.md`, `docs/PRODUCTION-ARCHITECTURE.md`,
  `docs/DEPLOYMENT.md`, `docs/SECURITY.md`, `docs/THREAT_MODEL.md`, `docs/TESTING.md`,
  `docs/OPERATIONS.md`, `docs/BACKUP-RESTORE.md`, `docs/LOCALIZATION.md`,
  `docs/MULTITENANCY.md`, `docs/adr/ADR-006-operating-profiles.md`.
- Content: boundaries, data inventory, auth/authorization/audit flows, retention/export/deletion,
  EU evidence ownership/review, backup/restore, incident and rollback procedures.
- Verification: repository searches for both profile names and contradictory “local production”
  wording; documentation links checked by review.
- Expected: docs describe implemented behavior and explicitly disclaim automatic legal compliance.
- Commit: `docs: define local and EU managed operations`.

### 4. CI and final reviews

- Paths: `.github/workflows/ci.yml` only if a distinct profile-contract command is needed; otherwise
  existing full-suite gates remain authoritative.
- Verification commands:
  - `ruff format --check src tests`
  - `ruff check src tests scripts`
  - `mypy src`
  - `pytest -m "not postgresql" -q`
  - `pytest -m postgresql -q` with isolated PostgreSQL
  - benchmark, OpenAPI diff, Bandit, dependency audit, build and release tests as CI defines
- Reviews: first specification compliance against OP-01..OP-16 and acceptance criteria; then a
  separate code-quality/security review for duplication, unsafe defaults and error leakage.
- Expected: all local available checks pass; GitHub PostgreSQL/container/restore/secret/release jobs
  provide the remaining evidence.
- Commit: `test(ci): verify operating profile contracts` when changes are required.

### 5. Publish

- Push `feature/operating-profiles-v0.6` with tracking and open a Draft PR against `main`.
- PR body: what/why, local and EU-managed impact, threat controls, test evidence, operational limits.
- Do not mark ready, merge or deploy in this plan.

