"""JSON-safe calibration report schema helpers."""

from __future__ import annotations

from typing import Literal, TypedDict

OutcomeLabel = Literal["UP", "DOWN", "TIMEOUT"]
SampleGate = Literal[
    "NO_SAMPLES",
    "INSUFFICIENT_SAMPLE",
    "WARMING_UP",
    "PRELIMINARY_MEASURED",
    "MEASURED",
]

OUTCOME_LABELS: tuple[OutcomeLabel, ...] = ("UP", "DOWN", "TIMEOUT")
TOP_LABEL_TIE_ORDER: tuple[OutcomeLabel, ...] = ("UP", "DOWN", "TIMEOUT")
RELIABILITY_BUCKETS: tuple[tuple[float, float], ...] = (
    (0.00, 0.40),
    (0.40, 0.50),
    (0.50, 0.60),
    (0.60, 0.70),
    (0.70, 0.80),
    (0.80, 0.90),
    (0.90, 1.00),
)


class CalibrationScope(TypedDict, total=False):
    timeframe: str | None
    symbol: str | None
    normalized_symbol: str | None
    model_version: str | None
    methodology_version: str | None
    since: str | None
    until: str | None
    limit: int | None


class CalibrationReport(TypedDict):
    status: str
    scope: CalibrationScope
    repository: str
    sample_count: int
    valid_count: int
    invalid_row_count: int
    sample_gate: SampleGate
    version_mix_warning: bool
    versions_present: dict[str, list[str]]
    metrics: dict
    reliability_buckets: list[dict]
    outcome_distribution: dict[str, int]
    terminal_return_diagnostics: dict
    warnings: list[str]

