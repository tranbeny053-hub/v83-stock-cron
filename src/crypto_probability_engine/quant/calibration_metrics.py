"""Calibration and reliability status."""

from __future__ import annotations

from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A


def calibration_state() -> dict:
    return {
        "calibration_status": DEFAULT_PHASE1A.calibration_status,
        "reliability_status": DEFAULT_PHASE1A.reliability_status,
        "profitability_claim": False,
        "reason": "Sprint 1 deterministic baseline is not calibrated.",
    }

