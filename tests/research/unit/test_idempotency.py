from decision_assurance.web_research.contracts import FreshnessPolicy, ResearchRequest
from decision_assurance.web_research.idempotency import normalize_query, semantic_fingerprint


def request(**overrides: object) -> ResearchRequest:
    values: dict[str, object] = {
        "decision_file_id": "D-1",
        "claim_refs": ("claim-b", "claim-a"),
        "query": "  Welche   Regeln gelten?  ",
        "locale": "de-DE",
        "preferred_languages": ("en", "de"),
        "allowed_domains": ("Example.ORG",),
        "blocked_domains": ("blocked.example",),
        "freshness": FreshnessPolicy(365, True),
    }
    values.update(overrides)
    return ResearchRequest(**values)  # type: ignore[arg-type]


def test_query_and_semantic_fingerprint_are_stable() -> None:
    assert normalize_query("  Äpfel\tUND  Birnen ") == "äpfel und birnen"
    first = semantic_fingerprint(
        "tenant-a", request(), "sha256:" + "a" * 64, "policy-v1", "providers-v1"
    )
    reordered = request(
        claim_refs=("claim-a", "claim-b"),
        preferred_languages=("de", "en"),
        allowed_domains=("example.org",),
        query="welche regeln gelten?",
    )
    second = semantic_fingerprint(
        "tenant-a", reordered, "sha256:" + "a" * 64, "policy-v1", "providers-v1"
    )
    assert first == second


def test_fingerprint_is_tenant_decision_version_and_refresh_bound() -> None:
    base = semantic_fingerprint(
        "tenant-a", request(), "sha256:" + "a" * 64, "policy-v1", "providers-v1"
    )
    assert base != semantic_fingerprint(
        "tenant-b", request(), "sha256:" + "a" * 64, "policy-v1", "providers-v1"
    )
    assert base != semantic_fingerprint(
        "tenant-a", request(), "sha256:" + "b" * 64, "policy-v1", "providers-v1"
    )
    refreshed = semantic_fingerprint(
        "tenant-a",
        request(force_refresh=True),
        "sha256:" + "a" * 64,
        "policy-v1",
        "providers-v1",
        refresh_generation="refresh-2",
    )
    assert base != refreshed
