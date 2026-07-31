from __future__ import annotations

from decision_assurance.production.egress import ResidencyEgressGuard


class TestAllowEgressGuard(ResidencyEgressGuard):
    """Explicit transport-test double; production providers default deny."""

    def __init__(self) -> None:
        super().__init__(lambda: None)

    def authorize_current(self, *, provider: str, connector: str, url: str) -> str:
        del provider, connector
        return url


ALLOW_EGRESS = TestAllowEgressGuard()
