"""The automation origin: stamped by the server from the machine credential, never by the client.

It is deliberately NOT a ``PredictionOrigin``. The prediction-origin cohorts are calibration and
control evidence, and an automated run must never be storable, countable or relabelable as one of
them, so ``AUTOMATED_RADAR`` lives only in the automation domain and its isolated ledger.
"""

from __future__ import annotations

from enum import StrEnum


class AutomationOrigin(StrEnum):
    """The only evidence origin the automation route can emit."""

    AUTOMATED_RADAR = "AUTOMATED_RADAR"


AUTOMATED_RADAR = AutomationOrigin.AUTOMATED_RADAR.value
