# B3 verification — 2026-10-31

## Scope and evidence

Repository baseline: main `96b32da9e146b3b276c5fec4e636f67f6ea10889`. Independent branch `fix/b3-server-owned-approval`; no #17 code or #16 benchmark package merged. Design/plan committed first as `aaa2981`. This report is local CODE/TEST evidence, not RUNTIME/PRODUCTION approval.

Entry path inspected: `api/routes/decisions.py:create_decision` -> ContractValidator -> `validate_semantics` -> creator/action tenant checks -> document deepcopy -> repository INSERT. The original code never calls TransitionPolicy and never assigns document status DRAFT, despite recording a DRAFT creation audit event. `decision_file.py:approval_digest` verifies reproducible content only; the existing valid-human transition controls are bypassed at initial insertion. Both SQLite and PostgreSQL originally inserted the supplied lifecycle. Evaluation and transition both previously read before an unconditional update; the PostgreSQL advisory lock at write time did not validate the read snapshot.

PR #16 original B3 adapter was read at pinned head `06bce76e5029ea6aa6cc2ea2f8805bb314a18283`, `src/decision_assurance/security_benchmark/adapters.py` lines 219–247. New API tests reproduce its formally valid, invented-human digest with both canonical action and no action. No real mail, provider or execution action was attempted.

## Executed checks

A temporary Python 3.12 virtual environment installed the project with its existing `.[dev]` dependency bounds. No dependency declarations or production configuration changed.

- Before production edits, the initial 29-case new HTTP suite: **23 failed, 6 passed**. The valid forged APPROVED case failed its expected rejection assertion because the original API accepted it. Some other failures revealed existing unhandled semantic errors/unsafe concurrency. This is an initial TDD run, not a claim that all 23 failures independently demonstrate B3.
- Final full non-service suite: **727 passed, 39 deselected**, 11 deprecation warnings. Command: `/tmp/b3-venv/bin/python -m pytest -m 'not postgresql and not keycloak_e2e and not live_provider' -q`. Includes 37 new HTTP regressions, nine new SQLite repository cases and one requester separation regression. Existing API, compiler, tenant, locale and positive human approval journeys pass.
- Strict Mypy: **136 source files**, no issues. Ruff lint/format, Bandit and `git diff --check` passed. Bandit printed existing comment-parser warnings without findings.
- Python wheel and source distribution build passed. Both generated OpenAPI v0.4/v0.5 files exactly match their checked-in contracts.
- Original DATS v0.1.0: **10/10 matched**; no catalog or expected outcome rewritten.
- Dependency audit: **no known vulnerabilities**; local editable decision-assurance-engine is not published on PyPI and is explicitly skipped by the auditor.
- Original pinned #16 governance adapter, extracted unchanged into `/tmp/b3-historical` and loaded against this branch's production modules: **all eight standard B3 cases PASS**, API `DENY`, `governance_escape=false`, `lifecycle_state=null`, `executed=null`. Cases cover DE/EN and tenant-a/tenant-b. Only B3 was invoked; this is not a full #16 benchmark run. Compact results: `B3-HISTORICAL-ADAPTER-RESULTS.json`.

Original-adapter reproduction: `git archive 06bce76e5029ea6aa6cc2ea2f8805bb314a18283 src/decision_assurance/security_benchmark benchmarks/security examples/decision-cases | tar -x -C /tmp/b3-historical`; append `/tmp/b3-historical/src/decision_assurance` to the imported `decision_assurance.__path__`, import `run_governance` and `own_cases`, then run only cases where family is B3 in an empty temporary workspace. Extracted package/files were not added to this PR.

## Failures resolved during verification

The first console-script pytest invocation lacked repository root on Python's module search path, causing six collection errors (`tests` / `scripts` imports). Using the repository CI command `python -m pytest` resolved them without source changes. The next full run had three failures: one old test expected 409 for agent approval, whereas explicit authenticated-human rejection now returns 403; the other two were missing host SOCKS-proxy support. The old expectation was updated to assert 403 and its exact stable reason. `socksio` was installed only in the temporary environment, and pip refreshed to the existing CI minimum. A later expanded fixture initially used null action_digest with a canonical action; fixing the synthetic digest binding made that formally valid regression pass. A Ruff warning on formatted test SQL was resolved with psycopg Identifier composition, not a broad lint exemption.

## Separate review passes

Specification compliance review: traced every public Decision create/compile/evaluate/transition route and both repository implementations. Compiler starts unapproved DRAFT; research handoff is DRAFT-only and has existing snapshot/row locking; direct backend interfaces remain trusted and are not presented as independent identity verification. Explicit role/kind, generator/requester/validator separation, canonical action binding, DE/EN envelopes, tenant scope, import replay and terminal immutability are covered. Approval identity and authority are derived from the authenticated request, never an imported digest. New PG fixtures deliberately seed historical approved export records through trusted test-only writes, not permissive imports.

Code quality review: checked all save_result callers after making expected_document mandatory, transaction boundaries, parameterized tenant-qualified CAS, rollback of report/audit/idempotency, preservation of PG deletion lock and RLS, stable error envelopes and offline semantic-validation compatibility. Changed snapshot and concurrent-approval tests show rejection without partial writes. Snapshot audit is recomputable from the stored result and versioned with a reason code; it is not claimed as a signature. No new provider, secret, migration, schema or execution subsystem.

Both passes were performed by the implementing actor; independent human review remains required.

## Unverified and release limits

- Nine new PostgreSQL repository cases are included and marked postgresql for existing service CI; no PostgreSQL binary/service, Docker or live Keycloak was available locally. Those cases and existing service/browser/container/restore/secret-scan/Actionlint jobs were not claimed as locally passed. Existing CI remains enabled. CI at the published commit must be inspected separately.
- Static-token HTTP tests prove local server behavior; no production OIDC/Keycloak, MFA, administrator provisioning, effective-person independence or durable production audit was verified. The existing trust contract depends on issuer-managed actor kind and roles. Distinct IDs do not prove distinct effective controllers.
- B2 remains separate in #17. B1/B6 and an external execution gateway are not fixed. No production readiness or general security certification is asserted.
- No migration retroactively establishes authenticity of existing APPROVED files. Deployment must remain blocked pending review/quarantine/re-approval of potentially affected stored records.
- The snapshot is bound when the server handles the authenticated transition and atomically commits it. A client-reviewed-version precondition and proof of what the human inspected are not introduced by this minimal correction.
- A database writer can still tamper with SQLite audit/history; hashes are not write protection. Trusted direct repository writers and issuer compromise remain outside the generator/API threat boundary.
- No automatic merge, release, production configuration change or external execution is authorized. Release decision remains BLOCKED with zero human approvals.


## Published CI follow-up

Published plan commit `3e0fd2def828572f3292e38cbb23096d2a04ab9e` corresponds to local `aaa2981`; implementation `78b472518d165cb05e5b0b3891703fa3f3d83166` has the exact locally verified tree `e9270a6a3880f066d1461a3f007af5e9fae232a4`. Publication used the authenticated GitHub connector after git push found no shell credential; no credentials were added.

Initial PR workflow: https://github.com/WernhervonSchrader/Decision-Assurance/actions/runs/41190737512 (PR merge ref for the implementation above). PostgreSQL integration actually ran: **31 passed, 1 failed**; the only failure was the existing full sales-quote journey's old 409 assertion for an agent approver. The new authenticated boundary correctly returns 403. This follow-up updates that assertion and exact reason; it does not weaken authorization. All nine added PostgreSQL repository cases passed in that run. Final-head PostgreSQL CI remains to be checked.

The same run has two unrelated release blockers in unchanged files: `pilot-ui` typecheck, three unit tests and build passed, but npm audit failed with **three high and two moderate** dependency findings (source-map-js, undici, vite, vitest/@vitest/mocker); browser E2E was consequently skipped. `ui/package.json` and `ui/package-lock.json` are byte-identical to main. `restore-verification` failed with PostgreSQL 16 rejecting `SET transaction_timeout = 0` from the restore input; recovery/workflow files are unchanged. This records observed failures, not a production exploit or a tested remediation. Neither gate is disabled or waived; dependency upgrades and recovery-toolchain correction are outside this B3 code fix. Secret scanning passed. Other job results are not generalized into a green-CI claim.

The follow-up changes only the existing service-test expectation and verification/release documentation. Production implementation snapshot is unchanged; no repeated full local suite is required for this assertion/documentation update. Independent review and release remain BLOCKED.
