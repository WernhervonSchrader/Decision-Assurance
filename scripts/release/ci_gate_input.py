from __future__ import annotations

import argparse
import json
from pathlib import Path

from decision_assurance.release_verification import MANDATORY_GATES

EVIDENCE = {
    "unit-quality": "ci/verify",
    "dependency-audit": "ci/verify:pip-audit",
    "secret-scan": "ci/secret-scan:gitleaks",
    "oidc-validation": "ci/verify:tests/production/identity",
    "postgresql-migrations": "ci/postgresql:migration-contract",
    "tenant-isolation": "ci/postgresql:rls-integration",
    "database-roles": "ci/postgresql:role-boundaries",
    "worker-recovery": "ci/verify:tests/production/worker",
    "production-configuration": "ci/verify:tests/production/configuration",
    "observability-health": "ci/verify:tests/production/observability",
    "container-scan": "supply-chain/trivy-results",
    "restore-verification": "ci/restore-verification",
    "controlled-pilot-e2e": "ci/verify:tests/production/e2e",
    "artifact-integrity": "release/SHA256SUMS",
}


def write_gate_input(output: Path) -> None:
    if set(EVIDENCE) != set(MANDATORY_GATES):
        raise RuntimeError("CI_RELEASE_GATE_MAPPING_INCOMPLETE")
    gates = [
        {
            "gate_id": gate_id,
            "status": "PASS",
            "reason_codes": [],
            "evidence_refs": [EVIDENCE[gate_id]],
        }
        for gate_id in MANDATORY_GATES
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(gates, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write_gate_input(args.output)


if __name__ == "__main__":
    main()
