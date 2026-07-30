from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass


class ProviderCircuitOpen(RuntimeError):
    pass


@dataclass(slots=True)
class _CircuitState:
    failures: int = 0
    opened_until: float = 0.0


class InMemoryProviderCircuitBreaker:
    """Bounded tenant/provider breaker for one Worker process."""

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        recovery_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        if not 1 <= failure_threshold <= 100 or not 1 <= recovery_seconds <= 3600:
            raise ValueError("INVALID_CIRCUIT_BREAKER_POLICY")
        self._threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._clock = clock
        self._states: dict[tuple[str, str], _CircuitState] = {}
        self._lock = threading.Lock()

    def before_call(self, tenant_id: str, provider_id: str) -> None:
        key = self._key(tenant_id, provider_id)
        with self._lock:
            state = self._states.get(key)
            if state is None:
                return
            if state.opened_until > self._clock():
                raise ProviderCircuitOpen("PROVIDER_CIRCUIT_OPEN")
            if state.opened_until:
                state.opened_until = 0.0
                state.failures = self._threshold - 1

    def record_success(self, tenant_id: str, provider_id: str) -> None:
        key = self._key(tenant_id, provider_id)
        with self._lock:
            self._states.pop(key, None)

    def record_failure(self, tenant_id: str, provider_id: str, *, retryable: bool) -> None:
        key = self._key(tenant_id, provider_id)
        with self._lock:
            if not retryable:
                self._states.pop(key, None)
                return
            state = self._states.setdefault(key, _CircuitState())
            state.failures += 1
            if state.failures >= self._threshold:
                state.opened_until = self._clock() + self._recovery_seconds

    @staticmethod
    def _key(tenant_id: str, provider_id: str) -> tuple[str, str]:
        if not tenant_id.strip() or not provider_id.strip():
            raise ValueError("INVALID_CIRCUIT_CONTEXT")
        return tenant_id, provider_id


class NoOpProviderCircuitBreaker:
    def before_call(self, tenant_id: str, provider_id: str) -> None:
        del tenant_id, provider_id

    def record_success(self, tenant_id: str, provider_id: str) -> None:
        del tenant_id, provider_id

    def record_failure(self, tenant_id: str, provider_id: str, *, retryable: bool) -> None:
        del tenant_id, provider_id, retryable
