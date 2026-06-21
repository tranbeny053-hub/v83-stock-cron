"""Typed failures for keyless public derivatives adapters."""

from __future__ import annotations


class PublicDerivativesAdapterError(RuntimeError):
    """Stable adapter failure without provider response leakage."""

    def __init__(self, code: str, message: str, *, provider: str, endpoint: str) -> None:
        super().__init__(message)
        self.code = code
        self.provider = provider
        self.endpoint = endpoint
