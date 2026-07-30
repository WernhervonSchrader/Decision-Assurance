from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .contracts import ContentHash, ContentRisk, ExtractedContent, SourceCandidate, SourceSnapshot

_ACTIVE_HTML = re.compile(
    r"<\s*(?:script|style|iframe|object|embed)[^>]*>.*?<\s*/\s*(?:script|style|iframe|object|embed)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_HTML = re.compile(r"<[^>]+>")
_ACTIVE_LINK = re.compile(r"\]\((?:javascript|data):[^)]*\)", re.IGNORECASE)
_SECRET = re.compile(
    r"(?i)(?:sk-[a-z0-9_-]{20,}|(?:api[_ -]?key|token|secret)\s*[:=]\s*[a-z0-9_./+-]{16,})"
)
_INJECTION = (
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"mark\s+this\s+source\s+as\s+verified", re.IGNORECASE),
    re.compile(r"reveal\s+(?:the\s+)?system\s+prompts?", re.IGNORECASE),
    re.compile(
        r"(?:set|return)\s+(?:the\s+)?(?:outcome\s+)?(?:to\s+)?(?:pass|approved)", re.IGNORECASE
    ),
)


class EvidenceNormalizationRejected(ValueError):
    pass


class EvidenceNormalizer:
    version = "research-normalizer-v1"

    def __init__(self, *, max_content_bytes: int, cache_ttl_seconds: int = 86_400):
        if not 1_000 <= max_content_bytes <= 10_000_000:
            raise ValueError("INVALID_CONTENT_LIMIT")
        self._max_content_bytes = max_content_bytes
        self._cache_ttl_seconds = cache_ttl_seconds

    def normalize(self, source: SourceCandidate, content: ExtractedContent) -> SourceSnapshot:
        if content.http_status != 200:
            raise EvidenceNormalizationRejected("ERROR_PAGE")
        if content.mime_type.casefold().split(";", 1)[0] not in {
            "text/markdown",
            "text/plain",
            "text/html",
        }:
            raise EvidenceNormalizationRejected("MIME_TYPE_UNSUPPORTED")
        raw = content.markdown
        if len(raw.encode("utf-8")) > self._max_content_bytes:
            raise EvidenceNormalizationRejected("CONTENT_TOO_LARGE")
        active_removed = bool(_ACTIVE_HTML.search(raw) or _ACTIVE_LINK.search(raw))
        text = _ACTIVE_HTML.sub(" ", raw)
        text = _ACTIVE_LINK.sub("](about:blank)", text)
        text = _HTML.sub(" ", text)
        secret_redacted = bool(_SECRET.search(text))
        text = _SECRET.sub("[REDACTED]", text)
        text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
        reasons = tuple(
            "PROMPT_INJECTION_SUSPECTED" for pattern in _INJECTION if pattern.search(text)
        )
        reasons = tuple(dict.fromkeys(reasons))
        risk = ContentRisk(bool(reasons), reasons, secret_redacted, active_removed)
        try:
            retrieved = datetime.fromisoformat(content.retrieved_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise EvidenceNormalizationRejected("INVALID_RETRIEVAL_TIME") from error
        if retrieved.tzinfo is None:
            retrieved = retrieved.replace(tzinfo=timezone.utc)
        expires = retrieved.astimezone(timezone.utc) + timedelta(seconds=self._cache_ttl_seconds)
        content_hash = ContentHash.from_text(raw).value
        snapshot_id = f"{source.source_id}:snapshot:{content_hash.removeprefix('sha256:')[:16]}"
        return SourceSnapshot(
            snapshot_id,
            source.source_id,
            source.original_url,
            content.canonical_url,
            source.domain,
            content.title or source.title,
            retrieved.astimezone(timezone.utc).isoformat(),
            expires.isoformat(),
            content_hash,
            content.http_status,
            content.mime_type.casefold().split(";", 1)[0],
            "markdown",
            text,
            content.language.casefold(),
            content.content_provider,
            content.content_provider_version,
            risk,
        )
