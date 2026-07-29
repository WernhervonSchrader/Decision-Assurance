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
