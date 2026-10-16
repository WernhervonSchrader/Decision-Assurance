from concurrent.futures import ThreadPoolExecutor

import pytest

from decision_assurance.security_benchmark.execution import ExecutionSandbox


@pytest.mark.parametrize(
    "change", ["price", "supplier", "bank", "expired", "version", "tenant", "forged"]
)
def test_changes_block_before_synthetic_effect(change: str) -> None:
    sandbox = ExecutionSandbox("tenant-a")
    grant = sandbox.approve()
    sandbox.change(change)
    result = sandbox.execute(grant)
    assert result["executed"] is False
    assert sandbox.effects == []
    assert result["audit_complete"] is True


def test_success_duplicate_and_rejected_retry() -> None:
    sandbox = ExecutionSandbox("tenant-a")
    grant = sandbox.approve()
    assert sandbox.execute(grant)["executed"] is True
    assert sandbox.execute(grant)["executed"] is False
    assert len(sandbox.effects) == 1
    denied = ExecutionSandbox("tenant-a")
    grant = denied.approve()
    denied.change("price")
    assert not denied.execute(grant)["executed"]
    denied.change("restore")
    assert not denied.execute(grant, wording="please try again")["executed"]


def test_atomic_recheck_after_validation_and_concurrent_single_use() -> None:
    sandbox = ExecutionSandbox("tenant-a")
    grant = sandbox.approve()
    result = sandbox.execute(grant, before_commit=lambda: sandbox.change("version"))
    assert not result["executed"]
    clean = ExecutionSandbox("tenant-b")
    grant = clean.approve()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: clean.execute(grant), range(2)))
    assert sum(x["executed"] for x in results) == 1


def test_failed_audit_prevents_effect_and_reports_failure() -> None:
    sandbox = ExecutionSandbox("tenant-a")
    grant = sandbox.approve()
    sandbox.audit_available = False
    result = sandbox.execute(grant)
    assert not result["executed"]
    assert not result["audit_complete"]
    assert result["error_code"] == "AUDIT_UNAVAILABLE"
