# Research Evidence Contract

A source candidate preserves canonical URL, rank, search provider/version and publication metadata.
A snapshot adds retrieval time, expiry, MIME, language, normalized text, content hash, extractor
provider/version and risk signals. An evidence candidate links tenant, run, Decision File, claims,
source and snapshot and records deterministic freshness, authority, relevance and conflict fields.

`usable_for_decision=true` means only that the compiler may attach the candidate. It is not a
truth, verification or approval signal. Handoff checks tenant, `DRAFT` state, claim references and
compare-and-swap document hash in one transaction. Records attach as `UNVERIFIED`, or conservatively
as `OUTDATED`/`CONFLICTING`. Only the existing engine can later produce governance findings and an
assurance outcome.

Public schemas are under `schemas/research/`; byte-identical packaged copies ship under
`decision_assurance/schemas/research/`. Decision File schema version remains `0.1.0`.
