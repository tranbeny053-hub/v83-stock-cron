"""Global risk flags."""

from __future__ import annotations


def global_risk_state() -> dict:
    return {
        "shelter_mode": False,
        "kill_switch": False,
        "status": "OK",
    }

