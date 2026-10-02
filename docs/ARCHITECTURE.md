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
tables in the shared database. OpenAI Web Search discovers; Firecrawl optionally extracts; the compiler alone translates
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

Operating Profiles v0.6 add one immutable deployment-mode and residency policy shared by every
tenant. Provider host/location declarations must exactly match the technical egress allowlist and
the effective runtime provider URLs before any privileged adapter is constructed. This prevents a
tenant request, environment override or stale allowlist from silently changing jurisdiction.

Running jobs renew their lease independently of provider latency. Lease loss and logical
cancellation are propagated into the Research orchestrator and checked at each provider and
persistence boundary. The MCP production transport requeues the existing terminal job and does not
execute retry providers inline.

# Bounded MCP Web Research v0.5

ADR-005 adds `decision_assurance.mcp` as a separate Streamable-HTTP process in the same distribution.
The transport authenticates and delegates to one application service; the service reuses existing
Decision/Research repositories, RBAC, submission/orchestration, compiler and handoff ports. It owns
no provider logic and exposes exactly five bounded tools. See [MCP Web Research](MCP-WEB-RESEARCH.md).

# Keycloak OIDC identity boundary

The existing authenticator port now accepts a Keycloak OIDC implementation; no parallel identity
architecture was introduced. Browser clients use Authorization Code with S256 PKCE. The API verifies
the signed token and creates an immutable identity/tenant context before centralized authorization,
repository access or Research provider dispatch. Keycloak roles are inputs to the application
permission matrix, never lifecycle approval. Keycloak uses its own PostgreSQL database and account.
See [Local Keycloak OIDC](KEYCLOAK.md).

# Proposed RIF Agent Runtime Harness boundary

**Design clarification, not an implemented RIF runtime.** See [ADR-008](adr/ADR-008-reasoning-routing-boundary.md),
[the routing contract](specifications/RIF-REASONING-ROUTING-v0.1.md) and
[the implementation plan](specifications/RIF-REASONING-ROUTING-v0.1-IMPLEMENTATION-PLAN.md).

RIF is the agent runtime harness. It governs how an agent executes, including context assembly,
instruction assembly, model and tool routing, runtime state, execution policies and advisory
reasoning gates such as JEV. Decision Assurance is not part of the harness. It is an
actor-independent validation and governance boundary that the harness invokes before a proposed
decision or action may create business effect.

RIF answers **How should the agent execute?** It owns runtime orchestration, context/instruction
assembly, model/tool routing, runtime state, permitted action corridors, execution policies,
reasoning selection, JEV, the Runtime Contract and the DA handoff. JEV belongs inside RIF and is
advisory or routing-relevant; optional TypeSafe Jev is a provider adapter. The agent/model generates
a Proposed Decision or Proposed Action. DA answers **May this proposed decision or action be
allowed to create business effect?** It independently validates evidence, rules, claims, limits,
trust, governance, human review, auditability and the traceable decision basis.

```text
Trigger -> Orchestrator -> RIF Runtime Harness
       -> JEV / Routing / Runtime Policy -> Agent Execution
       -> Proposed Decision or Action -> independent Decision Assurance
       -> PASS | REVIEW | BLOCK -> Execution / Human Review / Stop
```

Only DA produces the Governance Outcome. **`JEV CONTINUE != DA PASS`**; neither agent nor harness
can issue or substitute DA approval. The existing [Transition Policy](TRANSITION_POLICY.md) and
[Decision File Contract](DECISION_FILE_CONTRACT.md) still apply: DA `PASS` is not lifecycle
`APPROVED` and cannot replace required independent human approval, nonce or action binding.
The harness invokes DA before governance-required business effect, including effectful tools.
`REVIEW` waits for required review; `BLOCK` or unavailable valid DA validation stops the effect.

The runtime harness may determine how work is performed, but it must not determine whether a
governed business decision is valid. **`Generator != Validator != Governance`**: the agent
generates proposals, independent validators establish the decision basis, and DA's governance
rules and required human authority determine the outcome and approval.

| Control layer | Question | Responsibility |
| --- | --- | --- |
| **Runtime Containment** | What can the agent technically reach? | harness and technical environment: sandbox, tool permissions, network boundaries, identity, credentials, runtime policy, state, routing and allowed resources |
| **Decision Validation** | May the result create business effect? | independent DA: substantive admissibility, sufficient sources, rule compliance, complete evidence chain, acceptable risk and required human review |

DA is not a substitute for sandboxes or security controls. Runtime Containment is not a substitute
for Decision Assurance. Any applicable control in either layer can stop execution; passing one
cannot override the other. Existing explicitly defined fast paths for non-decision-relevant,
non-governed work remain valid, subject to runtime controls. Neither RIF nor JEV may reclassify a
governance-required action to remove the mandatory RIF/DA path; this clarification creates no new
fast path.

DA remains usable without RIF. Co-hosting a RIF reference package in this repository cannot change
actor independence or move DA inside the harness. No existing schema, lifecycle, governance gate
or execution authority changes with this clarification.
