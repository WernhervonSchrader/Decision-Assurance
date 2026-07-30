# Controlled Sales Quote Review pilot

The v0.5 pilot is a bounded operational verification profile, not general production authorization.
Its configuration is `config/pilot/sales-quote-review.json`: at most 25 users, three tenants, two
concurrent Research jobs, 100 provider cost units and 30-day retention. Only business-contact, quote
and public-web-evidence data classes are allowed. German and English are supported.

## Journey

An authenticated Generator submits untrusted German quote text. The Intake extractor proposes facts;
a human Validator confirms the claimed management approval; the verifier applies the tenant policy;
and only the Compiler creates an outcome-free Decision File. The API may queue optional Research,
which the Worker performs against deterministic provider adapters in tests. Research handoff stays
`UNVERIFIED`, retains provenance/correlation and cannot approve a Decision. The Engine alone produces
the assurance outcome. A distinct human Approver can approve only a `PASS` Decision in `REVIEW`;
agent approval and approval of a Research-induced `REVIEW` outcome are rejected.

The E2E uses two tenants with the same Intake and Decision identifiers to prove isolation. It checks
local OIDC, German messages/English fallback, audit continuity, correlation, metrics, provider-call
separation and terminal governance. Backup/restore and post-restore RLS are separate mandatory CI
gates because restore is an environment operation, not an API user step.

## Stop and escalation

Stop automated processing immediately on tenant-isolation failure, unbounded provider cost, audit
integrity failure or secret disclosure. Cancel queued jobs, preserve sanitized evidence, notify the
pilot owner and security contact, and follow `docs/INCIDENT-RESPONSE.md`. Do not expand users, tenants,
data classes, providers, budgets or retention without a reviewed profile change and new evidence.
