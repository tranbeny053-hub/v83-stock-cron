"""Write-free OKX cadence-readiness diagnostic.

This probe measures whether the GitHub runner can read the public OKX resources
needed by the future v1 cadence collector. It does not call the collector,
analysis service, persistence, databases, or Binance.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from crypto_probability_engine.adapters.derivatives.errors import (
    PublicDerivativesAdapterError,
)
from crypto_probability_engine.adapters.derivatives.okx_swap import OkxSwapDerivativesAdapter
from crypto_probability_engine.adapters.derivatives_endpoints import (
    OKX_CURRENT_FUNDING_PATH,
    OKX_CURRENT_OPEN_INTEREST_PATH,
    OKX_INSTRUMENTS_PATH,
    OKX_PUBLIC_BASE_URL,
    DerivativesPublicHttpClient,
)
from crypto_probability_engine.adapters.types import ProviderError
from crypto_probability_engine.derivatives_intel.instruments import (
    InstrumentResolution,
    InstrumentResolutionStatus,
    resolve_okx_swap_instrument,
)
from crypto_probability_engine.derivatives_intel.provenance import (
    build_okx_current_funding_metric,
    build_okx_current_open_interest_metrics,
)
from crypto_probability_engine.derivatives_intel.schemas import (
    METHODOLOGY_VERSION_V1,
    PROVIDER_POLICY_VERSION_V1,
)
from crypto_probability_engine.normalizers.symbols import normalize_symbol

DIAGNOSTIC_SCHEMA_VERSION = "okx-cadence-readiness.v1"
DIAGNOSTIC_SOURCE_MILESTONE = "wave-4d3-ops-2d2a-cadence-readiness-diagnostic"
DERIVATIVES_METHODOLOGY_VERSION = METHODOLOGY_VERSION_V1
PROVIDER_POLICY_VERSION = PROVIDER_POLICY_VERSION_V1
REQUIRED_PROVIDER = "OKX_SWAP"
OKX_CANDLES_PATH = "/api/v5/market/candles"
OKX_SERVER_TIME_PATH = "/api/v5/public/time"

TIMEFRAME_SECONDS = {"1H": 3600, "4H": 14_400}
MATRIX = (
    ("BTC/USDT", "1H"),
    ("BTC/USDT", "4H"),
    ("ETH/USDT", "1H"),
    ("ETH/USDT", "4H"),
)
MAX_CELLS = 4
REQUIRED_METRIC_IDS = (
    "okx.funding.current_estimate",
    "okx.open_interest.current.contracts",
    "okx.open_interest.current.base",
    "okx.open_interest.current.usd",
)
ALLOWED_ENDPOINTS = frozenset(
    {
        OKX_INSTRUMENTS_PATH,
        OKX_CURRENT_FUNDING_PATH,
        OKX_CURRENT_OPEN_INTEREST_PATH,
        OKX_CANDLES_PATH,
        OKX_SERVER_TIME_PATH,
    }
)
TOP_LEVEL_KEYS = frozenset(
    {
        "diagnostic_schema_version",
        "source_milestone",
        "source_commit_sha",
        "runner_identity_class",
        "process_started_at_utc",
        "diagnostic_completed_at_utc",
        "selected_cell_count",
        "derivatives_methodology_version",
        "provider_policy_version",
        "required_provider",
        "derivatives_logical_request_count",
        "candle_logical_request_count",
        "server_time_logical_request_count",
        "total_logical_request_count",
        "derivatives_http_attempt_count",
        "candle_http_attempt_count",
        "server_time_http_attempt_count",
        "total_http_attempt_count",
        "binance_request_count",
        "okx_server_time_utc",
        "okx_server_clock_offset_ms",
        "final_classification",
        "cells",
    }
)
CELL_KEYS = frozenset(
    {
        "symbol",
        "timeframe",
        "canonical_reference_close_utc",
        "candle_open_utc",
        "candle_confirmed",
        "observed_request_start_offset_seconds",
        "observed_completion_offset_seconds",
        "okx_inst_id",
        "provider_available",
        "block_status",
        "classification",
        "required_metric_ids",
        "present_metric_ids",
        "metric_valid_count",
        "no_lookahead_pass",
        "funding_response_ts_utc",
        "funding_time_utc",
        "next_funding_time_utc",
        "open_interest_ts_utc",
        "request_timings",
    }
)
TIMING_KEYS = frozenset(
    {
        "endpoint_path",
        "request_started_at_utc",
        "request_completed_at_utc",
        "elapsed_ms",
        "request_start_offset_seconds",
        "request_completed_offset_seconds",
        "http_status_class",
        "logical_request_count",
        "http_attempt_count",
    }
)
FINAL_CLASSIFICATION_ORDER = (
    "CONFIGURATION_ERROR",
    "RATE_LIMITED",
    "TIMEOUT",
    "HTTP_ERROR",
    "PROVIDER_UNAVAILABLE",
    "TIMESTAMP_INVALID",
    "NO_LOOKAHEAD_FAILED",
    "AVAILABLE_PARTIAL",
    "AVAILABLE_COMPLETE",
)


@dataclass(frozen=True)
class DiagnosticOptions:
    symbol: str = "ALL"
    timeframe: str = "ALL"
    max_cells: int = MAX_CELLS
    source_commit_sha: str = "LOCAL_UNVERIFIED"
    runner_identity_class: str = "local-offline-test"


@dataclass(frozen=True)
class DiagnosticDependencies:
    now_utc: Callable[[], datetime] = lambda: datetime.now(UTC)
    monotonic: Callable[[], float] = time.monotonic
    client_factory: Callable[[], DerivativesPublicHttpClient] = lambda: (
        DerivativesPublicHttpClient(
            timeout_seconds=3.0,
            max_retries=0,
            rate_limit_per_min=120,
        )
    )
    step_summary_path: str | None = None


DEFAULT_DEPENDENCIES = DiagnosticDependencies()


@dataclass(frozen=True)
class SymbolObservation:
    resolution: InstrumentResolution
    funding_payload: list[dict[str, Any]] | None
    open_interest_payload: list[dict[str, Any]] | None
    funding_fetched_at_utc: datetime | None
    open_interest_fetched_at_utc: datetime | None
    timings: tuple[dict[str, object], ...]
    classification: str | None


class RecordingOkxHttpClient:
    """Small counting wrapper around the approved public OKX client."""

    def __init__(
        self,
        client: DerivativesPublicHttpClient,
        *,
        now_utc: Callable[[], datetime],
        monotonic: Callable[[], float],
    ) -> None:
        self._client = client
        self._now_utc = now_utc
        self._monotonic = monotonic
        self.timings: list[dict[str, object]] = []
        self._last_error_by_path: dict[str, str] = {}
        self._last_completed_by_path: dict[str, datetime] = {}
        self._last_status_class_by_path: dict[str, str] = {}
        self._logical_counts = {"derivatives": 0, "candle": 0, "server_time": 0}
        self._attempt_counts = {"derivatives": 0, "candle": 0, "server_time": 0}
        self.binance_request_count = 0

    def get_json(
        self,
        *,
        base_url: str,
        path: str,
        params: Mapping[str, Any],
        provider: str,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        if base_url != OKX_PUBLIC_BASE_URL:
            self.binance_request_count += 1
            raise ProviderError(
                "PROVIDER_DEGRADED",
                "Non-OKX public host is outside this diagnostic boundary.",
                provider=provider,
            )
        if path not in ALLOWED_ENDPOINTS:
            raise ProviderError(
                "PROVIDER_DEGRADED",
                "Public endpoint is outside this diagnostic boundary.",
                provider=provider,
            )
        category = _request_category(path)
        self._logical_counts[category] += 1
        self._attempt_counts[category] += 1
        logical_count = self._logical_counts[category]
        attempt_count = self._attempt_counts[category]
        started_dt = _require_utc(self._now_utc())
        started_mono = self._monotonic()
        status_class = "UNKNOWN"
        try:
            payload = self._client.get_json(
                base_url=base_url,
                path=path,
                params=params,
                provider=provider,
                headers=headers,
            )
            status_class = "2xx"
            return payload
        except ProviderError as exc:
            status_class = _status_class_from_provider_error(exc)
            self._last_error_by_path[path] = _classification_from_provider_error(exc)
            raise
        finally:
            completed_mono = self._monotonic()
            completed_dt = _require_utc(self._now_utc())
            elapsed_ms = max(0, int(round((completed_mono - started_mono) * 1000)))
            self._last_completed_by_path[path] = completed_dt
            self._last_status_class_by_path[path] = status_class
            self.timings.append(
                {
                    "endpoint_path": path,
                    "request_started_at_utc": _iso(started_dt),
                    "request_completed_at_utc": _iso(completed_dt),
                    "elapsed_ms": elapsed_ms,
                    "request_start_offset_seconds": None,
                    "request_completed_offset_seconds": None,
                    "http_status_class": status_class,
                    "logical_request_count": logical_count,
                    "http_attempt_count": attempt_count,
                }
            )

    def counts(self) -> dict[str, int]:
        return {
            "derivatives_logical_request_count": self._logical_counts["derivatives"],
            "candle_logical_request_count": self._logical_counts["candle"],
            "server_time_logical_request_count": self._logical_counts["server_time"],
            "total_logical_request_count": sum(self._logical_counts.values()),
            "derivatives_http_attempt_count": self._attempt_counts["derivatives"],
            "candle_http_attempt_count": self._attempt_counts["candle"],
            "server_time_http_attempt_count": self._attempt_counts["server_time"],
            "total_http_attempt_count": sum(self._attempt_counts.values()),
            "binance_request_count": self.binance_request_count,
        }

    def latest_completed(self, path: str) -> datetime | None:
        return self._last_completed_by_path.get(path)

    def latest_error(self, path: str) -> str | None:
        return self._last_error_by_path.get(path)

    def timings_since(self, start_index: int) -> tuple[dict[str, object], ...]:
        return tuple(dict(row) for row in self.timings[start_index:])


def parse_args(argv: Sequence[str] | None = None) -> DiagnosticOptions:
    parser = argparse.ArgumentParser(description="Measure OKX cadence readiness without writes.")
    parser.add_argument("--symbol", choices=("BTC/USDT", "ETH/USDT", "ALL"), default="ALL")
    parser.add_argument("--timeframe", choices=("1H", "4H", "ALL"), default="ALL")
    parser.add_argument("--max-cells", type=int, default=MAX_CELLS)
    parser.add_argument("--source-commit-sha", default="LOCAL_UNVERIFIED")
    parser.add_argument(
        "--runner-identity-class",
        choices=("github-hosted-ubuntu", "local-offline-test"),
        default="local-offline-test",
    )
    args = parser.parse_args(argv)
    return DiagnosticOptions(
        symbol=args.symbol,
        timeframe=args.timeframe,
        max_cells=args.max_cells,
        source_commit_sha=args.source_commit_sha,
        runner_identity_class=args.runner_identity_class,
    )


def run_diagnostic(
    options: DiagnosticOptions,
    *,
    dependencies: DiagnosticDependencies = DEFAULT_DEPENDENCIES,
) -> dict[str, Any]:
    process_started_at = _require_utc(dependencies.now_utc())
    cells = _select_cells(options)
    if options.max_cells < 1 or options.max_cells > MAX_CELLS or len(cells) > options.max_cells:
        completed = _require_utc(dependencies.now_utc())
        return _output(
            options,
            process_started_at_utc=process_started_at,
            completed_at_utc=completed,
            cells=[],
            counts=_zero_counts(),
            okx_server_time_utc=None,
            okx_server_clock_offset_ms=None,
            final_classification="CONFIGURATION_ERROR",
        )

    recorder = RecordingOkxHttpClient(
        dependencies.client_factory(),
        now_utc=dependencies.now_utc,
        monotonic=dependencies.monotonic,
    )
    adapter = OkxSwapDerivativesAdapter(http_client=recorder)
    server_time_utc, clock_offset_ms, server_classification = _probe_server_time(
        recorder,
        local_now=process_started_at,
    )

    instruments_payload: list[dict[str, Any]] | None = None
    symbol_observations: dict[str, SymbolObservation] = {}
    rows: list[dict[str, object]] = []
    classifications = [server_classification] if server_classification else []
    for symbol, timeframe in cells:
        row, instruments_payload = _measure_cell(
            symbol,
            timeframe,
            recorder=recorder,
            adapter=adapter,
            instruments_payload=instruments_payload,
            symbol_observations=symbol_observations,
            now_utc=dependencies.now_utc,
        )
        rows.append(row)
        classifications.append(str(row["classification"]))

    completed_at = _require_utc(dependencies.now_utc())
    output = _output(
        options,
        process_started_at_utc=process_started_at,
        completed_at_utc=completed_at,
        cells=rows,
        counts=recorder.counts(),
        okx_server_time_utc=server_time_utc,
        okx_server_clock_offset_ms=clock_offset_ms,
        final_classification=_reduce_classification(classifications),
    )
    if dependencies.step_summary_path:
        append_step_summary(dependencies.step_summary_path, output)
    return output


def append_step_summary(path: str, output: Mapping[str, Any]) -> None:
    lines = [
        "## OKX Cadence Readiness Diagnostic",
        "",
        f"* Final classification: `{output['final_classification']}`",
        f"* Cells: `{output['selected_cell_count']}`",
        f"* Total logical requests: `{output['total_logical_request_count']}`",
        f"* Total HTTP attempts: `{output['total_http_attempt_count']}`",
        "",
        "| Symbol | Timeframe | Classification | Block | Metrics |",
        "|---|---:|---|---|---:|",
    ]
    for cell in output["cells"]:
        lines.append(
            "| {symbol} | {timeframe} | {classification} | {block_status} | "
            "{metric_valid_count} |".format(**cell)
        )
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main(
    argv: Sequence[str] | None = None,
    *,
    dependencies: DiagnosticDependencies | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
    options = parse_args(argv)
    environment = os.environ if environ is None else environ
    deps = dependencies or DiagnosticDependencies(
        step_summary_path=environment.get("GITHUB_STEP_SUMMARY")
    )
    try:
        output = run_diagnostic(options, dependencies=deps)
        _assert_output_contract(output)
        print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    except Exception:
        safe_output = _output(
            options,
            process_started_at_utc=datetime.now(UTC),
            completed_at_utc=datetime.now(UTC),
            cells=[],
            counts=_zero_counts(),
            okx_server_time_utc=None,
            okx_server_clock_offset_ms=None,
            final_classification="PROVIDER_UNAVAILABLE",
        )
        print(json.dumps(safe_output, sort_keys=True, separators=(",", ":")))
        return 1
    return 0


def _measure_cell(
    symbol: str,
    timeframe: str,
    *,
    recorder: RecordingOkxHttpClient,
    adapter: OkxSwapDerivativesAdapter,
    instruments_payload: list[dict[str, Any]] | None,
    symbol_observations: dict[str, SymbolObservation],
    now_utc: Callable[[], datetime],
) -> tuple[dict[str, object], list[dict[str, Any]] | None]:
    normalized = normalize_symbol(symbol)
    candle_start_index = len(recorder.timings)
    candle_payload: Any = None
    try:
        candle_payload = recorder.get_json(
            base_url=OKX_PUBLIC_BASE_URL,
            path=OKX_CANDLES_PATH,
            params={"instId": normalized.provider_symbols["okx"], "bar": timeframe, "limit": "10"},
            provider=REQUIRED_PROVIDER,
        )
        candle_classification = None
    except ProviderError:
        candle_classification = recorder.latest_error(OKX_CANDLES_PATH) or "PROVIDER_UNAVAILABLE"
    candle_timings = recorder.timings_since(candle_start_index)
    candle = _latest_closed_candle(candle_payload, timeframe) if candle_payload else None
    if candle is None:
        candle_classification = candle_classification or "TIMESTAMP_INVALID"
        candle_open_utc = None
        reference_close_utc = None
        candle_confirmed = False
    else:
        candle_open_utc, reference_close_utc = candle
        candle_confirmed = True

    if symbol not in symbol_observations:
        observation, instruments_payload = _fetch_symbol_observation(
            normalized.display,
            recorder=recorder,
            adapter=adapter,
            instruments_payload=instruments_payload,
        )
        symbol_observations[symbol] = observation
    observation = symbol_observations[symbol]
    analysis_completed_at = _require_utc(now_utc())
    metrics = _build_metrics_for_cell(observation, analysis_completed_at)
    present_metric_ids = tuple(
        metric["metric_id"] for metric in metrics if metric.get("metric_id") in REQUIRED_METRIC_IDS
    )
    valid_metrics = tuple(
        metric
        for metric in metrics
        if metric.get("metric_id") in REQUIRED_METRIC_IDS and metric.get("status") == "VALID"
    )
    no_lookahead_pass = (
        len(valid_metrics) == len(REQUIRED_METRIC_IDS)
        and all(metric.get("no_lookahead_assertion") is True for metric in valid_metrics)
    )
    no_lookahead_failed = (
        len(present_metric_ids) == len(REQUIRED_METRIC_IDS)
        and any(
            metric.get("status") == "DEGRADED"
            and metric.get("no_lookahead_assertion") is False
            for metric in metrics
            if metric.get("metric_id") in REQUIRED_METRIC_IDS
        )
    )
    provider_available = observation.classification is None and bool(metrics)
    block_status = _block_status(provider_available, valid_metrics)
    classification = _cell_classification(
        candle_classification=candle_classification,
        observation_classification=observation.classification,
        block_status=block_status,
        no_lookahead_pass=no_lookahead_pass,
        no_lookahead_failed=no_lookahead_failed,
        metric_valid_count=len(valid_metrics),
    )
    request_timings = _timings_with_offsets(
        (*candle_timings, *observation.timings),
        reference_close_utc=reference_close_utc,
    )
    first_started = _first_timing_dt(request_timings, "request_started_at_utc")
    completed = (
        _last_timing_dt(request_timings, "request_completed_at_utc") or analysis_completed_at
    )
    return (
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "canonical_reference_close_utc": _iso(reference_close_utc),
            "candle_open_utc": _iso(candle_open_utc),
            "candle_confirmed": candle_confirmed,
            "observed_request_start_offset_seconds": _offset_seconds(
                first_started, reference_close_utc
            ),
            "observed_completion_offset_seconds": _offset_seconds(completed, reference_close_utc),
            "okx_inst_id": observation.resolution.candidate,
            "provider_available": provider_available,
            "block_status": block_status,
            "classification": classification,
            "required_metric_ids": list(REQUIRED_METRIC_IDS),
            "present_metric_ids": sorted(present_metric_ids),
            "metric_valid_count": len(valid_metrics),
            "no_lookahead_pass": no_lookahead_pass,
            "funding_response_ts_utc": _payload_ts(observation.funding_payload, "ts"),
            "funding_time_utc": _payload_ts(observation.funding_payload, "fundingTime"),
            "next_funding_time_utc": _payload_ts(observation.funding_payload, "nextFundingTime"),
            "open_interest_ts_utc": _payload_ts(observation.open_interest_payload, "ts"),
            "request_timings": request_timings,
        },
        instruments_payload,
    )


def _fetch_symbol_observation(
    symbol: str,
    *,
    recorder: RecordingOkxHttpClient,
    adapter: OkxSwapDerivativesAdapter,
    instruments_payload: list[dict[str, Any]] | None,
) -> tuple[SymbolObservation, list[dict[str, Any]] | None]:
    start_index = len(recorder.timings)
    classification: str | None = None
    if instruments_payload is None:
        try:
            instruments_payload = adapter.fetch_instruments()
        except PublicDerivativesAdapterError:
            instruments_payload = None
            classification = recorder.latest_error(OKX_INSTRUMENTS_PATH) or "PROVIDER_UNAVAILABLE"
    resolution = resolve_okx_swap_instrument(symbol, instruments_payload or [])
    if resolution.status != InstrumentResolutionStatus.SUPPORTED and classification is None:
        classification = "PROVIDER_UNAVAILABLE"
    funding_payload: list[dict[str, Any]] | None = None
    open_interest_payload: list[dict[str, Any]] | None = None
    if resolution.candidate and classification is None:
        try:
            funding_payload = adapter.fetch_current_funding(resolution.candidate)
        except PublicDerivativesAdapterError:
            classification = (
                recorder.latest_error(OKX_CURRENT_FUNDING_PATH) or "PROVIDER_UNAVAILABLE"
            )
        try:
            open_interest_payload = adapter.fetch_current_open_interest(resolution.candidate)
        except PublicDerivativesAdapterError:
            classification = recorder.latest_error(OKX_CURRENT_OPEN_INTEREST_PATH) or (
                "PROVIDER_UNAVAILABLE"
            )
    timings = recorder.timings_since(start_index)
    return (
        SymbolObservation(
            resolution=resolution,
            funding_payload=funding_payload,
            open_interest_payload=open_interest_payload,
            funding_fetched_at_utc=recorder.latest_completed(OKX_CURRENT_FUNDING_PATH),
            open_interest_fetched_at_utc=recorder.latest_completed(
                OKX_CURRENT_OPEN_INTEREST_PATH
            ),
            timings=timings,
            classification=classification,
        ),
        instruments_payload,
    )


def _build_metrics_for_cell(
    observation: SymbolObservation,
    analysis_completed_at: datetime,
) -> tuple[dict[str, Any], ...]:
    metrics: list[dict[str, Any]] = []
    if observation.funding_payload is not None and observation.funding_fetched_at_utc is not None:
        metrics.append(
            build_okx_current_funding_metric(
                observation.funding_payload,
                observation.resolution,
                fetched_at_utc=observation.funding_fetched_at_utc,
                prediction_as_of_utc=analysis_completed_at,
                methodology_version=DERIVATIVES_METHODOLOGY_VERSION,
            )
        )
    if (
        observation.open_interest_payload is not None
        and observation.open_interest_fetched_at_utc is not None
    ):
        metrics.extend(
            build_okx_current_open_interest_metrics(
                observation.open_interest_payload,
                observation.resolution,
                fetched_at_utc=observation.open_interest_fetched_at_utc,
                prediction_as_of_utc=analysis_completed_at,
                methodology_version=DERIVATIVES_METHODOLOGY_VERSION,
            )
        )
    return tuple(metrics)


def _latest_closed_candle(payload: Any, timeframe: str) -> tuple[datetime, datetime] | None:
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return None
    candidates: list[datetime] = []
    for row in rows:
        if (
            isinstance(row, list)
            and len(row) >= 9
            and str(row[8]) == "1"
            and (opened := _millis_to_utc(row[0])) is not None
        ):
            candidates.append(opened)
    if not candidates:
        return None
    candle_open = max(candidates)
    return candle_open, candle_open + timedelta(seconds=TIMEFRAME_SECONDS[timeframe])


def _probe_server_time(
    recorder: RecordingOkxHttpClient,
    *,
    local_now: datetime,
) -> tuple[str | None, int | None, str | None]:
    try:
        payload = recorder.get_json(
            base_url=OKX_PUBLIC_BASE_URL,
            path=OKX_SERVER_TIME_PATH,
            params={},
            provider=REQUIRED_PROVIDER,
        )
    except ProviderError:
        return None, None, recorder.latest_error(OKX_SERVER_TIME_PATH) or "PROVIDER_UNAVAILABLE"
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        return None, None, "TIMESTAMP_INVALID"
    server_time = _millis_to_utc(rows[0].get("ts") if isinstance(rows[0], dict) else None)
    if server_time is None:
        return None, None, "TIMESTAMP_INVALID"
    offset_ms = int(round((server_time - local_now).total_seconds() * 1000))
    return _iso(server_time), offset_ms, None


def _select_cells(options: DiagnosticOptions) -> tuple[tuple[str, str], ...]:
    return tuple(
        (symbol, timeframe)
        for symbol, timeframe in MATRIX
        if options.symbol in {"ALL", symbol} and options.timeframe in {"ALL", timeframe}
    )


def _output(
    options: DiagnosticOptions,
    *,
    process_started_at_utc: datetime,
    completed_at_utc: datetime,
    cells: list[dict[str, object]],
    counts: Mapping[str, int],
    okx_server_time_utc: str | None,
    okx_server_clock_offset_ms: int | None,
    final_classification: str,
) -> dict[str, Any]:
    output = {
        "diagnostic_schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "source_milestone": DIAGNOSTIC_SOURCE_MILESTONE,
        "source_commit_sha": options.source_commit_sha,
        "runner_identity_class": options.runner_identity_class,
        "process_started_at_utc": _iso(process_started_at_utc),
        "diagnostic_completed_at_utc": _iso(completed_at_utc),
        "selected_cell_count": len(cells),
        "derivatives_methodology_version": DERIVATIVES_METHODOLOGY_VERSION,
        "provider_policy_version": PROVIDER_POLICY_VERSION,
        "required_provider": REQUIRED_PROVIDER,
        **dict(counts),
        "okx_server_time_utc": okx_server_time_utc,
        "okx_server_clock_offset_ms": okx_server_clock_offset_ms,
        "final_classification": final_classification,
        "cells": cells,
    }
    _assert_output_contract(output)
    return output


def _assert_output_contract(output: Mapping[str, Any]) -> None:
    if set(output) != TOP_LEVEL_KEYS:
        raise ValueError("Diagnostic output contains unexpected top-level keys.")
    for cell in output["cells"]:
        if set(cell) != CELL_KEYS:
            raise ValueError("Diagnostic cell contains unexpected keys.")
        for timing in cell["request_timings"]:
            if set(timing) != TIMING_KEYS:
                raise ValueError("Diagnostic timing contains unexpected keys.")


def _zero_counts() -> dict[str, int]:
    return {
        "derivatives_logical_request_count": 0,
        "candle_logical_request_count": 0,
        "server_time_logical_request_count": 0,
        "total_logical_request_count": 0,
        "derivatives_http_attempt_count": 0,
        "candle_http_attempt_count": 0,
        "server_time_http_attempt_count": 0,
        "total_http_attempt_count": 0,
        "binance_request_count": 0,
    }


def _timings_with_offsets(
    timings: Sequence[Mapping[str, object]],
    *,
    reference_close_utc: datetime | None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for timing in timings:
        row = dict(timing)
        started = _parse_iso(str(row["request_started_at_utc"]))
        completed = _parse_iso(str(row["request_completed_at_utc"]))
        row["request_start_offset_seconds"] = _offset_seconds(started, reference_close_utc)
        row["request_completed_offset_seconds"] = _offset_seconds(completed, reference_close_utc)
        rows.append(row)
    return rows


def _request_category(path: str) -> str:
    if path == OKX_CANDLES_PATH:
        return "candle"
    if path == OKX_SERVER_TIME_PATH:
        return "server_time"
    return "derivatives"


def _classification_from_provider_error(exc: ProviderError) -> str:
    if exc.http_status in {418, 429} or exc.error_type == "RATE_LIMIT":
        return "RATE_LIMITED"
    if exc.http_status is not None and exc.http_status >= 400:
        return "HTTP_ERROR"
    if exc.error_code == "MALFORMED_JSON" or exc.error_type == "SCHEMA":
        return "PROVIDER_UNAVAILABLE"
    if "timed out" in exc.message.lower():
        return "TIMEOUT"
    return "PROVIDER_UNAVAILABLE"


def _status_class_from_provider_error(exc: ProviderError) -> str:
    if exc.http_status is not None:
        return f"{exc.http_status // 100}xx"
    if "timed out" in exc.message.lower():
        return "TIMEOUT"
    return "TRANSPORT"


def _cell_classification(
    *,
    candle_classification: str | None,
    observation_classification: str | None,
    block_status: str,
    no_lookahead_pass: bool,
    no_lookahead_failed: bool,
    metric_valid_count: int,
) -> str:
    for candidate in (candle_classification, observation_classification):
        if candidate in {"RATE_LIMITED", "TIMEOUT", "HTTP_ERROR", "PROVIDER_UNAVAILABLE"}:
            return candidate
        if candidate == "TIMESTAMP_INVALID":
            return candidate
    if block_status == "UNAVAILABLE":
        return "PROVIDER_UNAVAILABLE"
    if not no_lookahead_pass and no_lookahead_failed:
        return "NO_LOOKAHEAD_FAILED"
    if block_status == "DEGRADED":
        return "AVAILABLE_PARTIAL"
    return "AVAILABLE_COMPLETE"


def _block_status(provider_available: bool, valid_metrics: Sequence[Mapping[str, Any]]) -> str:
    if not provider_available:
        return "UNAVAILABLE"
    if len(valid_metrics) == len(REQUIRED_METRIC_IDS):
        return "ACTIVE"
    return "DEGRADED"


def _reduce_classification(classifications: Sequence[str | None]) -> str:
    values = {value for value in classifications if value}
    for candidate in FINAL_CLASSIFICATION_ORDER:
        if candidate in values:
            return candidate
    return "AVAILABLE_COMPLETE"


def _payload_ts(payload: list[dict[str, Any]] | None, field: str) -> str | None:
    if not payload:
        return None
    return _iso(_millis_to_utc(payload[0].get(field)))


def _millis_to_utc(value: Any) -> datetime | None:
    if isinstance(value, bool):
        return None
    try:
        millis = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(millis / 1000, tz=UTC)


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("UTC timestamp required.")
    return value


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _require_utc(value).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _offset_seconds(value: datetime | None, reference: datetime | None) -> float | None:
    if value is None or reference is None:
        return None
    return (value - reference).total_seconds()


def _first_timing_dt(
    timings: Sequence[Mapping[str, object]],
    key: str,
) -> datetime | None:
    if not timings:
        return None
    return _parse_iso(str(timings[0][key]))


def _last_timing_dt(
    timings: Sequence[Mapping[str, object]],
    key: str,
) -> datetime | None:
    if not timings:
        return None
    return _parse_iso(str(timings[-1][key]))


if __name__ == "__main__":
    raise SystemExit(main())
