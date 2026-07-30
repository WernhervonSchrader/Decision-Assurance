from __future__ import annotations

SUPPORTED_LOCALES = ("en", "de")
FALLBACK_LOCALE = "en"

TRANSLATIONS = {
    "en": {
        "UNAUTHENTICATED": "Authentication required.",
        "FORBIDDEN": "You are not authorized to perform this action.",
        "NOT_FOUND": "Not found.",
        "INVALID_REQUEST": "The request is invalid.",
        "CONFLICT": "The request conflicts with the current state.",
        "INTERNAL_ERROR": "The operation failed.",
        "PAYLOAD_TOO_LARGE": "The request body is too large.",
        "NEEDS_CONFIRMATION": "Required intake information still needs confirmation.",
        "TRUSTED_POLICY_UNAVAILABLE": "No trusted tenant policy is available.",
        "INTAKE_CONTRACT_INVALID": "The intake contract is invalid.",
        "UNSUPPORTED_MEDIA_TYPE": "The request must use a JSON content type.",
        "SOURCE_BLOCKED": "The source is blocked by policy.",
        "URL_NOT_PUBLIC": "The source URL is not public.",
        "CONTENT_TOO_SHORT": "The extracted content is too short.",
        "CONTENT_TOO_LARGE": "The extracted content is too large.",
        "MIME_TYPE_UNSUPPORTED": "The source content type is not supported.",
        "PROVENANCE_MISSING": "Required source provenance is missing.",
        "PROMPT_INJECTION_SUSPECTED": "The source requires review for unsafe instructions.",
        "EXTRACTION_TIMEOUT": "Source extraction timed out.",
        "CONFLICTING_EVIDENCE": "The evidence contains an explicit conflict.",
        "PROVIDER_NOT_CONFIGURED": "The research provider is not configured.",
        "PROVIDER_RATE_LIMITED": "The research provider rate limit was reached.",
        "BUDGET_EXCEEDED": "The research provider budget was reached.",
        "RESEARCH_CANCELLED": "The research run was cancelled.",
    },
    "de": {
        "UNAUTHENTICATED": "Authentifizierung erforderlich.",
        "FORBIDDEN": "Sie sind für diese Aktion nicht berechtigt.",
        "NOT_FOUND": "Nicht gefunden.",
        "INVALID_REQUEST": "Die Anfrage ist ungültig.",
        "CONFLICT": "Die Anfrage widerspricht dem aktuellen Zustand.",
        "INTERNAL_ERROR": "Der Vorgang ist fehlgeschlagen.",
        "PAYLOAD_TOO_LARGE": "Der Anfrageinhalt ist zu groß.",
        "NEEDS_CONFIRMATION": "Erforderliche Intake-Angaben müssen noch bestätigt werden.",
        "TRUSTED_POLICY_UNAVAILABLE": "Für den Mandanten ist keine vertrauenswürdige Policy verfügbar.",
        "INTAKE_CONTRACT_INVALID": "Der Intake-Vertrag ist ungültig.",
        "UNSUPPORTED_MEDIA_TYPE": "Die Anfrage muss einen JSON-Inhaltstyp verwenden.",
        "SOURCE_BLOCKED": "Die Quelle ist durch die Richtlinie gesperrt.",
        "URL_NOT_PUBLIC": "Die Quell-URL ist nicht öffentlich erreichbar.",
        "CONTENT_TOO_SHORT": "Der extrahierte Inhalt ist zu kurz.",
        "CONTENT_TOO_LARGE": "Der extrahierte Inhalt ist zu groß.",
        "MIME_TYPE_UNSUPPORTED": "Der Inhaltstyp der Quelle wird nicht unterstützt.",
        "PROVENANCE_MISSING": "Erforderliche Herkunftsangaben fehlen.",
        "PROMPT_INJECTION_SUSPECTED": "Die Quelle erfordert eine Prüfung auf unsichere Anweisungen.",
        "EXTRACTION_TIMEOUT": "Die Quellenextraktion hat das Zeitlimit überschritten.",
        "CONFLICTING_EVIDENCE": "Die Evidenz enthält einen ausdrücklichen Widerspruch.",
        "PROVIDER_NOT_CONFIGURED": "Der Rechercheanbieter ist nicht konfiguriert.",
        "PROVIDER_RATE_LIMITED": "Das Anfragelimit des Rechercheanbieters wurde erreicht.",
        "BUDGET_EXCEEDED": "Das Budget für Rechercheanbieter wurde erreicht.",
        "RESEARCH_CANCELLED": "Der Recherchelauf wurde abgebrochen.",
    },
}


def select_locale(accept_language: str | None) -> str:
    if accept_language:
        for item in accept_language.split(","):
            language = item.split(";", 1)[0].strip().lower().split("-", 1)[0]
            if language in SUPPORTED_LOCALES:
                return language
    return FALLBACK_LOCALE


def localize(code: str, locale: str) -> str:
    catalog = TRANSLATIONS.get(locale, TRANSLATIONS[FALLBACK_LOCALE])
    return catalog.get(code, TRANSLATIONS[FALLBACK_LOCALE].get(code, code))
