# PR 11 security gate remediation — design and plan

Date: 2026-10-08. Base: a94322f38d5090aefe9991cd732b41a9fabb618b, existing draft PR 11. Scope: dependency/image patching only. No release or deployment.

CI run 36980262943 passed backend, PostgreSQL, restore, Keycloak E2E and secret checks, but UI npm audit failed on Undici 8.10.1 and Vitest/mocker 4.1.10; container scan failed on five CRITICAL Keycloak Java advisory matches. API image success does not satisfy these gates.

Options: suppress findings (rejected: loses the gate); major upgrades (unnecessary compatibility risk); smallest upstream patches plus exact current lock and unchanged checks (selected). Pin Vitest 4.1.11 and transitive Undici 8.10.2, and Keycloak 26.7.5 in both image stages. All are within current major versions. Upstream primary evidence: https://github.com/advisories/GHSA-82fw-gwwq-j7x9 ; https://github.com/nodejs/undici/releases/tag/v8.10.2 ; https://github.com/keycloak/keycloak/releases/tag/26.7.5 . Inspect actual scan, do not infer all fixes merely from release notes.

Requirements: tenant isolation, trusted OIDC identities, actor roles, EN/DE locales, PKCE, bootstrap-secret lifecycle, non-root images and audit behavior remain covered by existing tests. No API/schema/domain transitions change. Threats: vulnerable dev dependencies can disclose files or bypass TLS; outdated identity-provider libraries can permit unauthenticated abuse. Controls: upstream patches, immutable lock, build/scan, real PKCE/login/tenant/role negatives, no scanner exclusions. Residual risk: vulnerability databases and self-review are incomplete assurance.

Plan before production edits:
1. ui/package.json + ui/package-lock.json: patch Vitest, scoped Undici override; isolated Node 26 npm lock/install with no credentials. Run npm ci, tsc, unit tests, build, audit and unchanged Chromium EN/DE/two-tenant E2E. Trace retention remains CI policy.
2. Dockerfile.keycloak: same 26.7.5 image in both stages; update exact-version contract in tests/keycloak/contract/test_compose.py and current docs/KEYCLOAK.md, docs/TESTING.md. Preserve historical versioned design/remediation records. Run Keycloak contract tests, image build, archive-based CRITICAL fixed-available Trivy scan and existing real Keycloak OIDC E2E in isolated Compose services; no Docker socket mount.
3. Review full staged diff and secrets. Commit only patch scope, fast-forward existing PR 11 branch if remote head is still the verified base; otherwise inspect new remote changes before proceeding. Update PR description with exact commit/check results and remaining blockers. No weakening, bypass, main merge, release tag or deployment.

Acceptance: no known fixed-available CRITICAL image matches and npm audit at unchanged threshold passes; functional and OIDC/browser tests pass on published commit. Otherwise keep PR draft and report exact unresolved gate.

Additional observed HIGH: source-map-js 1.2.1, GHSA-68fv-2mgg-jv7q. Add scoped override 1.2.2, regenerate lock and rerun unchanged checks. Windows bind-mounted node_modules caused a worker startup timeout (no tests executed); run the same commands on container-local storage and retain that technical failure. No test timeout or gate is relaxed.

Observed local candidate: unchanged TypeScript lint, 3 Vitest tests, production build, npm audit (0 vulnerabilities) and 2 Chromium E2E tests pass on regenerated lock using container-local filesystem. The earlier Windows bind-mount worker timeout had zero executed tests and is retained as a technical failure. Keycloak contract tests: 12 passed; 26.7.5 image built. Critical image scan and real OIDC CI must still be checked before merge.
