# Security coverage matrix v0.1

Date: 2026-10-16. Status describes the named control, scope and evidence, not product certification.
TESTED requires a successful meaningful automated test against the actual named implementation.
PARTIALLY TESTED means a real subset was checked but the full property is not established.
SPECIFIED ONLY and MISSING are never counted as passed implementation.

## Exact Burseg mapping — pending source

The assignment refers to eleven principles from a previously discussed Christoph Burseg post.
Neither the post nor the eleven principles were supplied or found in this checkout. The owner
was asked for the URL/list. Web search did not establish an unambiguous matching source.
Attributing invented principles would be misleading. The exact mapping is therefore incomplete.

| Referenced principle | Source text | Mapping status |
|---|---|---|
| Burseg 1 | Not supplied | MISSING |
| Burseg 2 | Not supplied | MISSING |
| Burseg 3 | Not supplied | MISSING |
| Burseg 4 | Not supplied | MISSING |
| Burseg 5 | Not supplied | MISSING |
| Burseg 6 | Not supplied | MISSING |
| Burseg 7 | Not supplied | MISSING |
| Burseg 8 | Not supplied | MISSING |
| Burseg 9 | Not supplied | MISSING |
| Burseg 10 | Not supplied | MISSING |
| Burseg 11 | Not supplied | MISSING |

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
