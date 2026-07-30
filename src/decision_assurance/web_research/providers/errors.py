from __future__ import annotations

from ..contracts import ProviderError


class ProviderRequestFailed(RuntimeError):
    """Provider-neutral failure that never exposes response bodies or credentials."""

    def __init__(self, error: ProviderError):
        self.error = error
        super().__init__(error.reason_code)
