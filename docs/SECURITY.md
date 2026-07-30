# Security Model

Authentication is an injected boundary; the reference static-token adapter is
for local evaluation only. Authorization is centralized and enforced before
object access. Repository lookup always includes tenant. Cross-tenant misses
return the same 404 as absent objects. Inputs use the Decision File JSON Schema
and strict Pydantic models; SQL is parameterized. Writes are idempotent and
transactional. Bodies and audit pagination are bounded.

Do not commit identity/token files. Store them outside the repository with
owner-only permissions. The API never logs tokens or request bodies itself.
TLS, rate limiting, trusted proxy configuration, OIDC verification, PostgreSQL
RLS and centralized security monitoring are deployment responsibilities and
prerequisites for production claims. See [Threat Model](THREAT_MODEL.md).

Data is minimized to Decision Files, reports, audit events and idempotency
responses. v0.2 has no automated retention/deletion workflow. A tenant export,
retention and deletion policy must be approved before real personal or
regulated data is stored.

Web Research treats search and scraped material as untrusted and applies HTTPS/public-address,
credential, redirect, domain, MIME, size, active-content, secret-redaction and prompt-injection
controls before conservative handoff. Provider credentials and raw responses are not persisted as
Research errors or returned by the API. See [Web Research Security](web-research/security.md).

