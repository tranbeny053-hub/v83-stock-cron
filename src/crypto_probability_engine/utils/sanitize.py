"""Sanitization helpers for debug/export payloads."""

from __future__ import annotations

from typing import Any

SENSITIVE_TOKENS = (
    "code",
    "hash",
    "key",
    "token",
    "password",
    "passphrase",
    "secret",
)


def sanitize_for_export(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            lower = key.lower()
            if any(token in lower for token in SENSITIVE_TOKENS):
                sanitized[key] = "set (****)" if item else None
            elif lower in {"body", "article_body", "full_text", "content"}:
                sanitized[key] = "[removed]"
            else:
                sanitized[key] = sanitize_for_export(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_for_export(item) for item in value]
    return value

