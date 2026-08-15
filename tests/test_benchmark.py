from pathlib import Path

from decision_assurance.benchmark import run_benchmark


def test_gold_dataset_is_reproducible() -> None:
    manifest = Path(__file__).parents[1] / "benchmarks" / "dats" / "v0.1.0" / "catalog.json"
    first = run_benchmark(manifest)
    second = run_benchmark(manifest)
    assert first == second
    assert first["total"] == 10
    assert first["passed"] == 10
    assert first["failed"] == 0
