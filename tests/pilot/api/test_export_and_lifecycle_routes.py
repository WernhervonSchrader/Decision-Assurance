from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from decision_assurance.api.app import create_app
from decision_assurance.export.repository import InMemoryExportRepository
from decision_assurance.export.service import PilotExportService
from decision_assurance.export.signing import ExportSigner, SignatureEnvelope
from decision_assurance.export.validator import validate_export
from decision_assurance.identity import ActorKind, Identity, Role, StaticTokenAuthenticator
from decision_assurance.lifecycle.repository import InMemoryLifecycleRepository
from decision_assurance.lifecycle.service import PilotLifecycleService
from decision_assurance.observability.metrics import InMemoryMetrics
from decision_assurance.production.contracts import SecretValue
from decision_assurance.repositories.sqlite import SqliteDecisionRepository
from decision_assurance.tenancy import TenantContext

ROOT = Path(__file__).parents[3]
NOW = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)


def _snapshot() -> dict[str, object]:
    empty: list[object] = []
    return {
        "decision/decision-file.json": {"decision_id": "quote-1", "status": "APPROVED"},
        "decision/assurance-report.json": {"outcome": "PASS", "findings": []},
        "intake/intake-records.json": empty,
        "research/research-runs.json": empty,
        "research/sources.json": empty,
        "research/evidence.json": empty,
        "audit/decision-events.json": empty,
        "audit/intake-events.json": empty,
        "audit/research-events.json": empty,
        "audit/lifecycle-events.json": empty,
    }


class FailingSigner:
    key_id = "failing-test-key"

    def sign(self, payload: bytes) -> SignatureEnvelope:
        del payload
        raise ValueError("SIGNING_BACKEND_UNAVAILABLE")


def _client(tmp_path: Path, *, signer: ExportSigner | None = None) -> TestClient:
    tenant = TenantContext("tenant-a")
    repository = SqliteDecisionRepository(tmp_path / "api.db")
    repository.initialize()
    document = json.loads(
        (ROOT / "examples" / "decision-cases" / "low-risk-pass.json").read_text(encoding="utf-8")
    )
    document["decision_id"] = "quote-1"
    repository.create_decision(tenant, document)
    identities = {
        "admin": Identity("admin", tenant, Role.TENANT_ADMIN, ActorKind.HUMAN),
        "auditor": Identity("auditor", tenant, Role.AUDITOR, ActorKind.HUMAN),
        "other": Identity("other", TenantContext("tenant-b"), Role.TENANT_ADMIN, ActorKind.HUMAN),
    }
    export = PilotExportService(
        InMemoryExportRepository({("tenant-a", "quote-1"): _snapshot()}),
        version="0.8.0",
        commit_sha="a" * 40,
        policy_versions={"sales-quote": "1"},
        signer=signer,
        event_schema_version="1.0.0",
        clock=lambda: NOW,
    )
    lifecycle = PilotLifecycleService(
        InMemoryLifecycleRepository({"tenant-a": {"quote-1"}}),
        SecretValue("lifecycle-pepper"),
        clock=lambda: NOW,
    )
    return TestClient(
        create_app(
            repository,
            StaticTokenAuthenticator(identities),
            export_service=export,
            lifecycle_service=lifecycle,
            metrics=InMemoryMetrics(),
        )
    )


def _headers(token: str, key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if key:
        headers["Idempotency-Key"] = key
    return headers


def test_export_route_is_authorized_tenant_scoped_and_offline_valid(tmp_path: Path) -> None:
    client = _client(tmp_path)

    result = client.get("/v1/decisions/quote-1/export", headers=_headers("auditor"))
    hidden = client.get("/v1/decisions/quote-1/export", headers=_headers("other"))

    assert result.status_code == 200
    assert result.headers["content-type"] == "application/zip"
    assert "attachment" in result.headers["content-disposition"]
    assert validate_export(result.content).valid
    assert hidden.status_code == 404


def test_signing_failure_is_redacted_counted_and_returns_unavailable(tmp_path: Path) -> None:
    client = _client(tmp_path, signer=FailingSigner())
    result = client.get("/v1/decisions/quote-1/export", headers=_headers("auditor"))
    assert result.status_code == 503
    assert result.json()["code"] == "PILOT_EXPORT_UNAVAILABLE"
    assert "SIGNING_BACKEND_UNAVAILABLE" not in result.text
    assert client.app.state.metrics.counter("export_signature_failures_total") == 1


def test_legal_hold_blocks_delete_then_release_allows_physical_delete(tmp_path: Path) -> None:
    client = _client(tmp_path)
    held = client.put(
        "/v1/decisions/quote-1/legal-hold",
        headers=_headers("admin", "hold-1"),
        json={"reason_code": "LITIGATION"},
    )
    requested = client.post(
        "/v1/decisions/quote-1/deletion-requests",
        headers=_headers("admin", "delete-1"),
        json={"reason_code": "USER_REQUEST"},
    )
    executed = client.post(
        f"/v1/deletion-requests/{requested.json()['request_id']}/execute",
        headers=_headers("admin", "execute-1"),
    )

    assert held.status_code == 204
    assert requested.status_code == 202
    assert executed.json()["status"] == "BLOCKED_BY_HOLD"
    assert client.app.state.metrics.counter("legal_hold_violation_attempts_total") == 2
    assert (
        client.delete(
            "/v1/decisions/quote-1/legal-hold", headers=_headers("admin", "release-1")
        ).status_code
        == 204
    )
    completed = client.post(
        f"/v1/deletion-requests/{requested.json()['request_id']}/execute",
        headers=_headers("admin", "execute-2"),
    )
    assert completed.json()["status"] == "COMPLETED"
    assert (
        client.app.state.metrics.counter("deletion_activity_total", {"status": "blocked_by_hold"})
        == 2
    )
    assert client.app.state.metrics.counter("deletion_activity_total", {"status": "completed"}) == 1


def test_auditor_cannot_delete_or_manage_hold(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert (
        client.post(
            "/v1/decisions/quote-1/deletion-requests",
            headers=_headers("auditor", "delete-1"),
            json={"reason_code": "USER_REQUEST"},
        ).status_code
        == 403
    )
    assert (
        client.put(
            "/v1/decisions/quote-1/legal-hold",
            headers=_headers("auditor", "hold-1"),
            json={"reason_code": "LITIGATION"},
        ).status_code
        == 403
    )
