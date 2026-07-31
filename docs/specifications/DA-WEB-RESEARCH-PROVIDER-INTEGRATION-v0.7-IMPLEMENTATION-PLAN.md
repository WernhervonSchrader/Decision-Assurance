# Web Research Provider Integration v0.7 implementation plan

## 1. Development profile and secret boundary

- Paths: `production/contracts.py`, `production/config.py`, `production/egress.py`,
  `api/runtime.py`, `config/deployment/provider-development.example.json`, `.gitignore`,
  `.secrets/*.example`.
- Interfaces: explicit development operating mode; pinned `ResidencyEgressGuard` profile;
  provider-secret resolution through `SecretProviderPort`.
- First tests: production rejects development mode; development emits
  `EGRESS_ALLOWED_DEVELOPMENT`; runtime reload/downgrade blocks; missing/unsafe keys return
  `PROVIDER_NOT_CONFIGURED`; one missing connector does not prevent runtime construction.
- Expected: local files can enable only the named provider; no secret value is serialized.
- Commit boundary: included in the single provider-integration feature commit.

## 2. Provider contract and telemetry hardening

- Paths: `web_research/providers/brave.py`, `firecrawl.py`, new `telemetry.py`,
  `observability/logging.py`, provider tests.
- Interfaces: Brave `age` normalization with compatibility fallback; explicit 401/403/404/429/5xx
  mappings; shared secret-free provider call telemetry.
- Tests: success, invalid key, statuses, timeout, Retry-After, exact telemetry fields and canary
  redaction.
- Expected: no response body, URL, header or credential reaches connector logs.

## 3. Combined and hostile-network tests

- Paths: new `tests/research/integration/test_provider_pipeline.py`, existing URL/provider tests.
- Tests: actual adapters with separate MockTransports; full request-to-evidence flow; duplicate URL;
  public-to-private resolver change; prohibited redirect/canonical target; tenant isolation;
  prompt-injection non-handoff; residency/audit zero-call.
- Expected: deterministic data, no production dependency, every prohibited path fails before the
  relevant external call or before evidence compilation.

## 4. Live smoke harness

- Paths: `tests/research/live/test_provider_smoke.py`, `pyproject.toml`, provider documentation.
- Marker: `live_provider`; requires `DA_RUN_LIVE_PROVIDER_TESTS=1`, explicit development profile and
  local `BRAVE_API_KEY`/`FIRECRAWL_API_KEY` files.
- Output: connector, result class, duration, result count and correlation ID only.
- Runs: Brave-only, Firecrawl-only and combined; skipped safely otherwise.

## 5. Documentation and verification

- Paths: provider configuration, architecture/security/testing/threat documentation and README only
  where behavior changes.
- Commands and expected results:
  - `ruff format --check src tests` and `ruff check src tests scripts`: clean.
  - `mypy src`: strict success.
  - focused provider/integration/live-skip tests: pass.
  - `pytest -m "not postgresql and not live_provider" -q`: complete local suite pass.
  - `pytest -m postgresql -q` against PostgreSQL 16: pass.
  - Bandit, isolated pip-audit and Gitleaks history/diff: no blocking findings.
  - Python package and API/Worker/MCP images: build; non-root smoke and critical scan pass.
  - OpenAPI contracts and `git diff --check`: unchanged/clean.
  - If local secrets exist, run three live tests and report bounded metadata only.
- Final review: specification compliance, then separate code/security review.
- Publish: one Conventional Commit, push `feature/web-research-provider-integration`, open Draft PR;
  do not merge or deploy.
