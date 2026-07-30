from pathlib import Path

from decision_assurance.api.openapi import generate


def test_openapi_v05_has_no_drift_and_exposes_build_metadata(tmp_path: Path) -> None:
    generated = tmp_path / "openapi-v0.5.json"
    generate(generated, api_version="0.5.0")
    expected = Path(__file__).parents[3] / "docs" / "openapi-v0.5.json"

    assert generated.read_bytes() == expected.read_bytes()
    assert '"/version"' in generated.read_text(encoding="utf-8")
