# Export signing key rotation runbook

1. Provision a new Ed25519 key outside the repository and image.
2. Register its public key, unique key ID, `not_before` and `not_after` in the verifier trust store.
3. Keep the old public key while any retained archive may require verification.
4. Change only the signing reference/key ID, then create and offline-verify a tenant-bound canary.
5. Retire the prior private key after overlap without marking its public verification key revoked;
   normal expiry stops new signing but retained archives remain verifiable at their signed time.
   Use revocation only for compromise or invalid trust and record its actor/time in deployment evidence.
6. On suspected compromise, stop exports, revoke/rotate, scan artifacts and review affected exports.

Never log key material or pass it as a command-line argument. Production adapters return only a
signature and metadata; private bytes remain non-exportable.
