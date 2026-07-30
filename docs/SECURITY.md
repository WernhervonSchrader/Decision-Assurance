# Security Model

Authentication is an injected boundary; the reference static-token adapter is
for local evaluation only. Authorization is centralized and enforced before
object access. Repository lookup always includes tenant. Cross-tenant misses
return the same 404 as absent objects. Inputs use the Decision File JSON Schema
and strict Pydantic models; SQL is parameterized. Writes are idempotent and
transactional. Bodies and audit pagination are bounded.

Do not commit identity/token files. Store them outside the repository with
owner-only permissions. The API never logs tokens or request bodies itself.
The v0.5 production profile implements exact-issuer/audience OIDC verification, bounded JWKS caching,
RS256/ES256 allowlists, PostgreSQL forced RLS, external secret references, explicit egress policy,
redacted telemetry and separate application/worker/migration roles. TLS termination, edge rate
limits, managed identity operation, monitoring and encrypted storage remain deployment duties.
See [Threat Model](THREAT_MODEL.md).

Data is minimized to Decision, Intake, Research, job, audit and idempotency records. The pilot sets a
30-day retention ceiling, but automated export/deletion and legal hold are not implemented. Deployers
must supply and test those controls before storing real personal or regulated data.

Web Research treats search and scraped material as untrusted and applies HTTPS/public-address,
credential, redirect, domain, MIME, size, active-content, secret-redaction and prompt-injection
controls before conservative handoff. Provider credentials and raw responses are not persisted as
Research errors or returned by the API. See [Web Research Security](web-research/security.md).

The MCP resource server authenticates before every tool call, derives tenant only from verified
identity claims, applies central RBAC and enables inbound Host/Origin validation against DNS
rebinding. Tool schemas contain no tenant or provider-key field. Outputs omit page bodies and
assurance outcomes; internal failures return generic localized errors with correlation IDs. MCP does
not weaken provider SSRF, redirect, DNS, scheme, port, body, timeout, rate, budget or retry controls.

