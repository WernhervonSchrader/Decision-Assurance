# Decision Assurance v0.8 — Controlled Pilot implementation plan

This plan implements the approved v0.8 specification on
`feature/controlled-pilot-edge-v0.8`. Every stage begins with a failing test, changes the smallest
existing boundary, and ends with focused verification. No deployment or merge is part of the plan.

## Baseline evidence

- `HEAD`, local `main` and `origin/main`: `af06fc84e5e9d9ed2a490f6d8d8442d8741394df`.
- Non-live suite: 575 passed, 21 deselected, two pre-existing local cache/deprecation warnings.
- Untracked `.codex-*` verification artifacts predate the branch and are excluded from commits.
- Existing externally significant contracts: API v0.5, eight exact Keycloak role values, tenant
  claim `tenant_id`, PostgreSQL forced RLS, Research request-time egress gate and five MCP tools.

## Stage 1 — contracts, migration and controlled-pilot profile

**Files:**

- Add `schemas/production/pilot-export.schema.json`, `schemas/production/data-lifecycle.schema.json`
  and packaged copies.
- Add `src/decision_assurance/migrations/postgresql/003_controlled_pilot_v0_8.sql` and root copy.
- Extend `production/config.py`, `production/contracts.py`, `config/deployment/` and pilot profile.
- Add `tests/pilot/contract/`, `tests/pilot/configuration/`, migration and RLS tests.

**Interfaces/data:** `OperatingMode.CONTROLLED_PILOT`; `PilotEdgeConfig`; `RetentionPolicy`;
`LegalHold`; `DeletionRequest`; `LifecycleEvent`; tenant-scoped SQL tables with forced RLS,
composite keys and constrained states. Application grants are least privilege; deletion execution is
through an explicit lifecycle repository, never ad-hoc route SQL.

**TDD:** first assert schema strictness, packaged/root migration equality, RLS on every table,
profile positive case and each mandatory startup rejection. Implement types/parser/migration only
after red tests.

**Verify:** `pytest tests/pilot/contract tests/pilot/configuration tests/production/unit/test_postgresql_migrations.py -q`;
expected all pass. Commit: `feat(pilot): define controlled pilot contracts and profile`.

## Stage 2 — tenant-safe list/read model and lifecycle service

**Files:**

- Extend `repositories/protocols.py`, `repositories/postgresql.py`, `repositories/sqlite.py` only for
  bounded case listing and atomic case locking.
- Add `lifecycle/contracts.py`, `lifecycle/ports.py`, `lifecycle/service.py`,
  `lifecycle/postgresql.py`.
- Add `api/routes/pilot.py`, strict request/response models and DE/EN codes.
- Add unit, API, PostgreSQL, race, replay, legal-hold and cross-tenant tests.

**Interfaces:** `list_decisions(tenant, limit, cursor)`; `LifecycleRepository.request_delete`,
`set_hold`, `execute_delete`; `LifecycleService` authorizes through existing permissions and accepts
only `Identity`, case ID, reason code and idempotency key. No public tenant field exists.

**TDD:** prove wrong-tenant 404-equivalent behavior, hold-before-delete, replay convergence, audit
failure rollback, same-case advisory serialization and physical removal of all classified data.

**Verify:** focused lifecycle/API tests plus PostgreSQL marker tests; expected no soft-deleted case
content and one retained minimized tombstone. Commit: `feat(pilot): add governed data lifecycle`.

## Stage 3 — deterministic portable export

**Files:**

- Add `export/contracts.py`, `export/service.py`, `export/validator.py`, `export/postgresql.py`.
- Add API export route, CLI `scripts/pilot/validate_export.py`, schemas and fixtures.
- Add schema/checksum/audit/redaction/tamper/traversal/zip-bomb/cross-tenant tests.

**Interfaces:** `PilotExportService.build(identity, decision_id, correlation_id) -> ExportArchive`;
`validate_export(bytes) -> ValidationReport`. Repository snapshots run in one tenant-scoped,
read-only transaction. ZIP paths come from a constant tuple and canonical JSON serializer.

**TDD:** assert identical logical input yields the same member bytes, all required provenance is
present, prohibited fields/canaries are absent, and every mutation fails validation.

**Verify:** `pytest tests/pilot/export -q` and offline CLI against a generated fixture; expected
`VALID` with all member checksums. Commit: `feat(pilot): add verifiable decision export`.

## Stage 4 — BFF OIDC and session security

**Files:**

- Add `src/decision_assurance/pilot_ui/{app,config,oidc,session,api_client,routes}.py`.
- Add `decision-assurance-pilot-ui` entry point and optional maintained OAuth/template dependencies.
- Add `tests/pilot/ui/test_oidc.py`, session, CSRF, redirect, proxy and leakage tests.

**Interfaces:** bounded `LoginTransactionStore` and `SessionStore`; `OidcBrowserClient` with S256;
`PilotApiClient` forwarding only bearer/correlation/locale/idempotency headers. Stores are
thread-safe, capacity/TTL bounded and tokens never implement `repr`/serialization.

**TDD:** missing/wrong verifier, state/nonce replay, callback fixation, expired session, CSRF,
open redirect, IdP/JWKS failure and canary leakage fail before API business access.

**Verify:** `pytest tests/pilot/ui -q`, Ruff/Mypy/Bandit. Commit:
`feat(pilot-ui): add server-side OIDC BFF`.

## Stage 5 — minimal multilingual browser UI

**Files:**

- Add `ui/package.json`, lockfile, TypeScript/Vite/Vitest configuration, `ui/src/`, semantic HTML
  template, CSS and localized catalogs.
- Add static asset packaging and `Dockerfile.pilot-ui` with non-root user/read-only runtime.
- Add UI unit tests for rendering, locale parity, safe text rendering, lifecycle actions and no
  governance computation.

**Journey:** session banner; cases; Sales Quote creation/text upload; Intake verification; Research
job polling; sources/claims/evidence/conflicts; findings/outcome/status; permitted transitions;
audit timeline; export and delete/hold controls. Unsupported actions are absent from the UI but still
server-denied when called directly.

**TDD:** DOM tests use fixtures from API schemas; external content is inserted with `textContent`,
never HTML. A source warning marks content untrusted. No token/localStorage/sessionStorage access is
present in production modules.

**Verify:** `npm ci && npm run lint && npm test && npm run build && npm audit --audit-level=high`;
expected zero failures/high vulnerabilities. Commit: `feat(pilot-ui): add bounded sales quote journey`.

## Stage 6 — HTTPS edge and controlled-pilot composition

**Files:**

- Add pinned `deploy/edge/Caddyfile`, `Dockerfile.edge`, `compose.controlled-pilot.yaml`, secret
  examples only and deployment validation scripts.
- Extend Keycloak realm with the public pilot client and exact redirect/logout URIs; preserve eight
  role values and one-shot bootstrap.
- Add edge contract, Compose, non-root, TLS/header/host/forwarded/request-limit tests.

**Behavior:** public routes are `/`, `/auth/*`, `/api/*`, `/mcp`, and the configured Keycloak host;
internal database, worker and management ports remain private. Local integration uses an ephemeral
CA/certificate fixture; pilot configuration requires non-loopback HTTPS names and secret references.

**Verify:** `docker compose -f compose.controlled-pilot.yaml config`, Caddy validate, image user
inspection and TLS probes. Commit: `feat(edge): add controlled pilot HTTPS boundary`.

## Stage 7 — complete two-tenant browser/API E2E

**Files:**

- Add Playwright configuration/helpers under `ui/e2e/` and deterministic fake-provider fixture.
- Add `tests/pilot/e2e/` API/PostgreSQL journey and hostile direct-request matrix.
- Keep live OpenAI/Firecrawl tests opt-in and non-normative.

**Seed:** isolated PostgreSQL 16 and Keycloak realm create Tenant A/B users in generator, validator,
approver and auditor roles. Secrets are random ephemeral files. Each test owns IDs and tears down
volumes. Fake transport returns deterministic public sources/evidence; no provider cost occurs.

**Browsers/devices:** current Playwright Chromium desktop is blocking; Firefox is a documented
non-blocking compatibility smoke. Retries are zero locally and one in CI; traces/screenshots are
retained only on failure and scanned for token/secret canaries before upload.

**TDD/security matrix:** successful Tenant A journey; Tenant B UI/API/direct-ID denial; PKCE,
state/nonce, session, CSRF, host/proxy, storage, roles, SoD, audit, export, deletion, SSRF and prompt
injection negatives. Verify APPROVED only after a different human actor and offline export `VALID`.

**Verify:** local Compose plus `npm run e2e`; expected one complete APPROVED journey, all isolation
probes denied, no canary output. Commit: `test(pilot): prove browser journey and isolation`.

## Stage 8 — observability, operations and documentation

**Files:**

- Extend observability metrics/detection and add label allowlist tests.
- Update `README.md`, `docs/PRODUCTION-READINESS.md`, `DEPLOYMENT.md`, `OPERATIONS.md`, `SECURITY.md`,
  `PILOT.md`, `KEYCLOAK.md`, `TESTING.md`, `CI-RELEASE.md`, `THREAT_MODEL.md`,
  `BACKUP-RESTORE.md`, `INCIDENT-RESPONSE.md` and `OBSERVABILITY.md`.
- Add `docs/RETENTION-DELETE-LEGAL-HOLD.md` and `docs/PILOT-ACCEPTANCE.md`.

**Content:** Prometheus queries and alerts; correlation; pilot start/abort/recovery; backup/restore
drill; rollback; data classification and deletion schedule; evidence-class separation; explicit
non-production status and residual risks.

**Verify:** documentation contract tests, link/path scan and sample alert evaluation. Commit:
`docs(pilot): add controlled operations and acceptance evidence`.

## Stage 9 — CI, release evidence and final review

**Files:** extend `.github/workflows/ci.yml`, release gate input/schema/tests and add pinned actions.

**Gates:** Python legacy; PostgreSQL 16/RLS/migrations; Keycloak; UI build/unit/Playwright; frontend
audit; Ruff/Mypy/Bandit; Gitleaks; pip/npm audits; actionlint; Python/UI/edge builds; non-root; SBOM;
Trivy; Compose/Caddy/TLS headers; export; retention/hold; full pilot E2E; OpenAPI drift; checksums.

**Local final commands:**

```text
ruff format --check src tests scripts
ruff check src tests scripts
mypy src
pytest -q -m "not postgresql and not keycloak_e2e and not pilot_browser and not live_provider"
pytest -q -m postgresql
pytest -q -m keycloak_e2e
bandit -q -r src -s B105
pip-audit
python -m build
npm --prefix ui ci
npm --prefix ui run lint
npm --prefix ui test
npm --prefix ui run build
npm --prefix ui audit --audit-level=high
docker compose -f compose.controlled-pilot.yaml config
git diff --check
```

Run container scans/SBOM and the local Playwright pilot journey where Docker/browser capability is
available. Use the in-app browser for a final visible UI inspection against the local HTTPS stack;
capture no secrets or full sensitive content.

Perform two distinct reviews: (1) specification/security/architecture compliance, then (2) code
quality/maintainability. Resolve every blocking finding. Commit intentionally, push only tracked PR
scope, open a Draft PR against `main`, monitor all CI jobs and request a separate independent review.
Do not mark ready, merge or deploy.

## Final evidence record

The final report records baseline/branch, architecture, changed files, journey, security boundaries,
retention behavior, exact test counts and CI links, residual risks, exclusions, commit SHA and Draft
PR URL. Repository CI, local integration, deployment, organizational approval and production
approval are five distinct evidence classes.
