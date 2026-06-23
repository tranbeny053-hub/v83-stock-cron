from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import defaultdict
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

import crypto_probability_engine.adapters.provider_selection as provider_selection
import crypto_probability_engine.api.analysis_service as analysis_service
import crypto_probability_engine.derivatives_intel.runtime as derivatives_runtime
from crypto_probability_engine.adapters.http_client import PublicHttpClient
from scripts import collect_derivatives_evidence as collector

ROOT = Path(__file__).resolve().parents[2]
FIXED_NOW = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)


class _Monotonic:
    def __init__(self) -> None:
        self.value = 50.0

    def __call__(self) -> float:
        self.value += 0.25
        return self.value


class _FixtureRuntime:
    def __init__(
        self,
        *,
        provider_status: str = "ACTIVE",
        persist_result: dict[str, object] | None = None,
        fail_symbols: set[str] | None = None,
    ) -> None:
        self.provider_status = provider_status
        self.persist_result = persist_result or {
            "prediction": "OK",
            "feature_snapshot": "INSERTED",
            "derivatives_snapshot": "INSERTED",
            "overall": "OK",
        }
        self.fail_symbols = fail_symbols or set()
        self.analysis_calls: list[dict[str, object]] = []
        self.persist_calls: list[tuple[dict, object]] = []
        self.repository_calls: list[object] = []
        self.pending: dict[str, dict] = {}
        self.repository = object()

    def analyze(self, request, **kwargs) -> dict:
        self.analysis_calls.append({"request": request, **kwargs})
        if request.symbol in self.fail_symbols:
            raise RuntimeError("credential=must-not-leak")
        digest = hashlib.sha256(
            f"{request.symbol}|{request.timeframe}".encode()
        ).hexdigest()[:32]
        run_id = f"cadence-{digest}"
        prediction_id = f"{run_id}:{request.timeframe}"
        payload = {
            "run_id": run_id,
            "normalized_symbol": request.symbol.replace("/", ""),
            "probability_state": {"p": 1.0},
            "score_stack": {"score": 0.0},
            "gate_result": {"action": "NO_TRADE"},
            "decision_synthesis": {
                "future_quant_v2_hooks": {"decision_influence_frac": 0.0}
            },
            "derivatives_intelligence": {
                "methodology_version": collector.DERIVATIVES_METHODOLOGY,
                "influence_mode": "SHADOW_ONLY",
                "decision_influence_frac": 0.0,
                "block_status": self.provider_status,
            },
        }
        self.pending[run_id] = {
            "prediction_id": prediction_id,
            "run_id": run_id,
            "symbol": request.symbol,
            "normalized_symbol": payload["normalized_symbol"],
            "timeframe": request.timeframe,
            "reference_close_utc": "2026-06-22T08:00:00Z",
            "prediction_origin": kwargs["prediction_origin"],
        }
        return payload

    def inspect(self, payload: dict):
        row = self.pending.get(payload.get("run_id"))
        return ([row] if row else [], [], False, [], False)

    def persist(self, payload: dict, repository: object) -> dict[str, object]:
        self.persist_calls.append((payload, repository))
        return dict(self.persist_result)

    def build_repository(self, settings) -> object:
        self.repository_calls.append(settings)
        return self.repository

    def dependencies(self) -> collector.CollectorDependencies:
        return collector.CollectorDependencies(
            analyze=self.analyze,
            persist=self.persist,
            inspect_pending=self.inspect,
            repository_factory=self.build_repository,
            now_utc=lambda: FIXED_NOW,
            monotonic=_Monotonic(),
        )


class _NoDatabaseRead(dict):
    def get(self, key, default=None):
        if key == "SUPABASE_DB_URL":
            raise AssertionError("disabled/dry-run path read the database URL")
        return super().get(key, default)


class _CountingFakeTransport:
    """Count real HTTP-client crossings while returning deterministic fixtures."""

    def __init__(self) -> None:
        self.reference_now = datetime.now(UTC).replace(microsecond=0)
        self.logical_requests: list[dict[str, object]] = []
        self.http_attempts: list[dict[str, object]] = []
        self._current_logical_id: int | None = None
        self._attempts_by_logical: defaultdict[int, int] = defaultdict(int)

    @property
    def logical_request_count(self) -> int:
        return len(self.logical_requests)

    @property
    def http_attempt_count(self) -> int:
        return len(self.http_attempts)

    def begin_logical(
        self,
        *,
        provider: str,
        base_url: str,
        path: str,
        params: dict[str, object],
    ) -> int:
        logical_id = len(self.logical_requests)
        self.logical_requests.append(
            {
                "id": logical_id,
                "provider": provider,
                "base_url": base_url,
                "path": path,
                "params": dict(params),
            }
        )
        return logical_id

    def handle(self, request: httpx.Request) -> httpx.Response:
        logical_id = self._current_logical_id
        if logical_id is None:
            raise AssertionError("transport crossed without a logical request marker")
        self._attempts_by_logical[logical_id] += 1
        attempt = self._attempts_by_logical[logical_id]
        record = {
            "logical_id": logical_id,
            "attempt": attempt,
            "host": request.url.host,
            "path": request.url.path,
            "query": str(request.url.query, "utf-8"),
        }
        self.http_attempts.append(record)
        assert request.method == "GET"
        assert not request.headers.get("authorization")
        if self._is_spot_request(request) and attempt == 1:
            return httpx.Response(
                503,
                json={"code": "transient_fixture_retry"},
                request=request,
            )
        return httpx.Response(200, json=self._payload_for(request), request=request)

    def attempts_for_logical(self) -> dict[int, int]:
        return dict(self._attempts_by_logical)

    def _is_spot_request(self, request: httpx.Request) -> bool:
        if request.url.host == "data-api.binance.vision":
            return True
        if request.url.host != "www.okx.com":
            return False
        if request.url.path.startswith("/api/v5/market/"):
            return True
        return (
            request.url.path == "/api/v5/public/instruments"
            and request.url.params.get("instType") == "SPOT"
        )

    def _payload_for(self, request: httpx.Request) -> Any:
        host = request.url.host
        path = request.url.path
        params = request.url.params
        if host == "data-api.binance.vision":
            return self._binance_spot_payload(path, params)
        if host == "www.okx.com" and self._is_spot_request(request):
            return self._okx_spot_payload(path, params)
        if host == "fapi.binance.com":
            return self._binance_derivatives_payload(path, params)
        if host == "www.okx.com":
            return self._okx_derivatives_payload(path, params)
        raise AssertionError(f"unexpected fixture host: {host}")

    def _binance_spot_payload(self, path: str, params: httpx.QueryParams) -> Any:
        symbol = params.get("symbol", "BTCUSDT")
        if path == "/api/v3/exchangeInfo":
            return {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "status": "TRADING",
                        "baseAsset": "BTC",
                        "quoteAsset": "USDT",
                    },
                    {
                        "symbol": "ETHUSDT",
                        "status": "TRADING",
                        "baseAsset": "ETH",
                        "quoteAsset": "USDT",
                    },
                ]
            }
        if path == "/api/v3/klines":
            return _binance_candle_rows(
                latest_close=self._latest_close(str(params["interval"])),
                timeframe_seconds=_binance_interval_seconds(str(params["interval"])),
            )
        if path == "/api/v3/depth":
            return {"lastUpdateId": 1, "bids": [["120.0", "2.0"]], "asks": [["120.5", "2.5"]]}
        if path == "/api/v3/ticker/24hr":
            return {
                "symbol": symbol,
                "lastPrice": "120.25",
                "bidPrice": "120.0",
                "askPrice": "120.5",
                "volume": "10000",
                "quoteVolume": "1200000",
            }
        if path == "/api/v3/trades":
            return [
                {
                    "id": 1,
                    "price": "120.2",
                    "qty": "0.4",
                    "quoteQty": "48.08",
                    "time": _epoch_millis(self.reference_now),
                    "isBuyerMaker": False,
                    "isBestMatch": True,
                }
            ]
        raise AssertionError(f"unexpected Binance spot path: {path}")

    def _okx_spot_payload(self, path: str, params: httpx.QueryParams) -> Any:
        if path == "/api/v5/public/instruments":
            return {
                "code": "0",
                "data": [
                    {
                        "instId": "BTC-USDT",
                        "instType": "SPOT",
                        "baseCcy": "BTC",
                        "quoteCcy": "USDT",
                        "state": "live",
                    },
                    {
                        "instId": "ETH-USDT",
                        "instType": "SPOT",
                        "baseCcy": "ETH",
                        "quoteCcy": "USDT",
                        "state": "live",
                    },
                ],
            }
        if path == "/api/v5/market/candles":
            return {
                "code": "0",
                "data": _okx_candle_rows(
                    latest_close=self._latest_close(str(params["bar"])),
                    timeframe_seconds=_okx_interval_seconds(str(params["bar"])),
                ),
            }
        if path == "/api/v5/market/books":
            return {
                "code": "0",
                "data": [
                    {
                        "bids": [["120.0", "2.0", "0", "1"]],
                        "asks": [["120.5", "2.5", "0", "1"]],
                    }
                ],
            }
        if path == "/api/v5/market/ticker":
            return {
                "code": "0",
                "data": [
                    {
                        "instId": params.get("instId", "BTC-USDT"),
                        "last": "120.25",
                        "bidPx": "120.0",
                        "askPx": "120.5",
                        "vol24h": "10000",
                        "volCcy24h": "1200000",
                        "ts": str(_epoch_millis(self.reference_now)),
                    }
                ],
            }
        if path == "/api/v5/market/trades":
            return {
                "code": "0",
                "data": [
                    {
                        "instId": params.get("instId", "BTC-USDT"),
                        "tradeId": "1",
                        "px": "120.2",
                        "sz": "0.4",
                        "side": "buy",
                        "ts": str(_epoch_millis(self.reference_now)),
                    }
                ],
            }
        raise AssertionError(f"unexpected OKX spot path: {path}")

    def _binance_derivatives_payload(self, path: str, params: httpx.QueryParams) -> Any:
        if path == "/fapi/v1/exchangeInfo":
            return {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "status": "TRADING",
                        "contractType": "PERPETUAL",
                        "quoteAsset": "USDT",
                        "marginAsset": "USDT",
                    },
                    {
                        "symbol": "ETHUSDT",
                        "status": "TRADING",
                        "contractType": "PERPETUAL",
                        "quoteAsset": "USDT",
                        "marginAsset": "USDT",
                    },
                ]
            }
        if path == "/fapi/v1/premiumIndex":
            return {
                "symbol": params.get("symbol", "BTCUSDT"),
                "lastFundingRate": "-0.0001",
                "time": _epoch_millis(self.reference_now),
            }
        if path == "/fapi/v1/openInterest":
            return {
                "symbol": params.get("symbol", "BTCUSDT"),
                "openInterest": "1200",
                "time": _epoch_millis(self.reference_now),
            }
        raise AssertionError(f"unexpected Binance derivatives path: {path}")

    def _okx_derivatives_payload(self, path: str, params: httpx.QueryParams) -> Any:
        if path == "/api/v5/public/instruments":
            return {
                "code": "0",
                "data": [
                    {
                        "instId": "BTC-USDT-SWAP",
                        "instType": "SWAP",
                        "settleCcy": "USDT",
                        "ctType": "linear",
                        "state": "live",
                        "ctVal": "0.01",
                        "ctMult": "1",
                    },
                    {
                        "instId": "ETH-USDT-SWAP",
                        "instType": "SWAP",
                        "settleCcy": "USDT",
                        "ctType": "linear",
                        "state": "live",
                        "ctVal": "0.1",
                        "ctMult": "1",
                    },
                ],
            }
        if path == "/api/v5/public/funding-rate":
            return {
                "code": "0",
                "data": [
                    {
                        "instId": params.get("instId", "BTC-USDT-SWAP"),
                        "fundingRate": "0.0002",
                        "ts": str(_epoch_millis(self.reference_now)),
                    }
                ],
            }
        if path == "/api/v5/public/open-interest":
            return {
                "code": "0",
                "data": [
                    {
                        "instId": params.get("instId", "BTC-USDT-SWAP"),
                        "instType": "SWAP",
                        "oi": "40",
                        "oiCcy": "0.4",
                        "oiUsd": "26000",
                        "ts": str(_epoch_millis(self.reference_now)),
                    }
                ],
            }
        raise AssertionError(f"unexpected OKX derivatives path: {path}")

    def _latest_close(self, interval: str) -> datetime:
        seconds = (
            _binance_interval_seconds(interval)
            if interval in {"1h", "4h"}
            else _okx_interval_seconds(interval)
        )
        lag = 5 * 60 if seconds == 3600 else 20 * 60
        return self.reference_now - timedelta(seconds=lag)


def _epoch_millis(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _binance_interval_seconds(interval: str) -> int:
    return {"1h": 3600, "4h": 14_400}[interval]


def _okx_interval_seconds(interval: str) -> int:
    return {"1H": 3600, "4H": 14_400}[interval]


def _binance_candle_rows(
    *,
    latest_close: datetime,
    timeframe_seconds: int,
    count: int = 202,
) -> list[list[Any]]:
    start = latest_close - timedelta(seconds=(count - 1) * timeframe_seconds)
    rows: list[list[Any]] = []
    for idx in range(count):
        open_time = start + timedelta(seconds=idx * timeframe_seconds)
        rows.append(
            [
                _epoch_millis(open_time),
                "120.0",
                "121.0",
                "119.0",
                "120.25",
                "1000.0",
                _epoch_millis(open_time + timedelta(seconds=timeframe_seconds)) - 1,
                "0",
                0,
                "0",
                "0",
                "0",
            ]
        )
    return rows


def _okx_candle_rows(
    *,
    latest_close: datetime,
    timeframe_seconds: int,
    count: int = 202,
) -> list[list[Any]]:
    start = latest_close - timedelta(seconds=(count - 1) * timeframe_seconds)
    rows: list[list[Any]] = []
    for idx in range(count):
        open_time = start + timedelta(seconds=idx * timeframe_seconds)
        confirmed = "0" if idx == count - 1 else "1"
        rows.append(
            [
                str(_epoch_millis(open_time)),
                "120.0",
                "121.0",
                "119.0",
                "120.25",
                "1000.0",
                "0",
                "0",
                confirmed,
            ]
        )
    return list(reversed(rows))


def _run(
    runtime: _FixtureRuntime,
    *,
    enabled: str = "true",
    dry_run: bool = True,
    confirm: str = "",
    scope: str = "BTC_ONLY",
    database_url: str | None = None,
) -> dict:
    environ = {collector.ENABLE_ENV: enabled}
    if database_url is not None:
        environ["SUPABASE_DB_URL"] = database_url
    return collector.run_collector(
        collector.CollectorOptions(
            dry_run=dry_run,
            confirm_write=confirm,
            matrix_scope=scope,
        ),
        environ=environ,
        dependencies=runtime.dependencies(),
    )


@pytest.mark.parametrize("raw", [None, "", "false", "FALSE"])
def test_kill_switch_disabled_has_zero_runtime_or_repository_activity(raw) -> None:
    runtime = _FixtureRuntime()
    environ = _NoDatabaseRead()
    if raw is not None:
        environ[collector.ENABLE_ENV] = raw

    report = collector.run_collector(
        collector.CollectorOptions(),
        environ=environ,
        dependencies=runtime.dependencies(),
    )

    assert report["final_classification"] == "DISABLED"
    assert report["exit_code"] == 0
    assert all(row["classification"] == "SKIPPED_DISABLED" for row in report["matrix_cells"])
    assert runtime.analysis_calls == []
    assert runtime.persist_calls == []
    assert runtime.repository_calls == []


def test_invalid_kill_switch_fails_closed_without_dependencies() -> None:
    runtime = _FixtureRuntime()
    report = _run(runtime, enabled="yes")

    assert report["final_classification"] == "CONFIGURATION_ERROR"
    assert report["exit_code"] == 1
    assert runtime.analysis_calls == runtime.repository_calls == []


def test_cli_defaults_and_boolean_parser_are_strict() -> None:
    options = collector.parse_args([])
    assert options == collector.CollectorOptions()
    assert collector.parse_bool("true") is True
    assert collector.parse_bool("false") is False
    for invalid in ("1", " true ", "yes"):
        with pytest.raises(argparse.ArgumentTypeError):
            collector.parse_bool(invalid)


def test_enabled_dry_run_uses_process_local_settings_and_zero_persistence() -> None:
    runtime = _FixtureRuntime()
    before = dict(os.environ)
    report = collector.run_collector(
        collector.CollectorOptions(dry_run=True, matrix_scope="BTC_ONLY"),
        environ=_NoDatabaseRead({collector.ENABLE_ENV: "true"}),
        dependencies=runtime.dependencies(),
    )

    assert report["final_classification"] == "DRY_RUN_COMPLETE"
    assert [row["classification"] for row in report["matrix_cells"]] == [
        "SKIPPED_DRY_RUN",
        "SKIPPED_DRY_RUN",
    ]
    assert runtime.repository_calls == []
    assert runtime.persist_calls == []
    assert all(call["settings"].data_mode == "live" for call in runtime.analysis_calls)
    assert all(
        call["settings"].enable_derivatives_intel is True
        for call in runtime.analysis_calls
    )
    assert all(
        call["prediction_origin"] == collector.SCHEDULED_ORIGIN
        for call in runtime.analysis_calls
    )
    assert all(call["deterministic_identity"] is True for call in runtime.analysis_calls)
    assert dict(os.environ) == before


@pytest.mark.parametrize(
    ("confirm", "database_url", "classification"),
    [
        ("", "postgresql://fixture", "CONFIRMATION_REQUIRED"),
        ("wrong", "postgresql://fixture", "CONFIRMATION_REQUIRED"),
        (collector.WRITE_CONFIRMATION, None, "CONFIGURATION_ERROR"),
    ],
)
def test_write_gate_fails_before_provider_or_repository_activity(
    confirm: str,
    database_url: str | None,
    classification: str,
) -> None:
    runtime = _FixtureRuntime()
    report = _run(
        runtime,
        dry_run=False,
        confirm=confirm,
        database_url=database_url,
    )

    assert report["final_classification"] == classification
    assert report["exit_code"] == 1
    assert runtime.analysis_calls == runtime.repository_calls == []


def test_fixed_scopes_order_and_circuit_breakers(monkeypatch) -> None:
    assert collector._validated_cells("FULL_4_CELL") == collector.MATRIX  # noqa: SLF001
    assert collector._validated_cells("BTC_ONLY") == collector.MATRIX[:2]  # noqa: SLF001
    assert collector._validated_cells("ETH_ONLY") == collector.MATRIX[2:]  # noqa: SLF001
    with pytest.raises(ValueError):
        collector._validated_cells("SOL_ONLY")  # noqa: SLF001
    monkeypatch.setitem(
        collector.MATRIX_SCOPES,
        "TOO_LARGE",
        (*collector.MATRIX, ("BTC/USDT", "1H")),
    )
    with pytest.raises(ValueError):
        collector._validated_cells("TOO_LARGE")  # noqa: SLF001
    monkeypatch.setitem(
        collector.MATRIX_SCOPES,
        "DUPLICATE",
        (("BTC/USDT", "1H"), ("BTC/USDT", "1H")),
    )
    with pytest.raises(ValueError):
        collector._validated_cells("DUPLICATE")  # noqa: SLF001
    monkeypatch.setitem(collector.MATRIX_SCOPES, "BAD_CELL", (("SOL/USDT", "1H"),))
    with pytest.raises(ValueError):
        collector._validated_cells("BAD_CELL")  # noqa: SLF001


def test_deterministic_identity_and_pending_origin_are_required_before_persistence() -> None:
    runtime = _FixtureRuntime()
    valid = _run(
        runtime,
        dry_run=False,
        confirm=collector.WRITE_CONFIRMATION,
        scope="BTC_ONLY",
        database_url="postgresql://fixture",
    )
    assert all(collector.RUN_ID_PATTERN.fullmatch(row["run_id"]) for row in valid["matrix_cells"])
    assert all(
        row["prediction_id"] == f"{row['run_id']}:{row['timeframe']}"
        for row in valid["matrix_cells"]
    )
    assert len(runtime.persist_calls) == 2

    invalid_runtime = _FixtureRuntime()

    def invalid_analyze(*args, **kwargs):
        payload = invalid_runtime.analyze(*args, **kwargs)
        payload["run_id"] = "run_not_cadence"
        return payload

    deps = replace(invalid_runtime.dependencies(), analyze=invalid_analyze)
    report = collector.run_collector(
        collector.CollectorOptions(
            dry_run=False,
            confirm_write=collector.WRITE_CONFIRMATION,
            matrix_scope="BTC_ONLY",
        ),
        environ={collector.ENABLE_ENV: "true", "SUPABASE_DB_URL": "postgresql://fixture"},
        dependencies=deps,
    )
    assert all(
        row["classification"] == "SKIPPED_REFERENCE_UNCERTAIN"
        for row in report["matrix_cells"]
    )
    assert invalid_runtime.persist_calls == []


def test_safety_invariant_failure_prevents_persistence() -> None:
    runtime = _FixtureRuntime()

    def unsafe_analyze(*args, **kwargs):
        payload = runtime.analyze(*args, **kwargs)
        payload["derivatives_intelligence"]["decision_influence_frac"] = 0.1
        return payload

    report = collector.run_collector(
        collector.CollectorOptions(
            dry_run=False,
            confirm_write=collector.WRITE_CONFIRMATION,
            matrix_scope="BTC_ONLY",
        ),
        environ={collector.ENABLE_ENV: "true", "SUPABASE_DB_URL": "postgresql://fixture"},
        dependencies=replace(runtime.dependencies(), analyze=unsafe_analyze),
    )

    assert report["final_classification"] == "FAILED_SAFETY_INVARIANT"
    assert runtime.persist_calls == []


@pytest.mark.parametrize(
    ("persist_result", "expected", "final", "exit_code"),
    [
        (
            {
                "prediction": "OK",
                "feature_snapshot": "INSERTED",
                "derivatives_snapshot": "INSERTED",
                "overall": "OK",
            },
            "INSERTED",
            "COMPLETE",
            0,
        ),
        (
            {
                "prediction": "OK",
                "feature_snapshot": "IDENTICAL_DUPLICATE",
                "derivatives_snapshot": "IDENTICAL_DUPLICATE",
                "overall": "OK",
            },
            "ALREADY_EXISTS",
            "COMPLETE",
            0,
        ),
        (
            {
                "prediction": "OK",
                "feature_snapshot": "INSERTED",
                "derivatives_snapshot": "CONFLICT",
                "overall": "PARTIAL",
            },
            "PARTIAL_PERSISTENCE",
            "PARTIAL_PERSISTENCE",
            1,
        ),
        (
            {
                "prediction": "UNAVAILABLE",
                "feature_snapshot": None,
                "derivatives_snapshot": None,
                "overall": "UNAVAILABLE",
            },
            "FAILED",
            "FAILED",
            1,
        ),
    ],
)
def test_persistence_status_classification(
    persist_result: dict[str, object],
    expected: str,
    final: str,
    exit_code: int,
) -> None:
    runtime = _FixtureRuntime(persist_result=persist_result)
    report = _run(
        runtime,
        dry_run=False,
        confirm=collector.WRITE_CONFIRMATION,
        database_url="postgresql://fixture",
    )

    assert all(row["classification"] == expected for row in report["matrix_cells"])
    assert report["final_classification"] == final
    assert report["exit_code"] == exit_code
    assert len(runtime.persist_calls) == 2


def test_degraded_and_unavailable_provider_states_remain_separate() -> None:
    degraded = _run(
        _FixtureRuntime(provider_status="DEGRADED"),
        dry_run=False,
        confirm=collector.WRITE_CONFIRMATION,
        database_url="postgresql://fixture",
    )
    assert degraded["final_classification"] == "COMPLETE_WITH_DEGRADED_PROVIDER"
    assert all(row["classification"] == "INSERTED" for row in degraded["matrix_cells"])
    assert all(row["provider_status"] == "DEGRADED" for row in degraded["matrix_cells"])

    unavailable_runtime = _FixtureRuntime(provider_status="UNAVAILABLE")
    unavailable = _run(
        unavailable_runtime,
        dry_run=False,
        confirm=collector.WRITE_CONFIRMATION,
        database_url="postgresql://fixture",
    )
    assert unavailable["final_classification"] == "FAILED"
    assert all(
        row["classification"] == "PROVIDER_UNAVAILABLE"
        for row in unavailable["matrix_cells"]
    )
    assert all(
        row["derivatives_snapshot_status"] == "INSERTED"
        for row in unavailable["matrix_cells"]
    )


def test_one_cell_failure_is_sanitized_and_later_cell_runs() -> None:
    runtime = _FixtureRuntime(fail_symbols={"BTC/USDT"})
    report = _run(runtime, scope="FULL_4_CELL")

    assert [row["classification"] for row in report["matrix_cells"]] == [
        "FAILED",
        "FAILED",
        "SKIPPED_DRY_RUN",
        "SKIPPED_DRY_RUN",
    ]
    assert report["exit_code"] == 1
    encoded = json.dumps(report)
    assert "must-not-leak" not in encoded
    assert "credential=" not in encoded


def test_output_allowlist_and_single_json_stdout(monkeypatch, capsys) -> None:
    monkeypatch.delenv(collector.ENABLE_ENV, raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    exit_code = collector.main([])
    output = capsys.readouterr().out.strip()
    report = json.loads(output)

    assert exit_code == 0
    assert set(report) == collector.REPORT_FIELDS
    assert all(set(row) == collector.CELL_RESULT_FIELDS for row in report["matrix_cells"])
    assert output.count("{") >= 1
    assert "SUPABASE" not in output


def test_step_summary_is_allowlisted(tmp_path) -> None:
    path = tmp_path / "summary.md"
    report = _run(_FixtureRuntime())
    collector.append_step_summary(str(path), report)
    text = path.read_text()

    assert "DRY_RUN_COMPLETE" in text
    assert "SUPABASE" not in text
    assert "postgres" not in text.lower()


def test_provider_call_ceiling_matches_current_bounded_adapter_policy() -> None:
    assert collector.FULL_MATRIX_LOGICAL_REQUEST_CAP == 58
    assert collector.FULL_MATRIX_HTTP_ATTEMPT_CAP == 98
    assert collector.MAX_MATRIX_CELLS == 4
    assert collector.MAX_NEW_PREDICTIONS == 4
    assert collector.MAX_NEW_DERIVATIVES_SNAPSHOTS == 4


def test_full_matrix_provider_budget_is_observed_through_real_adapter_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counter = _CountingFakeTransport()
    client = httpx.Client(transport=httpx.MockTransport(counter.handle))
    original_get_json = PublicHttpClient.get_json

    def counting_get_json(self, *, base_url, path, params, provider, headers=None):
        self.sleep_func = lambda _: None
        logical_id = counter.begin_logical(
            provider=provider,
            base_url=base_url,
            path=path,
            params=dict(params),
        )
        previous = counter._current_logical_id  # noqa: SLF001
        counter._current_logical_id = logical_id  # noqa: SLF001
        try:
            return original_get_json(
                self,
                base_url=base_url,
                path=path,
                params=params,
                provider=provider,
                headers=headers,
            )
        finally:
            counter._current_logical_id = previous  # noqa: SLF001

    def live_analyze(request, **kwargs):
        provider_selection.clear_provider_cache()
        with derivatives_runtime._CACHE_GUARD:  # noqa: SLF001
            derivatives_runtime._SYMBOL_CACHE.clear()  # noqa: SLF001
        settings = kwargs["settings"].model_copy(
            update={
                "symbol_universe_cache_ttl_seconds": 0,
                "candle_cache_ttl_seconds": 0,
                "provider_rate_limit_per_min": 10_000,
                "provider_max_retries": 1,
            }
        )
        return analysis_service.analyze_request(request, **{**kwargs, "settings": settings})

    monkeypatch.setattr(PublicHttpClient, "_client", lambda self: client)
    monkeypatch.setattr(PublicHttpClient, "get_json", counting_get_json)
    provider_selection.clear_provider_cache()
    derivatives_runtime.clear_runtime_caches()
    try:
        report = collector.run_collector(
            collector.CollectorOptions(dry_run=True, matrix_scope="FULL_4_CELL"),
            environ={collector.ENABLE_ENV: "true"},
            dependencies=replace(
                collector.DEFAULT_DEPENDENCIES,
                analyze=live_analyze,
                persist=lambda *_, **__: pytest.fail("dry-run attempted persistence"),
                repository_factory=lambda *_: pytest.fail(
                    "dry-run constructed a repository"
                ),
                now_utc=lambda: FIXED_NOW,
                monotonic=_Monotonic(),
            ),
        )
    finally:
        provider_selection.clear_provider_cache()
        derivatives_runtime.clear_runtime_caches()
        for values in (
            analysis_service._PENDING_PREDICTION_ROWS,  # noqa: SLF001
            analysis_service._PENDING_FEATURE_SNAPSHOT_ROWS,  # noqa: SLF001
            analysis_service._PENDING_DERIVATIVES_SNAPSHOT_ROWS,  # noqa: SLF001
            analysis_service._PENDING_DERIVATIVES_SNAPSHOT_REQUIRED,  # noqa: SLF001
        ):
            values.clear()
        client.close()

    assert report["final_classification"] == "DRY_RUN_COMPLETE"
    assert [(row["symbol"], row["timeframe"]) for row in report["matrix_cells"]] == list(
        collector.MATRIX
    )
    assert all(row["classification"] == "SKIPPED_DRY_RUN" for row in report["matrix_cells"])
    assert len(report["matrix_cells"]) == collector.MAX_MATRIX_CELLS
    assert report["new_predictions"] == 0
    assert report["new_derivatives_snapshots"] == 0
    assert counter.logical_request_count <= collector.FULL_MATRIX_LOGICAL_REQUEST_CAP
    assert counter.http_attempt_count <= collector.FULL_MATRIX_HTTP_ATTEMPT_CAP
    assert counter.logical_request_count == 58
    assert counter.http_attempt_count == 98
    attempts = counter.attempts_for_logical()
    spot_ids = {
        int(row["id"])
        for row in counter.logical_requests
        if (
            str(row["base_url"]) == "https://data-api.binance.vision"
            or (
                str(row["base_url"]) == "https://www.okx.com"
                and (
                    str(row["path"]).startswith("/api/v5/market/")
                    or row["params"] == {"instType": "SPOT"}
                )
            )
        )
    }
    derivatives_ids = set(attempts) - spot_ids
    assert len(spot_ids) == 40
    assert all(attempts[logical_id] == 2 for logical_id in spot_ids)
    assert all(attempts[logical_id] == 1 for logical_id in derivatives_ids)
    assert not any("history" in str(row["path"]).lower() for row in counter.logical_requests)
    assert not any("fundingRate" in str(row["path"]) for row in counter.logical_requests)


def test_observed_insert_cap_breach_stops_subsequent_cells(monkeypatch) -> None:
    runtime = _FixtureRuntime()
    monkeypatch.setattr(collector, "MAX_NEW_PREDICTIONS", 0)
    report = _run(
        runtime,
        dry_run=False,
        confirm=collector.WRITE_CONFIRMATION,
        scope="FULL_4_CELL",
        database_url="postgresql://fixture",
    )

    assert report["cap_status"] == "BREACHED"
    assert report["exit_code"] == 1
    assert len(report["matrix_cells"]) == 1
    assert len(runtime.analysis_calls) == 1


def test_collector_source_uses_only_approved_persistence_entrypoint() -> None:
    source = (ROOT / "scripts/collect_derivatives_evidence.py").read_text()
    assert "persist_analysis_now" in source
    assert ".save_prediction(" not in source
    assert ".save_feature_snapshot(" not in source
    assert ".save_derivatives_snapshot(" not in source
    assert "INSERT INTO" not in source
    assert "/v1/analyze" not in source


def test_manual_workflow_contract_and_existing_integrity_workflow_unchanged() -> None:
    path = ROOT / ".github/workflows/derivatives-evidence-cadence.yml"
    text = path.read_text()
    assert text.startswith("name: UCPE Derivatives Evidence Collector\n")
    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "cron:" not in text
    assert "actions/checkout@v4" in text
    assert "actions/setup-python@v5" in text
    assert 'python-version: "3.11"' in text
    assert "group: derivatives-evidence-cadence" in text
    assert "cancel-in-progress: false" in text
    assert "timeout-minutes: 15" in text
    assert "contents: read" in text
    for name in ("enable_collector", "dry_run", "matrix_scope", "confirm_write"):
        assert f"      {name}:\n" in text
    assert re.search(
        r"enable_collector:\n(?: {8}.+\n)*? {8}type: boolean\n"
        r"(?: {8}.+\n)*? {8}default: false\n",
        text,
    )
    assert re.search(
        r"dry_run:\n(?: {8}.+\n)*? {8}type: boolean\n"
        r"(?: {8}.+\n)*? {8}default: true\n",
        text,
    )
    for option in ("FULL_4_CELL", "BTC_ONLY", "ETH_ONLY"):
        assert f"          - {option}\n" in text
    assert '        default: ""\n' in text
    assert "UCPE_DERIV_CADENCE_ENABLED: ${{ inputs.enable_collector }}" in text
    assert (
        "if: ${{ !inputs.enable_collector || inputs.dry_run || "
        "inputs.confirm_write != 'WRITE-EVIDENCE' }}"
    ) in text
    assert (
        "if: ${{ inputs.enable_collector && !inputs.dry_run && "
        "inputs.confirm_write == 'WRITE-EVIDENCE' }}"
    ) in text
    non_write_step = text.split(
        "- name: Run manual derivatives evidence collector without write secret", 1
    )[1].split("- name: Run confirmed manual derivatives evidence collector write", 1)[0]
    write_step = text.split(
        "- name: Run confirmed manual derivatives evidence collector write", 1
    )[1]
    assert "SUPABASE_DB_URL" not in non_write_step
    assert "SUPABASE_DB_URL: ${{ secrets.SUPABASE_DB_URL }}" in write_step
    assert text.count("SUPABASE_DB_URL: ${{ secrets.SUPABASE_DB_URL }}") == 1
    assert "secrets." not in "\n".join(
        line for line in text.splitlines() if line.strip().startswith("if:")
    )
    assert "secrets." not in text.split("jobs:", 1)[0]
    job_header = text.split("jobs:", 1)[1].split("steps:", 1)[0]
    assert "secrets." not in job_header
    for step in (non_write_step, write_step):
        run_block = step.split("run: |", 1)[1]
        assert "SUPABASE_DB_URL" not in run_block
    assert "HF_TOKEN" not in text
    assert "Authorization" not in text

    integrity = (ROOT / ".github/workflows/source-integrity-guard.yml").read_text()
    assert 'cron: "27 */2 * * *"' in integrity
    assert "actions/checkout@v4" in integrity
    assert "actions/setup-python@v5" in integrity
