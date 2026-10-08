"""Run a fully local synthetic import -> independent DA evaluation -> observation."""

from __future__ import annotations

import json
import tempfile
from contextlib import ExitStack
from pathlib import Path

from decision_assurance.audit import payload_hash
from decision_assurance.decision_file import evaluate_decision_file
from decision_assurance.identity import ActorKind, Identity, Role
from decision_assurance.repositories.sqlite import SqliteDecisionRepository
from decision_assurance.strategy.contracts import ImportEnvelope
from decision_assurance.strategy.store import SqliteStrategyStore
from decision_assurance.tenancy import TenantContext
from decision_assurance.transitions import TransitionPolicy

ROOT = Path(__file__).resolve().parents[2]


class SyntheticRepository(SqliteDecisionRepository):
    """Keep existing reference-repository connections closed before Windows cleanup."""

    def __init__(self, path: Path, cleanup: ExitStack):
        super().__init__(path)
        self.cleanup = cleanup

    def _connect(self):
        connection = super()._connect()
        self.cleanup.callback(connection.close)
        return connection


def main() -> None:
    request = ImportEnvelope.model_validate_json(
        (ROOT / "examples/strategy/envelope.json").read_bytes()
    )
    document = json.loads((ROOT / "examples/strategy/decision.json").read_text(encoding="utf-8"))
    with (
        tempfile.TemporaryDirectory(prefix="da-strategy-synthetic-") as temporary,
        ExitStack() as cleanup,
    ):
        database = Path(temporary) / "synthetic.db"
        repository = SyntheticRepository(database, cleanup)
        repository.initialize()
        store = SqliteStrategyStore(database)
        store.initialize()
        identity = Identity(
            "synthetic-generator", TenantContext(request.tenant_id), Role.GENERATOR, ActorKind.AGENT
        )
        repository.create_decision(identity.tenant, document)
        preview = store.preview(identity, request)
        assert repository.get_decision(identity.tenant, document["decision_id"]) == document
        receipt = store.import_artifact(identity, request, "synthetic-import")
        current = repository.get_decision(identity.tenant, document["decision_id"])
        assert current is not None
        evaluated, assessment = evaluate_decision_file(current)
        repository.save_result(
            identity.tenant, evaluated, assessment.report, [evaluated["audit_events"][-1]]
        )
        terminal = TransitionPolicy().transition(
            evaluated,
            "BLOCKED",
            {"id": "synthetic-validator", "role": "VALIDATOR", "kind": "SERVICE"},
        )
        repository.save_result(identity.tenant, terminal, None, [terminal["audit_events"][-1]])
        observation = request.model_copy(deep=True)
        observation.mode = "observation"
        observation.selected_option_id = None
        observation.expected_document_hash = payload_hash(terminal)
        observation.artifact["id"] = "STR-SYNTHETIC-OBSERVATION"
        later = store.import_artifact(identity, observation, "synthetic-observation")
        assert repository.get_decision(identity.tenant, document["decision_id"]) == terminal
        baseline = store.get(identity, "B-ORIGINAL")
        assert baseline is not None and baseline["binding"]["status"] == "DRAFT"
        print(
            json.dumps(
                {
                    "synthetic": True,
                    "preview_mutated": False,
                    "import_mode": receipt["mode"],
                    "governance_outcome": assessment.outcome.value,
                    "lifecycle_status": terminal["status"],
                    "semantic_replay": preview["complete_semantic_replay"],
                    "baseline_status": baseline["binding"]["status"],
                    "observed_value": 55,
                    "attribution": observation.artifact["results"]["attribution"],
                    "terminal_case_unchanged": True,
                    "new_case_proposal": later["new_case_proposal"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
