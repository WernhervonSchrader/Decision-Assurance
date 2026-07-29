import pytest

from decision_assurance.web_research.url_policy import (
    PublicUrlPolicy,
    UrlPolicyRejected,
    normalize_domain,
)


class Resolver:
    def __init__(self, values: dict[str, tuple[str, ...]]):
        self.values = values

    def resolve(self, hostname: str) -> tuple[str, ...]:
        return self.values.get(hostname, ("93.184.216.34",))


def test_domain_and_canonical_url_normalization() -> None:
    policy = PublicUrlPolicy(Resolver({}))
    safe = policy.validate("https://EXAMPLE.org:443/a/../page/?utm_source=x&b=2&a=1#fragment")
    assert normalize_domain("BÜCHER.Example.") == "xn--bcher-kva.example"
    assert safe.domain == "example.org"
    assert safe.canonical_url == "https://example.org/page/?a=1&b=2"


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("http://example.org", "URL_SCHEME_NOT_ALLOWED"),
        ("https://user:password@example.org", "URL_CREDENTIALS_NOT_ALLOWED"),
        ("https://localhost/page", "URL_NOT_PUBLIC"),
        ("https://169.254.169.254/latest/meta-data", "URL_NOT_PUBLIC"),
        ("https://[::1]/", "URL_NOT_PUBLIC"),
    ],
)
def test_unsafe_urls_fail_closed(url: str, code: str) -> None:
    with pytest.raises(UrlPolicyRejected, match=code):
        PublicUrlPolicy(Resolver({})).validate(url)


def test_dns_resolution_and_domain_rules_fail_closed() -> None:
    private = PublicUrlPolicy(Resolver({"example.org": ("10.0.0.1",)}))
    with pytest.raises(UrlPolicyRejected, match="URL_NOT_PUBLIC"):
        private.validate("https://example.org")

    deny = PublicUrlPolicy(Resolver({}), blocked_domains=("blocked.example",))
    with pytest.raises(UrlPolicyRejected, match="SOURCE_BLOCKED"):
        deny.validate("https://sub.blocked.example/page")

    allow = PublicUrlPolicy(Resolver({}), allowed_domains=("example.org",))
    with pytest.raises(UrlPolicyRejected, match="SOURCE_NOT_ALLOWED"):
        allow.validate("https://other.example/page")
