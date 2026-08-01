# Controlled-pilot MFA

Keycloak declares enabled TOTP (HMAC-SHA-256) and WebAuthn registration actions. Operators assign the
required action/authentication flow to pilot users; recovery questions are not enabled. DA trusts
only `acr`, `amr` and `auth_time` from a fully validated OIDC token.

The BFF requires MFA for `SYSTEM_ADMINISTRATOR`, `TENANT_ADMIN`, `APPROVER` and `AUDITOR`. Accepted
contexts are policy-versioned and require `otp` or `webauthn`; authentication must be recent. Missing,
malformed, downgraded or stale evidence denies login. Changing policy version invalidates existing
critical-role sessions across BFF instances.

Recovery is an operator/IdP process requiring verified identity and audit. No default question,
shared recovery code or application-side bypass is provided.
