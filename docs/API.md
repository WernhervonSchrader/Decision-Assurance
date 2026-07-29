# API Guide — Public Draft v0.3

The Decision API remains defined by [DA-API-v0.2](specifications/DA-API-v0.2.md) and the
new Intake boundary by [DA-INTAKE-v0.3](specifications/DA-INTAKE-v0.3.md), with generated
[OpenAPI JSON](openapi-v0.3.json). All `/v1` endpoints require a
Bearer identity except health checks. Identity establishes tenant, actor, role
and human/agent kind; `tenant_id` is never accepted from a body.

Intake endpoints are `POST /v1/intakes`, `GET /v1/intakes/{id}`,
`POST /v1/intakes/{id}/confirmations`, and `POST /v1/intakes/{id}/compile`.
Compilation returns a DRAFT Decision File with a null outcome. Evaluation remains exclusively
on the existing `POST /v1/decisions/{id}/evaluate` endpoint.

Every write requires `Idempotency-Key` (1–128 characters). Repeating the same
operation and payload returns the stored status/body; changing the payload under
the same key returns `409`. `Accept-Language` supports `de` and `en`, falling
back to English. `X-Correlation-ID` is accepted or generated and returned.

The static token adapter and `config/identities.example.json` exist only for a
controlled local reference run. They do not validate JWTs and must be replaced
by an OIDC adapter before exposed deployment.

