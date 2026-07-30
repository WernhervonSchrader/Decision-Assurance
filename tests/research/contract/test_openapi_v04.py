from pathlib import Path

from decision_assurance.api.openapi import generate


def test_openapi_v04_has_no_drift(tmp_path: Path) -> None:
    generated = tmp_path / "openapi-v0.4.json"
    generate(generated)
    expected = Path(__file__).parents[3] / "docs" / "openapi-v0.4.json"
    assert generated.read_bytes() == expected.read_bytes()
