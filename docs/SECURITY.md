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

Operating Profiles v0.6 treat deployment mode, residency and provider egress as one privileged
configuration boundary. `local` accepts only `local` core and provider processing; `eu-managed`
accepts only EU country codes. Every provider entry has a structured attestation; HTTPS references
alone are not proof, and `OPERATOR_SELF_DECLARATION` never authorizes restrictive production egress.
Startup validation is separate from a central request-time guard that runs immediately before every
OpenAI/Firecrawl network call, re-reads policy and tenant scope, and persists an allow/block event.
Profile and provider fields never appear in tenant request schemas, so a tenant cannot select a weaker
region or shared credential path.

Configuration proves consistency of declared intent, not physical residency. Deployment owners must
verify contracts, DPA/subprocessors, DNS/endpoint ownership, control-plane and support access,
encryption, backup locations and provider retention. Configuration or evidence drift blocks rollout;
suspected runtime drift disables provider egress and triggers the incident procedure in
[Operations](OPERATIONS.md).

Data is minimized to Decision, Intake, Research, job, audit and idempotency records. The pilot sets a
30-day retention ceiling, but automated export/deletion and legal hold are not implemented. Deployers
must supply and test those controls before storing real personal or regulated data.

For both operating profiles, exports and deletion require tenant-scoped authorization, two-person
approval, audit evidence and verification that no second tenant is included. Because the current
application does not implement a general export/deletion workflow, deployments with an immediate
automated erasure, legal-hold or portability obligation remain blocked until the documented
operational control is implemented and tested. Backup expiry must follow the same profile boundary;
restores may not silently resurrect data past its deletion deadline.

Web Research treats search and scraped material as untrusted and applies HTTPS/public-address,
credential, redirect, domain, MIME, size, active-content, secret-redaction and prompt-injection
controls before conservative handoff. Provider credentials and raw responses are not persisted as
Research errors or returned by the API. See [Web Research Security](web-research/security.md).

Direct OpenAI and Firecrawl development calls require the explicit
`development-provider-integration` profile. Its `external-unspecified` declaration is deliberately
unverified and is rejected by staging/production configuration. Both credentials resolve through
the secret-provider boundary; local files under `.secrets/` are ignored and a dedicated Gitleaks
rule rejects force-added provider-key files. Every provider transport is preceded by a persisted
request-time egress decision, and provider telemetry excludes URLs, bodies, headers and keys.

The MCP resource server authenticates before every tool call, derives tenant only from verified
identity claims, applies central RBAC and enables inbound Host/Origin validation against DNS
rebinding. Tool schemas contain no tenant or provider-key field. Outputs omit page bodies and
assurance outcomes; internal failures return generic localized errors with correlation IDs. MCP does
not weaken provider SSRF, redirect, DNS, scheme, port, body, timeout, rate, budget or retry controls.

