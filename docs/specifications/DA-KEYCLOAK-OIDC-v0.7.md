# Keycloak OIDC integration v0.7

Status: approved implementation basis for local development and a later EU-managed deployment.

## Context assessment

PR #5 is merged at `92c67dc`. The provider pipeline is already guarded, tenant-aware and live-tested.
Decision Assurance already has one central OIDC adapter, bounded JWKS caching, server-side permissions,
tenant-scoped repositories and actor-independence transition rules. The change extends those components;
it does not introduce a second authentication or authorization architecture.

The current baseline is 519 passing non-PostgreSQL/non-live tests. Existing OIDC tests prove signature,
issuer, audience, time-window and key-rotation checks, but the identity contract currently accepts one
flat role and does not validate Keycloak `azp` or scopes. There is no reproducible Keycloak runtime,
realm, PKCE E2E or structured security-event contract.

Keycloak `26.7.0` is pinned. It was the current supported server release in the official download and
container documentation checked on 2026-07-31.

## Alternatives and decision

1. **Extend the existing OIDC and authorization ports (selected).** Map verified Keycloak claims into a
   multi-role `Identity`, retain local permission mapping and governance transitions, and add a dedicated
   local Keycloak Compose stack. This has the smallest trust surface and preserves current tenant controls.
2. Put an OIDC proxy or API gateway in front of the API. This can terminate login but would not remove the
   need for token, tenant and object-level checks in Decision Assurance and would add another trust boundary.
3. Move business permissions into Keycloak Authorization Services. This would duplicate and fragment the
   repository's permission and lifecycle rules and could make role assignment bypass actor independence.

Decision: option 1. Keycloak establishes identity; Decision Assurance authorizes every business action.

## Requirements matrix

| ID | Requirement | Implementation location | Test and evidence |
| --- | --- | --- | --- |
| KC-01 | Pinned supported Keycloak with separate PostgreSQL | `Dockerfile.keycloak`, `compose.keycloak.yaml` | Compose config/build, health and persistence E2E |
| KC-02 | Local credentials only through ignored files/environment | `.secrets/*.example`, entrypoint, ignore/Gitleaks | secret contract and scan |
| KC-03 | No `start-dev`; local/production boundary explicit | optimized image and `start --optimized`; docs | container contract |
| KC-04 | Reproducible secret-free realm import | `integrations/keycloak/decision-assurance-realm.json` | JSON contract and restart E2E |
| KC-05 | Confidential API, public PKCE UI and isolated PKCE E2E client | realm clients/scopes/mappers | realm contract and live PKCE E2E |
| KC-06 | Explicit redirect, origin, logout, token and refresh controls | realm client/realm settings | exact configuration assertions |
| KC-07 | Eight requested roles and multiple roles per actor | realm roles, `identity.py`, `authorization.py` | mapping/least-privilege tests |
| KC-08 | Tenant only from a verified claim; conflicts fail before I/O | async identity dependency and tenant guard | header/path/body mismatch zero-call tests |
| KC-09 | Platform cross-tenant access has no implicit bypass | authorization/tenant guard | allowed own-tenant and denied cross-tenant tests |
| KC-10 | Signature, algorithm, issuer, audience, time and not-before | existing OIDC adapter, stricter errors | unit and Keycloak token E2E |
| KC-11 | `azp`, actor, tenant, roles and scopes validated | OIDC policy/authenticator | negative claim tests |
| KC-12 | JWKS cache and controlled refresh support rotation | existing cache with bounded refresh | rotation/outage tests |
| KC-13 | Authentication and authorization remain separate | OIDC mapper versus permission service | architecture and tests |
| KC-14 | Only liveness/readiness/version are public | API routes and dependencies | OpenAPI/API tests |
| KC-15 | Stable, secret-free security events | `security_events.py`, API dependencies, structured logger | exact event/redaction tests |
| KC-16 | Authentication | Keycloak OIDC and API dependency | valid, missing, modified, expired token tests |
| KC-17 | Authorization | `authorization.py` permission matrix | every new role allowed/denied tests |
| KC-18 | Tenant isolation | verified token context and tenant repositories/RLS | two-tenant API/PostgreSQL/E2E tests |
| KC-19 | Input validation | strict bearer/claim/tenant conflict validation | malformed and conflicting request tests |
| KC-20 | Audit logging | bounded security-event sink | allow/deny/reason-code tests |
| KC-21 | Data protection | no token/password/client-secret persistence or logs | canary scan and exception tests |
| KC-22 | Multilingual behavior | no new user-facing strings; stable machine codes | DE/EN API regression tests |
| KC-23 | Actor independence | existing transition policy remains authoritative | self-review/self-approval E2E |
| KC-24 | Research regression | authenticated tenant reaches unchanged provider pipeline | fake-provider authenticated E2E |
| KC-25 | Unauthorized calls cause zero DB/provider I/O | dependency executes before handlers | spy repository/provider tests |
| KC-26 | E2E environment is isolated and deterministic | `keycloak_e2e` marker, runtime-created users | CI job and local guide |
| KC-27 | CI security checks stay blocking | CI Keycloak job plus existing scans/builds | GitHub checks |
| KC-28 | No export/delete/retention/legal-hold scope | no implementation paths | complete diff review |

## Proposed architecture

```text
Browser -- Authorization Code + PKCE --> Keycloak 26.7.0 -- separate DB --> keycloak-postgres
   |                                      |
   | Bearer access token                  | discovery/JWKS
   v                                      v
Decision Assurance API -> OIDC verification -> verified Identity + tenant + roles + client/scopes
                       -> tenant-conflict guard
                       -> local permission guard
                       -> repository/RLS or guarded Research providers
                       -> business audit + bounded security events
```

Trust boundaries are browser-to-Keycloak, API-to-Keycloak JWKS, token-to-verified identity,
identity-to-authorization and tenant-aware service-to-storage/provider. Client headers, paths and bodies
are untrusted consistency assertions only; none establishes tenant context. The token tenant claim is
accepted only after cryptographic and registered-claim validation.

The realm is `decision-assurance`. `decision-assurance-api` is confidential, has no direct grants or
service account by default and is the required audience. `decision-assurance-ui` is public and permits
only explicit loopback development redirect/origin/logout URIs with Authorization Code and S256 PKCE.
`decision-assurance-e2e` is an isolated public PKCE client with a different explicit loopback URI.

Keycloak realm roles are `da_admin`, `tenant_admin`, `decision_author`, `decision_reviewer`,
`decision_approver`, `auditor`, `research_operator` and `readonly`. They map to local roles and then to
local permissions. Possession of several roles produces a union of permissions, but transition-level
actor-kind and actor-independence checks still run and cannot be overridden by a role.

Security events are stable machine records with schema version, UTC timestamp, decision, actor reference,
tenant, client, correlation ID and reason code. Invalid-token actor references are one-way, truncated
SHA-256 fingerprints. Tokens, cookies, authorization headers, passwords and secrets are never event fields.

## Error and operational model

- Missing, malformed, expired, issuer/audience/party/scope/tenant/role failures have stable `AUTH_*` codes.
- JWKS is cached with a bounded TTL and refreshed once for an unknown `kid`; an invalid or unavailable
  source fails closed.
- Local HTTP is permitted only for explicit loopback OIDC in a development/test policy. Production policy
  requires HTTPS and cannot enable the exception.
- The local realm import is reproducible: a fresh database imports exactly the versioned realm. On restart,
  Keycloak skips the already present realm and retains data. Applying realm changes to an existing local
  database requires a documented controlled recreate/import, not an implicit overwrite.
- Liveness exposes only status. Readiness exposes bounded component status/reason codes and no configuration.

## Threat model

| Threat | Likelihood / impact | Prevention and detection | Response / residual risk |
| --- | --- | --- | --- |
| Forged or algorithm-confused JWT | medium / critical | signature plus RS256 allowlist, issuer/audience/azp/time checks | deny and `AUTH_TOKEN_INVALID`; rotate keys if compromised |
| JWKS poisoning or rotation outage | low / critical | HTTPS in production, bounded document/key types/count, cache, refresh lock | fail closed; alert on invalid/unavailable JWKS |
| Tenant spoofing in header/path/body | medium / critical | compare with verified claim before handler I/O | deny and audit mismatch |
| Privilege escalation through realm roles | medium / critical | allowlisted role mapping and local permission matrix | unknown roles ignored; missing mapped role denied |
| Self-approval through multiple roles | medium / high | immutable actor ID/kind and transition independence rules | deny transition and business audit |
| Cross-tenant platform-admin access | medium / critical | no implicit admin bypass; explicit path absent in v0.7 | deny and `AUTH_CROSS_TENANT_DENIED` |
| Credential or token disclosure | medium / critical | file secrets, redaction, bounded events, Gitleaks | rotate credential and investigate |
| PKCE interception/open redirect | low / high | S256 only, exact redirect/origin/logout URIs, state/nonce E2E | revoke session/client and correct config |
| ROPC misuse | low / high | direct access grants disabled on all DA clients | CI assertion; disable affected client |
| Keycloak/DB denial of service | medium / high | health checks, resource bounds, restart/persistence tests | degraded readiness; restore DB |
| Realm drift/import ambiguity | medium / medium | versioned import and exact contract tests | controlled database recreate/import |
| Supply-chain image compromise | low / critical | pinned image version, Trivy/SBOM, official image | block release and update reviewed pin |

## E2E strategy

Pytest remains the framework. Unit and integration tests use generated RSA keys and mock JWKS transports.
Keycloak E2E runs against the isolated Compose project, creates random temporary users in two tenants through
the admin boundary, executes the browser protocol with PKCE S256, and cleans test identities. It covers one
Chromium-equivalent HTTP protocol journey at desktop loopback; no UI is added in this scope. CI retains
failure logs with secret redaction and removes runtime secret files. Flakiness is controlled with health-based
startup, bounded retries, unique IDs and no production dependency.

## Acceptance criteria

1. Keycloak 26.7.0 and its separate PostgreSQL become healthy from a fresh Compose project without `start-dev`.
2. The versioned realm contains exactly the requested roles, safe clients, S256 PKCE and no literal secret.
3. A live PKCE code flow yields a token accepted by the API only after all trust checks.
4. Multiple Keycloak roles map to a union of local permissions without bypassing actor independence.
5. Tenant mismatches and authorization failures occur before database or provider operations.
6. Unknown/expired/manipulated/wrong-issuer/wrong-audience/wrong-azp/missing-scope tokens fail with stable codes.
7. JWKS rotation succeeds and outage/invalid documents fail closed.
8. Security events contain only the documented bounded fields and stable reason codes.
9. Restart preserves realm/test state through the Keycloak PostgreSQL volume.
10. Existing authenticated Research E2E and provider regression suites remain green.
11. All repository, PostgreSQL, Keycloak, security, dependency, container, Trivy, OpenAPI and diff checks pass.
12. Only Keycloak/OIDC work is committed to a new Draft PR; nothing is merged or deployed.

## Specification review

The requested "confidential API client" is interpreted as a confidential resource-server registration with
no service account or DA direct grant. Browser login belongs only to the public UI/E2E clients. The requested
"allowed administrator access" means normal same-tenant tenant-admin permissions; platform cross-tenant
access remains denied because no separately authorized product endpoint is in scope. Local HTTP is a narrow
loopback development exception and cannot be configured in production. These interpretations remove the
otherwise conflicting requirements without weakening the production boundary.
