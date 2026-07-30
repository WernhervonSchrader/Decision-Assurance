# Web Research v0.4

Web Research is an optional, provider-neutral domain module inside the Decision Assurance
distribution. It discovers and extracts external material, preserves provenance, assesses
whether a candidate is safe enough to attach, and hands eligible records to a tenant-matching
`DRAFT` Decision File as `UNVERIFIED`, `OUTDATED`, or `CONFLICTING` evidence.

It never emits `PASS`, `REVIEW`, `BLOCK`, `APPROVED`, or `VERIFIED`. The existing Decision
Assurance Engine remains the only component that evaluates the resulting Decision File.

```text
authenticated request → Brave discovery → source selection → URL safety → Firecrawl scrape
→ normalization → evidence policy → tenant-scoped repository → conservative handoff
→ existing engine (only when separately invoked)
```

See [architecture](architecture.md), [security](security.md),
[provider configuration](provider-configuration.md), [evidence contract](evidence-contract.md),
and [testing](testing.md).
