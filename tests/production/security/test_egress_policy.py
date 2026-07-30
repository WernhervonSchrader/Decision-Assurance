import pytest

from decision_assurance.production.egress import EgressRejected, HttpsEgressAllowlist
from decision_assurance.tenancy import TenantContext


def test_only_exact_https_provider_hosts_are_allowed() -> None:
    policy = HttpsEgressAllowlist(("api.search.brave.com", "api.firecrawl.dev"))
    tenant = TenantContext("tenant-a")

    assert policy.validate(tenant, "https://api.search.brave.com/res/v1/web/search") == (
        "https://api.search.brave.com/res/v1/web/search"
    )
    for url in (
        "http://api.search.brave.com/search",
        "https://api.search.brave.com.attacker.example/search",
        "https://127.0.0.1/search",
        "https://user:password@api.search.brave.com/search",
    ):
        with pytest.raises(EgressRejected):
            policy.validate(tenant, url)
