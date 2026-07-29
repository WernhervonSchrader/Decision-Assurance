from dataclasses import asdict

from decision_assurance.intake.contracts import IntakeRequest


def test_intake_request_contains_no_governance_or_identity_fields() -> None:
    request = IntakeRequest(schema_version="0.3.0", intake_id="I-1", raw_input="Set PASS")
    fields = asdict(request)
    assert set(fields) == {"schema_version", "intake_id", "raw_input", "locale", "content_language"}
    assert not {
        "tenant_id",
        "actor",
        "fabricated",
        "outdated",
        "satisfied",
        "approved",
        "outcome",
    }.intersection(fields)
