from __future__ import annotations

from datetime import datetime, timezone

from .contracts import EvidenceAssessment, SourceCandidate, SourceSnapshot


class EvidencePolicy:
    version = "evidence-policy-v1"

    def __init__(
        self,
        *,
        primary_domains: tuple[str, ...] = (),
        secondary_domains: tuple[str, ...] = (),
        supported_languages: tuple[str, ...] = ("de", "en"),
        minimum_content_characters: int = 200,
    ):
        self._primary = frozenset(primary_domains)
        self._secondary = frozenset(secondary_domains)
        self._languages = frozenset(item.casefold() for item in supported_languages)
        self._minimum = minimum_content_characters

    def assess(
        self,
        snapshot: SourceSnapshot,
        source: SourceCandidate,
        *,
        maximum_age_days: int,
        now: datetime | None = None,
    ) -> EvidenceAssessment:
        reasons: list[str] = []
        provenance_complete = all(
            (
                source.search_provider,
                source.search_provider_version,
                snapshot.content_provider,
                snapshot.content_provider_version,
                snapshot.content_hash,
            )
        )
        if not provenance_complete:
            reasons.append("PROVENANCE_MISSING")
        if len(snapshot.text.strip()) < self._minimum:
            reasons.append("CONTENT_TOO_SHORT")
        lowered = snapshot.text.casefold()
        if any(item in lowered for item in ("sign in to continue", "log in to continue")):
            reasons.append("LOGIN_PAGE")
        if any(item in lowered for item in ("subscribe to continue", "paywall")):
            reasons.append("PAYWALL_DETECTED")
        if snapshot.language.casefold().split("-", 1)[0] not in self._languages:
            reasons.append("UNSUPPORTED_CONTENT_LANGUAGE")
        if snapshot.risk.prompt_injection_suspected:
            reasons.append("PROMPT_INJECTION_SUSPECTED")

        current = now or datetime.now(timezone.utc)
        freshness = "UNKNOWN"
        if source.published_at:
            try:
                published = datetime.fromisoformat(source.published_at.replace("Z", "+00:00"))
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                age = (current.astimezone(timezone.utc) - published.astimezone(timezone.utc)).days
                freshness = "CURRENT" if age <= maximum_age_days else "STALE"
                if freshness == "STALE":
                    reasons.append("CONTENT_OUTDATED")
            except ValueError:
                reasons.append("PUBLICATION_DATE_INVALID")

        if source.domain in self._primary:
            source_type, authority = "PRIMARY", 0.9
        elif source.domain in self._secondary:
            source_type, authority = "SECONDARY", 0.6
        else:
            source_type, authority = "UNKNOWN", 0.2
        relevance = round(max(0.2, 1.0 - (max(source.rank, 1) - 1) * 0.08), 2)
        blocking = {
            "PROVENANCE_MISSING",
            "CONTENT_TOO_SHORT",
            "LOGIN_PAGE",
            "PAYWALL_DETECTED",
            "UNSUPPORTED_CONTENT_LANGUAGE",
            "PROMPT_INJECTION_SUSPECTED",
        }
        usable = not blocking.intersection(reasons)
        if usable and not reasons:
            reasons.append("EXTERNAL_EVIDENCE_UNVERIFIED")
        return EvidenceAssessment(
            freshness,
            source_type,
            authority,
            relevance,
            "NOT_CHECKED",
            usable,
            True,
            tuple(dict.fromkeys(reasons)),
        )
