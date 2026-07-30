# CI and release verification

Decision Assurance v0.5 treats publication as a computed result, not a manually asserted label.
Every push and pull request runs formatting, lint, strict typing, unit/contract/E2E tests, Bandit,
dependency audit, build and OpenAPI drift checks. Separate jobs exercise a real PostgreSQL 16
service, forced tenant RLS, database roles and migrations; scan the complete Git history for
secrets; build all three production images and scan them for critical vulnerabilities; and restore a
native PostgreSQL backup into a fresh database before checking schema, RLS, roles and audit order.

The container job emits CycloneDX SBOMs for the API, Worker and MCP images. The release-evidence job runs
only after every required job succeeds, builds the wheel and source distribution, downloads the
SBOM and restore artifacts, and creates `SHA256SUMS`. It also reads the current GitHub Actions run
and job results through the Actions API. Gate input is `PASS` only when repository, run, commit SHA,
source-job result, step results and checksummed artifact content agree. Missing, stale, failed or
commit-mismatched evidence becomes `BLOCK`. The resulting `release-verification.json`, raw workflow
evidence and checksums are retained as CI artifacts; the workflow does not publish a package or
image.

## Fail-closed governance

`decision_assurance.release_verification.ReleaseVerifier` requires every named gate exactly once.
Missing, duplicated or unknown evidence blocks publication. A report is publication-eligible only
when its computed result is `PASS` and its ordered gate set exactly matches the mandatory set.

The following reason codes always become `BLOCK`, even if an input labels them `REVIEW`:

- `TENANT_ISOLATION_FAILURE`
- `CRITICAL_VULNERABILITY`
- `MIGRATION_FAILURE` or `RESTORE_FAILURE`
- `AUDIT_INTEGRITY_FAILURE`
- `STATIC_AUTH_PRODUCTION`
- `RESEARCH_OUTCOME_USED`
- `AGENT_APPROVAL`
- `SECRET_LEAKAGE`

Research `PASS`, `REVIEW` and `BLOCK` values are evidence-domain findings only. They cannot authorize
a release. Release approval remains a separate human-governed process after the technical report
passes. Branch protection must require all CI jobs and human review before merging or tagging.

To reproduce the report locally, prepare the gate evidence JSON and run:

```powershell
python -m scripts.release.generate_report --input gate-results.json `
  --output release-verification.json --commit-sha (git rev-parse HEAD)
```

Do not convert unavailable tooling into a passing gate. Record a missing mandatory gate and retain
the resulting `BLOCK` report until the evidence exists.
