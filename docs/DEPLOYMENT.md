# Deployment

## Local reference profile

The loopback-only SQLite/static-token profile remains for deterministic development and tests:

```powershell
$env:DA_DATABASE_PATH = ".local/decision-assurance.db"
$env:DA_IDENTITIES_PATH = "C:/protected/development-identities.json"
decision-assurance-api
```

It is not a production profile. Protect the identity file, bind only to `127.0.0.1` and never use
real credentials or regulated data.

## Production images

`Dockerfile.api` and `Dockerfile.worker` build the same immutable v0.5 wheel in separate non-root
images. Supply `DA_COMMIT_SHA` and `DA_BUILD_TIMESTAMP` as build arguments. The runtime filesystem is
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

Rollback selects the prior immutable image only when its expected schema is compatible. Database
changes are forward-only: apply a reviewed compensating migration or restore a verified backup into
a fresh instance. Never edit `schema_migrations` or tenant audit rows.
