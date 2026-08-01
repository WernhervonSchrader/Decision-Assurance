# Decision Assurance v0.9 — implementation plan

All production changes follow red/green tests. Commit boundaries are intentionally small. Expected
base: `26d5eae2348183a3f3bf95db0fa49b97359347e4`.

## 1. Contracts, schemas and operating modes

Add `provenance/config.py`, deployment/recovery schemas and packaged copies. Tests assert the exact
three signing modes, reference-only credentials, schema strictness, tenant fields, allowed states and
root/package equality. Verify with `pytest tests/deployment/contract tests/production -q`. Commit:
`feat(evidence): define provenance and deployment contracts`.

## 2. Signed export and offline CLI

Add `export/signing.py` and `export/versions.py`; extend service/validator and `decision-assurance`
CLI. Ports: `ExportSigner.sign(payload) -> SignatureEnvelope` and
`VerificationKeyResolver.resolve(key_id)`. Ed25519 file signer reads a protected reference only;
external callback never exposes key material; fake signer is deterministic. Tests first cover valid,
missing, altered, wrong/revoked/expired key, algorithm downgrade, unknown version, cross-tenant and
private-key canaries. Verify `pytest tests/pilot/export tests/deployment/export -q` plus CLI. Commit:
`feat(export): add signed v0.9 provenance`.

## 3. Event registry and explicit migration

Add `events/registry.py` with exact envelopes, parser registrations and lossless migration results.
Replace implicit stream-marker interpretation for v0.9 with registered stream identity while retaining
the v0.8 legacy verifier. Tests cover unknown type/version, data-loss detection, cross-stream links and
migration audit metadata. Commit: `feat(events): register versioned evidence streams`.

## 4. MFA policy and Keycloak contract

Add `oidc/mfa.py`; preserve validated claims through browser identity/session; extend realm required
actions and critical-role policy configuration. Tests cover `acr`/`amr`, manipulated values, missing
factor, expiry, downgrade and policy-version staleness. Keycloak E2E remains deterministic and never
uses productive recovery. Commit: `feat(identity): enforce pilot mfa evidence`.

## 5. PostgreSQL shared sessions and multi-instance proof

Add migration `004_deployment_evidence_v0_9.sql`, `pilot_ui/session_postgresql.py` and a session port.
Store HMAC session identifiers and encrypted token envelopes under forced RLS. Tests instantiate two
stores against one database: A creates, B reads, B logs out, A rejects; role-policy changes revoke;
wrong tenant cannot read. Stateless API and edge balancing remain existing boundaries. Commit:
`feat(session): add shared pilot session store`.

## 6. Recovery, monitoring and deployment bundle

Add recovery evidence model/CLI, low-cardinality alert rules, deployment evidence collector/validator
and acceptance state machine. Tests cover measured RPO/RTO, broken chains, certificate mismatch,
expired chain, self-declaration, alarm firing/failure, replay, digest tampering, missing evidence,
creator/reviewer identity and the impossibility of automatic acceptance. Commit:
`feat(deployment): add verifiable pilot evidence gate`.

## 7. CI and operations documentation

Extend CI with focused provenance/event/MFA/evidence tests, PostgreSQL multi-instance test, Prometheus
rule validation, recovery artifact and leak scan. Update required documentation and add signature,
event-version, key-rotation, MFA, monitoring and evidence-format guides. Repository, local integration,
deployment, organizational and production evidence stay distinct. Commit:
`docs(evidence): define reproducible pilot operations`.

## 8. Final verification and publication

Run Ruff format/check, Mypy strict, all non-live tests, PostgreSQL 16, Keycloak E2E, UI unit/build and
Playwright, Bandit, pip/npm audits, Python build, OpenAPI drift, Actionlint, Compose/Caddy validation,
Gitleaks, non-root image smoke, SBOM, Trivy and `git diff --check`. Run opt-in live TLS/KMS checks only
when explicit local references exist; report them as deployment evidence, not CI evidence.

Perform separate specification/security and code-quality reviews, remediate blockers, intentionally
commit only tracked PR scope, push the feature branch and open a Draft PR. Monitor CI and request an
independent review of the exact head. Do not mark Ready, merge or deploy.
