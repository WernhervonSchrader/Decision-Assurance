# Observability contract

Production telemetry is operational evidence, not a second business datastore. Every API request,
Research run and background job carries the same bounded correlation identifier. Logs contain only
allowlisted operational fields; request bodies, raw Intake text, extracted content, bearer tokens,
provider payloads and resolved secrets are prohibited and redacted defensively.

Metrics expose fixed names and bounded dimensions such as route, status class, outcome, provider and
reason category. Tenant, actor, decision, run, job, URL and arbitrary reason text are never metric
labels. Audit events remain the authoritative tenant-scoped history.

Liveness proves only that the process can respond. Readiness aggregates critical database and
configuration probes plus deployment-defined worker/schema checks. A critical `UNAVAILABLE`
component returns HTTP 503; optional provider degradation remains visible without claiming that the
assurance outcome itself changed.

Minimum alerts cover authentication failures, database unavailability, migration mismatch, stale
worker heartbeat, oldest queued-job age, dead letters, provider error rate, budget rejection and
audit-sequence anomalies.
