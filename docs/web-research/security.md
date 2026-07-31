# Web Research Security

All discovered and extracted content is untrusted. URLs must be HTTPS, contain no credentials,
resolve only to public addresses, use port 443, and pass request allow/deny rules. This blocks
localhost, private/reserved/link-local ranges, cloud metadata addresses, unsafe IPv6 and
cross-domain canonical redirects. IDNA names are normalized before use.

OpenAI receives a bounded research query plus locale, freshness and domain filters through the
Responses API `web_search` tool. The request-time Egress Guard authorizes the exact OpenAI endpoint
before transport. Returned summaries, citations and consulted-source URLs remain untrusted search
artifacts; they are never executed as instructions and do not constitute fetched full text.

Firecrawl receives only the canonical URL and fixed safe scrape options: Markdown,
`onlyMainContent=true`, `skipTlsVerification=false`, no actions, target headers, browser, login,
code execution, search or crawl. MIME, status and byte limits fail closed. Active HTML is removed,
likely secrets are redacted, and prompt-injection phrases are marked. Such content cannot change
policy, call tools, verify itself, or create an assurance outcome.

If Firecrawl is unavailable or blocked, selected OpenAI sources remain `CITATION_ONLY`. The system
creates no snapshot, content hash, derived claim or Decision evidence from that citation alone.

Provider bodies and credentials are not stored in errors or returned by the API. Operators remain
responsible for legal retrieval authority, licensing, site terms, privacy and retention schedules.
Lexical prompt-injection and contradiction detection is conservative, not complete; it fails
toward human review but is not a substitute for content security review.

MCP clients cannot provide tenant IDs or provider configuration. Bearer authentication precedes
each tool call, central permissions precede object access, mutations require idempotency keys, and
server/mode limits always cap client requests. Tool output contains source/evidence metadata but not
extracted page bodies or secrets. No arbitrary URL, crawl, shell or filesystem tool is registered.
