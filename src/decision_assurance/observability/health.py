from __future__ import annotations

from collections.abc import Callable

from ..production.contracts import HealthComponent, HealthReport, HealthStatus
from ..production.ports import HealthProbePort


class ReadinessDependency(HealthProbePort):
    def __init__(self, component: str, ready: Callable[[], bool], reason_code: str):
        self._component = component
        self._ready = ready
        self._reason_code = reason_code

    def check(self) -> HealthComponent:
        try:
            available = self._ready()
        except Exception:
            available = False
        return HealthComponent(
            self._component,
            HealthStatus.HEALTHY if available else HealthStatus.UNAVAILABLE,
            None if available else self._reason_code,
        )


class StaticHealthProbe:
    def __init__(
        self,
        component: str,
        status: HealthStatus,
        reason_code: str | None = None,
        *,
        critical: bool = True,
    ):
        self._component = HealthComponent(component, status, reason_code, critical)

    def check(self) -> HealthComponent:
        return self._component


class HealthService:
    def __init__(self, probes: tuple[HealthProbePort, ...], *, clock: Callable[[], str]):
        if not probes:
            raise ValueError("HEALTH_PROBES_REQUIRED")
        self._probes = probes
        self._clock = clock

    def check(self) -> HealthReport:
        return HealthReport(tuple(probe.check() for probe in self._probes), self._clock())
