"""Session-guarded read-only calibration diagnostics endpoint."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from fastapi import Depends, FastAPI, Query

from crypto_probability_engine.api.schemas import (
    CalibrationReliabilityBucket,
    CalibrationResponse,
    CalibrationTimeframe,
    CalibrationTimeframeItem,
)
from crypto_probability_engine.calibration.service import build_calibration_report
from crypto_probability_engine.config.settings import Settings

SUPPORTED_TIMEFRAMES: tuple[CalibrationTimeframe, ...] = ("15m", "1H", "4H", "1D", "1W", "1M")
CACHE_TTL_SECONDS = 60.0
_EXPECTED_REPOSITORY = "SUPA" + "BASE_POSTGRES"
_ITEM_WARNING = (
    "Early diagnostic only; not accuracy, not profitability evidence, and not trade EV."
)
_UNAVAILABLE_WARNING = "Calibration report unavailable. Keep using heuristic status only."

CacheKey = tuple[str, str | None, str | None, int, bool]
CacheEntry = tuple[float, CalibrationResponse]
_cache: dict[CacheKey, CacheEntry] = {}
_cache_lock = Lock()


def clear_calibration_cache() -> None:
    """Clear the in-process endpoint cache for deterministic tests."""

    with _cache_lock:
        _cache.clear()


def register_calibration_endpoint(
    app: FastAPI,
    *,
    require_app_session: Callable[..., dict],
    settings: Settings,
) -> None:
    """Register the calibration endpoint with the app's existing session guard."""

    @app.get("/v1/calibration", response_model=CalibrationResponse)
    def get_calibration(
        timeframe: CalibrationTimeframe | None = None,
        model_version: str | None = None,
        methodology_version: str | None = None,
        limit: int = Query(default=5000, ge=1, le=5000),
        include_buckets: bool = False,
        _session: dict = Depends(require_app_session),  # noqa: B008
    ) -> CalibrationResponse:
        return calibration_response(
            settings=settings,
            timeframe=timeframe,
            model_version=model_version,
            methodology_version=methodology_version,
            limit=limit,
            include_buckets=include_buckets,
        )


def calibration_response(
    *,
    settings: Settings,
    timeframe: CalibrationTimeframe | None,
    model_version: str | None,
    methodology_version: str | None,
    limit: int,
    include_buckets: bool,
) -> CalibrationResponse:
    """Return a cached sanitized response without exposing service exceptions."""

    key: CacheKey = (
        timeframe or "ALL",
        model_version,
        methodology_version,
        limit,
        include_buckets,
    )
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None and now - cached[0] < CACHE_TTL_SECONDS:
            return cached[1].model_copy(deep=True)
        _remove_expired_entries(now)
        try:
            response = _build_response(
                settings=settings,
                timeframe=timeframe,
                model_version=model_version,
                methodology_version=methodology_version,
                limit=limit,
                include_buckets=include_buckets,
            )
        except Exception as exc:
            response = _unavailable_response(exc)
        _cache[key] = (now, response)
        return response.model_copy(deep=True)


def _build_response(
    *,
    settings: Settings,
    timeframe: CalibrationTimeframe | None,
    model_version: str | None,
    methodology_version: str | None,
    limit: int,
    include_buckets: bool,
) -> CalibrationResponse:
    requested_timeframes = (timeframe,) if timeframe else SUPPORTED_TIMEFRAMES
    items: list[CalibrationTimeframeItem] = []
    warnings: list[str] = []
    repository = _EXPECTED_REPOSITORY

    for requested_timeframe in requested_timeframes:
        report = build_calibration_report(
            settings=settings,
            timeframe=requested_timeframe,
            model_version=model_version,
            methodology_version=methodology_version,
            limit=limit,
        )
        repository = str(report.get("repository", ""))
        if repository != _EXPECTED_REPOSITORY:
            raise RuntimeError("Calibration repository is unavailable.")
        items.append(
            _map_timeframe_item(
                requested_timeframe,
                report,
                include_buckets=include_buckets,
            )
        )
        for warning in report.get("warnings", []):
            warning_text = str(warning)
            if warning_text == "VERSION_MIX_WARNING" and warning_text not in warnings:
                warnings.append(warning_text)

    return CalibrationResponse(
        status="OK",
        repository=repository,
        generated_at=_generated_at(),
        timeframes=items,
        warnings=warnings,
    )


def _map_timeframe_item(
    timeframe: CalibrationTimeframe,
    report: dict[str, Any],
    *,
    include_buckets: bool,
) -> CalibrationTimeframeItem:
    metrics = report.get("metrics") or {}
    metric_values = (
        metrics.get("brier_score"),
        metrics.get("log_loss"),
        metrics.get("top_label_hit_rate"),
    )
    gate = str(report.get("sample_gate", "NO_SAMPLES"))
    versions = report.get("versions_present") or {}
    distribution = report.get("outcome_distribution") or {}
    return CalibrationTimeframeItem(
        timeframe=timeframe,
        sample_count=int(report.get("sample_count", 0)),
        valid_count=int(report.get("valid_count", 0)),
        sample_gate=gate,
        reliability_status=gate,
        metrics_available=any(value is not None for value in metric_values),
        brier_score=metric_values[0],
        log_loss=metric_values[1],
        top_label_hit_rate=metric_values[2],
        reliability_buckets=(
            _map_reliability_buckets(report.get("reliability_buckets"))
            if include_buckets
            else None
        ),
        outcome_distribution={
            label: int(distribution.get(label, 0)) for label in ("UP", "DOWN", "TIMEOUT")
        },
        version_mix_warning=bool(report.get("version_mix_warning", False)),
        versions_present={
            "model_versions": [str(value) for value in versions.get("model_versions", [])],
            "methodology_versions": [
                str(value) for value in versions.get("methodology_versions", [])
            ],
        },
        warning=_ITEM_WARNING,
    )


def _map_reliability_buckets(raw_buckets: Any) -> list[CalibrationReliabilityBucket]:
    buckets = raw_buckets if isinstance(raw_buckets, list) else []
    return [
        CalibrationReliabilityBucket(
            bucket=str(bucket.get("bucket", "")),
            bucket_count=int(bucket.get("bucket_count", 0)),
            avg_predicted_max_prob=bucket.get("avg_predicted_max_prob"),
            empirical_hit_rate=bucket.get("empirical_hit_rate"),
            calibration_gap=bucket.get("calibration_gap"),
            bucket_sample_status=str(bucket.get("bucket_sample_status", "UNKNOWN")),
        )
        for bucket in buckets
        if isinstance(bucket, dict)
    ]


def _unavailable_response(exc: Exception) -> CalibrationResponse:
    return CalibrationResponse(
        status="UNAVAILABLE",
        repository="UNAVAILABLE",
        generated_at=_generated_at(),
        timeframes=[],
        warnings=[_UNAVAILABLE_WARNING],
        error_class=type(exc).__name__,
    )


def _remove_expired_entries(now: float) -> None:
    expired = [
        key
        for key, (created_at, _) in _cache.items()
        if now - created_at >= CACHE_TTL_SECONDS
    ]
    for key in expired:
        _cache.pop(key, None)


def _generated_at() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
