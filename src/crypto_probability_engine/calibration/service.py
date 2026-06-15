"""Read-only calibration report orchestration and sample gates."""

from __future__ import annotations

from typing import Any

from crypto_probability_engine.calibration.metrics import compute_calibration_metrics
from crypto_probability_engine.calibration.schemas import CalibrationReport, SampleGate
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.repository import (
    PersistenceRepository,
    build_persistence_repository,
)


def sample_gate_for(valid_count: int) -> SampleGate:
    if valid_count <= 0:
        return "NO_SAMPLES"
    if valid_count < 100:
        return "INSUFFICIENT_SAMPLE"
    if valid_count < 300:
        return "WARMING_UP"
    if valid_count < 500:
        return "PRELIMINARY_MEASURED"
    return "MEASURED"


def build_calibration_report(
    repository: PersistenceRepository | None = None,
    *,
    settings: Settings | None = None,
    timeframe: str | None = None,
    symbol: str | None = None,
    normalized_symbol: str | None = None,
    model_version: str | None = None,
    methodology_version: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
) -> CalibrationReport:
    """Build a JSON-safe diagnostic calibration report without mutating state."""

    repository = repository or build_persistence_repository(settings or Settings.from_env())
    rows = repository.fetch_resolved_prediction_outcomes_for_calibration(
        timeframe=timeframe,
        symbol=symbol,
        normalized_symbol=normalized_symbol,
        model_version=model_version,
        methodology_version=methodology_version,
        since=since,
        until=until,
        limit=limit,
    )
    computed = compute_calibration_metrics(rows)
    versions_present = _versions_present(rows)
    version_mix_warning = (
        len(versions_present["model_versions"]) > 1
        or len(versions_present["methodology_versions"]) > 1
    )
    gate = sample_gate_for(int(computed["valid_count"]))
    warnings = []
    if version_mix_warning:
        warnings.append("VERSION_MIX_WARNING")
    if (symbol or normalized_symbol) and gate in {"NO_SAMPLES", "INSUFFICIENT_SAMPLE"}:
        warnings.append("SYMBOL_INSUFFICIENT_SAMPLE")
    report: CalibrationReport = {
        "status": "OK",
        "scope": {
            "timeframe": timeframe,
            "symbol": symbol,
            "normalized_symbol": normalized_symbol,
            "model_version": model_version,
            "methodology_version": methodology_version,
            "since": since,
            "until": until,
            "limit": limit,
        },
        "repository": _repository_type(repository),
        "sample_count": int(computed["sample_count"]),
        "valid_count": int(computed["valid_count"]),
        "invalid_row_count": int(computed["invalid_row_count"]),
        "sample_gate": gate,
        "version_mix_warning": version_mix_warning,
        "versions_present": versions_present,
        "metrics": computed["metrics"],
        "reliability_buckets": computed["reliability_buckets"],
        "outcome_distribution": computed["outcome_distribution"],
        "terminal_return_diagnostics": computed["terminal_return_diagnostics"],
        "warnings": warnings,
    }
    return report


def _versions_present(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    model_versions = sorted(
        {str(row.get("model_version")) for row in rows if row.get("model_version")}
    )
    methodology_versions = sorted(
        {str(row.get("methodology_version")) for row in rows if row.get("methodology_version")}
    )
    return {
        "model_versions": model_versions,
        "methodology_versions": methodology_versions,
    }


def _repository_type(repository: PersistenceRepository) -> str:
    repo_type = getattr(repository, "repository_type", None)
    if callable(repo_type):
        return str(repo_type())
    return type(repository).__name__

