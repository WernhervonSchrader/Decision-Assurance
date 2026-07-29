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
