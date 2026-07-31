from __future__ import annotations

import time
from collections.abc import Callable

from ...production.egress import current_egress_context
from ...production.ports import StructuredLoggerPort


class ProviderCallTelemetry:
    """Emits bounded provider metadata without URLs, payloads, headers or credentials."""

    def __init__(
        self,
        logger: StructuredLoggerPort | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._logger = logger
        self._clock = clock

    def start(self) -> float:
        return self._clock()

    def record(
        self,
        started_at: float,
        *,
        connector: str,
        status_code: int | None,
        reason_code: str,
    ) -> None:
        context = current_egress_context()
        if self._logger is None or context is None:
            return
        duration_ms = max(0.0, (self._clock() - started_at) * 1000)
        try:
            self._logger.emit(
                "web_research.provider_call",
                level="INFO" if status_code is not None and status_code < 400 else "WARNING",
                correlation_id=context.correlation_id,
                fields={
                    "connector": connector,
                    "status_code": status_code,
                    "duration_ms": round(duration_ms, 3),
                    "reason_code": reason_code,
                },
            )
        except ValueError:
            return


NOOP_PROVIDER_TELEMETRY = ProviderCallTelemetry()
