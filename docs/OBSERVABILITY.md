# Observability contract

Reference rules live in `deploy/observability/decision-assurance-alerts.yml`; a deterministic local
evaluator proves firing. A real pilot must connect actual Prometheus-compatible collection and a
notification receiver, trigger a canary alert and record receipt as deployment evidence.
Rule expressions use the exact names accepted and rendered by the bounded metrics backend; the local
test passes a real counter/gauge through Prometheus rendering before evaluating the alert.
Controlled-pilot runtimes publish every operational gauge from their first scrape with a fail-closed
zero baseline. The BFF refreshes the shared-session gauge from a real PostgreSQL probe and updates
Keycloak availability around the token exchange; MFA policy denials increment their dedicated
counter. Tenant conflicts, audit-persistence failures, export-signing failures and legal-hold delete
attempts are incremented at their fail-closed runtime boundaries. Client-side OIDC rejection no
longer marks Keycloak unavailable; only network/timeouts and provider 5xx do. Backup, restore and TLS
remain unhealthy until the operational evidence collector supplies a measured, integrity-valid
recovery report and verified certificate lifetime. Critical availability rules use `absent(...)`, so a missing exporter or
missing series fires instead of silently evaluating to healthy.

The controlled-pilot BFF reads those signed-off measurements from protected, read-only files named
by `DA_PILOT_TLS_EVIDENCE_PATH` and `DA_PILOT_RECOVERY_EVIDENCE_PATH`. The Compose profile mounts
them as `pilot-tls-evidence` and `pilot-recovery-evidence` secrets. Missing, oversized, malformed,
expired or failed evidence keeps `/health/ready` at HTTP 503. Example files are placeholders only and
must never be interpreted as pilot acceptance evidence. The API measures the global Research backlog
from its PostgreSQL worker connection at scrape time; authentication, deletion and assurance-outcome
series are emitted at their authoritative runtime boundaries.

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

Pilot dashboards use only bounded labels (`route`, `status`, `outcome`, `provider`, `reason`,
`retryable`). Track login rejection ratio, API 4xx/5xx and latency, oldest queued job/job outcomes,
provider failure ratio, assurance outcome distribution, approval result and lifecycle status. Never
label metrics with tenant, actor, URL, decision, claim or correlation ID. Correlation IDs belong in
redacted logs/audit. Alert examples: auth rejection >10%/5m, any tenant-conflict or audit anomaly,
oldest queue >5m, provider 5xx >20%/10m, and BLOCK-rate deviation >3x the reviewed baseline.
