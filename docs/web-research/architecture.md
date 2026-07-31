# Web Research Architecture

The module follows ADR-003 Variant B: its own contracts, lifecycle, ports, repository boundary,
tables, audit chain and policy code within the existing Python distribution, FastAPI process and
SQLite database. This preserves a hard modular trust boundary without claiming physical service
or database isolation.

OpenAI Responses Web Search implements only `SearchProviderPort`; Firecrawl implements only
`ContentExtractorPort`.
No provider SDK types cross those ports. Fakes run the complete pipeline in tests. The lifecycle
is `CREATED → SEARCHING → SOURCES_DISCOVERED → EXTRACTING → EVIDENCE_COMPILED → COMPLETED`,
with `PARTIALLY_COMPLETED`, `FAILED`, and `CANCELLED`. Only authorized retry may leave failed or
partial states, and it selects only failed sources.

Semantic idempotency includes tenant, Decision File version, normalized query, claims, language,
domain and freshness rules, limits, policy version and provider-configuration version. Successful
handoff advances the stored comparison hash so an exact replay still converges to the original
run. `force_refresh` additionally requires an administrator-authorized refresh generation.

There is no queue or worker in v0.4. Provider calls execute inside the API request. The ports and
tenant-owned tables permit later extraction to a separately deployed service.

The v0.5 production profile now supplies a PostgreSQL-backed Worker. ADR-005 adds an MCP process in
the same distribution; it maps five tool contracts to existing application/domain services and does
not call OpenAI or Firecrawl directly. Production `research_start` submits a durable job. The MCP
transport and personal skill contain no Research business rules.

Artifacts remain distinct: `SEARCH_RESULT -> SELECTED_SOURCE -> FETCHED_CONTENT -> DERIVED_CLAIM`.
If optional Firecrawl extraction is unavailable, the run may retain a `CITATION_ONLY` selected
source, but it creates no snapshot, content hash, derived claim or Decision evidence handoff.
