from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .contracts import EnvironmentProfile, SecretReference, SecretValue

_PLACEHOLDERS = {
    "changeme",
    "replace-me",
    "placeholder",
    "example-secret",
    "secret",
    "password",
}


class SecretResolutionError(RuntimeError):
    """Generic error that never includes a reference's resolved value."""


class EnvironmentSecretProvider:
    def __init__(self, profile: EnvironmentProfile, environment: Mapping[str, str]):
        if profile not in {EnvironmentProfile.DEVELOPMENT, EnvironmentProfile.TEST}:
            raise ValueError("ENVIRONMENT_SECRETS_NOT_ALLOWED")
        self._environment = environment

    def resolve(self, reference: SecretReference) -> SecretValue:
        value = self._environment.get(reference.name)
        if value is None and not reference.required:
            raise SecretResolutionError("OPTIONAL_SECRET_UNSET")
        if value is None or _unsafe(value):
            raise SecretResolutionError("SECRET_UNAVAILABLE")
        return SecretValue(value)

    def __repr__(self) -> str:
        return "EnvironmentSecretProvider(**redacted**)"


class ExternalSecretProvider:
    """Adapter around a deployment-supplied resolver (Vault/KMS/platform secret store)."""

    def __init__(self, resolver: Callable[[str], str]):
        self._resolver = resolver

    def resolve(self, reference: SecretReference) -> SecretValue:
        try:
            value = self._resolver(reference.name)
        except Exception:
            raise SecretResolutionError("SECRET_PROVIDER_UNAVAILABLE") from None
        if _unsafe(value):
            raise SecretResolutionError("SECRET_UNAVAILABLE")
        return SecretValue(value)

    def __repr__(self) -> str:
        return "ExternalSecretProvider(**redacted**)"


class FileSecretProvider:
    """Reads platform-mounted secret files from one fixed directory."""

    def __init__(self, directory: Path):
        self._directory = directory.resolve()
        if not self._directory.is_dir():
            raise ValueError("SECRET_DIRECTORY_UNAVAILABLE")

    def resolve(self, reference: SecretReference) -> SecretValue:
        path = (self._directory / reference.name).resolve()
        if path.parent != self._directory:
            raise SecretResolutionError("SECRET_UNAVAILABLE")
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            raise SecretResolutionError("SECRET_UNAVAILABLE") from None
        if _unsafe(value):
            raise SecretResolutionError("SECRET_UNAVAILABLE")
        return SecretValue(value)

    def __repr__(self) -> str:
        return "FileSecretProvider(**redacted**)"


@dataclass(slots=True)
class _CachedSecret:
    value: SecretValue
    expires_at: float


class RotatingSecretProvider:
    def __init__(
        self,
        provider: EnvironmentSecretProvider | ExternalSecretProvider | FileSecretProvider,
        *,
        ttl_seconds: int = 60,
        clock: Callable[[], float] = time.monotonic,
    ):
        if not 1 <= ttl_seconds <= 3600:
            raise ValueError("INVALID_SECRET_CACHE_TTL")
        self._provider = provider
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._cache: dict[str, _CachedSecret] = {}
        self._lock = threading.Lock()

    def resolve(self, reference: SecretReference) -> SecretValue:
        with self._lock:
            cached = self._cache.get(reference.name)
            if cached is not None and self._clock() < cached.expires_at:
                return cached.value
            value = self._provider.resolve(reference)
            self._cache[reference.name] = _CachedSecret(
                value=value,
                expires_at=self._clock() + self._ttl_seconds,
            )
            return value

    def invalidate(self, reference: SecretReference | None = None) -> None:
        with self._lock:
            if reference is None:
                self._cache.clear()
            else:
                self._cache.pop(reference.name, None)

    def __repr__(self) -> str:
        return "RotatingSecretProvider(**redacted**)"


def _unsafe(value: str) -> bool:
    stripped = value.strip()
    return not stripped or stripped.casefold() in _PLACEHOLDERS
