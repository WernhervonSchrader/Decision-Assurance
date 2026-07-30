# Production identity and authorization

Decision Assurance production profiles authenticate bearer tokens through a configured OIDC trust
relationship. The application trusts only an exact HTTPS issuer, one intended audience, an explicit
`RS256`/`ES256` allowlist, and the configured JWKS endpoint. Signature and registered claims are
validated before any tenant, actor, role, kind, organization or group value is mapped.

## Trust boundary

- `tenant_id` is created only from a successfully verified claim. Request bodies, headers other than
  the bearer token, URL parameters and stored documents cannot select a tenant.
- JWKS documents are fetched only from the configured HTTPS URI, have a bounded key count and cache
  lifetime, reject duplicate key identifiers and refresh once when an unknown `kid` appears.
- Unknown keys, issuer outages, malformed claims, invalid roles and all cryptographic failures expose
  only the generic authentication error to callers.
- Static token mappings remain a development/test adapter. Production configuration rejects them.

## Claim mapping

The default required claims are `sub`, `tenant_id`, `role` and `actor_kind`, in addition to `iss`,
`aud`, `iat`, `nbf` and `exp`. Organization and groups are optional, explicitly configured mappings.
Groups must be a bounded list of non-empty strings.

Supported roles are Generator, Validator, Approver, Auditor, Reviewer, Tenant Administrator and
System Administrator. Reviewer is read-only. System Administrator receives only cross-cutting report
and audit visibility through separately tenant-scoped operational access; it is not an implicit
tenant business administrator. Approval additionally requires `ActorKind.HUMAN`, regardless of role.

## Rotation and failure behavior

Publish the replacement signing key before issuing tokens with its `kid`. An unknown `kid` causes one
controlled refresh. Keep the prior public key available until the maximum token lifetime and allowed
clock skew have elapsed. During an issuer or JWKS outage, cached known keys remain usable only until
their bounded cache expiry; unknown or expired trust material fails closed.
