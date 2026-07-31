# Provider Configuration

Copy `.env.example` into a protected runtime configuration mechanism; never commit real keys.
`OPENAI_API_KEY` enables discovery and `FIRECRAWL_API_KEY` enables optional extraction. The names are secret
references, not permission to expose values as ordinary configuration. Local development should set
`DA_SECRET_DIRECTORY=.secrets` and create `.secrets/OPENAI_API_KEY` and
`.secrets/FIRECRAWL_API_KEY` from the committed `*.example` templates. `.secrets/*` is ignored except
templates, and Gitleaks rejects a force-added real provider-secret file. Missing keys
do not prevent startup: the provider returns `PROVIDER_NOT_CONFIGURED` and the run fails in a
controlled, retrievable state without a stack trace or credential value.

Real OpenAI and Firecrawl hosts are enabled locally only with
`config/deployment/provider-development.example.json`. Its
`development-provider-integration` mode and `external-unspecified` location are an explicit
development exception with unverified operator declarations. The request-time Egress Guard reloads
that profile for every call and records the decision before transport. Staging and production reject
this mode; it provides no residency evidence or production approval.

Base URLs must be credential-free HTTPS URLs. Timeouts are bounded. Provider calls are not
blindly repeated because safe provider idempotency is unavailable. HTTP 408, selected 5xx and 429
are classified retryable; an authenticated retry creates a new, budgeted attempt. A bounded
`Retry-After` window rejects premature retries; v0.4 does not sleep inside the synchronous request.

Provider telemetry contains only connector, status class/code, duration, correlation ID and a
bounded reason code. URLs, headers, bodies, result content and credentials are excluded. OpenAI and
Firecrawl fail closed independently when their own key is unavailable.

OpenAI discovery uses `POST /v1/responses` with the `web_search` tool and requests
`web_search_call.action.sources`. `OPENAI_WEB_SEARCH_MODEL` is configurable and defaults to
`gpt-5.6`. OpenAI summaries and URLs remain search/citation evidence; only a successful normalized
Firecrawl fetch may produce full-text evidence and a content hash.

`WEB_RESEARCH_PROVIDER_BUDGET` is an atomic per-run provider-call ceiling. Cache TTL and content
size are runtime-wide controls. The policy example illustrates dependency injection; the reference
runtime uses built-in Evidence Policy v1 defaults unless an embedding application injects another.
