from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit

from ..tenancy import TenantContext

_HOST = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


class EgressRejected(PermissionError):
    pass


class HttpsEgressAllowlist:
    def __init__(self, hosts: tuple[str, ...]):
        normalized = tuple(sorted({item.casefold().rstrip(".") for item in hosts}))
        if not normalized or any(not _valid_public_hostname(item) for item in normalized):
            raise ValueError("INVALID_EGRESS_ALLOWLIST")
        self._hosts = frozenset(normalized)

    def validate(self, tenant: TenantContext, url: str) -> str:
        del tenant
        try:
            parsed = urlsplit(url)
            host = (parsed.hostname or "").casefold().rstrip(".")
            port = parsed.port
        except ValueError:
            raise EgressRejected("EGRESS_REJECTED") from None
        if (
            parsed.scheme != "https"
            or not host
            or host not in self._hosts
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
            or not _valid_public_hostname(host)
        ):
            raise EgressRejected("EGRESS_REJECTED")
        return urlunsplit(("https", parsed.netloc.casefold(), parsed.path or "/", parsed.query, ""))


def _valid_public_hostname(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        return bool(_HOST.fullmatch(host)) and host != "localhost" and not host.endswith(".local")
