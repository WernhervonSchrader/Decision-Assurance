from __future__ import annotations

import re
from dataclasses import replace

from .contracts import ResearchRun

_WORDS = re.compile(r"[a-z0-9]+")
_NEGATION_PAIRS = (
    (" is required", " is not required"),
    (" must ", " must not "),
    (" shall ", " shall not "),
    (" is allowed", " is prohibited"),
)
_STOP_WORDS = {"a", "an", "and", "is", "not", "the", "to", "must", "shall"}


def _core(value: str) -> set[str]:
    return {item for item in _WORDS.findall(value.casefold()) if item not in _STOP_WORDS}


def _contradicts(left: str, right: str) -> bool:
    left_value, right_value = f" {left.casefold()} ", f" {right.casefold()} "
    explicit = any(
        (positive in left_value and negative in right_value)
        or (negative in left_value and positive in right_value)
        for positive, negative in _NEGATION_PAIRS
    )
    if not explicit:
        return False
    left_core, right_core = _core(left), _core(right)
    overlap = left_core.intersection(right_core)
    return bool(overlap) and len(overlap) / max(1, min(len(left_core), len(right_core))) >= 0.5


def mark_conflicting_evidence(run: ResearchRun) -> None:
    """Mark only explicit lexical contradictions; never resolve which source is true."""

    snapshots = {item.snapshot_id: item for item in run.snapshots}
    conflicting: set[str] = set()
    for index, left in enumerate(run.evidence):
        for right in run.evidence[index + 1 :]:
            if not set(left.claim_refs).intersection(right.claim_refs):
                continue
            left_snapshot = snapshots.get(left.snapshot_id)
            right_snapshot = snapshots.get(right.snapshot_id)
            if (
                left_snapshot
                and right_snapshot
                and _contradicts(left_snapshot.text, right_snapshot.text)
            ):
                conflicting.update((left.evidence_id, right.evidence_id))
    if not conflicting:
        return
    source_ids: set[str] = set()
    for index, item in enumerate(run.evidence):
        if item.evidence_id not in conflicting:
            continue
        source_ids.add(item.source_id)
        assessment = replace(
            item.assessment,
            conflict_status="CONFLICTING",
            requires_human_review=True,
            reason_codes=tuple(
                dict.fromkeys((*item.assessment.reason_codes, "CONFLICTING_EVIDENCE"))
            ),
        )
        run.evidence[index] = replace(item, assessment=assessment)
    for source in run.sources:
        if source.source_id in source_ids:
            source.status = "REVIEW_REQUIRED"
            source.reason_codes = tuple(
                dict.fromkeys((*source.reason_codes, "CONFLICTING_EVIDENCE"))
            )
