# Decision Assurance Test Suite (DATS)

This directory is the canonical, reusable Gold Dataset for deterministic Decision Assurance
regression testing. It is project-owned synthetic evidence, not an independent product assessment.

## Stable access

- Dataset release: `v0.1.0/catalog.json`
- Case contract: `schemas/dats-case.schema.json`
- Catalog contract: `schemas/dats-catalog.schema.json`
- Runner: `decision-assurance benchmark benchmarks/dats/v0.1.0/catalog.json`
- External source record: `sources/owasp-state-agentic-ai-security-governance-2.01.json`

Each case contains the task, deterministic input, normalized expected result, explicit failure
signals and provenance in one file. Consumers must pin `dataset_version`; a changed expected result
requires a new dataset version rather than an in-place rewrite of an accepted release.

The normalized gate vocabulary is `PASS`, `FAIL`, and `REQUIRES_HUMAN_REVIEW`. The legacy engine
outcomes `PASS`, `BLOCK`, and `REVIEW` remain present for traceability. Reason codes are locale-neutral;
v0.1.0 contains English task text and no personal, customer or tenant data.

The OWASP report is registered as an authoritative external context source, not copied into the
repository. Its mapping to DATS is a Decision Assurance project interpretation; neither the dataset
nor its results imply OWASP endorsement or certification.
