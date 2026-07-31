# Decision Assurance

**Public Draft v0.5 — production foundation and controlled-pilot candidate, not a recognized
standard or certification.**

Decision Assurance (DA) is a control layer for AI-supported decisions. Before a
result enters a business process, DA checks evidence, policies, constraints,
uncertainty, role separation and required human authority. The deterministic
governance outcome is always exactly one of `PASS`, `REVIEW` or `BLOCK`.

The MVP is useful to an enterprise team because the complete case remains a
portable, reviewable JSON record instead of hidden model-session state. Core
evaluation requires no LLM and never turns an internal failure into `PASS`.

## What runs today

- normative [Decision File Contract](docs/DECISION_FILE_CONTRACT.md) and examples
- executable [Transition Policy](docs/TRANSITION_POLICY.md)
- deterministic reference engine and Assurance Reports
- hash-linked, append-only audit records
- vendor-neutral [case directory interface](docs/ARCHITECTURE.md)
- 10-scenario open Gold Dataset and reproducible benchmark
- CLI commands: `validate`, `evaluate`, `transition`, `report`, `benchmark`
- CI for schemas, unit/transition tests, examples and Gold regression
- authenticated, tenant-aware [REST API](docs/API.md) with SQLite reference persistence
- centralized role authorization, DE/EN errors, idempotent writes and bounded audit pagination
- two-tenant [E2E journeys](docs/TESTING.md) through `APPROVED` and `BLOCKED`
- controlled DE/EN [real-world intake](docs/INTAKE.md) with provenance, verification and confirmation
- a separate 13-case raw-text intake benchmark with raw-only and trusted-context variants
- provider-neutral [Web Research](docs/web-research/README.md) with OpenAI Web Search discovery,
  optional guarded Firecrawl extraction, tenant-scoped evidence and conservative DRAFT-only handoff
- PostgreSQL persistence with forced row-level security and least-privilege application/worker roles
- production OIDC/JWKS, external secret references and exact HTTPS egress allowlists
- reproducible [Keycloak OIDC development/E2E environment](docs/KEYCLOAK.md) with PostgreSQL 16,
  S256 PKCE, controlled tenant/role claims and secret-free realm import
- durable asynchronous Research jobs with leases, retry, cancellation and recovery
- bounded MCP Web Research adapter with five authenticated tools and a validated personal-skill
  source template for ChatGPT Work/Codex
- non-root containers, readiness, redacted telemetry, backup/restore, CycloneDX SBOMs and
  fail-closed [release verification](docs/CI-RELEASE.md)
- a bounded [Sales Quote Review pilot](docs/PILOT.md) with two tenants and human gates
- validated `local` self-managed and `eu-managed` [operating profiles](docs/DEPLOYMENT.md)
  that share one runtime while failing closed on contradictory residency declarations

Case lifecycle (`DRAFT`, `VALIDATION`, `REVIEW`, `APPROVED`, `BLOCKED`) and
governance outcome (`PASS`, `REVIEW`, `BLOCK`) are deliberately separate.
`APPROVED` requires explicit human authority even when evaluation returns
`PASS`.

## Install and verify

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\decision-assurance.exe benchmark tests\gold\manifest.json
```

Linux and macOS use `.venv/bin/python` and `.venv/bin/decision-assurance`.

## Reference API

The API is created through an injected repository and authenticator. A
loopback-only local runtime is included for evaluation:

```powershell
$env:DA_DATABASE_PATH = ".local/decision-assurance.db"
$env:DA_IDENTITIES_PATH = "C:/protected/development-identities.json"
decision-assurance-api
```

The static identity adapter is not production OIDC and is rejected by configured production. Read the
[deployment](docs/DEPLOYMENT.md), [security](docs/SECURITY.md) and
[operations](docs/OPERATIONS.md) limitations before using real data.

Production deployments choose exactly one operating profile. `local` is self-managed PostgreSQL,
OIDC and external-secret infrastructure inside the operator boundary; it is not the SQLite reference
runtime. `eu-managed` additionally requires explicit EU country codes for storage, processing,
backup, support and external processing plus HTTPS residency/subprocessor evidence references.
Every configured provider host has a requested processing location plus a structured attestation. Its
host must exactly match the runtime egress allowlist and actual OpenAI/Firecrawl base URLs. Startup
validation is supplemented by a request-time guard; missing, unverified, expired, tenant-incompatible
or profile-incompatible evidence blocks immediately before network access and records a secret-free
decision event. The supplied OpenAI/Firecrawl profile entries remain blocked until independently
verified evidence is supplied.

The MCP adapter is a separate process from the REST API and exposes stateless Streamable HTTP at
`http://127.0.0.1:8001/mcp` in local reference mode:

```powershell
$env:DA_MCP_ISSUER_URL = "http://localhost/identity"
$env:DA_MCP_RESOURCE_SERVER_URL = "http://127.0.0.1:8001"
decision-assurance-mcp
```

It uses the same protected database, identity and provider configuration. This loopback server is
not production-ready. See [MCP Web Research and ChatGPT Work](docs/MCP-WEB-RESEARCH.md).

## CLI examples

```powershell
decision-assurance validate examples\decision-cases\low-risk-pass.json
decision-assurance evaluate examples\decision-cases\hard-constraint-block.json
decision-assurance report examples\decision-cases\missing-evidence-review.json
decision-assurance transition case.json VALIDATION --actor-id validator-1 --actor-role VALIDATOR
decision-assurance benchmark tests\gold\manifest.json
```

Controlled Intake keeps user text untrusted and emits no assurance outcome:

```powershell
decision-assurance intake create quote.txt --intake-id Q-42 --locale en --policy policy.json --output intake.json
decision-assurance intake inspect intake.json
decision-assurance intake compile intake.json --policy policy.json --output decision.json
decision-assurance intake evaluate decision.json
```

If a candidate requires a human decision, an authenticated validator or approver can use
`intake confirm`. The original value, correction, reason and actor remain in the record.

The transition command writes the validated new state back to the Decision File
and appends an embedded, hash-linked audit event. Filesystem integrations should
also append that event to `audit/events.jsonl` via `CaseStore`.

## Repository map

```text
schemas/                         normative JSON Schemas
examples/decision-cases/         valid Decision Files
src/decision_assurance/          domain engine, API, policy, repositories and CLI
integrations/chatgpt-work/       validated personal-skill source templates (not installed)
integrations/keycloak/           secret-free, versioned local realm import
migrations/                      SQLite and PostgreSQL/RLS migrations
tests/fixtures/invalid/           deliberately invalid contracts
tests/gold/                       open Gold Dataset manifest
benchmarks/intake/cases/          13-case untrusted-text benchmark
docs/                             contract, policy and architecture
.github/workflows/ci.yml          public verification pipeline
Dockerfile.api / Dockerfile.worker / Dockerfile.mcp process container targets
Dockerfile.keycloak / compose.keycloak.yaml isolated Keycloak development target
```

The included benchmark is the project-owned **open benchmark suite**. It is not
an independent assessment. The engine does not simulate legal, medical or other
professional approval.

## License and positioning

Reference code is licensed under Apache-2.0. Normative specification licensing
may be separated in a future reviewed release. Internal research sources such as
RIF or RRS are not public product claims and are not required to run this MVP.
