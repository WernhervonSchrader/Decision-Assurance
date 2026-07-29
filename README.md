# Decision Assurance

**Public Draft v0.2 — executable reference platform, not a recognized standard or certification.**

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

The static identity adapter is not production OIDC. Read the
[deployment](docs/DEPLOYMENT.md), [security](docs/SECURITY.md) and
[operations](docs/OPERATIONS.md) limitations before using real data.

## CLI examples

```powershell
decision-assurance validate examples\decision-cases\low-risk-pass.json
decision-assurance evaluate examples\decision-cases\hard-constraint-block.json
decision-assurance report examples\decision-cases\missing-evidence-review.json
decision-assurance transition case.json VALIDATION --actor-id validator-1 --actor-role VALIDATOR
decision-assurance benchmark tests\gold\manifest.json
```

The transition command writes the validated new state back to the Decision File
and appends an embedded, hash-linked audit event. Filesystem integrations should
also append that event to `audit/events.jsonl` via `CaseStore`.

## Repository map

```text
schemas/                         normative JSON Schemas
examples/decision-cases/         valid Decision Files
src/decision_assurance/          domain engine, API, policy, repositories and CLI
migrations/                      SQLite reference migration
tests/fixtures/invalid/           deliberately invalid contracts
tests/gold/                       open Gold Dataset manifest
docs/                             contract, policy and architecture
.github/workflows/ci.yml          public verification pipeline
```

The included benchmark is the project-owned **open benchmark suite**. It is not
an independent assessment. The engine does not simulate legal, medical or other
professional approval.

## License and positioning

Reference code is licensed under Apache-2.0. Normative specification licensing
may be separated in a future reviewed release. Internal research sources such as
RIF or RRS are not public product claims and are not required to run this MVP.
