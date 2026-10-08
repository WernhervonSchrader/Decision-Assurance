from __future__ import annotations

import copy
from typing import Any

from ..audit import payload_hash
from ..decision_file import validate_semantics
from ..identity import Identity
from ..validation import ContractValidator
from .contracts import ImportEnvelope, test_report_reasons
from .validation import hard_status, validate_import


def preview_document(
    identity: Identity, envelope: ImportEnvelope, document: dict[str, Any]
) -> dict[str, Any]:
    """Pure conservative mapping. Callers supply identity from a trusted boundary."""
    if identity.tenant.tenant_id != envelope.tenant_id:
        raise PermissionError("STRATEGY_TENANT_MISMATCH")
    if document["decision_id"] != envelope.decision_id:
        raise ValueError("STRATEGY_CASE_MISMATCH")
    if payload_hash(document) != envelope.expected_document_hash:
        raise ValueError("STRATEGY_DOCUMENT_CHANGED")
    if envelope.mode == "draft" and document["status"] != "DRAFT":
        raise ValueError("STRATEGY_DECISION_NOT_DRAFT")
    if envelope.mode == "draft" and document["decision_outcome"] is not None:
        raise ValueError("STRATEGY_EVALUATED_DRAFT_REQUIRES_NEW_CASE")
    ContractValidator().validate("decision-file", document)
    validate_semantics(document)
    validate_import(envelope)
    artifact = envelope.artifact
    result = copy.deepcopy(document)
    mapping: list[dict[str, str]] = []
    prefix = "strategy:" + payload_hash(artifact)[7:31] + ":"
    reasons = ["STRATEGY_ANALYSIS_UNVERIFIED", "STRATEGY_FULL_REPLAY_NOT_PERFORMED"]
    subjects: dict[str, str | None] = {}

    def index_subjects(value: Any, path: str = "") -> None:
        if isinstance(value, dict):
            if "id" in value and isinstance(value["id"], str):
                digest = payload_hash(value)
                subjects[path] = digest
                key = value["id"]
                if key in subjects and subjects[key] != digest:
                    subjects[key] = None  # bare IDs shared by different versions are ambiguous
                else:
                    subjects[key] = digest
            for key, item in value.items():
                index_subjects(item, path + "/" + key)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                index_subjects(item, path + "/" + str(index))

    index_subjects(artifact)
    subjects[envelope.decision_id] = envelope.expected_document_hash
    known_subjects = {key for key, digest in subjects.items() if digest is not None}
    reasons.extend(test_report_reasons(envelope.provenance.test_reports, known_subjects))
    test_bindings = [
        {
            "report_id": report.id,
            "subjects": [
                {
                    "check_id": check.id,
                    "subject_ref": check.subject_ref,
                    "subject_hash": subjects.get(check.subject_ref or "")
                    or report.file_hashes.get(check.subject_ref or ""),
                }
                for check in report.checks
            ],
        }
        for report in envelope.provenance.test_reports
    ]
    baseline = artifact if envelope.mode == "baseline" else artifact["baseline"]
    if baseline is not None and baseline["original_decision"]["id"] != envelope.decision_id:
        raise ValueError("STRATEGY_BASELINE_CASE_MISMATCH")
    if envelope.mode == "draft":
        request = artifact["request"]

        def add(section: str, source_id: str, value: dict[str, Any]) -> str:
            target = prefix + section + ":" + source_id
            if any(item["id"] == target for item in result[section]):
                raise ValueError("STRATEGY_MAPPING_ID_COLLISION")
            result[section].append({"id": target, **value})
            mapping.append({"section": section, "source_id": source_id, "target_id": target})
            return target

        claim_targets = {
            claim["id"]: add(
                "claims",
                claim["id"],
                {"statement": claim["text"], "mandatory_evidence": claim["material"]},
            )
            for claim in request["claims"]
        }
        source_records = {
            s["id"]: s
            for s in request["evidence"]["sources"] + (request["evidence"].get("full_pool") or [])
        }
        for source_id, source in source_records.items():
            claim_refs = [
                claim_targets[c["id"]] for c in request["claims"] if source_id in c["source_ids"]
            ]
            if not claim_refs:
                # No invented evidence-to-claim relationship: original still retains the source.
                continue
            add(
                "evidence",
                source_id,
                {
                    "claim_refs": claim_refs,
                    "source_ref": "strategy:" + artifact["id"] + ":source:" + source_id,
                    "status": "CONFLICTING" if source["stance"] == "contradicts" else "UNVERIFIED",
                    "content_hash": payload_hash(source),
                },
            )
        for assumption in request["assumptions"] or []:
            add(
                "assumptions",
                assumption["id"],
                {"statement": assumption["statement"], "status": "UNVERIFIED"},
            )
            if assumption["counterevidence_ids"]:
                add(
                    "conflicts",
                    assumption["id"],
                    {
                        "severity": "MEDIUM",
                        "resolved": False,
                        "description": assumption["statement"],
                    },
                )
        if request["options"]:
            option = next(
                o for o in request["options"]["options"] if o["id"] == envelope.selected_option_id
            )
            supplied = next(o for o in artifact["results"]["options"] if o["id"] == option["id"])
            for condition in request["options"]["hard_conditions"]:
                state = hard_status(condition, option["hard_values"].get(condition["id"]))
                violated = (
                    state == "violated" or supplied["conditions"][condition["id"]] == "violated"
                )
                reason = (
                    "STRATEGY_HARD_CONDITION_VIOLATED"
                    if violated
                    else "STRATEGY_HARD_CONDITION_UNVERIFIED"
                )
                add(
                    "constraints",
                    condition["id"],
                    {"severity": "MANDATORY", "satisfied": False, "reason_code": reason},
                )
                reasons.append(reason)
        add("risks", artifact["id"], {"level": "MEDIUM", "unresolved": True})
        add(
            "constraints",
            "analysis-completeness",
            {
                "severity": "REVIEW_REQUIRED",
                "satisfied": False,
                "reason_code": "STRATEGY_FULL_REPLAY_NOT_PERFORMED",
            },
        )
    ContractValidator().validate("decision-file", result)
    validate_semantics(result)
    return {
        "adapter_version": envelope.adapter_version,
        "artifact_id": artifact["id"],
        "document": result,
        "mapping": mapping,
        "reason_codes": sorted(set(reasons)),
        "complete_semantic_replay": False,
        "test_reports": [r.model_dump() for r in envelope.provenance.test_reports],
        "test_subject_bindings": test_bindings,
        "baseline_ref": baseline["id"] if baseline else None,
        "new_case_proposal": envelope.mode == "observation",
    }
