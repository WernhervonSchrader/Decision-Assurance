from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any, cast

from .contracts import (
    ContentRisk,
    EvidenceAssessment,
    EvidenceCandidate,
    FreshnessPolicy,
    Provenance,
    ProviderError,
    ResearchAttempt,
    ResearchAuditEvent,
    ResearchError,
    ResearchRequest,
    ResearchRun,
    ResearchStatus,
    SourceCandidate,
    SourceSnapshot,
)


def to_data(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: to_data(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, dict):
        return {str(key): to_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_data(item) for item in value]
    return value


def run_from_data(raw: dict[str, Any]) -> ResearchRun:
    request_raw = cast(dict[str, Any], raw["request"])
    freshness_raw = cast(dict[str, Any], request_raw["freshness"])
    request = ResearchRequest(
        decision_file_id=str(request_raw["decision_file_id"]),
        claim_refs=tuple(request_raw["claim_refs"]),
        query=str(request_raw["query"]),
        locale=str(request_raw["locale"]),
        preferred_languages=tuple(request_raw["preferred_languages"]),
        max_search_results=int(request_raw["max_search_results"]),
        max_sources_to_extract=int(request_raw["max_sources_to_extract"]),
        allowed_domains=tuple(request_raw["allowed_domains"]),
        blocked_domains=tuple(request_raw["blocked_domains"]),
        freshness=FreshnessPolicy(
            int(freshness_raw["maximum_age_days"]), bool(freshness_raw["prefer_recent"])
        ),
        research_policy=str(request_raw["research_policy"]),
        force_refresh=bool(request_raw["force_refresh"]),
        schema_version=str(request_raw["schema_version"]),
    )
    sources = [
        SourceCandidate(**{**item, "reason_codes": tuple(item["reason_codes"])})
        for item in raw.get("sources", [])
    ]
    snapshots = [
        SourceSnapshot(
            **{
                **item,
                "risk": ContentRisk(
                    **{
                        **item["risk"],
                        "risk_reasons": tuple(item["risk"]["risk_reasons"]),
                    }
                ),
            }
        )
        for item in raw.get("snapshots", [])
    ]
    evidence = [
        EvidenceCandidate(
            **{
                **item,
                "claim_refs": tuple(item["claim_refs"]),
                "assessment": EvidenceAssessment(
                    **{
                        **item["assessment"],
                        "reason_codes": tuple(item["assessment"]["reason_codes"]),
                    }
                ),
                "provenance": Provenance(**item["provenance"]),
                "risk": ContentRisk(
                    **{
                        **item["risk"],
                        "risk_reasons": tuple(item["risk"]["risk_reasons"]),
                    }
                ),
            }
        )
        for item in raw.get("evidence", [])
    ]
    attempts = [ResearchAttempt(**item) for item in raw.get("attempts", [])]
    errors = [
        ResearchError(
            reason_code=item["reason_code"],
            provider=ProviderError(**item["provider"]) if item.get("provider") else None,
            source_id=item.get("source_id"),
        )
        for item in raw.get("errors", [])
    ]
    audit_events = [
        ResearchAuditEvent(
            **{
                **item,
                "from_status": ResearchStatus(item["from_status"]),
                "to_status": ResearchStatus(item["to_status"]),
                "reason_codes": tuple(item["reason_codes"]),
                "schema_version": item.get("schema_version", "research-audit-v1"),
                "decision": item.get("decision"),
                "operating_profile": item.get("operating_profile"),
                "policy_version": item.get("policy_version"),
                "provider": item.get("provider"),
                "connector": item.get("connector"),
                "target_host": item.get("target_host"),
                "requested_processing_location": item.get("requested_processing_location"),
                "evidence_id": item.get("evidence_id"),
                "evidence_status": item.get("evidence_status"),
            }
        )
        for item in raw.get("audit_events", [])
    ]
    return ResearchRun(
        research_run_id=str(raw["research_run_id"]),
        tenant_id=str(raw["tenant_id"]),
        actor_id=str(raw["actor_id"]),
        request=request,
        expected_document_hash=str(raw["expected_document_hash"]),
        semantic_fingerprint=str(raw["semantic_fingerprint"]),
        status=ResearchStatus(str(raw["status"])),
        created_at=str(raw["created_at"]),
        updated_at=str(raw["updated_at"]),
        correlation_id=str(raw["correlation_id"]),
        sources=sources,
        snapshots=snapshots,
        evidence=evidence,
        attempts=attempts,
        errors=errors,
        audit_events=audit_events,
        provider_cost_units=int(raw.get("provider_cost_units", 0)),
        compiled_decision_file_id=cast(str | None, raw.get("compiled_decision_file_id")),
    )
