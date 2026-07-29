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
    },
    "de": {
        "UNAUTHENTICATED": "Authentifizierung erforderlich.",
        "FORBIDDEN": "Sie sind für diese Aktion nicht berechtigt.",
        "NOT_FOUND": "Nicht gefunden.",
        "INVALID_REQUEST": "Die Anfrage ist ungültig.",
        "CONFLICT": "Die Anfrage widerspricht dem aktuellen Zustand.",
        "INTERNAL_ERROR": "Der Vorgang ist fehlgeschlagen.",
        "PAYLOAD_TOO_LARGE": "Der Anfrageinhalt ist zu groß.",
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
