import pytest

from decision_assurance.web_research.circuit_breaker import (
    InMemoryProviderCircuitBreaker,
    ProviderCircuitOpen,
)


def test_retryable_failures_open_and_success_closes_tenant_provider_circuit() -> None:
    now = 10.0
    breaker = InMemoryProviderCircuitBreaker(
        failure_threshold=2, recovery_seconds=30, clock=lambda: now
    )
    breaker.record_failure("tenant-a", "openai", retryable=True)
    breaker.before_call("tenant-a", "openai")
    breaker.record_failure("tenant-a", "openai", retryable=True)

    with pytest.raises(ProviderCircuitOpen, match="PROVIDER_CIRCUIT_OPEN"):
        breaker.before_call("tenant-a", "openai")
    breaker.before_call("tenant-b", "openai")

    now = 41.0
    breaker.before_call("tenant-a", "openai")
    breaker.record_success("tenant-a", "openai")
    breaker.before_call("tenant-a", "openai")


def test_non_retryable_failure_does_not_poison_circuit() -> None:
    breaker = InMemoryProviderCircuitBreaker(failure_threshold=1)
    breaker.record_failure("tenant-a", "firecrawl", retryable=False)
    breaker.before_call("tenant-a", "firecrawl")


@pytest.mark.parametrize("threshold,recovery", [(0, 30), (3, 0), (101, 30), (3, 3601)])
def test_invalid_policy_is_rejected(threshold: int, recovery: float) -> None:
    with pytest.raises(ValueError, match="INVALID_CIRCUIT_BREAKER_POLICY"):
        InMemoryProviderCircuitBreaker(failure_threshold=threshold, recovery_seconds=recovery)
