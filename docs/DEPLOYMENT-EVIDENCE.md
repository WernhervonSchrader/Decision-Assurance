# Deployment evidence format and acceptance

`deployment-evidence.schema.json` describes a concrete controlled-pilot deployment: exact commit,
immutable image digests, SBOM/configuration hashes, tenant, evidence timestamps/source/digests,
provider residency state and open risks. Required evidence covers TLS/host/edge/OIDC, MFA, database,
recovery, monitoring/alert test, multi-instance sessions, signed export, lifecycle/legal hold and an
independent technical review.

Self-declaration cannot satisfy the technical gate. Provider residency may be `VERIFIED`, or provider
access must be explicitly `ACCESS_BLOCKED`; an unverified enabled provider is invalid. Every item is
bound to the exact deployment, tenant and commit. Replay/staleness, bad digests, missing evidence and
secret-shaped fields block validation.

Software can produce only `INCOMPLETE`, `BLOCKED` or `PILOT_REVIEW_REQUIRED`. Only a validated
OIDC-backed `HUMAN` identity with the server-side `REVIEWER` role, matching tenant and different from
the creator, may record `PILOT_ACCEPTED`; a bundle cannot serialize itself as accepted. This does not
imply production or regulatory approval.
