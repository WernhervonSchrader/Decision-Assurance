# Deployment evidence format and acceptance

`deployment-evidence.schema.json` describes a concrete controlled-pilot deployment: exact commit,
immutable image digests, SBOM/configuration hashes, tenant, evidence timestamps/source/digests,
provider residency state and open risks. Required evidence covers TLS/host/edge/OIDC, MFA, database,
recovery, monitoring/alert test, multi-instance sessions, signed export, lifecycle/legal hold and an
independent technical review.

Self-declaration cannot satisfy the technical gate. Provider access may be `VERIFIED` or deliberately
`BLOCKED`; an unverified enabled provider is invalid. Replay/staleness, bad digests, missing evidence
and secret-shaped fields block validation.

Software can produce only `INCOMPLETE`, `BLOCKED` or `PILOT_REVIEW_REQUIRED`. A separate authorized
human reviewer, different from the creator, may record `PILOT_ACCEPTED`. This does not imply
production or regulatory approval.
