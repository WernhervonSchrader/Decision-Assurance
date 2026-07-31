# Local Keycloak OIDC development environment

Decision Assurance includes a reproducible Keycloak 26.7.0 environment for development and
isolated E2E verification. It is not a production deployment or evidence of production readiness.
Keycloak establishes identity; Decision Assurance remains the authority for permissions, tenant
isolation, lifecycle transitions and actor independence.

## Start and stop

Copy the three placeholder files under `.secrets/` to names without `.example`, replace every
placeholder with a unique random value and restrict them to the current OS user. Never put a real
secret in Compose, the realm export, an environment committed to Git or a command transcript.

```powershell
docker compose -p decision-assurance-keycloak-local -f compose.keycloak.yaml up -d --build
docker compose -p decision-assurance-keycloak-local -f compose.keycloak.yaml ps
$env:DA_CONFIG_PATH = "config/deployment/keycloak-development.example.json"
$env:DA_DATABASE_PATH = ".local/keycloak-development.db"
$env:DA_SECRET_DIRECTORY = ".secrets"
decision-assurance-api
```

The local issuer is `http://127.0.0.1:8080/realms/decision-assurance`. Plain HTTP is accepted only
when `allow_insecure_loopback` is explicitly true and both issuer and JWKS endpoints are loopback.
Staging and production reject that option. Stop without deleting the PostgreSQL volume with
`docker compose -p decision-assurance-keycloak-local -f compose.keycloak.yaml down`.

The realm import contains no users or secrets. The bootstrap administrator exists only to manage
the isolated instance. Automated E2E creates random temporary identities through the Admin API,
uses Authorization Code with S256 PKCE, and deletes those identities afterward. Password grant is
used only by the test harness to obtain isolated administrative setup authority; application users
and production clients never use it.

## Realm, clients and claims

The `decision-assurance` realm has exactly these application roles: `da_admin`, `tenant_admin`,
`decision_author`, `decision_reviewer`, `decision_approver`, `auditor`, `research_operator` and
`readonly`. Users may hold several roles. The API maps them centrally but still enforces the
Decision Assurance permission matrix and human actor-independence rules.

| Client | Type and allowed use |
| --- | --- |
| `decision-assurance-api` | confidential server client; no browser, direct grant or service account flow |
| `decision-assurance-ui` | public Authorization Code client; S256 PKCE, exact loopback redirects/origins |
| `decision-assurance-e2e` | isolated public S256-PKCE client for automated local/CI verification only |

Access tokens are five minutes. Refresh reuse is disabled. The `da.api` scope emits the API
audience and the admin-managed `tenant_id`, `actor_kind` and optional `organization` attributes.
The `roles` scope exposes only the eight Decision Assurance realm roles. The API requires signature,
approved algorithm, issuer, audience, expiry, issued-at, subject, authorized party, tenant, actor
kind, roles and scope. `nbf` is verified whenever Keycloak emits it. Unknown signing keys trigger one
bounded JWKS refresh; malformed, duplicate, unavailable or non-matching signing keys fail closed.

Only `/health/live`, `/health/ready` and, when build metadata is configured, `/version` are public.
Interactive docs and the runtime OpenAPI route are disabled; reviewed OpenAPI artifacts are generated
offline. All `/v1` routes require authentication and centralized authorization.

Stable security reason codes are `AUTH_TOKEN_MISSING`, `AUTH_TOKEN_INVALID`,
`AUTH_TOKEN_EXPIRED`, `AUTH_ISSUER_MISMATCH`, `AUTH_AUDIENCE_MISMATCH`, `AUTH_ROLE_REQUIRED`,
`AUTH_TENANT_MISMATCH`, `AUTH_CROSS_TENANT_DENIED` and `AUTH_ALLOWED`. Events contain schema/event
identity, timestamp, decision, actor or pseudonymous reference, verified tenant, client, correlation
ID, permission and reason code—never tokens, cookies, passwords, request bodies or client secrets.

## Backup, restore and rotation

The named volume contains only the separate Keycloak PostgreSQL database. A development backup uses
`pg_dump --format=custom` against the `keycloak` database and must be encrypted and access-controlled.
Restore only into a fresh isolated Keycloak database, then verify realm/client/role contracts, PKCE,
tenant denial and a container restart. Do not use the Decision Assurance application database or its
credentials for Keycloak.

For signing-key rotation, publish the replacement public key before issuing tokens with its `kid`;
retain the old public key for the maximum access-token lifetime plus clock skew. Rotate bootstrap,
database and any future confidential-client secrets by replacing their secret-store values and
restarting the local stack without displaying them. A realm export containing a `secret` field is
not eligible for commit.

## Production gate

Production requires a separate reviewed configuration: TLS and a stable domain, managed secret
storage, e-mail verification, MFA policy, SMTP, monitoring/on-call, encrypted backups/PITR,
high availability, capacity and denial-of-service controls, admin hardening and recovery drills.
EU-managed use additionally requires verified locations and contractual evidence for identity,
database, backup, support and control-plane access. No local result grants production approval.

Run the isolated suite only with explicit opt-in:

```powershell
$env:DA_RUN_KEYCLOAK_E2E = "1"
python -m pytest tests/keycloak -q --basetemp .codex-pytest-keycloak
```
