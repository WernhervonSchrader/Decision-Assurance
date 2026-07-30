# MVP Architecture

The MVP separates contracts, deterministic governance and transport:

1. `ContractValidator` rejects malformed or unknown input.
2. `DecisionAssuranceEngine` creates findings and applies `BLOCK > REVIEW > PASS`.
3. `TransitionPolicy` authorizes lifecycle changes independently of outcome.
4. `CaseStore` writes the agent-independent filesystem representation.
5. CLI and benchmark runner are thin adapters over the same core.

## Canonical case directory

```text
cases/<decision_id>/
  decision.json
  evidence/<evidence_id>.*
  validation/validation-report.json
  review/review-request.json
  review/review-decision.json
  reports/assurance-report.json
  audit/events.jsonl
  lock.json
```

Names are deterministic and UTF-8 JSON is used throughout. `decision.json` is
written atomically through a temporary sibling file. `events.jsonl` is
append-only. A writer creates `lock.json` with actor, acquisition time and the
hash of the version it read; a second writer must stop while a non-expired lock
exists. Changes are accepted only if the recorded base hash still matches.
Conflicts are resolved by producing a new reviewed version, never by merging
audit logs. External evidence may be stored in `evidence/` or referenced by an
immutable URI and content hash.

Schema and artifact format versions are explicit. Unknown fields and newer
versions fail closed in v0.1.0. The structure contains no provider session IDs,
prompts or proprietary LLM state, so Codex, Claude, Cursor and conventional
software can operate on the same case.

The current `CaseStore` implements directory creation, atomic Decision File
writes and append-only audit writes. Lease expiry and compare-and-swap locking
are documented protocol requirements for the next storage-hardening increment.

# Controlled Intake v0.3 boundary

`Raw input → Extractor port → Candidate facts → Verifier + tenant Policy Registry port → Human
confirmation when required → Compiler → Decision File → existing Decision Assurance Engine`.

Intake and Decision domains use separate contracts, state machines, repository protocols and
tables. They deliberately share one database in v0.3. Every Intake primary and foreign key
contains the tenant. Only the compiler crosses the boundary into a Decision File; only the
existing engine produces assurance findings and outcomes.

# Web Research v0.4 boundary

Web Research owns provider-neutral contracts, lifecycle, ports, policies, audit and tenant-keyed
tables in the shared database. Brave discovers; Firecrawl extracts; the compiler alone translates
eligible candidates to Decision evidence. Only the existing engine evaluates that Decision File.
See [the detailed architecture](web-research/architecture.md) and ADR-003.

# Production Foundation v0.5

The production profile separates API and Worker processes over one PostgreSQL database. OIDC
establishes the tenant; repositories set transaction-local tenant context and PostgreSQL forces RLS.
The Worker has a queue-only cross-tenant role and uses a tenant-scoped application connection for
domain work. Migration credentials are unavailable to both runtimes.

Configuration contains secret references only. Provider calls occur only in the Worker and pass an
exact HTTPS egress policy. Logs contain allowlisted metadata, metrics use bounded labels, and
readiness checks material dependencies. See [Production Architecture](PRODUCTION-ARCHITECTURE.md).

Running jobs renew their lease independently of provider latency. Lease loss and logical
cancellation are propagated into the Research orchestrator and checked at each provider and
persistence boundary. The MCP production transport requeues the existing terminal job and does not
execute retry providers inline.

# Bounded MCP Web Research v0.5

ADR-005 adds `decision_assurance.mcp` as a separate Streamable-HTTP process in the same distribution.
The transport authenticates and delegates to one application service; the service reuses existing
Decision/Research repositories, RBAC, submission/orchestration, compiler and handoff ports. It owns
no provider logic and exposes exactly five bounded tools. See [MCP Web Research](MCP-WEB-RESEARCH.md).
