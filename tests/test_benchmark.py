from pathlib import Path

from decision_assurance.benchmark import run_benchmark


def test_gold_dataset_is_reproducible() -> None:
    manifest = Path(__file__).parent / "gold" / "manifest.json"
    first = run_benchmark(manifest)
    second = run_benchmark(manifest)
    assert first == second
    assert first["total"] == 10
    assert first["passed"] == 10
    assert first["failed"] == 0

