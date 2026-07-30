from __future__ import annotations

import ipaddress
import posixpath
import socket
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class UrlPolicyRejected(ValueError):
    pass


class ResolverPort(Protocol):
    def resolve(self, hostname: str) -> tuple[str, ...]: ...


class SystemResolver:
    def resolve(self, hostname: str) -> tuple[str, ...]:
        try:
            values = {
                str(item[4][0])
                for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
            }
        except socket.gaierror as error:
            raise UrlPolicyRejected("URL_RESOLUTION_FAILED") from error
        return tuple(sorted(values))


@dataclass(frozen=True, slots=True)
class SafeUrl:
    original_url: str
    canonical_url: str
    domain: str


def normalize_domain(value: str) -> str:
    candidate = value.strip().rstrip(".").casefold()
    if not candidate or "/" in candidate or "@" in candidate:
        raise ValueError("INVALID_DOMAIN")
    try:
        return candidate.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise ValueError("INVALID_DOMAIN") from error


def _matches(domain: str, rule: str) -> bool:
    return domain == rule or domain.endswith("." + rule)


def _is_public(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.is_global and not any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_reserved,
            address.is_multicast,
            address.is_unspecified,
        )
    )


class PublicUrlPolicy:
    def __init__(
        self,
        resolver: ResolverPort,
        *,
        allowed_domains: tuple[str, ...] = (),
        blocked_domains: tuple[str, ...] = (),
    ):
        self._resolver = resolver
        self._allowed = tuple(normalize_domain(item) for item in allowed_domains)
        self._blocked = tuple(normalize_domain(item) for item in blocked_domains)

    def for_domains(
        self, *, allowed_domains: tuple[str, ...], blocked_domains: tuple[str, ...]
    ) -> PublicUrlPolicy:
        return PublicUrlPolicy(
            self._resolver,
            allowed_domains=allowed_domains,
            blocked_domains=blocked_domains,
        )

    def validate(self, value: str) -> SafeUrl:
        parsed = urlsplit(value)
        if parsed.scheme.casefold() != "https":
            raise UrlPolicyRejected("URL_SCHEME_NOT_ALLOWED")
        if parsed.username is not None or parsed.password is not None:
            raise UrlPolicyRejected("URL_CREDENTIALS_NOT_ALLOWED")
        if not parsed.hostname:
            raise UrlPolicyRejected("URL_NOT_PUBLIC")
        try:
            domain = normalize_domain(parsed.hostname)
            port = parsed.port
        except ValueError as error:
            raise UrlPolicyRejected("URL_NOT_PUBLIC") from error
        if port not in {None, 443}:
            raise UrlPolicyRejected("URL_PORT_NOT_ALLOWED")
        if domain in {"localhost", "localhost.localdomain"} or domain.endswith(".localhost"):
            raise UrlPolicyRejected("URL_NOT_PUBLIC")
        if any(_matches(domain, item) for item in self._blocked):
            raise UrlPolicyRejected("SOURCE_BLOCKED")
        if self._allowed and not any(_matches(domain, item) for item in self._allowed):
            raise UrlPolicyRejected("SOURCE_NOT_ALLOWED")

        literal: tuple[str, ...]
        try:
            literal = (str(ipaddress.ip_address(domain)),)
        except ValueError:
            literal = self._resolver.resolve(domain)
        if not literal or any(not _is_public(item) for item in literal):
            raise UrlPolicyRejected("URL_NOT_PUBLIC")

        path = posixpath.normpath(parsed.path or "/")
        if parsed.path.endswith("/") and not path.endswith("/"):
            path += "/"
        if not path.startswith("/"):
            path = "/" + path
        query = [
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.casefold().startswith("utm_") and key.casefold() not in {"gclid", "fbclid"}
        ]
        try:
            netloc = f"[{domain}]" if ipaddress.ip_address(domain).version == 6 else domain
        except ValueError:
            netloc = domain
        canonical = urlunsplit(("https", netloc, path, urlencode(sorted(query)), ""))
        return SafeUrl(value, canonical, domain)
