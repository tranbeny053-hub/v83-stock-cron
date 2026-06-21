"""Environment flag parsing."""

from __future__ import annotations

import os

TRUE_VALUES = {"1", "true", "yes", "on"}


def parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


QUANT_V2_SHADOW_ENABLED = parse_bool(
    os.environ.get("UCPE_QUANT_V2_SHADOW_ENABLED"),
    default=True,
)
