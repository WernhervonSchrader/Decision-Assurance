# API Guide — Public Draft v0.4

The Decision API remains defined by [DA-API-v0.2](specifications/DA-API-v0.2.md) and the
Intake boundary by [DA-INTAKE-v0.3](specifications/DA-INTAKE-v0.3.md), and Research by
[DA-WEB-RESEARCH-v0.4](specifications/DA-WEB-RESEARCH-v0.4.md), with generated
[OpenAPI JSON](openapi-v0.4.json). All `/v1` endpoints require a
Bearer identity except health checks. Identity establishes tenant, actor, role
and human/agent kind; `tenant_id` is never accepted from a body.

Intake endpoints are `POST /v1/intakes`, `GET /v1/intakes/{id}`,
`POST /v1/intakes/{id}/confirmations`, and `POST /v1/intakes/{id}/compile`.
Authorized auditors can retrieve the append-only Intake trail through
`GET /v1/intakes/{id}/audit`.
Compilation returns a DRAFT Decision File with a null outcome. Evaluation remains exclusively
on the existing `POST /v1/decisions/{id}/evaluate` endpoint.

Every write requires `Idempotency-Key` (1–128 characters). Repeating the same
operation and payload returns the stored status/body; changing the payload under
the same key returns `409`. `Accept-Language` supports `de` and `en`, falling
back to English. `X-Correlation-ID` is accepted or generated and returned.

The static token adapter and `config/identities.example.json` exist only for a
controlled local reference run. They do not validate JWTs and must be replaced
by an OIDC adapter before exposed deployment.

# Research API v0.4

`POST /v1/research-runs` and the run `GET`, `sources`, `evidence`, `audit`, `retry`, and `cancel`
routes are authenticated and tenant-derived. Writes require `Idempotency-Key`; list routes use
bounded `limit`/`offset`. Bodies reject tenant, actor and credential fields. Cross-tenant IDs return
the same `404` as absent IDs. `force_refresh` requires `TENANT_ADMIN` plus `refresh_generation`.
Responses contain normalized metadata and reason codes, never snapshots, extracted text,
credentials or provider response bodies. See `docs/openapi-v0.4.json`.

