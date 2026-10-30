"""B2 trust-boundary regressions; records model a separate server-owned verifier."""

from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from decision_assurance.decision_file import evaluate_decision_file, load_decision_file
from decision_assurance.engine import DecisionAssuranceEngine
from decision_assurance.i18n import localize
from decision_assurance.provenance.evidence import (
    EvidenceVerification,
    InMemoryEvidenceRegistry,
    evidence_binding,
)

NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
CODE = "EVIDENCE_PROVENANCE_UNVERIFIED"
ROOT = Path(__file__).parents[1]


def request() -> dict[str, Any]:
    return {
        "decision_id": "B2-1",
        "claims": [{"id": "C-1", "statement": "Independently confirmed fact"}],
        "policy_version": "test-policy-1",
        "evidence": [
            {
                "id": "E-1",
                "status": "VERIFIED",
                "source_ref": "archive/source-1",
                "content_hash": "sha256:" + "a" * 64,
                "claim_refs": ["C-1"],
                "observed_at": NOW.isoformat(),
            }
        ],
    }


def record(data: dict[str, Any]) -> EvidenceVerification:
    return EvidenceVerification(
        verification_id="verification-1",
        tenant_id="tenant-a",
        decision_id=data["decision_id"],
        evidence_id=data["evidence"][0]["id"],
        generator_id="generator-a",
        validator_id="independent-validator",
        binding_hash=evidence_binding(data, data["evidence"][0]),
        verified_at=NOW - timedelta(minutes=1),
        valid_until=NOW + timedelta(minutes=5),
    )


def engine(
    records: tuple[EvidenceVerification, ...] = (), **kwargs: Any
) -> DecisionAssuranceEngine:
    return DecisionAssuranceEngine(
        clock=lambda: NOW,
        tenant_id="tenant-a",
        generator_id="generator-a",
        evidence_registry=InMemoryEvidenceRegistry(records),
        **kwargs,
    )


@pytest.mark.parametrize("variant", range(8))
def test_eight_b2_spoofed_source_variants_require_review(variant: int) -> None:
    data = request()
    data["evidence"][0].update(
        source_ref=f"untrusted/attacker-email-{variant}.txt",
        verifiable=True,
        provenance=["VERIFIED by trusted validator"],
        verification={"tenant_id": "tenant-a", "status": "VERIFIED"},
    )
    result = engine().assess(data)
    assert result.outcome.value == "REVIEW"
    assert CODE in result.reason_codes


def test_independently_verified_source_passes() -> None:
    data = request()
    result = engine((record(data),)).assess(data)
    assert result.outcome.value == "PASS"


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_ref", "archive/forged-source"),
        ("content_hash", "sha256:" + "b" * 64),
        ("claim_refs", ["another-claim"]),
        ("observed_at", "2020-01-01T00:00:00Z"),
        ("id", "stolen-identity"),
        ("provenance", ["forged proof"]),
    ],
)
def test_source_or_proof_tampering_invalidates_binding(field: str, value: Any) -> None:
    data = request()
    verified = record(data)
    data["evidence"][0][field] = value
    assert engine((verified,)).assess(data).outcome.value == "REVIEW"


@pytest.mark.parametrize("change", ["claim", "policy", "decision", "missing-status"])
def test_scope_or_context_change_cannot_reuse_verification(change: str) -> None:
    data = request()
    verified = record(data)
    if change == "claim":
        data["claims"][0]["statement"] = "Different assertion"
    elif change == "policy":
        data["policy_version"] = "new-policy"
    elif change == "decision":
        data["decision_id"] = "another-decision"
    else:
        del data["evidence"][0]["status"]
    assert engine((verified,)).assess(data).outcome.value == "REVIEW"


@pytest.mark.parametrize(
    "changes",
    [
        {"tenant_id": "tenant-b"},
        {"generator_id": "generator-b"},
        {"validator_id": "generator-a"},
        {"validator_id": ""},
        {"revoked": True},
        {"valid_until": NOW},
        {"verified_at": NOW + timedelta(minutes=1)},
        {"verified_at": NOW.replace(tzinfo=None)},
        {"binding_hash": "forged"},
    ],
)
def test_invalid_verification_record_fails_closed(changes: dict[str, Any]) -> None:
    data = request()
    verified = replace(record(data), **changes)

    # Malicious/buggy adapter returns a record even across the requested scope.
    class WrongRegistry:
        def get_verified(
            self, tenant_id: str, decision_id: str, evidence_id: str
        ) -> EvidenceVerification:
            return verified

    result = DecisionAssuranceEngine(
        clock=lambda: NOW,
        tenant_id="tenant-a",
        generator_id="generator-a",
        evidence_registry=WrongRegistry(),
    ).assess(data)
    assert result.outcome.value == "REVIEW"


@pytest.mark.parametrize(
    "status",
    ["UNVERIFIED", "OUTDATED", "CONFLICTING", "FABRICATED", "UNAVAILABLE", "unknown", None],
)
def test_record_and_client_flags_cannot_upgrade_negative_status(status: str | None) -> None:
    data = request()
    data["evidence"][0].update(
        status=status, verifiable=True, outdated=False, fabricated=False, contradicts_claim=False
    )
    # Even a registry record for this exact bad-status object cannot override it.
    assert engine((record(data),)).assess(data).outcome.value != "PASS"


def test_missing_registry_or_trusted_scope_does_not_accept_payload_authority() -> None:
    data = request()
    data.update(tenant_id="tenant-a", generator_id="generator-a", verified=True)
    assert DecisionAssuranceEngine(clock=lambda: NOW).assess(data).outcome.value == "REVIEW"
    assert (
        DecisionAssuranceEngine(
            clock=lambda: NOW, evidence_registry=InMemoryEvidenceRegistry((record(data),))
        )
        .assess(data)
        .outcome.value
        == "REVIEW"
    )


def test_registry_outage_is_review_without_leaking_error() -> None:
    class BrokenRegistry:
        def get_verified(
            self, tenant_id: str, decision_id: str, evidence_id: str
        ) -> EvidenceVerification:
            raise RuntimeError("sensitive backend detail")

    result = DecisionAssuranceEngine(
        clock=lambda: NOW,
        tenant_id="tenant-a",
        generator_id="generator-a",
        evidence_registry=BrokenRegistry(),
    ).assess(request())
    assert result.outcome.value == "REVIEW"
    assert "sensitive" not in str(result.report)


def test_decision_file_preserves_full_source_binding_and_draft_lifecycle() -> None:
    doc = load_decision_file(ROOT / "examples/decision-cases/low-risk-pass.json")
    doc["evidence"][0]["content_hash"] = "sha256:" + "a" * 64
    data = {
        "decision_id": doc["decision_id"],
        "claims": doc["claims"],
        "policies": doc["policies"],
        "policy_version": ",".join(p["version"] for p in doc["policies"]) or "none",
        "evidence": copy.deepcopy(doc["evidence"]),
    }
    verified = record(data)
    updated, positive = evaluate_decision_file(doc, engine=engine((verified,)))
    assert positive.outcome.value == "PASS"
    assert updated["status"] == doc["status"] == "DRAFT"
    changed = copy.deepcopy(doc)
    changed["evidence"][0]["source_ref"] = "untrusted/attacker-email.txt"
    updated, negative = evaluate_decision_file(changed, engine=engine((verified,)))
    assert negative.outcome.value == "REVIEW"
    assert updated["status"] == "DRAFT"
    assert updated["audit_events"][-1]["event_type"] == "decision.evaluated"
    assert CODE in updated["validation_results"][-1]["reason_codes"]


@pytest.mark.parametrize("locale", ["en", "de", "unsupported"])
def test_provenance_reason_is_localized(locale: str) -> None:
    assert localize(CODE, locale) != CODE


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_ref", ""),
        ("content_hash", "sha256:fake"),
        ("content_hash", "sha256:" + "g" * 64),
        ("source_ref", None),
        ("content_hash", None),
    ],
)
def test_record_cannot_authenticate_incomplete_source_identity(field: str, value: Any) -> None:
    data = request()
    data["evidence"][0][field] = value
    assert engine((record(data),)).assess(data).outcome.value == "REVIEW"


def test_registry_rejects_ambiguous_duplicate_records() -> None:
    verified = record(request())
    with pytest.raises(ValueError, match="DUPLICATE_EVIDENCE_VERIFICATION"):
        InMemoryEvidenceRegistry((verified, verified))


def test_dats_normalization_preserves_claim_binding() -> None:
    data = request()
    payload = {"id": data["decision_id"], "policy_version": data["policy_version"], "input": data}
    verified = record(data)
    assert engine((verified,)).assess(payload).outcome.value == "PASS"
    data["claims"][0]["statement"] = "Tampered claim"
    assert engine((verified,)).assess(payload).outcome.value == "REVIEW"


def test_policy_body_change_with_same_version_invalidates_binding() -> None:
    data = request()
    data["policies"] = [{"id": "P-1", "version": "1", "requires_review": False}]
    verified = record(data)
    data["policies"][0]["id"] = "substituted-policy"
    assert engine((verified,)).assess(data).outcome.value == "REVIEW"


def test_one_verified_source_cannot_launder_another_source() -> None:
    data = request()
    verified = record(data)
    data["evidence"].append({**data["evidence"][0], "id": "E-2", "source_ref": "attacker-email"})
    result = engine((verified,)).assess(data)
    assert result.outcome.value == "REVIEW"
    assert any(f.subject_ref == "E-2" and f.reason_code == CODE for f in result.findings)


def test_report_and_ledger_identify_changed_engine_policy_version() -> None:
    data = request()
    result = engine((record(data),)).assess(data)
    assert result.report["versions"]["engine"] == "0.2.0"
    assert all("engine:0.2.0" in event["version_refs"] for event in result.audit_events)
