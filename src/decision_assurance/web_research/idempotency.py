from __future__ import annotations

import hashlib
import json
import unicodedata

from .contracts import ResearchRequest
from .url_policy import normalize_domain


def normalize_query(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def semantic_fingerprint(
    tenant_id: str,
    request: ResearchRequest,
    decision_file_version_hash: str,
    research_policy_version: str,
    provider_configuration_version: str,
    *,
    refresh_generation: str | None = None,
) -> str:
    payload = {
        "tenant_id": tenant_id,
        "decision_file_id": request.decision_file_id,
        "decision_file_version_hash": decision_file_version_hash,
        "claim_refs": sorted(request.claim_refs),
        "query": normalize_query(request.query),
        "locale": request.locale.casefold(),
        "preferred_languages": sorted(item.casefold() for item in request.preferred_languages),
        "allowed_domains": sorted(normalize_domain(item) for item in request.allowed_domains),
        "blocked_domains": sorted(normalize_domain(item) for item in request.blocked_domains),
        "freshness": {
            "maximum_age_days": request.freshness.maximum_age_days,
            "prefer_recent": request.freshness.prefer_recent,
        },
        "max_search_results": request.max_search_results,
        "max_sources_to_extract": request.max_sources_to_extract,
        "research_policy": request.research_policy,
        "research_policy_version": research_policy_version,
        "provider_configuration_version": provider_configuration_version,
        "refresh_generation": refresh_generation if request.force_refresh else None,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()
