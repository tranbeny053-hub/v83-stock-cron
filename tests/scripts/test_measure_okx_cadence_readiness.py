from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from crypto_probability_engine.adapters.derivatives_endpoints import (
    DerivativesPublicHttpClient,
)
from scripts import measure_okx_cadence_readiness as diagnostic

ROOT = Path(__file__).resolve().parents[2]
FIXED_NOW = datetime(2026, 6, 22, 12, 5, tzinfo=UTC)


class _StepClock:
    def __init__(self, start: datetime = FIXED_NOW) -> None:
        self.value = start - timedelta(seconds=1)

    def __call__(self) -> datetime:
        self.value += timedelta(seconds=1)
        return self.value


class _Monotonic:
    def __init__(self) -> None:
        self.value = 500.0

    def __call__(self) -> float:
        self.value += 0.01
        return self.value


class _OkxFixtureTransport:
    def __init__(
        self,
        *,
        funding_status: int = 200,
        timeout_path: str | None = None,
        malformed_path: str | None = None,
        omit_oi_usd: bool = False,
        future_event: bool = False,
        provider_timestamp: Any | None = None,
    ) -> None:
        self.funding_status = funding_status
        self.timeout_path = timeout_path
        self.malformed_path = malformed_path
        self.omit_oi_usd = omit_oi_usd
        self.future_event = future_event
        self.provider_timestamp = provider_timestamp
        self.calls: list[dict[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(
            {
                "host": str(request.url.host),
                "path": request.url.path,
                "query": str(request.url.query, "utf-8"),
            }
        )
        if request.url.path == self.timeout_path:
            raise httpx.TimeoutException("fixture timeout", request=request)
        if request.url.path == self.malformed_path:
            return httpx.Response(200, json={"unexpected": []}, request=request)
        if request.url.path == diagnostic.OKX_SERVER_TIME_PATH:
            return httpx.Response(
                200,
                json={"code": "0", "data": [{"ts": str(_ms(FIXED_NOW))}]},
                request=request,
            )
        if request.url.path == diagnostic.OKX_CANDLES_PATH:
            return httpx.Response(
                200,
                json={"code": "0", "data": self._candles(request.url.params["bar"])},
                request=request,
            )
        if request.url.path == diagnostic.OKX_INSTRUMENTS_PATH:
            return httpx.Response(200, json={"code": "0", "data": _instruments()}, request=request)
        if request.url.path == diagnostic.OKX_CURRENT_FUNDING_PATH:
            if self.funding_status != 200:
                return httpx.Response(
                    self.funding_status,
                    json={"code": "fixture"},
                    request=request,
                )
            return httpx.Response(
                200,
                json={"code": "0", "data": [self._funding_row(request.url.params["instId"])]},
                request=request,
            )
        if request.url.path == diagnostic.OKX_CURRENT_OPEN_INTEREST_PATH:
            return httpx.Response(
                200,
                json={"code": "0", "data": [self._open_interest_row(request.url.params["instId"])]},
                request=request,
            )
        raise AssertionError(f"unexpected path {request.url.path}")

    def _candles(self, bar: str) -> list[list[str]]:
        if bar == "1H":
            confirmed_open = datetime(2026, 6, 22, 11, 0, tzinfo=UTC)
            forming_open = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)
        else:
            confirmed_open = datetime(2026, 6, 22, 8, 0, tzinfo=UTC)
            forming_open = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)
        return [
            [str(_ms(forming_open)), "1", "2", "1", "2", "10", "10", "20", "0"],
            [str(_ms(confirmed_open)), "1", "2", "1", "2", "10", "10", "20", "1"],
        ]

    def _funding_row(self, inst_id: str) -> dict[str, str]:
        event_ts = self._provider_timestamp()
        return {
            "instId": inst_id,
            "fundingRate": "0.0001",
            "ts": event_ts,
            "fundingTime": str(_ms(datetime(2026, 6, 22, 8, 0, tzinfo=UTC))),
            "nextFundingTime": str(_ms(datetime(2026, 6, 22, 16, 0, tzinfo=UTC))),
        }

    def _open_interest_row(self, inst_id: str) -> dict[str, str]:
        event_ts = self._provider_timestamp()
        row = {
            "instId": inst_id,
            "oi": "100",
            "oiCcy": "2.5",
            "oiUsd": "250000",
            "ts": event_ts,
        }
        if self.omit_oi_usd:
            row.pop("oiUsd")
        return row

    def _provider_timestamp(self) -> Any:
        if self.provider_timestamp is not None:
            return self.provider_timestamp
        event_time = datetime(2099, 1, 1, tzinfo=UTC) if self.future_event else FIXED_NOW
        return str(_ms(event_time))


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _instruments() -> list[dict[str, str]]:
    return [
        {
            "instId": "BTC-USDT-SWAP",
            "instType": "SWAP",
            "settleCcy": "USDT",
            "ctType": "linear",
            "state": "live",
            "ctVal": "0.01",
            "ctMult": "1",
            "ctValCcy": "BTC",
        },
        {
            "instId": "ETH-USDT-SWAP",
            "instType": "SWAP",
            "settleCcy": "USDT",
            "ctType": "linear",
            "state": "live",
            "ctVal": "0.1",
            "ctMult": "1",
            "ctValCcy": "ETH",
        },
    ]


def _run(
    transport: _OkxFixtureTransport | None = None,
    *,
    options: diagnostic.DiagnosticOptions | None = None,
) -> tuple[dict[str, Any], _OkxFixtureTransport]:
    fixture = transport or _OkxFixtureTransport()

    def factory() -> DerivativesPublicHttpClient:
        return DerivativesPublicHttpClient(
            timeout_seconds=3.0,
            max_retries=0,
            rate_limit_per_min=10_000,
            client=httpx.Client(transport=httpx.MockTransport(fixture)),
        )

    output = diagnostic.run_diagnostic(
        options or diagnostic.DiagnosticOptions(),
        dependencies=diagnostic.DiagnosticDependencies(
            now_utc=_StepClock(),
            monotonic=_Monotonic(),
            client_factory=factory,
        ),
    )
    return output, fixture


def test_full_matrix_okx_readiness_is_complete_and_bounded() -> None:
    output, fixture = _run()

    assert output["final_classification"] == "AVAILABLE_COMPLETE"
    assert output["selected_cell_count"] == 4
    assert output["derivatives_methodology_version"] == "deriv-intel-okx-shadow-v1"
    assert output["provider_policy_version"] == "deriv-provider-policy-okx-only-v1"
    assert output["required_provider"] == "OKX_SWAP"
    assert output["derivatives_logical_request_count"] == 5
    assert output["candle_logical_request_count"] == 4
    assert output["server_time_logical_request_count"] == 1
    assert output["total_logical_request_count"] == 10
    assert output["derivatives_http_attempt_count"] == 5
    assert output["candle_http_attempt_count"] == 4
    assert output["server_time_http_attempt_count"] == 1
    assert output["total_http_attempt_count"] == 10
    assert output["binance_request_count"] == 0
    assert len(fixture.calls) == 10
    assert not any(call["host"] == "fapi.binance.com" for call in fixture.calls)
    assert [cell["symbol"] for cell in output["cells"]] == [
        "BTC/USDT",
        "BTC/USDT",
        "ETH/USDT",
        "ETH/USDT",
    ]
    assert [cell["timeframe"] for cell in output["cells"]] == ["1H", "4H", "1H", "4H"]
    for cell in output["cells"]:
        assert cell["classification"] == "AVAILABLE_COMPLETE"
        assert cell["block_status"] == "ACTIVE"
        assert cell["provider_available"] is True
        assert cell["metric_valid_count"] == 4
        assert cell["no_lookahead_pass"] is True
        assert cell["present_metric_ids"] == sorted(diagnostic.REQUIRED_METRIC_IDS)
        assert cell["funding_response_ts_utc"] != cell["funding_time_utc"]
        assert cell["funding_time_utc"] != cell["next_funding_time_utc"]
        assert set(cell) == diagnostic.CELL_KEYS
        assert all(set(timing) == diagnostic.TIMING_KEYS for timing in cell["request_timings"])


def test_single_cell_scope_uses_one_server_one_candle_and_three_derivatives_requests() -> None:
    output, _ = _run(
        options=diagnostic.DiagnosticOptions(symbol="BTC/USDT", timeframe="1H", max_cells=1)
    )

    assert output["selected_cell_count"] == 1
    assert output["derivatives_logical_request_count"] == 3
    assert output["candle_logical_request_count"] == 1
    assert output["server_time_logical_request_count"] == 1
    assert output["total_logical_request_count"] == 5
    assert output["cells"][0]["okx_inst_id"] == "BTC-USDT-SWAP"


def test_configuration_error_does_not_start_provider_requests() -> None:
    output, fixture = _run(options=diagnostic.DiagnosticOptions(max_cells=5))

    assert output["final_classification"] == "CONFIGURATION_ERROR"
    assert output["selected_cell_count"] == 0
    assert output["total_logical_request_count"] == 0
    assert fixture.calls == []


def test_zero_cell_selection_fails_closed_before_provider_requests() -> None:
    output, fixture = _run(options=diagnostic.DiagnosticOptions(symbol="SOL/USDT"))

    assert output["final_classification"] == "CONFIGURATION_ERROR"
    assert output["selected_cell_count"] == 0
    assert output["server_time_logical_request_count"] == 0
    assert output["candle_logical_request_count"] == 0
    assert output["derivatives_logical_request_count"] == 0
    assert output["total_logical_request_count"] == 0
    assert output["total_http_attempt_count"] == 0
    assert fixture.calls == []
    assert diagnostic._reduce_classification([]) == "CONFIGURATION_ERROR"


def test_latest_closed_candle_ignores_current_forming_candle() -> None:
    output, _ = _run(
        options=diagnostic.DiagnosticOptions(symbol="BTC/USDT", timeframe="1H", max_cells=1)
    )
    cell = output["cells"][0]

    assert cell["candle_open_utc"] == "2026-06-22T11:00:00Z"
    assert cell["canonical_reference_close_utc"] == "2026-06-22T12:00:00Z"
    assert cell["candle_confirmed"] is True
    assert cell["observed_request_start_offset_seconds"] is not None
    assert cell["observed_completion_offset_seconds"] is not None


def test_server_clock_offset_uses_request_midpoint() -> None:
    output, _ = _run(
        options=diagnostic.DiagnosticOptions(symbol="BTC/USDT", timeframe="1H", max_cells=1)
    )

    assert output["okx_server_time_utc"] == "2026-06-22T12:05:00Z"
    assert output["okx_server_clock_offset_ms"] == -1500


@pytest.mark.parametrize(
    ("transport", "expected"),
    [
        (_OkxFixtureTransport(funding_status=429), "RATE_LIMITED"),
        (_OkxFixtureTransport(funding_status=503), "HTTP_ERROR"),
        (_OkxFixtureTransport(timeout_path=diagnostic.OKX_CURRENT_FUNDING_PATH), "TIMEOUT"),
        (
            _OkxFixtureTransport(malformed_path=diagnostic.OKX_CURRENT_OPEN_INTEREST_PATH),
            "PROVIDER_UNAVAILABLE",
        ),
    ],
)
def test_provider_failures_are_sanitized_and_classified(
    transport: _OkxFixtureTransport,
    expected: str,
) -> None:
    output, _ = _run(transport, options=diagnostic.DiagnosticOptions(symbol="BTC/USDT"))

    assert output["final_classification"] == expected
    encoded = json.dumps(output)
    assert "fixture timeout" not in encoded
    assert "traceback" not in encoded.lower()
    assert "https://" not in encoded


def test_mixed_candle_timestamp_and_funding_rate_limit_uses_precedence() -> None:
    output, _ = _run(
        _OkxFixtureTransport(
            funding_status=429,
            malformed_path=diagnostic.OKX_CANDLES_PATH,
        ),
        options=diagnostic.DiagnosticOptions(symbol="BTC/USDT", timeframe="1H", max_cells=1),
    )

    assert output["final_classification"] == "RATE_LIMITED"
    assert output["cells"][0]["classification"] == "RATE_LIMITED"
    assert output["cells"][0]["candle_confirmed"] is False


def test_missing_metric_is_available_partial() -> None:
    output, _ = _run(
        _OkxFixtureTransport(omit_oi_usd=True),
        options=diagnostic.DiagnosticOptions(symbol="BTC/USDT", timeframe="1H", max_cells=1),
    )
    cell = output["cells"][0]

    assert output["final_classification"] == "AVAILABLE_PARTIAL"
    assert cell["classification"] == "AVAILABLE_PARTIAL"
    assert cell["block_status"] == "DEGRADED"
    assert cell["metric_valid_count"] == 3


def test_future_provider_timestamps_fail_no_lookahead() -> None:
    output, _ = _run(
        _OkxFixtureTransport(future_event=True),
        options=diagnostic.DiagnosticOptions(symbol="BTC/USDT", timeframe="1H", max_cells=1),
    )
    cell = output["cells"][0]

    assert output["final_classification"] == "NO_LOOKAHEAD_FAILED"
    assert cell["classification"] == "NO_LOOKAHEAD_FAILED"
    assert cell["no_lookahead_pass"] is False
    assert cell["present_metric_ids"] == sorted(diagnostic.REQUIRED_METRIC_IDS)


def test_invalid_provider_timestamp_does_not_raise_and_classifies_safely() -> None:
    output, _ = _run(
        _OkxFixtureTransport(provider_timestamp="9" * 400),
        options=diagnostic.DiagnosticOptions(symbol="BTC/USDT", timeframe="1H", max_cells=1),
    )
    cell = output["cells"][0]

    assert diagnostic._millis_to_utc(float("inf")) is None
    assert output["final_classification"] == "AVAILABLE_PARTIAL"
    assert cell["classification"] == "AVAILABLE_PARTIAL"
    assert cell["metric_valid_count"] == 0
    assert cell["funding_response_ts_utc"] is None
    assert cell["open_interest_ts_utc"] is None


def test_server_time_timeout_is_classified_without_stopping_cell_measurement() -> None:
    output, _ = _run(_OkxFixtureTransport(timeout_path=diagnostic.OKX_SERVER_TIME_PATH))

    assert output["final_classification"] == "TIMEOUT"
    assert output["okx_server_time_utc"] is None
    assert output["okx_server_clock_offset_ms"] is None
    assert output["selected_cell_count"] == 4


def test_output_contract_compact_json_and_step_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary_path = tmp_path / "summary.md"
    fixture = _OkxFixtureTransport()

    def factory() -> DerivativesPublicHttpClient:
        return DerivativesPublicHttpClient(
            timeout_seconds=3.0,
            max_retries=0,
            rate_limit_per_min=10_000,
            client=httpx.Client(transport=httpx.MockTransport(fixture)),
        )

    exit_code = diagnostic.main(
        ["--symbol", "BTC/USDT", "--timeframe", "1H", "--max-cells", "1"],
        dependencies=diagnostic.DiagnosticDependencies(
            now_utc=_StepClock(),
            monotonic=_Monotonic(),
            client_factory=factory,
            step_summary_path=str(summary_path),
        ),
        environ={},
    )
    stdout = capsys.readouterr().out
    output = json.loads(stdout)

    assert exit_code == 0
    assert stdout == json.dumps(output, sort_keys=True, separators=(",", ":")) + "\n"
    assert set(output) == diagnostic.TOP_LEVEL_KEYS
    assert all(set(cell) == diagnostic.CELL_KEYS for cell in output["cells"])
    assert all(
        set(timing) == diagnostic.TIMING_KEYS
        for cell in output["cells"]
        for timing in cell["request_timings"]
    )
    assert "AVAILABLE_COMPLETE" in summary_path.read_text()
    encoded = json.dumps(output) + summary_path.read_text()
    assert "Authorization" not in encoded
    assert "Cookie" not in encoded
    assert "SUPABASE" not in encoded
    assert "response_body" not in encoded.lower()


def test_workflow_contract_is_manual_only_and_secret_free() -> None:
    text = (ROOT / ".github/workflows/derivatives-cadence-readiness-diagnostic.yml").read_text()

    assert text.startswith("name: Derivatives Cadence Readiness Diagnostic\n")
    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "cron:" not in text
    assert "contents: read" in text
    assert "group: derivatives-cadence-readiness-diagnostic" in text
    assert "cancel-in-progress: false" in text
    assert "timeout-minutes: 10" in text
    assert "actions/checkout@v4" in text
    assert "actions/setup-python@v5" in text
    assert 'python-version: "3.11"' in text
    assert "PYTHONPATH: src" in text
    assert "scripts/measure_okx_cadence_readiness.py" in text
    assert "SUPABASE" not in text
    assert "HF_TOKEN" not in text
    assert "secrets." not in text
    assert "UCPE_DERIV_CADENCE_ENABLED" not in text
    assert "UCPE_ENABLE_DERIVATIVES_INTEL" not in text


def test_source_scan_proves_write_free_diagnostic_boundary() -> None:
    source = (ROOT / "scripts/measure_okx_cadence_readiness.py").read_text()
    forbidden = [
        "collect_derivatives_evidence",
        "analyze_request",
        "persist_analysis_now",
        "build_operator_repository",
        "OperatorRepository",
        "save_prediction",
        "save_derivatives_snapshot",
        "INSERT INTO",
        "UPDATE public",
        "SUPABASE",
        "HF_TOKEN",
        "Authorization",
        "Cookie",
    ]
    for value in forbidden:
        assert value not in source
    assert "BINANCE_USDM_BASE_URL" not in source
    assert "fapi.binance.com" not in source
