# PR #6 review remediation specification

Status: implementation basis for the two blocking findings on `feature/keycloak-oidc-v0.7`.

## Normative basis and DA security contracts

The reusable security baseline is OpenID Connect Core for authentication semantics, RFC 7519 section 7.3 for security-sensitive string comparison, RFC 8725 for JWT algorithm/issuer/audience/claim validation, and the applicable validation and privacy guidance in RFC 9068 for JWT OAuth access tokens. OWASP Logging and Secrets Management guidance governs exclusion, lifetime and rotation of credentials. Keycloak's supported `bootstrap-admin user` lifecycle is authoritative for initial and recovery administration.

This remediation does not invent alternative JWT validation semantics and does not claim broader RFC 9068 profile conformance beyond the repository's existing access-token contract. It changes only the two reviewed boundaries.

The role vocabulary and bootstrap-username classification are Decision Assurance security contracts, not names prescribed by OIDC or an RFC:

> External roles are mapped only through a versioned, explicit and case-sensitive allowlist. Unknown or differently spelled roles confer no permission. Initial administrator credentials are supplied only to a separate one-time bootstrap process and are unavailable to the regular Keycloak service afterward.

Primary references:

- https://openid.net/specs/openid-connect-core-1_0.html
- https://www.rfc-editor.org/rfc/rfc7519.html#section-7.3
- https://www.rfc-editor.org/rfc/rfc8725.html
- https://www.rfc-editor.org/rfc/rfc9068.html
- https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- https://www.keycloak.org/server/bootstrap-admin-recovery

## A. Context assessment

PR #6 at `b2b0649` has green CI and a working Keycloak 26.7.0 OIDC flow, but the independent gate is `FAIL` for two bounded reasons. The OIDC boundary first maps the eight external Keycloak roles and then incorrectly falls back to the internal `Role` enum. The regular Keycloak process also receives bootstrap username and password secrets on every start; Keycloak event `KC-SERVICES0077` writes the bootstrap username to its log during initial creation.

Existing tenant-aware repositories, authorization guards, transition-level actor independence, JWKS verification, request-time provider egress guards and OpenAI/Firecrawl adapters remain unchanged. The tracked tree is clean; existing untracked `.codex-*` test artifacts are outside the change.

Risks are privilege escalation through role-name drift, credential disclosure in retained logs, bootstrap failure leaving an unusable local realm, accidental secret output during diagnostics, and regressions in authenticated Research.

## B. Requirements matrix

| Requirement | Implementation location | Test method | Completion evidence |
|---|---|---|---|
| Exact eight-role allowlist | `oidc/authenticator.py` boundary parser | signed-token parameterized tests | internal/variant names denied |
| Unknown roles confer no permission | OIDC boundary parser | unknown-only and mixed-role tests | only exact mapped roles present |
| Pre-access denial | API dependencies/routes unchanged | repository/provider spies | zero calls on denial |
| One-time bootstrap lifecycle | `compose.keycloak.yaml`, bootstrap entrypoint | fresh-volume lifecycle E2E | bootstrap, ready, login, restart |
| No bootstrap secrets in regular service | Compose service mounts and environment | container inspection | no username/password mount or environment |
| Exact event treatment | bootstrap entrypoint | synthetic canary log scan | `KC-SERVICES0077` retained redacted; other logs retained |
| No secret values in output | security scan helper and CI | username/password/DB canary scan | zero matches without printing values |
| Multilingual support | no user-facing application text changed | existing localization suite | unchanged/pass |
| Multi-tenancy and isolation | existing verified token tenant boundary | tenant-conflict and E2E tests | no cross-tenant access |
| Authentication | exact role parser plus existing JWT/JWKS checks | OIDC negative tests | fail-closed reason codes |
| Authorization | existing permission matrix | role and pre-access tests | prohibited operations denied |
| Actor independence | existing transition policy | multi-role E2E | self-validation remains denied |
| Input validation | exact case-sensitive parser | malformed variants | no normalization or aliasing |
| Audit logging | security-event schema unchanged | redaction tests | no tokens, secrets, names or email |
| Data protection | ephemeral bootstrap secrets and persistent DB | mount/log inspection | no secret persistence in runtime container |
| E2E testing | existing Keycloak PKCE harness plus lifecycle test | real Keycloak 26.7.0 | login/restart/Research pass |
| CI security checks | `.github/workflows/ci.yml` | CI and local equivalents | scan/build/test gates green |

## C. Proposed architecture

The OIDC trust boundary parses external realm roles through one closed `KEYCLOAK_ROLE_MAP`. Values are compared exactly and case-sensitively. Unknown values are ignored; a token with no exact mapped role fails with `AUTH_ROLE_REQUIRED`. No generic enum parsing occurs at this boundary.

Keycloak initialization is split from normal runtime:

```text
secret files -> short-lived bootstrap service -> Keycloak PostgreSQL
                                             (service exits and is removed)

DB password -> regular Keycloak service -> imported realm -> OIDC API
```

The bootstrap service is profile-gated and invoked explicitly while the regular Keycloak node is stopped. It uses Keycloak's supported `bootstrap-admin user --optimized` command. Its dedicated entrypoint passes every line except the single `KC-SERVICES0077` record unchanged; that record is retained with a fixed redacted message. The regular service never mounts or loads the bootstrap username/password. Restart uses only persistent PostgreSQL state.

The secret-file values are exported to command-specific `DA_KEYCLOAK_BOOTSTRAP_USERNAME` and `DA_KEYCLOAK_BOOTSTRAP_PASSWORD` variables and selected through Keycloak's `--username:env` and `--password:env` options. The reserved `KC_BOOTSTRAP_ADMIN_*` startup variables are deliberately absent: setting them during the dedicated command would also activate the normal-start bootstrap path and violate the one-time lifecycle.

Bootstrap failures expose only a generic status. Captured output is scanned against secret files without printing either matched values or log bodies. Recovery repeats the bootstrap command only with all Keycloak nodes stopped and follows the documented temporary-admin removal/rotation procedure.

Alternatives rejected:

1. Keep bootstrap variables on regular startup and rename the username: does not remove secret lifetime or logging.
2. Disable Keycloak logging or an entire category: hides unrelated security events.
3. Automatically run bootstrap on every Compose start: conflicts with one-time state and can block restart.

## D. Threat model update

| Threat | Likelihood / impact | Prevention | Detection / response | Residual risk |
|---|---|---|---|---|
| Internal enum injected as external role | medium / critical | closed exact mapping | negative signed-token matrix | trusted IdP can still assign an approved powerful role |
| Case/alias normalization escalation | medium / high | no normalization | variant tests | none beyond explicit mapping changes |
| Bootstrap username/password retained in logs | high / high | separate service and exact event redaction | canary scan of captured output | upstream event format change fails the canary gate |
| Bootstrap secrets retained in normal container | medium / high | no mounts or variables on regular service | inspect mounts and PID environment | DB credential remains required at runtime |
| Partial bootstrap or concurrent server | low / high | explicit stopped-node sequence and exit-code gate | readiness/login verification | operator can bypass documented sequence |
| Overbroad log filter | low / high | exact event-code branch only | unit test preserves adjacent lines | future Keycloak event semantics require review |
| CI diagnostics disclose canaries | medium / high | never print captured output or secret values | static workflow contract and Gitleaks | runner administrators remain trusted |

## E. Implementation plan

1. Add failing OIDC role-boundary tests in `tests/production/identity/test_oidc_authentication.py`, including all internal enum names, spelling variants, mixed roles and pre-access behavior.
2. Remove generic `Role(item)` fallback in `src/decision_assurance/oidc/authenticator.py`; retain only the explicit external mapping.
3. Split `integrations/keycloak/entrypoint.sh` into DB-only regular startup and a new short-lived bootstrap entrypoint with exact `KC-SERVICES0077` redaction.
4. Add a profile-gated `keycloak-bootstrap` service to `compose.keycloak.yaml`; remove bootstrap secrets from the regular service.
5. Add a secret-safe scanner under `scripts/security/` and contract/lifecycle tests under `tests/keycloak/` using generated canaries without displaying them.
6. Update CI to bootstrap before starting Keycloak, scan captured outputs, verify the regular container has no bootstrap secret access, then run existing PKCE/Research/restart E2E.
7. Update `docs/KEYCLOAK.md`, operations, testing and recovery documentation for initial bootstrap and recovery.
8. Run focused tests, full suites, PostgreSQL 16, lint/type/security/dependency/secret/container checks, builds and `git diff --check`.
9. Review only the remediation diff, commit and push the same branch, then update Draft-PR #6. Do not declare `PASS`, merge or deploy.

Expected commit: `fix(identity): close Keycloak review findings`.

## F. Acceptance criteria

1. Only the eight exact external role names can map to local permissions.
2. Every internal enum spelling and requested variant fails closed unless another exact valid role is present.
3. Authorization denial occurs before protected repositories or providers.
4. A fresh database can be bootstrapped, started, authenticated, restarted and reused.
5. The normal Keycloak container has no bootstrap username/password mount or environment value.
6. Canary username, password and DB password occur in neither retained bootstrap output, normal Keycloak logs nor CI output produced by the lifecycle steps.
7. Only `KC-SERVICES0077` is redacted; unrelated Keycloak messages remain observable.
8. Existing Tenant, Actor-Independence, JWKS, PKCE and Research behavior remains green.
9. PR #6 remains Draft and receives a new independent review on the corrected head.
