import pytest

from decision_assurance.production.contracts import (
    GateResult,
    JobStatus,
    OidcPolicy,
    PilotProfile,
    ReleaseStatus,
    ReleaseVerificationReport,
    SecretValue,
)


def test_release_status_blocks_on_any_blocking_gate() -> None:
    report = ReleaseVerificationReport(
        version="0.5.0",
        commit_sha="a" * 40,
        generated_at="2026-07-30T00:00:00Z",
        gates=(
            GateResult("tests", ReleaseStatus.PASS, (), ("pytest.xml",)),
            GateResult(
                "tenant-isolation",
                ReleaseStatus.BLOCK,
                ("RLS_ISOLATION_FAILED",),
                ("rls.xml",),
            ),
        ),
    )

    assert report.status is ReleaseStatus.BLOCK


def test_release_gate_cannot_pass_without_evidence() -> None:
    with pytest.raises(ValueError, match="RELEASE_GATE_EVIDENCE_REQUIRED"):
        GateResult("tests", ReleaseStatus.PASS, (), ())


def test_pilot_profile_cannot_disable_human_approval() -> None:
    with pytest.raises(ValueError, match="HUMAN_APPROVAL_REQUIRED"):
        PilotProfile(
            "sales-quote-pilot",
            "Sales Quote Review",
            25,
            2,
            100,
            2,
            ("de", "en"),
            ("openai-web-search", "firecrawl"),
            ("business-confidential",),
            90,
            ("background-research",),
            "Escalate to the pilot owner.",
            ("tenant-isolation-failure",),
            human_approval_required=False,
        )


def test_oidc_policy_is_https_and_algorithm_allowlisted() -> None:
    assert OidcPolicy("https://id.example", "decision-assurance", ("RS256",)).tenant_claim == (
        "tenant_id"
    )
    with pytest.raises(ValueError, match="INVALID_OIDC_ALGORITHM_ALLOWLIST"):
        OidcPolicy("https://id.example", "decision-assurance", ("HS256",))


def test_oidc_policy_allows_http_only_for_explicit_loopback_development() -> None:
    policy = OidcPolicy(
        "http://127.0.0.1:8080/realms/decision-assurance",
        "decision-assurance-api",
        ("RS256",),
        allow_insecure_loopback=True,
    )
    assert policy.allow_insecure_loopback

    with pytest.raises(ValueError, match="INVALID_OIDC_TRUST_CONFIGURATION"):
        OidcPolicy(
            "http://identity.example/realms/decision-assurance",
            "decision-assurance-api",
            ("RS256",),
            allow_insecure_loopback=True,
        )


def test_secret_repr_is_always_redacted_and_job_status_has_no_assurance_outcomes() -> None:
    assert repr(SecretValue("not-a-real-secret")) == "SecretValue(**redacted**)"
    assert not {item.value for item in JobStatus} & {"PASS", "REVIEW", "BLOCK", "APPROVED"}
