from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .decision_file import load_decision_file


class CaseStore:
    """Vendor-neutral filesystem interface with atomic single-writer updates."""

    SUBDIRECTORIES = ("evidence", "validation", "review", "reports", "audit")

    def __init__(self, root: Path):
        self.root = root

    def case_path(self, decision_id: str) -> Path:
        return self.root / decision_id

    def create(self, document: dict[str, Any]) -> Path:
        case = self.case_path(document["decision_id"])
        case.mkdir(parents=True, exist_ok=False)
        for name in self.SUBDIRECTORIES:
            (case / name).mkdir()
        self.save(document)
        (case / "audit" / "events.jsonl").touch()
        return case

    def load(self, decision_id: str) -> dict[str, Any]:
        return load_decision_file(self.case_path(decision_id) / "decision.json")

    def save(self, document: dict[str, Any]) -> None:
        case = self.case_path(document["decision_id"])
        target = case / "decision.json"
        temporary = case / ".decision.json.tmp"
        temporary.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        os.replace(temporary, target)

    def append_audit_event(self, decision_id: str, event: dict[str, Any]) -> None:
        path = self.case_path(decision_id) / "audit" / "events.jsonl"
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")

    def write_assurance_report(self, decision_id: str, report: dict[str, Any]) -> Path:
        path = self.case_path(decision_id) / "reports" / "assurance-report.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path
