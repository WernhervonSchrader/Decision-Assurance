from __future__ import annotations

import base64
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("SIGNING_TIME_MUST_BE_AWARE")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class SignatureEnvelope:
    format_version: str
    algorithm: str
    key_id: str
    signed_at: str
    signature: str

    def as_dict(self) -> dict[str, str]:
        return {
            "format_version": self.format_version,
            "algorithm": self.algorithm,
            "key_id": self.key_id,
            "signed_at": self.signed_at,
            "signature": self.signature,
        }


class ExportSigner(Protocol):
    @property
    def key_id(self) -> str: ...

    def sign(self, payload: bytes) -> SignatureEnvelope: ...


@dataclass(frozen=True, slots=True)
class VerificationKey:
    key_id: str
    public_key_pem: bytes
    not_before: datetime
    not_after: datetime
    revoked_at: datetime | None = None

    def usable_at(self, value: datetime) -> bool:
        instant = _utc(value)
        return _utc(self.not_before) <= instant <= _utc(self.not_after) and (
            self.revoked_at is None or instant < _utc(self.revoked_at)
        )


class VerificationKeyResolver(Protocol):
    def resolve(self, key_id: str) -> VerificationKey | None: ...


class InMemoryVerificationKeyResolver:
    def __init__(self, keys: Mapping[str, VerificationKey]):
        self._keys = dict(keys)

    def resolve(self, key_id: str) -> VerificationKey | None:
        return self._keys.get(key_id)


class Ed25519Signer:
    def __init__(
        self,
        private_key: Ed25519PrivateKey,
        *,
        key_id: str,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        if not key_id or len(key_id) > 128:
            raise ValueError("INVALID_SIGNING_KEY_ID")
        self._private_key = private_key
        self._key_id = key_id
        self._clock = clock

    @property
    def key_id(self) -> str:
        return self._key_id

    @property
    def public_key_pem(self) -> bytes:
        return self._private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def sign(self, payload: bytes) -> SignatureEnvelope:
        unsigned = SignatureEnvelope("1.0.0", "EdDSA", self.key_id, _timestamp(self._clock()), "")
        signature = self._private_key.sign(_signing_input(unsigned, payload))
        encoded = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
        return SignatureEnvelope(
            unsigned.format_version,
            unsigned.algorithm,
            unsigned.key_id,
            unsigned.signed_at,
            encoded,
        )


class FileEd25519Signer(Ed25519Signer):
    @classmethod
    def from_reference(
        cls,
        path: Path,
        *,
        key_id: str,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> FileEd25519Signer:
        if not path.is_file():
            raise ValueError("SIGNING_KEY_REFERENCE_UNAVAILABLE")
        loaded = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(loaded, Ed25519PrivateKey):
            raise ValueError("SIGNING_KEY_TYPE_UNSUPPORTED")
        return cls(loaded, key_id=key_id, clock=clock)


class ExternalSigningAdapter:
    def __init__(
        self, key_id: str, callback: Callable[[bytes], bytes], clock: Callable[[], datetime]
    ):
        if not key_id:
            raise ValueError("INVALID_SIGNING_KEY_ID")
        self._key_id = key_id
        self._callback = callback
        self._clock = clock

    @property
    def key_id(self) -> str:
        return self._key_id

    def sign(self, payload: bytes) -> SignatureEnvelope:
        unsigned = SignatureEnvelope("1.0.0", "EdDSA", self.key_id, _timestamp(self._clock()), "")
        signature = self._callback(_signing_input(unsigned, payload))
        if len(signature) != 64:
            raise ValueError("EXTERNAL_SIGNATURE_INVALID")
        encoded = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
        return SignatureEnvelope(
            unsigned.format_version,
            unsigned.algorithm,
            unsigned.key_id,
            unsigned.signed_at,
            encoded,
        )


class FakeEd25519Signer(Ed25519Signer):
    def __init__(
        self,
        *,
        key_id: str = "fake-test-key",
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        super().__init__(
            Ed25519PrivateKey.from_private_bytes(b"\x19" * 32), key_id=key_id, clock=clock
        )


def verify_ed25519(
    public_key_pem: bytes,
    payload: bytes,
    signature: str,
    envelope: SignatureEnvelope,
) -> bool:
    try:
        padded = signature + "=" * (-len(signature) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        key = serialization.load_pem_public_key(public_key_pem)
        if not isinstance(key, Ed25519PublicKey):
            return False
        key.verify(decoded, _signing_input(envelope, payload))
        return True
    except (ValueError, TypeError, InvalidSignature):
        return False


def _signing_input(envelope: SignatureEnvelope, payload: bytes) -> bytes:
    protected = {
        "algorithm": envelope.algorithm,
        "format_version": envelope.format_version,
        "key_id": envelope.key_id,
        "signed_at": envelope.signed_at,
    }
    canonical = json.dumps(
        protected, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return canonical + b"." + payload
