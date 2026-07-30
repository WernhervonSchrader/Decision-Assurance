# ADR-003: Modular web-research boundary

**Status:** Accepted — 2026-07-29

## Context

Decision Assurance v0.3 has secure transport, tenant-aware persistence and a
separate controlled Intake domain, but no external source discovery or content
retrieval. Putting network providers into the deterministic engine would make
availability, web content and cost part of the governance trust boundary.

Three alternatives were considered:

1. Direct provider calls from the engine are initially small, but couple
   untrusted network behavior to assurance outcomes and are difficult to fake.
2. A modular domain in the same distribution creates explicit contracts,
   lifecycle and storage without distributed transactions.
3. A separate service provides physical isolation, but prematurely adds
   service authentication, deployment, queues and cross-service consistency.

## Decision

Implement web research as a separate, provider-neutral domain module in the
Decision Assurance distribution. Brave Search is only a source-discovery
adapter. Firecrawl is only a selected-content extraction adapter. Provider
responses and web content remain untrusted until the research normalizer and
evidence policy have assessed provenance, freshness, safety and usability.

Research owns its contracts, lifecycle, audit trail, idempotency records,
budgets, snapshots and tenant-keyed tables. The tables share the existing
database; a second service or physical database is deferred. External evidence
is handed to an existing tenant-matching DRAFT Decision File through a narrow,
idempotent compiler/handoff port. It is initially `UNVERIFIED`, `OUTDATED` or
`CONFLICTING`; research never creates `PASS`, `REVIEW`, `BLOCK` or `APPROVED`.
Only the existing Decision Assurance Engine creates an assurance outcome.

Trust boundaries exist at authenticated HTTP input, tenant resolution, each
provider call, URL validation, content normalization, evidence assessment and
Decision File handoff. Provider configuration is injected. Secrets are never
part of domain contracts, audit payloads, semantic fingerprints or errors.

The lifecycle is `CREATED → SEARCHING → SOURCES_DISCOVERED → EXTRACTING →
EVIDENCE_COMPILED → COMPLETED`, with controlled partial, failed and cancelled
states. Every transition is actor-, tenant-, time- and reason-bound and appears
once in the hash-linked Research audit trail.

The semantic idempotency fingerprint includes tenant, target Decision File and
version hash, claim references, normalized query/languages/domains/freshness,
limits and non-secret policy/provider configuration versions. Snapshots and
content hashes are reusable only inside the same tenant and TTL. Retry skips
successful work and reserves bounded provider budget before a new call.

All target URLs are external data. Only public HTTPS URLs without credentials
may be extracted. Private, loopback, link-local, reserved and metadata
addresses fail closed. Prompt-like instructions are recorded as content risk
and cannot trigger a tool, change a policy or become verified evidence.

## Consequences

The provider adapters can be replaced and tested without network access. Web
failures cannot alter governance rules. Rich research provenance remains in
the research domain because the current Decision File contract intentionally
contains only compact evidence references. The reference implementation runs
bounded work in-process; a queue or separate service is a later scaling option.
SQLite has no row-level security; production multi-tenancy still requires the
existing PostgreSQL/RLS deployment gate. Provider-side redirects, MIME
metadata, retention controls and generic semantic conflict detection remain
bounded provider capabilities and are treated conservatively when absent.

The ports and domain can later move to a separate service without changing the
Decision Engine or provider-neutral contracts. Such a move is justified only
by independent deployment, regulatory isolation or material scaling needs.
