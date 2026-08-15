# Decision File v0.2 — Implementation Plan

## Scope and commit boundary

One contract-focused change: schema, semantic validator, compiler/fixtures, transition integration,
tests and documentation. No database migration, public deployment, identity-provider change or
automatic action execution is included.

## Tasks

1. **Version and schema**
   - Files: `schemas/decision-file.schema.json`, packaged schema mirror.
   - Add `requested_by`, nullable `canonical_action`, reversibility, action/approval digests and nonce.
   - Gate: malformed or incomplete v0.2 documents fail contract validation.

2. **Deterministic binding**
   - File: `src/decision_assurance/decision_file.py`.
   - Add canonical digest helpers, approval binding and fail-closed semantic checks.
   - Gate: tampering, replay, wrong role and wrong action binding raise `DecisionFileSemanticError`.

3. **Lifecycle integration**
   - Files: API decision route, `src/decision_assurance/transitions.py`, and package exports.
   - On APPROVED, bind the authenticated human approver, server-generated nonce and action digest;
     include approval digests in the transition audit payload hash.
   - Gate: pre-approval before REVIEW and cross-tenant canonical actions fail closed; the existing
     action-less lifecycle remains valid.

4. **Migration and producers**
   - Files: intake compiler, benchmark fixture and decision examples.
   - Emit v0.2 with explicit requester and `canonical_action: null` unless an action is known.
   - Migrate only unapproved v0.1 records; block legacy approvals from automatic conversion.

5. **Tests**
   - Files: semantic, transition, API E2E, compiler and installed-contract tests.
   - Commands:
     - `pytest tests/test_decision_file.py tests/test_transitions.py tests/intake/unit/test_compiler.py tests/test_installed_contracts.py -q`
     - `pytest tests/e2e/test_decision_journeys.py -q`
     - `pytest -q`
     - `ruff format --check .`
     - `ruff check .`
     - `mypy src`
   - Expected: zero failures; external PostgreSQL, Keycloak, provider and browser environments remain
     separately evidenced by their existing CI jobs.

6. **Documentation and review**
   - Update Decision File Contract and Transition Policy.
   - Review specification compliance separately from code quality.
   - Verify `git diff --check`, schema mirror equality and clean test output.

## Rollback

Before publication, revert this isolated change. After v0.2 records exist, retain the v0.2 reader
and migrate forward; never relabel v0.2 data as v0.1. Existing v0.1 records remain source evidence
and must not be overwritten during migration.
