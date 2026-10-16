# Security coverage matrix v0.1

Date: 2026-10-16. Status describes the named control, scope and evidence, not product certification.
TESTED requires a successful meaningful automated test against the actual named implementation.
PARTIALLY TESTED means a real subset was checked but the full property is not established.
SPECIFIED ONLY and MISSING are never counted as passed implementation.

## Eleven supplied principles: exact numbering, scoped coverage

Source provenance: the owner supplied the numbered transcript in this task on 2026-10-16,
attributed to Christoph Burseg. No URL was supplied; authorship/publication has not been
independently verified. The short descriptions below paraphrase that supplied ordering.
This is an engineering coverage comparison, not a certification or an endorsement of every
suggested mechanism. A model confirmation cannot replace independent authorization.

| # / supplied principle | Actual implementation and executed evidence | Status and remaining gap |
|---|---|---|
| 1. Constrain filenames, termination, length and control characters; report violations | Decision File ID schema restricts characters and length. `security_benchmark/contracts.py` and `test_adapters.py` reject unsafe relative payload paths. | PARTIALLY TESTED: these scoped guards pass; direct `case_store.py` methods concatenate caller IDs without their own validation. Universal filename/control-character/length enforcement and violation reporting are not established. That direct-store gap is inspection evidence, not an executed exploit. |
| 2. Treat payment details as proposals; validate and compare with trusted history | C3 in `test_execution.py` rejects a changed bank value in the isolated execution sandbox. | MISSING for productive payment control: no implemented IBAN checksum or known-good/history registry was found. Sandbox string comparison does not prove this principle. |
| 3. Cap retries; quarantine suspicious input | `dataset.py` bounds download attempts; research policy/orchestrator bounds attempts and budget. `test_orchestration_controls.py` tests retry limits and retry-after; `production/jobs/test_worker.py` distinguishes retryable and poisoned failures. | PARTIALLY TESTED: bounded retry behavior passes; a general suspicious-content quarantine and its operational release procedure are missing. A terminal poison failure is not evidence of quarantine. |
| 4. Use deterministic engines for critical decisions | Real deterministic engine/TransitionPolicy, 61 existing engine/contract/transition checks and B0/B4/B5 controls. | PARTIALLY TESTED: B1/B2 expose incomplete policy/provenance, B3 real lifecycle admission bypass. There is no universal tested invoice/tool-call/social-engineering decision engine. |
| 5. Accept model outputs only through narrow strict schemas | Strict Decision File and benchmark contracts, research contracts, API negative-schema tests; `research/contract/test_research_schemas.py` rejects unknown identity/provider fields. | PARTIALLY TESTED: actual contracts pass; the optional fresh agent adapter is disabled. Strict JSON compliance of every live model response has not been tested. |
| 6. Keep external text out of shell; constrain URL hosts | Benchmark has no payload-to-shell dispatcher. `reporting.py` permits only two fixed read-only Git metadata commands. Locked downloader host/redirect checks and offline socket-denial E2E pass. | TESTED for the named benchmark boundary only. This does not certify every external integration or all repository shell use. |
| 7. Preview writes, then confirm before execution | Canonical action binding and genuine human API approval are tested. C1-C7 simulate authorization and atomic freshness recheck before effects. Runtime execution contract remains a separate specification. | SPECIFIED ONLY for a productive dry-run-to-confirmation-to-effect gateway: no production mail/purchase executor is shipped. LLM confirmation alone would not satisfy authorization. |
| 8. Grant only the exact task privileges | Actual authenticated API B4 rejects generator evaluate/approve; B0 human approval succeeds; two-tenant authorization/isolation tests pass. | PARTIALLY TESTED: B3 shows generator creation accepts a forged already-APPROVED document. Role separation is incomplete despite individual protected routes. |
| 9. Log every security event | Actual engine audit links, API persistence and security-event sink checks; `production/identity/test_security_events.py` checks secret-safe event contracts. | PARTIALLY TESTED: named paths emit tested events; universal completeness is unproven. B3 admission conflicts with intended approval semantics; B6 permits SQLite writer tampering. In-memory and sandbox logs are labelled separately. |
| 10. Documents must not cause tool calls; control logic stays outside | Offline runner treats LLMail text as data and denies network. Existing `mcp_adapter/integration/test_mcp_service.py::test_prompt_injection_never_hands_off_or_produces_an_outcome` and research E2E test actual handoff controls. | PARTIALLY TESTED: named boundaries pass; fresh agent resilience remains unmeasured, B3 governance gap remains, and a productive effect gateway is absent. Imported text validation alone is not injection defense. |
| 11. Immediate emergency stop for agents/tools, triggerable by agent | Tenant-scoped `research_cancel`, worker cancellation checks and research cooperative cancellation. `test_cancel_is_idempotent_and_appends_research_audit`, `test_running_cancel_stops_before_next_provider_or_persistence`, and `test_cancelled_delivery_never_invokes_processor` pass. | PARTIALLY TESTED: cooperative cancellation is real; no immediate global kill switch or guaranteed interruption of in-flight external calls is implemented/tested. |

All eleven source items are mapped; a complete mapping does not mean complete implementation.
Statuses apply to the stated property and boundary. C-series success never raises productive
control coverage to TESTED. Follow-up issues should address the listed gaps in addition to B1/B2/B3/B6.

## Verified DA control inventory — project categories, not attributed to Burseg

| Control area | Actual component / scope | Status | Executed evidence and remaining gap |
|---|---|---|---|
| Authentication and request identity | FastAPI + StaticTokenAuthenticator in benchmark; maintained OIDC elsewhere | PARTIALLY TESTED | New two-tenant API tests prove missing/invalid identity denial; live IdP not exercised here |
| Least privilege and role separation | `api/dependencies.py`, authorization policies, TransitionPolicy | PARTIALLY TESTED | B4 actual generator evaluation/approval denied; B0 genuine human approval succeeds; B3 create bypass remains |
| Tenant isolation | Actual API + SQLite; actual PostgreSQL forced RLS | TESTED | DE/EN two-tenant API tests and 28 existing PostgreSQL tests pass; no simulated cross-tenant business effect |
| Strict input contracts and canonical binding | ContractValidator, Decision File semantics/digests | TESTED | 61 existing contract/Gold/engine/transition tests and new negative schema/ID/action tests pass; digest does not authenticate a human |
| Evidence authenticity and completeness | Engine status/claim/missing-evidence logic | PARTIALLY TESTED | B5 handles missing evidence, B2 falsifies independent-origin assumption; no independent source-authenticity registry is established |
| Human approval and protected lifecycle | Authenticated decision routes, TransitionPolicy | PARTIALLY TESTED | B0 and B4 succeed as intended; B3 proves generator can create a fabricated APPROVED file |
| Layered injection defense | Existing intake/research isolation; new optional AgentPort | PARTIALLY TESTED | Existing regression tests and data-only runner execute; fresh model resilience is unmeasured; imported payload validation is not defense evidence |
| Audit and repudiation resistance | Actual engine links, API persistence, SQLite writer; PostgreSQL controls | PARTIALLY TESTED | Missing/link regressions tested; B6 SQLite writer tamper succeeds; PostgreSQL tests pass without establishing all deployment protections |
| Fresh execution-time context and replay | No production purchase/mail executor; isolated sandbox only | SPECIFIED ONLY | C1–C7 and concurrency/audit-failure tests pass against the test adapter; Runtime Contract PR #14 remains specification |
| Controlled egress and effects | Offline benchmark, locked source downloader, fake sink | TESTED | Network-denial smoke, redirect/hash/path/byte-range tests pass; no external model/mail/purchase adapter is shipped |
| Reproducible assurance and regression evidence | Immutable lock, seed/strata, JSON/Markdown, full stream comparison and CI smoke | TESTED | 27-case smoke, 1,315-case standard, checkpoint/mutation/stream tests, unchanged DATS 10/10; no universal security score |

Production execution controls remain unimplemented/unproven regardless of the passing sandbox.
Existing specifications, including the separate runtime draft, do not raise implementation status.
Full threat model and finding scopes are in `DA-SECURITY-BENCHMARK-v0.1.md`.
