# Reference Deployment

This command starts the loopback-only local reference API:

```powershell
$env:DA_DATABASE_PATH = ".local/decision-assurance.db"
$env:DA_IDENTITIES_PATH = "C:/protected/development-identities.json"
decision-assurance-api
```

Configuration is validated at startup; missing values stop the process. Copy
`config/identities.example.json` outside the repository, replace the placeholder
with a non-production development token and restrict file permissions.

The reference server binds only to `127.0.0.1`. An exposed deployment needs a
maintained OIDC adapter, TLS/HSTS edge, request timeout and rate limits,
PostgreSQL plus tested RLS/migrations, secrets management, encrypted backups,
monitoring and a rollback plan. v0.2 intentionally makes no production-readiness
claim without these controls.

