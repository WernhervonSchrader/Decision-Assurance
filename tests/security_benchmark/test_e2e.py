import copy
import gc
import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from decision_assurance.decision_file import bind_canonical_action
from decision_assurance.security_benchmark.adapters import api_harness, decision_fixture, headers
from decision_assurance.security_benchmark.cases import own_cases, smoke_cases
from decision_assurance.security_benchmark.contracts import ROOT, SCHEMA
from decision_assurance.security_benchmark.reporting import (
    format_number,
    locale_name,
    markdown_report,
)
from decision_assurance.security_benchmark.runner import run_cases
from decision_assurance.security_benchmark.streaming import run_streaming


@pytest.mark.parametrize("tenant,locale", [("tenant-a", "en"), ("tenant-b", "de")])
def test_real_api_authentication_roles_tenants_validation_and_audit(
    tmp_path: Path, tenant: str, locale: str
) -> None:
    case = copy.deepcopy(own_cases("smoke")[0])
    case.update(tenant_id=tenant, locale=locale)
    doc = decision_fixture(case)
    with api_harness(tmp_path / "journey.sqlite", tenant)[0] as client:
        assert client.get("/v1/decisions").status_code == 401
        assert (
            client.get("/v1/decisions", headers=headers("expired-test-identity", "x")).status_code
            == 401
        )
        first = client.post("/v1/decisions", json=doc, headers=headers("gen", "create", locale))
        assert first.status_code == 201
        repeated = client.post("/v1/decisions", json=doc, headers=headers("gen", "create", locale))
        assert repeated.status_code == 201
        assert first.json() == repeated.json()
        path = "/v1/decisions/" + doc["decision_id"]
        assert client.get(path, headers=headers("other", "read")).status_code == 404
        assert client.get("/v1/decisions", headers=headers("other", "list")).json()["items"] == []
        assert client.post(path + "/evaluate", headers=headers("gen", "eval")).status_code == 403
        assert client.post(path + "/evaluate", headers=headers("val", "eval")).status_code == 200
        assert (
            client.post(
                path + "/transitions",
                json={"target": "APPROVED"},
                headers=headers("gen", "approve"),
            ).status_code
            == 403
        )
        tampered = copy.deepcopy(doc)
        tampered["canonical_action"]["tenant_id"] = "tenant-other"
        assert (
            client.post("/v1/decisions", json=tampered, headers=headers("gen", "cross")).status_code
            == 422
        )
        tampered["canonical_action"] = bind_canonical_action(tampered["canonical_action"])
        assert (
            client.post(
                "/v1/decisions", json=tampered, headers=headers("gen", "cross-bound")
            ).status_code
            == 403
        )
        malformed = dict(doc, unexpected="data")
        assert (
            client.post(
                "/v1/decisions", json=malformed, headers=headers("gen", "invalid")
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/v1/decisions", json=malformed, headers=headers("gen", "create")
            ).status_code
            == 409
        )
        audit = client.get(path + "/audit", headers=headers("aud", "audit")).json()["items"]
        assert [e["event_type"] for e in audit] == ["decision.created", "decision.evaluated"]
        assert all(e["tenant_id"] == tenant for e in audit)
    gc.collect()


def test_schema_and_translation_catalogs_have_no_drift() -> None:
    assert (
        SCHEMA.read_bytes()
        == (ROOT / "benchmarks/security/schemas/security-case.schema.json").read_bytes()
    )
    catalog = json.loads(
        (ROOT / "src/decision_assurance/security_benchmark/locales.json").read_text(encoding="utf8")
    )
    assert catalog["en"].keys() == catalog["de"].keys()
    assert catalog["en"]["metrics"].keys() == catalog["de"]["metrics"].keys()
    assert locale_name("fr-FR") == "en"
    assert format_number(10000, "de") == "10.000"
    assert format_number(0.125, "de", percentage=True) == "12,50 %"
    assert format_number(0.125, "en", percentage=True) == "12.50%"


def test_offline_smoke_never_contacts_external_endpoints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Network must remain disabled")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    report = run_cases(smoke_cases(), tmp_path, payload_root=ROOT / "benchmarks/security/fixtures")
    assert 20 <= report["total_cases"] <= 50
    assert report["counts"]["TEST_ERROR"] == report["counts"]["INFRASTRUCTURE_ERROR"] == 0
    assert report["counts"]["INCONCLUSIVE"] > 0
    assert "Security-Benchmark-Bericht" in markdown_report(report, "de")
    assert "Security Benchmark Report" in markdown_report(report, "en")


def test_cli_exports_reports_and_does_not_greenwash_known_findings(tmp_path: Path) -> None:
    command = [
        sys.executable,
        "-m",
        "decision_assurance.security_benchmark",
        "run",
        "--output",
        str(tmp_path),
        "--locale",
        "de",
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)  # noqa: S603
    assert result.returncode == 2, result.stdout + result.stderr
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["counts"]["SECURITY_FAILURE"] > 0
    assert report["counts"]["INFRASTRUCTURE_ERROR"] == 0
    assert report["dataset_revision"] == "1063bdf01ec8762b812d5e06ee768a06faa5a6f7"
    assert "Security-Benchmark-Bericht" in (tmp_path / "report.md").read_text(encoding="utf8")
    accepted = subprocess.run(  # noqa: S603 - fixed module and test-owned paths
        command + ["--baseline", str(tmp_path / "report.json")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )  # noqa: S603
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert json.loads((tmp_path / "report.json").read_text())["counts"]["SECURITY_FAILURE"] > 0


def test_full_streaming_batches_match_small_run_and_resume(tmp_path: Path) -> None:
    cases = own_cases("smoke")
    report = run_streaming(cases, tmp_path / "stream", payload_root=tmp_path, batch_size=3)
    ordinary = run_cases(cases, tmp_path / "ordinary", profile="full")
    assert report["counts"] == ordinary["counts"]
    assert report["metrics"] == ordinary["metrics"]
    assert report["case_set_sha256"] == ordinary["case_set_sha256"]
    resumed = run_streaming(cases, tmp_path / "stream", payload_root=tmp_path, batch_size=3)
    assert resumed["checkpoint_reused_cases"] == len(cases)
    processing = {"checkpoint_reused_cases", "fresh_case_measurements", "fresh_security_components"}
    assert {k: v for k, v in resumed.items() if k not in processing} == {
        k: v for k, v in report.items() if k not in processing
    }
    assert len((tmp_path / "stream/results.jsonl").read_text().splitlines()) == len(cases)
