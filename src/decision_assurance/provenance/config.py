from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath, PureWindowsPath


class SigningMode(str, Enum):
    DEVELOPMENT = "development"
    CONTROLLED_PILOT = "controlled-pilot"
    PRODUCTION_ADAPTER = "production-adapter"


@dataclass(frozen=True, slots=True)
class SigningSettings:
    mode: SigningMode
    key_id: str
    key_reference: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> SigningSettings:
        if set(value) != {"mode", "key_id", "key_reference"}:
            raise ValueError("INVALID_SIGNING_CONFIGURATION")
        try:
            mode = SigningMode(str(value["mode"]))
        except ValueError:
            raise ValueError("INVALID_SIGNING_MODE") from None
        key_id = value["key_id"]
        reference = value["key_reference"]
        if (
            not isinstance(key_id, str)
            or not 1 <= len(key_id) <= 128
            or not isinstance(reference, str)
            or not 1 <= len(reference) <= 512
        ):
            raise ValueError("INVALID_SIGNING_CONFIGURATION")
        if mode is SigningMode.DEVELOPMENT and not reference.startswith(".secrets/"):
            raise ValueError("DEVELOPMENT_SIGNING_REFERENCE_REQUIRED")
        if mode is SigningMode.CONTROLLED_PILOT:
            posix = PurePosixPath(reference)
            windows = PureWindowsPath(reference)
            parts = {*posix.parts, *windows.parts}
            if not (posix.is_absolute() or windows.is_absolute()) or ".secrets" in parts:
                raise ValueError("PILOT_SECRET_REFERENCE_REQUIRED")
        if mode is SigningMode.PRODUCTION_ADAPTER and not reference.startswith(
            ("kms-ref://", "hsm-ref://", "vault-ref://")
        ):
            raise ValueError("EXTERNAL_SIGNING_REFERENCE_REQUIRED")
        return cls(mode, key_id, reference)
