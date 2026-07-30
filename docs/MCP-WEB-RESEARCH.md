# MCP Web Research and ChatGPT Work

Decision Assurance v0.5 exposes the existing Web Research domain through one separately runnable
MCP resource server. It does not duplicate Brave or Firecrawl and it does not expose arbitrary
browsing. The supported transport is stateless Streamable HTTP at `/mcp` using the official MCP
Python SDK `>=1.29,<2`.

## Boundary and tools

```text
ChatGPT Work/Codex -> personal skill -> MCP /mcp -> existing Research service
-> queued Worker -> Brave/Firecrawl -> conservative evidence -> DRAFT Decision File
```

Exactly five tools are available:

| Tool | Required permission | Purpose |
| --- | --- | --- |
| `research_start` | `research:create` | start bounded Quick, Verified or Deep research |
| `research_get` | `research:read` | read status, sources, conflicts and evidence draft |
| `research_retry` | `research:retry` | retry only permitted failed provider steps |
| `research_cancel` | `research:cancel` | idempotently cancel and audit |
| `research_handoff` | `research:handoff` | invoke/confirm existing DRAFT-only handoff |

Generator and Validator can start and hand off. Validator can retry. Generator and Validator can
cancel. Auditor, Reviewer and Approver have read-only access; Tenant Administrator has tenant-wide
permissions. System Administrator cannot read tenant business records. Central authorization is
authoritative.

Tenant is never an input. The MCP bearer token is checked before every tool call by the existing
static-development or production OIDC authenticator. The adapter derives tenant, actor, role and kind
only from that verified identity. Provider keys remain server-side and are resolved only from
`BRAVE_SEARCH_API_KEY`/`FIRECRAWL_API_KEY` in reference mode or their protected secret references in
configured production.

## Research modes and limits

Quick caps at 5 search results/2 extractions, Verified at 10/5, and Deep at 20/10. Effective limits
are the minimum of client request, mode cap and server Research policy. Retry reuses the stored
request and cannot change domains, SSRF policy, budget or limits. Outputs never include raw extracted
page text, credentials or an assurance outcome.

## Local PowerShell test flow

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest tests\mcp_adapter -q

$env:DA_DATABASE_PATH = ".local/decision-assurance.db"
$env:DA_IDENTITIES_PATH = "C:/protected/development-identities.json"
$env:DA_MCP_HOST = "127.0.0.1"
$env:DA_MCP_PORT = "8001"
$env:DA_MCP_ISSUER_URL = "http://localhost/identity"
$env:DA_MCP_RESOURCE_SERVER_URL = "http://127.0.0.1:8001"
$env:DA_MCP_ALLOWED_HOSTS = "127.0.0.1:8001,localhost:8001"
.\.venv\Scripts\decision-assurance-mcp.exe
```

The reachable local endpoint is `http://127.0.0.1:8001/mcp`. A bearer token from the protected
development identity file is required. With provider keys absent, provider work fails with a
controlled error; standard tests use fakes and never require keys. Do not expose this static-token,
SQLite development process to a network.

## Production-like deployment requirements

Run `decision-assurance-mcp` or `Dockerfile.mcp` beside API and Worker from the same immutable wheel.
Set `DA_CONFIG_PATH`, PostgreSQL application DSN secret, OIDC configuration and the MCP settings in
`.env.example`. Terminate TLS at a maintained edge and publish the externally reachable HTTPS base
URL as `DA_MCP_RESOURCE_SERVER_URL`; allow its exact Host and the required ChatGPT origin. Configure
the OIDC authorization server for the MCP resource and the actual external audience/resource.

The MCP process submits durable Research jobs. A healthy Worker must be running for provider work.
PostgreSQL forced RLS, network egress allowlists, external secret management, edge rate limiting,
monitoring, retention/deletion, backups and incident response remain mandatory. Compose binds MCP to
loopback and is a staging example, not a public production deployment. This repository change does
not deploy an endpoint.

## ChatGPT Work connection and skill installation

After deployment and separate owner approval:

1. Configure a ChatGPT Work MCP connection to `https://<approved-host>/mcp` and complete the tenant's
   OIDC/OAuth authorization flow. Do not paste provider keys into ChatGPT or the skill.
2. Confirm tool discovery returns exactly the five tools above. Test a read with a read-only role and
   confirm mutation is denied.
3. Create a personal skill from
   `integrations/chatgpt-work/conduct-assured-web-research/`. Preserve its directory structure and
   six files. The repository directory itself is only source and is not automatically installed.
4. Run one German Verified request against a DRAFT Decision File, poll with `research_get`, and call
   `research_handoff`. Confirm attached evidence remains `UNVERIFIED` and the Decision has no outcome.
5. Run one English Deep request with conflicting fake/test sources. Confirm conflicts remain visible
   and require human review. Verify a second tenant receives non-enumerating not-found behavior.

Stop and investigate if authentication metadata, role mapping, tenant isolation, Worker processing,
audit, limits, handoff status or secret scans differ from these expectations.
