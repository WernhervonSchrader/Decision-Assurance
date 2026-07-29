# Codex Engineering Operating Standard

This file defines mandatory repository-wide instructions for Codex and other coding agents working on Decision Assurance.

The objective is not merely to produce working code. Build production-ready software that is maintainable, secure, testable, multilingual, multi-tenant capable, auditable and operationally verifiable.

Use the Superpowers methodology when available. If the plugin is unavailable, follow the same workflow manually.

## 1. Mandatory engineering workflow

For every new application, major feature, architecture change or behavioral modification:

1. Inspect the repository, documentation, existing conventions, recent commits and current test status.
2. Clarify the objective, users, constraints, risks and measurable success criteria.
3. Present two or three implementation approaches with trade-offs.
4. Recommend one approach and explain the decision.
5. Produce a written design specification.
6. Review the specification for contradictions, ambiguity, missing requirements and unnecessary complexity.
7. Produce a detailed implementation plan containing exact file paths, interfaces, data structures, migrations, tests, verification commands, expected results and commit boundaries.
8. Implement with test-driven development where reasonably applicable.
9. Review specification compliance and code quality separately.
10. Run all relevant automated checks before declaring completion.
11. Provide evidence of completion rather than unsupported claims.

Do not begin production implementation before the design and implementation plan exist.

For trivial typo corrections or documentation-only changes, use a proportionate abbreviated workflow.

## 2. Mandatory-by-definition capabilities

The following capabilities must always be considered in architecture, design, implementation, testing and documentation. They are not optional enhancements and must not be postponed without an explicit documented architecture decision.

### 2.1 Multilingual capability

Every user-facing application must be designed for multilingual operation from the beginning.

Minimum requirements:

- No hard-coded user-facing text in application logic or UI components.
- All user-facing text must use a translation or localization layer.
- German and English must be supported unless the approved specification states otherwise.
- Locale detection and explicit locale selection must be supported.
- Fallback locale behavior must be defined.
- Dates, times, numbers, percentages and currencies must be locale-aware.
- Validation messages, emails, notifications, audit displays and error messages must be translatable.
- Right-to-left support must not be unnecessarily prevented.
- Translatable database content must use an explicit localization strategy.
- Translation keys must be stable, understandable and tested.
- Automated checks must detect missing translations and verify fallback behavior and locale formatting.

Distinguish explicitly between interface language, user locale, tenant default locale, content language, machine-readable audit language and localized audit display text.

Audit records should retain stable machine-readable codes. Localized display text may be generated separately.

### 2.2 Multi-tenancy

Every business application must be designed so it can support multiple tenants safely, even if the first release initially serves one tenant.

Minimum requirements:

- Every tenant-owned record must have an explicit tenant identifier.
- Tenant context must be established at the authentication or request boundary.
- Tenant isolation must be enforced server-side.
- Never trust a client-provided tenant identifier without authorization validation.
- Every query, mutation, background job, cache key, file path, search index and event must preserve tenant context.
- Cross-tenant access must fail closed.
- Administrative cross-tenant access must be explicit, authorized, narrowly scoped and audited.
- Database migrations must preserve tenant boundaries.
- Unique constraints must be deliberately classified as global or tenant-scoped.
- Tenant export, deletion, retention, suspension and restoration must be planned.
- Tenant-specific configuration, branding, locale, feature flags and limits must use a defined configuration model.
- Background workers and scheduled jobs must execute with explicit tenant identity.
- Logs and metrics should include tenant identifiers where lawful and appropriate without exposing sensitive tenant data.
- Automated isolation tests must prove that one tenant cannot read, modify, infer or enumerate another tenant’s data.

Where supported, evaluate database row-level security as an additional protection layer. Do not rely exclusively on application-level filtering when stronger isolation is practical.

### 2.3 End-to-end testing

End-to-end tests are mandatory for all material user journeys. Unit and integration tests do not replace E2E tests.

Minimum E2E coverage:

- authentication,
- authorization,
- tenant selection and tenant isolation,
- primary application workflows,
- validation failures,
- critical error paths,
- German and English behavior,
- state transitions,
- file upload and download where applicable,
- external integrations where applicable,
- administrative functions,
- security-sensitive actions,
- audit-trail creation,
- logout and session expiry.

E2E tests must:

- run against an isolated test environment,
- use deterministic test data,
- create and clean up their own data,
- avoid production dependencies,
- include at least two tenants,
- include at least two user roles,
- test German and English,
- verify successful and prohibited actions,
- produce actionable failure output,
- run locally and in CI.

Every implementation plan must state the E2E framework, test environment, seed strategy, service dependencies, browser and device coverage, CI execution strategy, artifact retention, screenshot or trace handling and flakiness controls.

A project is not complete until its material user journeys pass E2E testing.

## 3. Security by default

Security must be addressed in the design, implementation plan, code, tests and operational documentation. Use secure defaults, least privilege and fail-closed behavior.

### 3.1 Authentication

Plan and implement as applicable:

- an established authentication provider or maintained library,
- secure password hashing if passwords are stored,
- email verification,
- protected password reset,
- multi-factor authentication readiness,
- secure session handling,
- short-lived access tokens where appropriate,
- refresh-token rotation where applicable,
- abuse throttling and account lockout controls,
- session revocation,
- logout from one or all devices,
- protection against session fixation,
- secure cookies,
- CSRF protection where relevant.

Never implement custom cryptographic authentication mechanisms.

### 3.2 Authorization

Authorization must be enforced server-side.

Minimum requirements:

- define roles and permissions explicitly,
- apply least privilege,
- distinguish tenant membership from authorization,
- protect every sensitive operation,
- verify object-level authorization,
- prevent insecure direct object references,
- test horizontal and vertical privilege escalation,
- audit privileged actions,
- define emergency or break-glass access where needed.

UI visibility is not authorization.

### 3.3 Input and output security

- Validate all external input with explicit schemas.
- Reject unexpected fields where appropriate.
- Normalize inputs consistently.
- Use parameterized database access.
- Encode output according to context.
- Prevent XSS and injection attacks.
- Validate redirects and callback URLs.
- Restrict file names, types, sizes and content.
- Scan or quarantine uploads where appropriate.
- Prevent path traversal.
- Avoid unsafe deserialization.
- Validate webhook signatures.
- Use allowlists for high-risk integrations.

### 3.4 Secrets and configuration

- Never commit secrets.
- Use environment-specific secret management.
- Validate required configuration at application startup.
- Separate development, test, staging and production credentials.
- Rotate compromised credentials.
- Prevent secrets from appearing in logs, stack traces, client bundles or test artifacts.
- Provide example environment files with placeholders only.
- Document ownership and rotation responsibilities.

### 3.5 Data protection

Plan explicitly for data classification, encryption in transit, encryption at rest where appropriate, tenant isolation, data minimization, retention periods, deletion and export procedures, backup protection, restore testing, pseudonymization or anonymization where useful, sensitive-field redaction, regional and legal storage constraints and GDPR handling of personal data.

Do not collect or retain data merely because it might be useful later.

### 3.6 API and web security

Minimum requirements:

- authentication and authorization on protected endpoints,
- request and response schema validation,
- rate limiting,
- request-size limits,
- timeout handling,
- bounded pagination,
- replay protection where necessary,
- idempotency for critical writes,
- restrictive CORS configuration,
- explicit API versioning strategy,
- predictable error formats without sensitive details,
- abuse monitoring,
- protection against mass assignment,
- Content Security Policy where relevant,
- HSTS,
- clickjacking protection,
- MIME-sniffing protection,
- referrer policy,
- permissions policy,
- secure cookies,
- CSRF protection,
- open-redirect prevention,
- safe handling of user-generated HTML.

Administrative and internal endpoints must not be publicly exposed accidentally.

### 3.7 Infrastructure and supply-chain security

Minimum requirements:

- controlled dependency versions,
- dependency vulnerability scanning,
- secret scanning,
- static analysis,
- software composition analysis,
- container scanning where containers are used,
- minimal runtime images,
- non-root execution where practical,
- protected production branches,
- mandatory review for critical changes,
- least-privilege CI permissions,
- protected deployment environments,
- reproducible builds where practical,
- software bill of materials where appropriate.

Do not automatically apply major dependency upgrades without reviewing compatibility and security consequences.

### 3.8 Logging, audit and observability

Distinguish between operational logs, security logs, business events, audit records, metrics and traces.

Material audit records should contain timestamp, actor, tenant, action, target object, previous state where relevant, resulting state, decision or authorization result, request or correlation identifier, source channel and reason or policy code where applicable.

Audit records must be tamper-resistant according to risk level.

Never log passwords, access tokens, refresh tokens, secret keys, complete payment details, unnecessary personal data or sensitive request bodies without redaction.

### 3.9 Error handling and resilience

Plan for graceful failure, secure error messages, bounded retries, exponential backoff where appropriate, circuit breakers for unstable dependencies, idempotent processing, queue failure handling, dead-letter processing where relevant, timeout budgets, partial failure, recovery procedures, degraded operation, health checks and readiness checks.

Never conceal a failed operation behind a generic success response.

## 4. Mandatory threat modelling

For every application or major feature, create a concise threat model before implementation.

Cover at least assets, actors, trust boundaries, tenant boundaries, entry points, sensitive data, external services, likely abuse cases, privilege escalation, data leakage, tampering, denial of service, repudiation, spoofing and supply-chain risk.

For each material threat, document likelihood, impact, prevention, detection, response and residual risk.

Threat modelling must affect engineering decisions. Do not produce ceremonial documentation.

## 5. Architecture rules

Prefer small focused modules, explicit interfaces, typed schemas, deterministic state transitions, immutable or append-only audit-critical events, dependency inversion around external services, tenant-aware repositories and services, centralized authorization policies, centralized localization, explicit configuration and framework-independent testable business logic.

Avoid hidden global state, hard-coded tenants, hard-coded languages, authorization scattered across UI components, direct database access from presentation code, unbounded retries, silent exception handling, shared mutable tenant context, undocumented background processes and implicit state transitions.

## 6. Decision Assurance lifecycle and governance

For workflows with business or governance relevance:

- define every state explicitly,
- define allowed and prohibited transitions,
- define required roles,
- define required evidence,
- define validation rules,
- define human-review gates,
- define automatic and manual transitions,
- define timeout, cancellation and retry behavior,
- define audit events,
- test every allowed transition,
- test every prohibited transition.

No state may be modified through an undocumented bypass.

The default Decision Assurance lifecycle is:

`DRAFT -> VALIDATION -> REVIEW -> APPROVED | BLOCKED`

Any additional state or transition requires documented justification.

## 7. Testing standard

Every material change requires a balanced test strategy.

Required test layers:

1. Unit tests for deterministic business logic.
2. Integration tests for databases, queues, storage and external adapters.
3. Contract tests for APIs and service boundaries.
4. Authentication and authorization tests.
5. Tenant-isolation tests.
6. Localization tests.
7. Migration tests.
8. End-to-end tests.
9. Security-focused negative tests.
10. Regression tests for previously discovered defects.

Tests must prove that allowed actions succeed and prohibited actions fail correctly.

Minimum negative-test categories:

- unauthenticated access,
- unauthorized role,
- wrong tenant,
- missing tenant context,
- manipulated object identifier,
- invalid state transition,
- malformed input,
- oversized input,
- unsupported locale,
- missing translation,
- expired session,
- replayed request,
- duplicated request,
- failed external dependency,
- partial transaction failure.

## 8. CI/CD requirements

The implementation plan must include CI checks for formatting, linting, static type checks, unit tests, integration tests, tenant-isolation tests, localization checks, E2E tests, dependency vulnerability scanning, secret scanning, static security analysis, build verification and migration verification.

Critical checks must block merging.

Deployment planning must include environment separation, migration sequence, rollback approach, configuration validation, health checks, smoke tests, post-deployment verification and deployment auditability.

## 9. Required documentation

Create or update where applicable:

- `README.md`,
- architecture overview,
- installation instructions,
- environment configuration,
- security model,
- threat model,
- tenant model,
- localization model,
- testing strategy,
- E2E test guide,
- deployment guide,
- operational runbook,
- backup and restore procedure,
- incident-response notes,
- API documentation,
- data-retention and deletion description,
- architecture decision records.

Documentation must describe the implemented system, not an intended future state.

## 10. Definition of Done

A feature or application may be declared complete only when:

- the specification is approved,
- implementation follows the specification,
- multilingual implications are implemented or explicitly documented,
- tenant boundaries are implemented and tested,
- authorization is enforced server-side,
- security requirements are implemented,
- the threat model is updated,
- unit tests pass,
- integration tests pass,
- tenant-isolation tests pass,
- localization tests pass,
- E2E tests pass,
- security scans have no unresolved critical findings,
- migrations are verified,
- documentation is updated,
- no known critical or high-severity defect remains,
- completion is supported by command output, test reports or equivalent evidence.

Do not declare completion merely because code has been written.

## 11. Required output before implementation

Before touching production code, provide:

### A. Context assessment

Current repository state, relevant architecture, existing patterns, test baseline, risks and constraints.

### B. Requirements matrix

For every requirement, state the requirement, implementation location, test method and completion evidence.

Always include rows for multilingual support, multi-tenancy, authentication, authorization, tenant isolation, input validation, audit logging, data protection, E2E testing and CI security checks.

### C. Proposed architecture

Include components, trust boundaries, tenant boundaries, localization flow, authentication flow, authorization flow, data flow, audit flow, error handling and external dependencies.

### D. Threat model

List the material threats and planned controls.

### E. Implementation plan

Use small independently testable tasks containing exact paths, interfaces, failing tests, implementation steps, commands, expected outputs and commit messages.

### F. Acceptance criteria

Use objective and testable criteria.

## 12. Decision rule

Whenever speed conflicts with security, tenant isolation, traceability or testability, explain the trade-off and choose the safer architecture unless the project owner explicitly accepts the residual risk.

Whenever a requirement is unclear, use an explicit documented assumption rather than a hidden assumption.

Whenever a shortcut creates future migration risk for multilingual operation, multi-tenancy, security or E2E testing, do not take it without recording the decision and consequences.

Build the smallest solution that fulfils the full operational and security requirements. Do not confuse minimum scope with incomplete engineering.
