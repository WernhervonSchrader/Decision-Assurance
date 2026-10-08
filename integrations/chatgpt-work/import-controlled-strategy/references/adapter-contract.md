# Bounded contract

Read [STRATEGY-INTEGRATION.md](../../../../docs/STRATEGY-INTEGRATION.md) and [the envelope schema](../../../../schemas/strategy/import-envelope.schema.json). The optional API must be explicitly wired into the authenticated DA application.

Only POST /v1/strategy/preview, POST /v1/strategy/imports and GET /v1/strategy/artifacts/{artifact_id} are described. They are REST paths, not assumed ChatGPT tools. If no approved REST connector is available, use only the read-only strategy-preview CLI and provide its result to the authorized operator.

Keep all three RIF artifact categories, original IDs/versions/plans, baselines and observations. Preserve test method, checked subject, actual file identity/local deviations, execution status and required outcomes. Never call a missing, skipped, failed or NOT_REPRODUCED check positive verification. Expected rejection is not a technical abort.

No normative Decision File extension or hidden JSON in text fields is permitted. A hash binds data but does not authenticate human authority. Imported hard conditions remain unverified; full RIF replay and semantic verification are explicitly outside the DA adapter.
