# DA Public Draft v0.4 — Controlled Web Research

**Status:** implementation specification approved by project owner

## Architecture rule

> Brave discovers candidate sources. Firecrawl extracts selected content.
> Research assesses untrusted evidence and hands conservative evidence
> references to a DRAFT Decision File. Only the Decision Assurance Engine
> evaluates that Decision File and produces an assurance outcome.

The flow is:

`request → discovery → safe source selection → extraction → normalization → evidence policy → DRAFT Decision File handoff → existing engine`.

## Boundaries

- Tenant and actor come only from authenticated identity.
- Domain contracts contain no Brave or Firecrawl SDK types.
- Search snippets are discovery metadata, never evidence.
- Web content cannot change prompts, policies, roles, tools or outcomes.
- Only public HTTPS URLs without credentials are extractable.
- All primary, foreign and unique keys are tenant scoped.
- Identical semantic requests, content and audit operations are idempotent.
- Provider errors are bounded, classified and safe to expose by code only.
- No live provider call is permitted in the standard test suite.

## Lifecycle

`CREATED → SEARCHING → SOURCES_DISCOVERED → EXTRACTING → EVIDENCE_COMPILED → COMPLETED`

`PARTIALLY_COMPLETED`, `FAILED` and `CANCELLED` represent controlled completion
or interruption. Only explicit retry may resume failed or partial work;
`COMPLETED` and `CANCELLED` are terminal.

## Evidence handoff

The request identifies an existing Decision File and explicit claim references.
The handoff requires the same tenant, DRAFT status and an unchanged document
hash. Clean external content remains `UNVERIFIED`; stale and conflicting
content retain those statuses. Missing provenance, unsafe URLs, prompt
injection and unsupported content prevent handoff.

The full provenance record remains in tenant-owned Research storage. The
Decision File receives only a stable research reference, retrieval timestamp,
content hash, claim references and conservative status. Compare-and-swap and
deterministic evidence IDs make interrupted handoffs convergent on retry.

## Idempotency, retry and cost

HTTP replay is scoped by tenant, actor, operation and key. Independently, a
semantic request fingerprint deduplicates equivalent work across actors of the
same tenant. Canonical URL and content hashes deduplicate sources and evidence.
Successful provider attempts and snapshots are reused; retry only schedules
unfinished or failed steps. Each new provider attempt atomically reserves a
tenant/run budget unit. Automatic retry is bounded and only used where the
provider error is classified retryable. Force refresh requires tenant-admin
authority and a new refresh generation.

## Tenant and persistence model

Research runs, attempts, sources, snapshots, evidence, audit, idempotency,
handoffs and budgets use composite keys containing `tenant_id`. They use their
own repository port and tables in the existing database. Cross-tenant reads
look absent, and cross-tenant relationships are rejected by foreign keys.

## Known constraints

- The reference API performs bounded work in-process and introduces no queue.
- SQLite is not a production RLS boundary.
- Generic natural-language contradiction detection is conservative; an
  unchecked conflict state never means that sources agree.
- Provider metadata such as final MIME type or redirect chain may be absent and
  therefore fails toward unusable/review rather than assumed-safe.
- Crawling rights, licenses, robots policies, retention and provider contracts
  remain deployment and tenant responsibilities.

## Security defaults

The reference implementation uses HTTPS provider endpoints, bounded timeouts,
content and result limits, public-IP validation, canonical URL normalization,
MIME allowlists, sanitization, secret redaction and provider budgets. Firecrawl
is called only for single-page markdown extraction, with TLS verification
enabled and without browser actions, custom target headers or autonomous crawl.
