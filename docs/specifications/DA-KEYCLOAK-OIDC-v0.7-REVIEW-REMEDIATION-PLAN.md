# PR #6 review remediation execution plan

This plan implements only the two independent-review blockers described in `DA-KEYCLOAK-OIDC-v0.7-REVIEW-REMEDIATION.md`.

## Task 1: closed external-role boundary

- Files: `src/decision_assurance/oidc/authenticator.py`, `tests/production/identity/test_oidc_authentication.py`, `tests/production/identity/test_security_events.py`.
- First failing tests: exact accepted names; uppercase, title-case, hyphen, all internal `Role` values and unknown-only rejected; unknown plus valid maps only valid; denied API call leaves repository/provider spies untouched.
- Implementation: parse only `KEYCLOAK_ROLE_MAP.get(item)` and reject an empty mapped set with `AUTH_ROLE_REQUIRED`.
- Verification: `python -m pytest tests/production/identity -q`.

## Task 2: one-time bootstrap service

- Files: `compose.keycloak.yaml`, `Dockerfile.keycloak`, `integrations/keycloak/entrypoint.sh`, new `integrations/keycloak/bootstrap-entrypoint.sh`.
- First failing contract tests: regular service lacks bootstrap secrets; bootstrap service is profile-gated, one-shot, non-root and separately logged; entrypoint filter is exact.
- Implementation: DB-only regular entrypoint; bootstrap entrypoint loads three secret files and invokes `bootstrap-admin user --optimized --username:env ... --password:env ... --no-prompt`; exact event-code replacement; no broad logger suppression.
- Verification: Compose config parse, container build, fresh-volume bootstrap/start/login/restart.

## Task 3: leak gate

- Files: new `scripts/security/assert_no_secret_values.py`, new tests under `tests/keycloak/contract`, `.github/workflows/ci.yml`.
- First failing tests: scanner rejects a canary match without echoing it and accepts secret-free inputs; workflow never prints captured bootstrap output; normal container inspection rejects bootstrap mounts/variables.
- Implementation: bounded binary-safe comparison of non-empty secret file contents against named output files, status-only output and stable exit code.
- Verification: unit tests plus CI-equivalent canary lifecycle.

## Task 4: documentation

- Files: `docs/KEYCLOAK.md`, `docs/OPERATIONS.md`, `docs/TESTING.md`, `docs/BACKUP-RESTORE.md`, and the review-remediation specification.
- Cover initial setup, normal restart, temporary-admin removal/rotation, recovery with stopped nodes, exact event treatment and secret-safe diagnostics.

## Task 5: final evidence and publication

- Commands: Ruff, Mypy strict, full pytest excluding explicit live markers, Keycloak live E2E, PostgreSQL-16 suite, Bandit, isolated dependency audit, Gitleaks full history/staged, Python and four container builds, Trivy critical scans and `git diff --check`.
- Review `git diff origin/main...HEAD` and the remediation-only delta from `b2b0649` separately.
- Commit only the remediation, push `feature/keycloak-oidc-v0.7`, update PR #6 and keep it Draft.
