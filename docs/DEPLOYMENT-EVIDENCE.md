# Deployment evidence format and acceptance

`deployment-evidence.schema.json` describes a concrete controlled-pilot deployment: exact commit,
immutable image digests, SBOM/configuration hashes, tenant, evidence timestamps/source/digests,
provider residency state and open risks. Required evidence covers TLS/host/edge/OIDC, MFA, database,
recovery, monitoring/alert test, multi-instance sessions, signed export, lifecycle/legal hold and an
independent technical review.

Self-declaration cannot satisfy the technical gate. Provider residency may be `VERIFIED`, or provider
access must be explicitly `ACCESS_BLOCKED`; an unverified enabled provider is invalid. Every item is
bound to the exact deployment, tenant and commit. The gate resolves every digest to the immutable
artifact, recomputes SHA-256 and checks an exact typed binding for kind, deployment, tenant, commit,
verification result, observation time and source. Replay, relabeling, staleness, missing artifacts,
bad digests and secret-shaped fields block validation. Each of the 13 evidence kinds additionally
has an exact v1 payload contract: for example certificate lifetime/chain/TLS version, public DNS
addresses, recovery commit/report/RPO/RTO, forced-RLS count, monitoring scrape and alert receipt,
multi-instance revocation, offline export signature verification and independent-review result.
Metadata-only `verified=true` envelopes fail closed. Controlled-pilot deployments resolve immutable
content-addressed JSON from a protected file store; production stores implement the same digest port.

Software can produce only `INCOMPLETE`, `BLOCKED` or `PILOT_REVIEW_REQUIRED`. Only a validated
OIDC-backed `HUMAN` identity with the server-side `REVIEWER` role, matching tenant and different from
the creator, may record `PILOT_ACCEPTED`; a bundle cannot serialize itself as accepted. This does not
imply production or regulatory approval. Acceptance emits a versioned
`deployment.pilot-accepted` event through a mandatory persistence port before returning success. The
PostgreSQL adapter stores it in a forced-RLS, tenant-scoped, append-only ledger.
