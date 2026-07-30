# Provider Configuration

Copy `.env.example` into a protected runtime configuration mechanism; never commit real keys.
`BRAVE_SEARCH_API_KEY` enables discovery and `FIRECRAWL_API_KEY` enables extraction. Missing keys
do not prevent startup: the provider returns `PROVIDER_NOT_CONFIGURED` and the run fails in a
controlled, retrievable state without a stack trace or credential value.

Base URLs must be credential-free HTTPS URLs. Timeouts are bounded. Firecrawl timeouts are not
blindly repeated because safe provider idempotency is unavailable. HTTP 408, selected 5xx and 429
are classified retryable; an authenticated retry creates a new, budgeted attempt. A bounded
`Retry-After` window rejects premature retries; v0.4 does not sleep inside the synchronous request.

`WEB_RESEARCH_PROVIDER_BUDGET` is an atomic per-run provider-call ceiling. Cache TTL and content
size are runtime-wide controls. The policy example illustrates dependency injection; the reference
runtime uses built-in Evidence Policy v1 defaults unless an embedding application injects another.
