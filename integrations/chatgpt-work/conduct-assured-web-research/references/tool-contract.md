# Tool contract

Use exactly these tools:

| Tool | Purpose | Mutation rule |
| --- | --- | --- |
| `research_start` | start tenant-scoped research for one Decision File/case and its claims | idempotency key required |
| `research_get` | read bounded status, sources, extraction states, conflicts, and evidence draft | read-only |
| `research_retry` | retry only eligible failed provider steps under original rules | idempotency key required |
| `research_cancel` | cancel an eligible run and preserve audit state | idempotency key required |
| `research_handoff` | invoke or confirm the existing conservative DRAFT-only handoff | idempotency key required |

Never send `tenant_id`, provider keys, credentials, outcomes, arbitrary provider configuration, or
general crawl instructions. Tenant comes only from authenticated identity. Use the returned
correlation, Research, job, and audit identifiers when reporting status or asking an operator to
investigate. Stable errors are fail-closed; do not infer success from an internal or provider error.
