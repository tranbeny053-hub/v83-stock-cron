"""Correlation and beta placeholder for Sprint 1."""

from __future__ import annotations


def correlation_beta_state() -> dict:
    return {
        "status": "DEGRADED",
        "reason": "Correlation/beta requires verified cross-asset history.",
        "beta": None,
        "influence_frac": 0.0,
    }

