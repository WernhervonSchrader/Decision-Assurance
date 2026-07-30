# ADR-006: Fail-closed local and EU-managed operating profiles

**Status:** Accepted — 2026-07-30

## Context

Decision Assurance v0.5 has one production runtime with PostgreSQL RLS, OIDC, external secrets and
bounded HTTPS provider egress. It did not encode who operates infrastructure, where data is stored or
processed, or whether the runtime provider hosts agree with those declarations. A label such as
“local” or “EU” without machine-checked contradictions would create misleading security and data
protection claims. Operating mode must remain deployment authority and must not become tenant input.

## Alternatives

### A. Documentation-only profiles

Operators document local or EU placement without runtime validation. This is inexpensive but allows
missing locations, undeclared providers and environment overrides to drift silently.

### B. Infer provider region from DNS names or top-level domains

The runtime derives country from host naming. This looks automated but DNS names do not prove
processing, support or control-plane location and would create false assurance.

### C. Typed profile, residency and explicit provider-egress declarations

Operators declare all core locations plus each provider host and processing location. The runtime
requires exact equality with the HTTPS allowlist and effective provider URLs before privileged
adapter construction. External evidence remains necessary because declarations cannot prove physical
processing.

## Decision

Choose C. Production and staging select exactly one immutable `local` or `eu-managed` profile.
`local` requires storage, application processing, backup, support and provider processing to be
`local`. `eu-managed` requires EU ISO country codes and HTTPS residency/subprocessor evidence.

Each `provider_egress` item contains exactly `host` and `processing_location`. Provider hosts must be
unique; their normalized set must equal `egress_allowed_hosts`; every processing location must occur
in `external_processing_locations`. The actual Brave and Firecrawl base URL host set must equal the
declaration and pass the existing HTTPS public-host policy. A mismatch fails before secrets,
PostgreSQL, OIDC or provider adapters. Unknown fields, including tenant selectors, fail closed.

Both profiles use the same images, schema, OIDC claim contract, centralized authorization, tenant
context, PostgreSQL forced RLS, stable audit codes and DE/EN localization. There is no runtime
fallback between profiles, regions, providers, database or identity modes.

## Consequences

- Configuration changes to mode, countries, hosts or provider locations are reviewed deployments,
  not dynamic tenant settings.
- Supplied local profiles require operator-owned local provider endpoints; public SaaS providers may
  be used only with an accurately declared, evidence-backed compatible profile.
- Configuration detects contradictions but cannot prove provider behavior, DPA terms, support access
  or actual physical location; those remain operator evidence and periodic review duties.
- General automated tenant export, deletion, legal hold and cross-tenant administration remain
  unimplemented. Deployments needing them are blocked until tenant-scoped authorization, audit and
  negative tests exist.
- Disaster recovery cannot silently cross the active boundary. If no compliant restore target is
  available, availability yields to confidentiality and residency requirements.
- No database migration, business-state change or OIDC/Keycloak implementation is introduced.

## Verification

Configuration and E2E regression tests cover valid local and EU providers, missing residency,
undeclared processing, prohibited regions, allowlist/URL mismatch, unknown tenant-specific fields and
failure before secrets/adapters. Existing two-tenant PostgreSQL, OIDC, authorization, localization,
backup/restore and security gates remain mandatory release evidence.
