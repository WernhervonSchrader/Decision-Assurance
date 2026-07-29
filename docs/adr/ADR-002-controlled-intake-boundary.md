# ADR-002: Separate controlled Intake domain boundary

**Status:** Accepted — 2026-07-29

## Decision

Implement Intake as a separate framework-independent domain module in the same
Python distribution, with its own contracts, lifecycle, audit and tenant-owned
storage. Connect it to v0.2 only through a compiler that emits the existing
Decision File Contract.

Intake uses separate tables and repository interfaces inside the same database;
physical database separation is deferred. Composite primary and foreign keys
contain `tenant_id`. Extractor and Policy Registry are ports. Only the compiler
may create a Decision File, only from `READY` plus verified/human-confirmed
facts, and only the existing engine may create governance outcomes.

> Intake interprets untrusted input. The compiler translates verified intake
> state into a Decision File. Only the Decision Assurance Engine evaluates that
> Decision File and produces an assurance outcome.

## Alternatives considered

Adding extraction fields directly to Decision Files is smaller but makes
untrusted candidates appear equivalent to governed evidence and mixes Intake
and Decision lifecycles. A separate network service offers stronger operational
isolation but adds distributed transactions and deployment scope with no current
test need. The chosen modular boundary preserves trust while remaining locally
reproducible.

## Consequences

There are two explicit lifecycles and audit streams. Transport adapters must
report both without conflation. SQLite remains a reference persistence adapter;
production claims still require OIDC, PostgreSQL/RLS and operational controls.
Optional future model extractors implement the same protocol and remain
untrusted candidate producers.
