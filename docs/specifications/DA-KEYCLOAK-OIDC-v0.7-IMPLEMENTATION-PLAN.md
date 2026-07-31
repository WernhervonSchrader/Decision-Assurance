# Keycloak OIDC v0.7 implementation plan

## 1. Compose and realm contracts

- Paths: `Dockerfile.keycloak`, `compose.keycloak.yaml`, `integrations/keycloak/entrypoint.sh`,
  `integrations/keycloak/decision-assurance-realm.json`, `.secrets/keycloak-*.example`, ignore/Gitleaks.
- First failing tests: add `tests/keycloak/contract/test_realm.py` and `test_compose.py` for image `26.7.0`,
  non-root user, no `start-dev`, separate DB/user/volume, file secrets, health, roles, clients, PKCE S256,
  exact redirects/origins/logout, token lifetime/refresh reuse, disabled grants/accounts and absent secrets.
- Implement an optimized official image and file-secret entrypoint ending in `exec kc.sh`; startup realm import
  is skipped safely when already present.
- Expected: `docker compose -f compose.keycloak.yaml config` succeeds only with local secret files.
- Commit boundary: `feat(keycloak): add reproducible local realm environment`.

## 2. Multi-role identity and local permission mapping

- Paths: `identity.py`, `authorization.py`, OIDC contracts/config and corresponding tests.
- Add Keycloak role mapping and a backward-compatible multi-role identity. Add least-privilege
  `RESEARCH_OPERATOR` and `READONLY` local roles; local authorization unions permissions.
- Add OIDC allowed parties, required scopes and loopback-only development trust configuration.
- Failing tests: multiple recognized roles, unknown-only roles, missing scope/party, production HTTP rejection,
  research operator versus readonly, and unchanged service/human semantics.
- Expected: roles never directly alter a transition or tenant context.
- Commit boundary: `feat(auth): map verified Keycloak roles to local permissions`.

## 3. Stable authentication outcomes and security events

- Paths: `oidc/authenticator.py`, `oidc/jwks.py`, new `security_events.py`, logging port/adapter, API dependencies.
- Classify missing/invalid/expired/issuer/audience/role/tenant/cross-tenant outcomes without provider details.
- Validate `azp`, roles and scopes only after signature/registered claims. Add bounded event records and a logger
  sink; hash invalid bearer material only into a short pseudonymous reference.
- Make the identity dependency async and compare optional top-level body, route and `X-Tenant-ID` assertions
  with the verified tenant before route handlers run. Update central permission calls to emit allow/deny events.
- Failing tests: exact codes/events, secret canaries, malformed JSON, conflict zero repository/provider calls.
- Expected: no authorization header, token, cookie or secret is serializable in a security event.
- Commit boundary: `feat(auth): enforce tenant claims and security audit events`.

## 4. Runtime and Keycloak development profile

- Paths: runtime/config contracts, `config/deployment/keycloak-development.example.json`, `.env.example`,
  configuration schemas and tests.
- Permit HTTP only for loopback development OIDC; production keeps HTTPS. Wire the existing OIDC factory in
  the reference runtime when the explicit Keycloak development profile is selected. Preserve provider keys
  and the request-time provider egress guard unchanged.
- Add bounded JWKS cache configuration and readiness without exposing endpoints or secrets.
- Failing tests: development OIDC selection, production downgrade rejection and unavailable JWKS.
- Expected: default reference tests remain static; production remains OIDC-only.
- Commit boundary: included with authentication commit.

## 5. Unit, API and Research regression tests

- Paths: production identity/configuration tests, new security-event and tenant-boundary tests, existing
  decision/research E2E tests.
- Cover valid/missing/manipulated/expired/issuer/audience/azp/scope/role, rotation/outage, two tenants,
  tenant admin versus platform admin, actor independence and audit reason codes.
- Add spies proving denied requests do not call repositories, OpenAI or Firecrawl. Run the current fake-provider
  Research journey using a verified multi-role identity.
- Expected: standard suite uses no Keycloak/provider network and stays deterministic.

## 6. Live Keycloak E2E and persistence

- Paths: `tests/keycloak/e2e/test_keycloak_oidc.py`, helper module and CI workflow.
- Gate with `DA_RUN_KEYCLOAK_E2E=1`. Generate temporary identities/passwords at runtime, obtain the admin token
  only for test setup, execute Authorization Code with PKCE S256 against the E2E client, and call the API.
- Test missing/incorrect roles and tenant conflict, restart Keycloak without deleting its volume, and confirm
  the realm/user remains available. Delete temporary users in teardown.
- CI creates random secret files, starts only the Keycloak stack, waits for health, runs marked tests, captures
  bounded diagnostics on failure and tears down volumes.
- Expected: no real user password or client secret exists in Git or test artifacts.

## 7. Documentation

- Update `README.md`, architecture/security/threat/testing/deployment documents and add
  `docs/keycloak/{local-development,configuration,roles-and-tenancy,backup-restore,rotation}.md`.
- Document DE/EN UI ownership for a future UI, machine-code audit language, local versus EU-managed boundaries,
  TLS/domain/email/MFA/SMTP/monitoring/backup/HA prerequisites, realm update/import and incident response.
- Explicitly state that roles do not replace governance and local success is not production approval.

## 8. Verification and publication

- Run Ruff format/check, strict Mypy, all non-live tests, PostgreSQL 16, Keycloak E2E, authenticated Research
  regression, Bandit, Gitleaks history/staged, pip-audit, builds, API/worker/MCP/Keycloak non-root smoke, Trivy,
  OpenAPI drift and `git diff --check`.
- Inspect `git diff origin/main...HEAD` against every requirement and confirm the OpenAI/Firecrawl secret files
  are unchanged and untracked.
- Stage explicit OIDC/Keycloak paths only, create a Conventional Commit, push
  `feature/keycloak-oidc-v0.7`, and open a Draft PR against `main`.
- Expected: Draft PR only; no merge and no deployment.
