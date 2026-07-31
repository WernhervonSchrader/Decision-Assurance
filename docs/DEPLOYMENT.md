# Deployment

## Supported production paths

Use one repository profile as a reviewed starting point:

- `config/deployment/local.example.json`: self-managed PostgreSQL, OIDC, secrets, backup and support
  access within the operator's local boundary. Override both Research base URLs to hosts on the
  declared allowlist. This is distinct from the SQLite development runtime.
- `config/deployment/eu-managed.example.json`: managed services with declared EU member-country
  locations for storage, processing, backup, support and external processing. Replace the example
  HTTPS evidence references with owned, review-dated residency and subprocessor evidence.

Both modes use the same images and database schema. Configuration is deployment authority and must
be delivered read-only. A missing/unknown mode, missing location category, non-EU managed location,
remote local core location or missing EU evidence prevents startup. Profile acceptance is not GDPR
certification or proof of a provider's actual processing location.

| Control | `local` | `eu-managed` |
| --- | --- | --- |
| Data and application processing | storage, processing and backups are exactly `local` | every storage, processing and backup location is an EU ISO country code |
| Provider egress | each allowlisted host is declared `local`, but OpenAI/Firecrawl remain blocked until a verified attestation is supplied | each allowlisted host has one declared EU processing country; OpenAI/Firecrawl remain blocked until a verified attestation is supplied |
| Identity | production OIDC with exact HTTPS issuer/audience/JWKS and signed tenant/role claims inside the operator boundary | the same OIDC contract, with identity/support locations included in the EU deployment review |
| PostgreSQL | PostgreSQL 16, forced RLS, separate migration/application/Worker credentials, encrypted local storage and backups | the same schema and roles on an EU-located managed service with encrypted backups/PITR |
| Retention and deletion | operator applies the approved tenant schedule to live data, jobs, audit and local backups | operator applies the same tenant schedule to primary, replica, backup and provider copies in the declared countries |
| Export and restore | tenant-scoped export to an access-controlled local destination; restore only to a fresh local target | tenant-scoped export and fresh-target restore remain inside declared EU locations |
| Incident response | isolate local egress, revoke local credentials, preserve local evidence and test two-tenant RLS | additionally block non-EU routes/support, preserve provider evidence and assess cross-border exposure |

`provider_egress` is mandatory for production and staging. Each entry contains provider/service,
host, requested `processing_location`, tenant scope, confirmed processing locations and a structured
attestation. Its host set must equal `egress_allowed_hosts`, and the effective
`OPENAI_BASE_URL`/`FIRECRAWL_BASE_URL` host set must equal the declaration. Startup validation
is only an early check: the central request-time guard runs immediately before every external request.
`DPA`, signed provider attestations and verifiable technical provider configuration are admissible;
operator self-declarations are not. Until an attestation is independently verified and in date,
OpenAI and Firecrawl are fail-closed blocked. Do not label a public SaaS hostname `local`.

Each decision persists a secret-free `research.egress-decision` event with schema version,
`ALLOWED`/`BLOCKED`, tenant, actor/correlation, profile/policy, provider, host, requested location,
evidence identity/status and one reason code. Stable block codes include
`EGRESS_LOCATION_NOT_ALLOWED`, `EGRESS_EVIDENCE_MISSING`, `EGRESS_EVIDENCE_UNVERIFIED`,
`EGRESS_EVIDENCE_EXPIRED`, `EGRESS_HOST_MISMATCH`, `EGRESS_TENANT_MISMATCH`,
`EGRESS_CONFIGURATION_CHANGED` and `EGRESS_AUDIT_FAILED`.

Before rollout, record configuration hash, image digest, tenant set, OIDC issuer, secret owner,
database/backup locations, support countries, external processor countries, evidence owner/review
date, retention policy and rollback target. Deployment order is migration -> API/Worker/MCP ->
readiness -> two-tenant DE/EN smoke tests -> traffic. Rollback uses prior compatible images and the
same operating profile; it may not silently change jurisdiction.

## Retention, tenant export and deletion gate

Before admitting personal or regulated data, the deployment owner must approve a per-tenant record
covering data classes, legal basis, live retention, audit retention, provider retention, backup
expiry, legal hold, export authorization and deletion verification. The current application has no
general tenant export/deletion API. Until a reviewed, tenant-scoped and audited operational workflow
exists, any request requiring automated export, erasure, suspension or legal hold is unsupported and
the production admission decision is `BLOCK`.

An approved manual procedure must use a dedicated least-privilege role, establish exactly one tenant
context, produce an encrypted manifest with counts and hashes, require two-person approval, and
verify that no other tenant is present. Deletion must cover primary rows, jobs, cached evidence,
provider-held copies and backup expiry; audit records are retained or pseudonymized only under the
approved legal schedule. Never delete shared backups in place. Record the deletion tombstone and
allow the immutable backup to expire, preventing restoration after the erasure deadline through a
documented suppression/re-deletion control.

## Profile change and incident gate

Operating mode is immutable for a running release. A mode, country, provider-host or processing-site
change is a new reviewed deployment: update evidence, rotate affected credentials, run configuration
contracts, two-tenant DE/EN smoke tests and a fresh restore drill before traffic. Runtime fallback to
another mode, region, SQLite, static identity, environment secrets or undeclared provider is
forbidden.

On suspected residency drift, disable Research submission and provider egress, keep the API out of
readiness when a core dependency is affected, preserve configuration hashes and provider/access
logs, revoke exposed credentials, identify tenants and data classes, and follow the notification and
regulatory assessment owned by the deployment operator. Resume only after corrected configuration,
evidence review and all release gates pass.

## Local reference profile

The loopback-only SQLite/static-token profile remains for deterministic development and tests:

```powershell
$env:DA_DATABASE_PATH = ".local/decision-assurance.db"
$env:DA_IDENTITIES_PATH = "C:/protected/development-identities.json"
decision-assurance-api
```

It is not a production profile. Protect the identity file, bind only to `127.0.0.1` and never use
real credentials or regulated data.

The alternative Keycloak development profile is documented in [KEYCLOAK.md](KEYCLOAK.md). It binds
Keycloak to loopback, uses a separate PostgreSQL 16 database and accepts HTTP only through an
explicit development-only loopback flag. It is not the `local` production profile. Production must
replace it with TLS/domain, managed secrets, MFA/e-mail/SMTP, monitoring, encrypted backup/PITR and
HA configuration and must independently validate EU-managed location/contract requirements.

## Production images

`Dockerfile.api`, `Dockerfile.worker` and `Dockerfile.mcp` build the same immutable v0.5 wheel in
separate non-root images. Supply `DA_COMMIT_SHA` and `DA_BUILD_TIMESTAMP` as build arguments. The runtime filesystem is
read-only compatible; only `/tmp` is a small `noexec,nosuid` tmpfs. Terminate TLS/HSTS and enforce
request/rate limits at a maintained edge proxy.

The API uses the application DSN. The Worker needs both an application DSN for tenant-scoped domain
operations and a separately privileged Worker DSN limited to queue tables. Migration credentials are
used only by the one-shot migration container. All are mounted secret files under `/run/secrets`;
none belongs in Compose, image layers, environment values or source control.

For local staging, create ignored `.secrets/` files for the five Compose secret references, then set
the immutable build metadata and start:

```powershell
$env:DA_COMMIT_SHA = (git rev-parse HEAD)
$env:DA_BUILD_TIMESTAMP = (Get-Date).ToUniversalTime().ToString("o")
docker compose up --build
```

Create PostgreSQL login roles outside the application and grant each exactly one group role from
`migrations/postgresql/roles.sql`. The bootstrap PostgreSQL superuser is not an API, Worker or steady
state migration credential. Verify `/version`, `/health/live` and `/health/ready` before traffic.

MCP listens on port 8001 and `/mcp`. Production configuration must explicitly set issuer URL,
external HTTPS resource-server URL and exact allowed Host/Origin values; startup fails closed when
they are missing. The edge must forward bearer authentication without logging it. MCP has no public
unauthenticated health tool; probe process/readiness internally and verify authenticated protocol
initialization synthetically. Detailed rollout and ChatGPT Work steps are in
[MCP Web Research](MCP-WEB-RESEARCH.md).

Rollback selects the prior immutable image only when its expected schema is compatible. Database
changes are forward-only: apply a reviewed compensating migration or restore a verified backup into
a fresh instance. Never edit `schema_migrations` or tenant audit rows.
