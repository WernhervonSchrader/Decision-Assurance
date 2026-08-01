# Pilot export signatures

Signed v0.9 exports add `signature.json` to the existing deterministic archive. Ed25519 (`EdDSA`)
signs the exact canonical `manifest.json` bytes. The manifest binds tenant, decision, export ID,
software version, commit, event/export versions and every member SHA-256 digest. The private key is
never exported. Offline verification uses a separately trusted public-key registry:

```text
decision-assurance-validate-export export.zip --key-registry verification-keys.json --expected-tenant tenant-a
```

The verifier returns `SIGNED_VALID` or `LEGACY_UNSIGNED` and otherwise exits non-zero. Unknown
versions/algorithms/keys, missing signatures, unusable keys, tenant mismatch, archive/member changes
and broken audit chains fail closed. A v0.8 archive remains verifiable as legacy evidence but is never
upgraded in place or described as signed.

Signing configuration has exactly three provider-neutral modes: `development` references a local
`.secrets/` PEM; `controlled-pilot` references a protected absolute file/secret-store mount;
`production-adapter` references a KMS/HSM/vault identifier and requires an injected conforming
signer. No cloud SDK is a core dependency.

Normal public-key expiry is evaluated at the recorded signing time, so retained historical exports
remain verifiable. Compromise revocation is evaluated at verification time and remains fail-closed;
it is deliberately distinct from routine signing-key retirement.
