# Decision Assurance Operating Profiles v0.6

Status: approved implementation basis for the `local` and `eu-managed` paths.

## A. Context assessment

Decision Assurance v0.5 already has one modular Python runtime, PostgreSQL with forced RLS, OIDC,
external secret references, separate API/Worker/MCP processes, bounded egress, backup verification,
DE/EN API localization and mandatory CI release evidence. Configuration currently distinguishes
development/test/staging/production but does not state who operates the infrastructure or where
tenant data may be stored, processed, backed up or accessed for support.

The baseline on merged `main` is 460 non-PostgreSQL tests, Ruff and strict Mypy passing. The latest
PR PostgreSQL, container, restore, secret and release-evidence jobs also pass. The principal risk is
that an operator can call a deployment “local” or “EU” without a machine-checked contract. The
change must not fork business logic, weaken RLS, introduce client-selected tenant or deployment
context, or claim that configuration alone proves legal compliance.

Assumptions:

- `local` means a self-managed production deployment, not the SQLite/static-identity development
  profile. Storage, processing, backup and operator access stay within the named local boundary.
- `eu-managed` means a managed deployment whose declared storage, processing, backup, support and
  external-processing countries are EU member states.
- Country codes are ISO 3166-1 alpha-2. A runtime allowlist is a technical guard; contracts,
  subprocessors and independent evidence remain operational prerequisites.
- Both paths support German and English and share the same machine-readable audit codes.

## B. Requirements matrix

| ID | Requirement | Implementation location | Test method | Completion evidence |
| --- | --- | --- | --- | --- |
| OP-01 | Exactly one `local` or `eu-managed` operating mode is required in staging/production | `production/contracts.py`, `production/config.py` | configuration unit tests | typed config loads or fails closed |
| OP-02 | Local production declares one local boundary and no remote support location | deployment config and residency validator | positive/negative contract tests | `local.example.json` accepted; remote support rejected |
| OP-03 | EU-managed locations are explicit EU country codes | residency validator | table-driven EU/non-EU tests | non-EU storage/processing/backup/support rejected |
| OP-04 | EU-managed requires HTTPS evidence references for residency and subprocessors | residency validator | missing/HTTP reference tests | startup rejection reason code |
| OP-05 | Both paths use the same application and domain modules | runtime loader and two config fixtures | runtime construction tests | identical adapter classes and policies |
| OP-06 | Multilingual behavior remains DE/EN with tenant/user locale flow unchanged | existing i18n/API layers; operating-profile docs | existing localization suite plus profile E2E | DE/EN journeys pass for both modes |
| OP-07 | Multi-tenancy remains explicit and server-side | PostgreSQL repositories/RLS unchanged | existing two-tenant PostgreSQL/E2E suite | cross-tenant probes fail |
| OP-08 | Authentication remains OIDC in both production paths | config validation/runtime | unsafe fallback tests | static authentication rejected |
| OP-09 | Authorization remains centralized and object-level | existing authorization/transition modules | existing role and escalation tests | prohibited actions fail |
| OP-10 | Tenant isolation applies to data, cache, jobs, files and evidence | existing tenant repositories plus deployment docs | isolation and handoff tests | no cross-tenant access |
| OP-11 | Input is schema/type validated and unknown operating fields rejected | config parser and deployment schema | contract tests | malformed/unknown input rejected |
| OP-12 | Audit records keep stable codes; deployment mode is operational metadata, not user input | audit design/runbook | audit regression tests and review | no localized text or client mode in audit authority |
| OP-13 | Data protection declares storage, processing, backup, support and external processing | residency policy/config examples/docs | policy tests and documentation review | complete location inventory required |
| OP-14 | Material E2E covers both profiles without production dependencies | `tests/production/e2e/test_operating_profiles.py` | deterministic runtime assembly for two tenants/locales/roles | both modes construct fail-closed production apps |
| OP-15 | CI keeps formatting, types, unit/integration/E2E, PostgreSQL, scans, build and migration gates | `.github/workflows/ci.yml` and existing release mapping | CI run | all mandatory gates pass |
| OP-16 | Tenant export/deletion/retention and backup/restore remain operator-owned per mode | deployment/operations/backup docs | runbook review and restore job | explicit mode-specific procedures |

## C. Proposed architecture

One codebase and artifact set serves both modes. A new `OperatingMode` and immutable
`DataResidencyPolicy` are parsed at startup. The policy is configuration authority only; it never
comes from an HTTP/MCP request and never changes tenant identity or authorization.

```text
signed configuration + secret references
                 |
                 v
 RuntimeConfig(mode, residency policy) ---- fail closed on contradiction
                 |
       +---------+---------+
       |                   |
 local operator       EU managed operator
 local boundary       explicit EU countries + evidence
       |                   |
       +---------+---------+
                 |
 shared API / Worker / MCP / PostgreSQL-RLS / Engine / audit
```

Trust boundaries are configuration delivery, secret resolution, OIDC, the HTTP/MCP edge,
PostgreSQL, provider egress, backup storage and operator/support access. Tenant boundaries remain at
verified identity and transaction-local RLS. Localization remains user locale -> tenant default ->
English fallback; configuration and audit reason codes remain machine-readable English identifiers.

Authentication and authorization flows are unchanged. Data flows add a startup check before any
adapter construction. Local data locations use the reserved `local` boundary. EU-managed data
locations use explicit EU country codes and HTTPS evidence references. Errors expose stable reason
codes without provider or secret detail. No fallback switches operating mode, database, identity or
secret provider.

External dependencies remain PostgreSQL, OIDC, secret storage and optional Research providers. An
EU-managed deployment may enable a provider only when its declared processing location is EU and
its evidence is recorded; technical configuration does not replace DPA/SCC/legal assessment.

## D. Threat model

| Threat | Likelihood / impact | Prevention | Detection | Response | Residual risk |
| --- | --- | --- | --- | --- | --- |
| False EU label with non-EU data path | medium / critical | EU country allowlist; complete location sets; HTTPS evidence refs | startup failure; config tests; deployment review | block rollout and correct provider/location contract | evidence may be stale or misleading |
| Local mode silently uses managed support | medium / high | support must be `local`; external processing explicitly declared | startup/config audit | disable access/egress and investigate | operator can misstate infrastructure |
| Client changes mode or jurisdiction | low / critical | config-only immutable context; no request field | unknown-field/API tests and logs | reject request and security review | compromised deployment config remains trusted |
| Cross-tenant access in either mode | medium / critical | verified tenant context, RLS, tenant keys | two-tenant tests and audit alerts | stop service and incident process | privileged DBA/operator risk |
| Backup leaves approved boundary | medium / high | explicit backup locations; mode-specific runbook | backup manifest/operator evidence | quarantine/delete invalid copy and rotate credentials | storage-provider control-plane access |
| Non-EU support access | medium / high | EU support-country allowlist; least privilege; audited break-glass | access logs and quarterly review | revoke session, notify owner, incident assessment | IdP/provider compromise |
| Residency evidence tampering/staleness | medium / high | HTTPS references, review dates/ownership in runbook, release review | periodic evidence review | block renewal/deployment | external attestations are not cryptographic proof of processing |
| Profile drift between paths | medium / medium | shared typed model and same images; fixture parity tests | CI diff/contract tests | roll back config and regenerate evidence | cloud-specific controls remain external |
| Supply-chain or config injection | low / high | read-only images, scans, signed deployment process, unknown fields rejected | CI/secret/static scans | block release, rotate and rebuild | zero-day and CI administrator risk |
| Regional outage/DoS | medium / high | explicit backup/failover location, bounded retries, recovery drills | health/metrics and restore evidence | degraded mode or approved in-boundary failover | single-jurisdiction correlated failure |

## Specification review

The design intentionally avoids provider-specific infrastructure-as-code because no EU managed
provider has been selected. It does not promise GDPR compliance from a country code. Local and
EU-managed are operational modes, not tenant-selectable features. The existing development profile
is not renamed, preventing ambiguity with local production. The smallest enforceable slice is typed
configuration, example profiles, runtime construction tests, documentation and CI coverage; data
models and migrations do not change.

## F. Acceptance criteria

1. Both example profiles load into the same production runtime interfaces.
2. Missing operating mode or residency data fails startup in staging/production.
3. EU-managed rejects every non-EU storage, processing, backup, support or external-processing code.
4. EU-managed rejects missing or non-HTTPS residency evidence.
5. Local rejects remote storage, processing, backup or support declarations.
6. Neither mode permits SQLite, static identity or environment secrets in production.
7. Existing tenant, authorization, localization, audit, lifecycle and Research tests remain green.
8. Deterministic profile E2E covers local and EU-managed, two tenants, two roles and DE/EN.
9. Full non-PostgreSQL and PostgreSQL suites plus CI security/release gates pass.
10. Documentation distinguishes interface locale, tenant locale, content language, audit codes and
    localized audit display, and documents retention/export/deletion/restore per mode.

