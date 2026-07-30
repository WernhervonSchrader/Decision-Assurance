# Evidence contract

An evidence bundle is a conservative draft, not a truth or assurance decision.

For each material claim record:

- the specific source and provenance identifiers;
- publication/effective and retrieval timing when available;
- what the source states as fact;
- any analyst inference, clearly separated;
- freshness, usability, conflict, prompt-injection, and human-review indicators;
- unknown, missing, stale, or unconfirmed information.

Do not resolve conflicting sources by assertion. When evidence is contradictory or insufficient,
stop and state that human review is required. Handoff may attach only the statuses produced by the
Decision Assurance compiler: `UNVERIFIED`, `OUTDATED`, or `CONFLICTING`. Only the existing Engine can
evaluate the Decision File and produce governance findings or an assurance outcome.
