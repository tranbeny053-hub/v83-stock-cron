"""Deterministic memory features."""

from __future__ import annotations


def memory_feature_state() -> dict:
    return {
        "status": "DEGRADED",
        "reason": "Durable memory is optional and not configured by default.",
        "influence_frac": 0.0,
    }

