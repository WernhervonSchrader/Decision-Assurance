# Decision Assurance v0.9 — Deployment Evidence and Cryptographic Pilot Provenance

Status: approved implementation specification for PR #8. This specification does not authorize a
deployment, production use, certification claim, or automatic pilot acceptance.

## A. Context assessment

The exact base is merge commit `26d5eae2348183a3f3bf95db0fa49b97359347e4`. PR #7 already
provides the controlled-pilot edge, browser BFF, portable v0.8 export, tenant-scoped lifecycle,
PostgreSQL forced RLS, Keycloak OIDC, recovery smoke and CI evidence. Its export proves internal
consistency but not origin. Browser sessions are process-local. Recovery output is structural rather
than a measured evidence record. MFA, deployment evidence and human pilot acceptance are not yet
machine-verifiable.

Constraints are: no deployment; no productive DNS, certificate, KMS or monitoring dependency; no
new provider or use case; no weakening of OIDC, tenancy, actor independence, egress, deletion or
legal hold; and no private material in repository, logs, images, browser storage or evidence.

Three operating modes are mandatory:

1. `development`: local key references and local test certificates, explicitly non-production.
2. `controlled-pilot`: protected file/secret-store references on the selected pilot host.
3. `production-adapter`: provider-neutral KMS/HSM/Key-Vault ports with no mandatory vendor SDK.

## B. Requirements matrix

| Requirement | Implementation location | Test/evidence |
| --- | --- | --- |
| Signed export and offline verification | `export/signing.py`, `export/service.py`, `export/validator.py`, CLI | valid/tampered/wrong-key/algorithm/key-state tests |
| Three key operating modes | `provenance/config.py`, existing secret references | strict parser and fail-closed startup tests |
| Export/event versioning | `export/versions.py`, `events/registry.py` | legacy/current/unknown/migration tests |
| Deployment/TLS evidence | `deployment/contracts.py`, JSON schemas | hostname, validity, chain and self-declaration tests |
| MFA identity evidence | `oidc/mfa.py`, Keycloak realm | role policy, `acr`/`amr`, downgrade and stale-session tests |
| Shared sessions | `pilot_ui/session_postgresql.py`, migration 004 | two-store create/get/revoke/role-version tests |
| Recovery RPO/RTO | `recovery/evidence.py`, restore script | schema, integrity and measured-report tests |
| Monitoring/alerts | `observability/alerts.py`, Prometheus rules | rule schema and synthetic firing test |
| Deployment bundle/gate | `deployment/evidence.py`, schemas | tamper, replay, actor independence and missing evidence tests |
| Multilingual support | stable machine codes; DE/EN documentation/UI messages | catalog parity and existing UI regression |
| Multi-tenancy | tenant in export, sessions and evidence; no client override | cross-tenant verification/session tests |
| Authentication | existing OIDC plus validated MFA context | invalid/expired/downgraded claim tests |
| Authorization | existing roles; human acceptance requires independent reviewer | role and creator/reviewer separation tests |
| Tenant isolation | forced RLS and tenant-bound identifiers/signatures | PostgreSQL and negative object-ID tests |
| Input validation | strict dataclasses/JSON schemas; unknown fields rejected | malformed, oversized and unknown-version tests |
| Audit logging | versioned event envelope and migration audit | chain/version/tamper tests |
| Data protection | references only; no private key/token/payload in evidence | canary and recursive sensitive-key scan |
| E2E testing | two BFF stores/instances, shared PostgreSQL and existing browser journey | deterministic multi-instance test in CI |
| CI security checks | existing gates plus provenance, MFA, recovery and alert jobs | GitHub Actions results bound to exact head |

## C. Proposed architecture

### Cryptographic boundary

The selected format is a detached Ed25519 signature over RFC-8785-compatible canonical JSON as
already constrained by the repository serializer (UTF-8, sorted keys, no insignificant whitespace).
The signature member contains format version, algorithm `EdDSA`, key identifier, signing timestamp
and base64url signature. Ed25519 is supplied by the maintained `cryptography` dependency; no custom
primitive is implemented. The manifest contains every business identifier and member digest, so the
signature binds tenant, decision, export, software, schemas and content.

`ExportSigner` and `VerificationKeyResolver` are dependency-inverted ports. Implementations are a
fake signer for deterministic tests, a protected file-reference signer for development/controlled
pilot, and a provider-neutral external signer callback for KMS/HSM/Key Vault integration. Private
bytes never cross an API or enter evidence. Verification keys carry lifecycle state and validity.

Legacy v0.8 archives remain internally verifiable and return `LEGACY_UNSIGNED`; they are never
reported as signed. v0.9 is fail-closed for absent/unknown signature, algorithm, key, version or
member mutation. Original archives are immutable; migration emits a separate artifact and audit
record.

### Identity and session boundary

MFA assurance is derived only from validated ID/access-token `acr`, `amr`, authentication time and
policy version. Critical external roles require an allowlisted assurance context containing a real
second factor (`otp`, `webauthn` or configured equivalent). Client fields cannot assert MFA.
Keycloak enables TOTP and WebAuthn required actions without insecure recovery questions.

The BFF session port gains a PostgreSQL implementation. Session identifiers are stored only as an
HMAC digest; access tokens are encrypted by a deployment-supplied envelope protector before
persistence. A session records tenant, actor, roles, MFA context and role-policy version. Logout,
role-policy changes and expiry revoke across instances. In-memory storage remains development-only.

### Deployment and recovery evidence boundary

Evidence is immutable JSON validated against packaged schemas. TLS evidence distinguishes measured
certificate/chain/hostname data from self-declaration. Live collection is opt-in. Recovery evidence
records targets and observations separately, environment, data volume, timestamps, commit, backup
point, restore point, chain/export checks and measured duration. It never turns a local observation
into a service promise.

The deployment bundle references immutable image digests, SBOM/config hashes and typed evidence.
Its technical gate returns only `INCOMPLETE`, `BLOCKED`, or `PILOT_REVIEW_REQUIRED`. Human
`PILOT_ACCEPTED` requires an authorized reviewer different from the creator and is a separate,
audited transition. Software cannot manufacture organizational acceptance.

### Data, tenant, localization and audit flow

OIDC establishes tenant/actor/MFA → BFF resolves shared session → API/RLS enforce tenant → export
snapshot is created → manifest and member hashes are signed → offline verifier resolves a public
key → deployment evidence references the verified export and environment measurements → technical
gate decides whether human review may begin. Machine evidence uses stable English codes; localized
display remains separate and German/English catalogs retain parity.

## D. Threat model

| Threat | Likelihood / impact | Prevention | Detection/response | Residual risk |
| --- | --- | --- | --- | --- |
| Manifest/member substitution | medium/critical | signature binds canonical manifest and all hashes | offline failure/alert/block gate | signing-host compromise |
| Wrong/revoked key or downgrade | medium/critical | key-id registry, validity/state, exact `EdDSA` allowlist | stable failure code and signature alert | external revocation freshness |
| Private-key leakage | low/critical | reference-only configuration, non-exportable port, redaction/canaries | secret scan; revoke/rotate key | compromised signer runtime |
| Legacy falsely reported signed | medium/high | explicit `LEGACY_UNSIGNED` result | compatibility tests | organizational mislabeling |
| Event-schema confusion | medium/high | exact version registry and explicit migration | unknown-version alert/block | future migration defects |
| Forged/self-declared TLS evidence | medium/high | evidence source and verification state are mandatory | gate rejects unverified data | real CA/host proof is deployment-specific |
| MFA claim manipulation/downgrade | medium/critical | validated-token claims only; role policy/version binding | denial metric; revoke sessions | compromised IdP |
| Cross-instance session theft/staleness | medium/critical | hashed IDs, encrypted token, shared revocation, expiry | session-store alerts/logout | envelope-key compromise |
| Cross-tenant evidence reuse | medium/critical | tenant/decision/commit binding and RLS | mismatch block/audit | privileged DB operator |
| Recovery evidence fabrication | medium/high | measured fields, hashes, exact commit and independent review | bundle/gate validation | operator can falsify external inputs |
| Replay old deployment bundle | medium/high | deployment ID, created-at, commit/digest freshness policy | replay/freshness block | clock authority remains trusted |
| Automatic organizational approval | low/critical | state machine forbids software acceptance | audit and actor-independence tests | malicious authorized reviewer |
| Metric cardinality/data leak | medium/high | fixed low-cardinality labels | schema tests and alert | permitted operational metadata |
| Supply-chain compromise | low/critical | pinned deps/actions, SBOM/digests/scans | CI block/rebuild | upstream trust |

Residual risk is explicitly carried into the bundle. When speed conflicts with provenance, tenant
isolation or traceability, the system blocks.

## E. Specification review

The review resolved these ambiguities:

- “real evidence” means reproducible collectors and schemas in this PR; no public endpoint is
  contacted by normal CI and no deployment is authorized.
- JWS interoperability is achieved by an explicit detached-signature envelope using the standard
  EdDSA algorithm; no remote JWT semantics or online service is required.
- A production adapter is an interface and conformance suite, not a chosen Azure/AWS/GCP SDK.
- MFA support is policy enforcement over validated IdP evidence, not a DA-generated claim.
- Multi-instance proof covers shared BFF state and stateless API behavior; it does not claim global
  high availability.
- RPO/RTO observations are measurements, never promises.

## F. Acceptance criteria

1. Work remains on `feature/deployment-evidence-v0.9` based on exact commit `26d5eae…`; `main` is
   unchanged and nothing is deployed.
2. New v0.9 exports are asymmetrically signed; all listed tampering and key failures block offline.
3. Legacy v0.8 archives are identified as internally consistent but unsigned.
4. Event parsing accepts only registered versions and lossless explicit migrations.
5. Critical roles require validated MFA evidence; stale/downgraded sessions fail.
6. Two BFF instances share and revoke a PostgreSQL session without local-state dependence.
7. Recovery, TLS, monitoring and deployment bundles are strict, tenant-bound and machine-readable.
8. Technical gating never returns `PILOT_ACCEPTED`; human acceptance enforces actor independence.
9. No secret/private key/token is committed, logged, exported or embedded in images.
10. Existing and new tests, typing, lint, dependency/secret/container checks and CI pass.
11. A Draft PR and independent review conclude the work; it is not made Ready, merged or deployed.
