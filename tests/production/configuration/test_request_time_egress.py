from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from decision_assurance.production.config import RuntimeConfig, load_config
from decision_assurance.production.contracts import EnvironmentProfile
from decision_assurance.production.egress import (
    EgressDecision,
    EgressRejected,
    EgressRequestContext,
    ResidencyEgressGuard,
    bind_egress_context,
)
from decision_assurance.tenancy import TenantContext
from decision_assurance.web_research.audit import append_egress_decision
from decision_assurance.web_research.contracts import (
    FreshnessPolicy,
    ResearchRequest,
    ResearchRun,
    ResearchStatus,
    SearchQuery,
)
from decision_assurance.web_research.providers.brave import BraveSearchProvider
from decision_assurance.web_research.providers.errors import ProviderRequestFailed
from decision_assurance.web_research.repository import SqliteResearchRepository

NOW = datetime(2026, 7, 31, tzinfo=timezone.utc)


def _attestation(
    *,
    status: str = "VERIFIED",
    evidence_type: str = "DPA",
    expires_at: str = "2027-01-01T00:00:00Z",
    confirmed: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "evidence_id": "evidence-brave-1",
        "evidence_type": evidence_type,
        "evidence_ref": "https://evidence.example/brave-dpa",
        "issuer": "provider-contracts",
        "issued_at": "2026-01-01T00:00:00Z",
        "valid_from": "2026-01-01T00:00:00Z",
        "expires_at": expires_at,
        "verification_status": status,
        "verified_at": "2026-07-01T00:00:00Z" if status == "VERIFIED" else None,
        "verified_by": "security-reviewer" if status == "VERIFIED" else None,
        "document_hash": "sha256:" + "a" * 64 if status == "VERIFIED" else None,
    }


def _raw(*, status: str = "VERIFIED", confirmed: list[str] | None = None) -> dict[str, Any]:
    return {
        "profile": "production",
        "operating_mode": "local",
        "data_residency": {
            "storage_locations": ["local"],
            "processing_locations": ["local"],
            "backup_locations": ["local"],
            "support_access_locations": ["local"],
            "external_processing_locations": ["local"],
            "evidence_refs": [],
        },
        "database_backend": "postgresql",
        "authentication_mode": "oidc",
        "secret_provider": "external",
        "database_dsn_secret": "database-dsn",
        "worker_database_dsn_secret": "worker-database-dsn",
        "oidc": {
            "issuer": "https://identity.example",
            "audience": "decision-assurance",
            "jwks_uri": "https://identity.example/jwks.json",
            "algorithms": ["RS256"],
        },
        "egress_allowed_hosts": ["brave.example"],
        "provider_egress": [
            {
                "provider": "brave-search",
                "service": "web-search-v1",
                "host": "brave.example",
                "processing_location": "local",
                "confirmed_processing_locations": (
                    confirmed if confirmed is not None else ["local"]
                ),
                "tenant_ids": ["tenant-a"],
                "attestation": _attestation(status=status, confirmed=confirmed),
            }
        ],
        "worker": {},
    }


def _guard(raw: dict[str, Any]) -> tuple[ResidencyEgressGuard, dict[str, RuntimeConfig]]:
    state: dict[str, RuntimeConfig] = {"config": RuntimeConfig.from_mapping(raw)}
    return ResidencyEgressGuard(lambda: state["config"], clock=lambda: NOW), state


def _context(events: list[EgressDecision], tenant_id: str = "tenant-a") -> EgressRequestContext:
    return EgressRequestContext(
        tenant_id=tenant_id,
        actor_id="actor-1",
        correlation_id="corr-1",
        record_decision=events.append,
    )


def test_allowed_request_emits_complete_secret_free_event() -> None:
    guard, _ = _guard(_raw())
    events: list[EgressDecision] = []

    assert (
        guard.authorize(
            _context(events),
            provider="brave-search",
            connector="web-search-v1",
            url="https://brave.example/res/v1/web/search",
        )
        == "https://brave.example/res/v1/web/search"
    )
    event = events[0]
    assert event.decision == "ALLOWED"
    assert event.reason_code == "EGRESS_ALLOWED"
    assert "secret" not in repr(asdict(event)).casefold()


def test_explicit_development_provider_profile_allows_only_unverified_dev_egress() -> None:
    config = load_config(
        Path("config/deployment/provider-development.example.json"),
        {"DA_PROFILE": "development"},
    )
    events: list[EgressDecision] = []
    guard = ResidencyEgressGuard(
        lambda: config,
        clock=lambda: NOW,
        expected_profile=EnvironmentProfile.DEVELOPMENT,
    )
    result = guard.authorize(
        _context(events),
        provider="brave-search",
        connector="web-search-v1",
        url="https://api.search.brave.com/res/v1/web/search",
    )
    assert result == "https://api.search.brave.com/res/v1/web/search"
    assert events[0].reason_code == "EGRESS_ALLOWED_DEVELOPMENT"
    assert events[0].evidence_status == "UNVERIFIED"


def test_runtime_profile_change_blocks_development_guard() -> None:
    production = RuntimeConfig.from_mapping(_raw())
    events: list[EgressDecision] = []
    guard = ResidencyEgressGuard(
        lambda: production,
        clock=lambda: NOW,
        expected_profile=EnvironmentProfile.DEVELOPMENT,
    )
    with pytest.raises(EgressRejected, match="EGRESS_CONFIGURATION_CHANGED"):
        guard.authorize(
            _context(events),
            provider="brave-search",
            connector="web-search-v1",
            url="https://brave.example/res/v1/web/search",
        )
    assert events[0].decision == "BLOCKED"


@pytest.mark.parametrize(
    ("raw_mutation", "reason"),
    [
        (
            lambda raw: raw["provider_egress"][0]["attestation"].update(
                {"verification_status": "UNVERIFIED"}
            ),
            "EGRESS_EVIDENCE_UNVERIFIED",
        ),
        (
            lambda raw: raw["provider_egress"][0]["attestation"].update(
                {"expires_at": "2026-07-30T00:00:00Z"}
            ),
            "EGRESS_EVIDENCE_EXPIRED",
        ),
        (
            lambda raw: raw["provider_egress"][0]["attestation"].update(
                {"verified_at": None, "verified_by": None}
            ),
            "EGRESS_EVIDENCE_UNVERIFIED",
        ),
        (
            lambda raw: raw["provider_egress"][0]["attestation"].update(
                {"issued_at": "not-a-timestamp"}
            ),
            "EGRESS_EVIDENCE_UNVERIFIED",
        ),
        (
            lambda raw: raw["provider_egress"][0].update({"confirmed_processing_locations": []}),
            "EGRESS_EVIDENCE_MISSING",
        ),
        (
            lambda raw: raw["provider_egress"][0].update(
                {"confirmed_processing_locations": ["DE"]}
            ),
            "EGRESS_LOCATION_NOT_ALLOWED",
        ),
    ],
)
def test_missing_expired_or_mismatched_attestation_blocks(raw_mutation, reason: str) -> None:  # type: ignore[no-untyped-def]
    raw = _raw()
    raw_mutation(raw)
    guard, _ = _guard(raw)
    events: list[EgressDecision] = []
    with pytest.raises(EgressRejected, match=reason):
        guard.authorize(
            _context(events),
            provider="brave-search",
            connector="web-search-v1",
            url="https://brave.example/res/v1/web/search",
        )
    assert events[0].decision == "BLOCKED"
    assert events[0].reason_code == reason


def test_changed_configuration_is_used_on_next_request() -> None:
    guard, state = _guard(_raw())
    state["config"] = RuntimeConfig.from_mapping(_raw(status="UNVERIFIED"))
    events: list[EgressDecision] = []
    with pytest.raises(EgressRejected, match="EGRESS_EVIDENCE_UNVERIFIED"):
        guard.authorize(
            _context(events),
            provider="brave-search",
            connector="web-search-v1",
            url="https://brave.example/res/v1/web/search",
        )


def test_changed_configuration_file_is_reloaded_on_next_request(tmp_path: Path) -> None:
    path = tmp_path / "production.json"
    path.write_text(json.dumps(_raw()), encoding="utf-8")
    guard = ResidencyEgressGuard(
        lambda: load_config(path, {"DA_PROFILE": "production"}), clock=lambda: NOW
    )
    events: list[EgressDecision] = []
    assert guard.authorize(
        _context(events),
        provider="brave-search",
        connector="web-search-v1",
        url="https://brave.example/res/v1/web/search",
    )

    path.write_text(json.dumps(_raw(status="UNVERIFIED")), encoding="utf-8")
    with pytest.raises(EgressRejected, match="EGRESS_EVIDENCE_UNVERIFIED"):
        guard.authorize(
            _context(events),
            provider="brave-search",
            connector="web-search-v1",
            url="https://brave.example/res/v1/web/search",
        )


def test_invalid_changed_configuration_is_audited_and_blocks() -> None:
    events: list[EgressDecision] = []
    guard = ResidencyEgressGuard(
        lambda: (_ for _ in ()).throw(ValueError("contains-a-secret")), clock=lambda: NOW
    )
    with pytest.raises(EgressRejected, match="EGRESS_CONFIGURATION_CHANGED") as caught:
        guard.authorize(
            _context(events),
            provider="brave-search",
            connector="web-search-v1",
            url="https://brave.example/res/v1/web/search",
        )
    assert events[0].reason_code == "EGRESS_CONFIGURATION_CHANGED"
    assert "contains-a-secret" not in str(caught.value)


@pytest.mark.anyio
async def test_blocked_brave_request_never_reaches_network() -> None:
    raw = _raw(status="UNVERIFIED")
    guard, _ = _guard(raw)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"web": {"results": []}})

    provider = BraveSearchProvider(
        api_key="super-secret",
        base_url="https://brave.example",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        egress_guard=guard,
    )
    events: list[EgressDecision] = []
    context = _context(events)
    with bind_egress_context(context):
        with pytest.raises(ProviderRequestFailed) as caught:
            await provider.search(
                SearchQuery("query", "en-US", ("en",), 1, FreshnessPolicy(1, True))
            )
    assert caught.value.error.reason_code == "EGRESS_EVIDENCE_UNVERIFIED"
    assert calls == 0
    assert events[0].decision == "BLOCKED"
    assert "super-secret" not in repr(events[0])


def test_tenant_scope_mismatch_blocks() -> None:
    guard, _ = _guard(_raw())
    events: list[EgressDecision] = []
    with pytest.raises(EgressRejected, match="EGRESS_TENANT_MISMATCH"):
        guard.authorize(
            _context(events, tenant_id="tenant-b"),
            provider="brave-search",
            connector="web-search-v1",
            url="https://brave.example/res/v1/web/search",
        )


def test_host_and_attestation_mismatch_blocks() -> None:
    guard, _ = _guard(_raw())
    events: list[EgressDecision] = []
    with pytest.raises(EgressRejected, match="EGRESS_HOST_MISMATCH"):
        guard.authorize(
            _context(events),
            provider="brave-search",
            connector="web-search-v1",
            url="https://undeclared.example/res/v1/web/search",
        )
    assert events[0].reason_code == "EGRESS_HOST_MISMATCH"


def test_startup_validation_and_request_guard_agree_for_unchanged_config() -> None:
    raw = _raw()
    config = RuntimeConfig.from_mapping(raw)
    config.validate_provider_urls(("https://brave.example",))
    guard = ResidencyEgressGuard(lambda: config, clock=lambda: NOW)
    events: list[EgressDecision] = []
    assert guard.authorize(
        _context(events),
        provider="brave-search",
        connector="web-search-v1",
        url="https://brave.example/res/v1/web/search",
    )
    assert events[0].reason_code == "EGRESS_ALLOWED"


@pytest.mark.anyio
async def test_audit_failure_blocks_before_network() -> None:
    guard, _ = _guard(_raw())
    context = EgressRequestContext(
        tenant_id="tenant-a",
        actor_id="actor-1",
        correlation_id="corr-1",
        record_decision=lambda event: (_ for _ in ()).throw(RuntimeError("audit down")),
    )
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"web": {"results": []}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = BraveSearchProvider(
        api_key="super-secret",
        base_url="https://brave.example",
        client=client,
        egress_guard=guard,
    )
    with bind_egress_context(context):
        with pytest.raises(ProviderRequestFailed, match="EGRESS_AUDIT_FAILED"):
            await provider.search(
                SearchQuery("query", "en-US", ("en",), 1, FreshnessPolicy(1, True))
            )
    await client.aclose()
    assert calls == 0


def test_direct_adapter_without_bound_context_fails_closed() -> None:
    provider = BraveSearchProvider(api_key="secret", base_url="https://brave.example")
    with pytest.raises(ProviderRequestFailed, match="EGRESS_CONTEXT_REQUIRED"):
        import asyncio

        asyncio.run(
            provider.search(SearchQuery("query", "en-US", ("en",), 1, FreshnessPolicy(1, True)))
        )


def test_persisted_egress_event_is_tenant_scoped(tmp_path: Path) -> None:
    repository = SqliteResearchRepository(tmp_path / "research.db")
    repository.initialize()
    request = ResearchRequest(
        "decision-1",
        ("claim-1",),
        "query",
        "en-US",
        ("en",),
        1,
        1,
        (),
        (),
        FreshnessPolicy(1, True),
        "standard",
        False,
        "0.4.0",
    )
    run = ResearchRun(
        "run-1",
        "tenant-a",
        "actor-1",
        request,
        "hash",
        "fingerprint",
        ResearchStatus.CREATED,
        NOW.isoformat(),
        NOW.isoformat(),
        "corr-1",
    )
    event = EgressDecision(
        "BLOCKED",
        NOW.isoformat(),
        "tenant-a",
        "actor-1",
        "corr-1",
        "production",
        "residency-policy-v1",
        "brave-search",
        "web-search-v1",
        "brave.example",
        "local",
        "evidence-1",
        "UNVERIFIED",
        "EGRESS_EVIDENCE_UNVERIFIED",
    )
    append_egress_decision(run, event)
    repository.create_or_get(TenantContext("tenant-a"), run)
    repository.save(TenantContext("tenant-a"), run)
    records = repository.list_audit(TenantContext("tenant-a"), "run-1")
    assert records[0]["event_type"] == "research.egress-decision"
    assert records[0]["schema_version"] == "research-egress-decision-v1"
    assert records[0]["decision"] == "BLOCKED"
    assert records[0]["reason_codes"] == ["EGRESS_EVIDENCE_UNVERIFIED"]
