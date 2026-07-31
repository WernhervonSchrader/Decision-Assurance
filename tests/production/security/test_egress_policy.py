import pytest

from decision_assurance.production.egress import EgressRejected, HttpsEgressAllowlist
from decision_assurance.tenancy import TenantContext


def test_only_exact_https_provider_hosts_are_allowed() -> None:
    policy = HttpsEgressAllowlist(("api.openai.com", "api.firecrawl.dev"))
    tenant = TenantContext("tenant-a")

    assert policy.validate(tenant, "https://api.openai.com/v1/responses") == (
        "https://api.openai.com/v1/responses"
    )
    for url in (
        "http://api.openai.com/v1/responses",
        "https://api.openai.com.attacker.example/v1/responses",
        "https://127.0.0.1/search",
        "https://user:password@api.openai.com/v1/responses",
    ):
        with pytest.raises(EgressRejected):
            policy.validate(tenant, url)
