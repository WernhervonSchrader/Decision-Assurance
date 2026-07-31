# Web Research

Web Research is an optional, provider-neutral domain module inside the Decision Assurance
distribution. It discovers and extracts external material, preserves provenance, assesses
whether a candidate is safe enough to attach, and hands eligible records to a tenant-matching
`DRAFT` Decision File as `UNVERIFIED`, `OUTDATED`, or `CONFLICTING` evidence.

It never emits `PASS`, `REVIEW`, `BLOCK`, `APPROVED`, or `VERIFIED`. The existing Decision
Assurance Engine remains the only component that evaluates the resulting Decision File.

```text
authenticated request → OpenAI Web Search → source evaluation → selected source → URL safety
→ optional Firecrawl fetch → normalization → evidence policy → tenant-scoped repository → conservative handoff
→ existing engine (only when separately invoked)
```

See [architecture](architecture.md), [security](security.md),
[provider configuration](provider-configuration.md), [evidence contract](evidence-contract.md),
and [testing](testing.md).

The production foundation additionally provides a bounded MCP adapter in the same Python distribution. It reuses this
domain and exposes only `research_start`, `research_get`, `research_retry`, `research_cancel` and
`research_handoff`; it is not a second Research implementation. See
[MCP Web Research](../MCP-WEB-RESEARCH.md).
