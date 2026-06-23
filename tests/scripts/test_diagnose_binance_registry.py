from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from crypto_probability_engine.adapters.types import ProviderError
from scripts import diagnose_binance_registry as diagnostic

ROOT = Path(__file__).resolve().parents[2]


class _StepClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        self.value += 0.001
        return self.value


class _FakeClient:
    def __init__(self, timeout: float, outcomes: list[object], calls: list[dict]) -> None:
        self.timeout = timeout
        self.outcomes = outcomes
        self.calls = calls

    def get_json(self, *, base_url, path, params, provider):
        self.calls.append(
            {
                "timeout": self.timeout,
                "base_url": base_url,
                "path": path,
                "params": dict(params),
                "provider": provider,
            }
        )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _run_with_outcomes(outcomes: list[object]) -> tuple[dict, list[dict]]:
    calls: list[dict] = []

    def factory(timeout: float) -> _FakeClient:
        return _FakeClient(timeout, outcomes, calls)

    output = diagnostic.run_diagnostic(client_factory=factory, monotonic=_StepClock())
    return output, calls


def _binance_payload() -> dict:
    return {"symbols": [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}]}


def _okx_payload() -> dict:
    return {"code": "0", "data": [{"instId": "BTC-USDT-SWAP"}]}


def _provider_error(status: int) -> ProviderError:
    return ProviderError(
        "PROVIDER_DEGRADED",
        "sanitized fixture failure",
        provider="BINANCE_USDM",
        http_status=status,
    )


def test_valid_binance_and_okx_payloads_are_ok() -> None:
    output, calls = _run_with_outcomes([_binance_payload(), _binance_payload(), _okx_payload()])

    assert output["final_classification"] == "BINANCE_OK"
    assert output["probe_count"] == 3
    assert len(calls) == 3
    assert calls[0]["timeout"] == 3.0
    assert calls[1]["timeout"] == 10.0
    assert calls[2]["timeout"] == 10.0
    assert calls[0]["path"] == "/fapi/v1/exchangeInfo"
    assert calls[0]["params"] == {}
    assert calls[2]["path"] == "/api/v5/public/instruments"
    assert calls[2]["params"] == {"instType": "SWAP"}
    assert output["probes"][0]["symbols_count"] == 2
    assert output["probes"][2]["data_count"] == 1


@pytest.mark.parametrize(
    ("status", "category"),
    [
        (401, "AUTH_FORBIDDEN"),
        (403, "AUTH_FORBIDDEN"),
        (418, "RATE_LIMITED"),
        (429, "RATE_LIMITED"),
        (451, "LEGAL_BLOCK_451"),
        (500, "SERVER_5XX"),
        (503, "SERVER_5XX"),
        (400, "CLIENT_4XX"),
        (404, "CLIENT_4XX"),
    ],
)
def test_http_status_categories(status: int, category: str) -> None:
    output, _ = _run_with_outcomes([_provider_error(status), _binance_payload(), _okx_payload()])

    assert output["probes"][0]["outcome"] == "FAILED"
    assert output["probes"][0]["http_status"] == status
    assert output["probes"][0]["error_category"] == category


def test_timeout_network_malformed_and_unknown_categories() -> None:
    malformed_json = ProviderError(
        "SCHEMA_VALIDATION_FAILED",
        "malformed fixture",
        provider="BINANCE_USDM",
        error_code="MALFORMED_JSON",
        error_type="SCHEMA",
    )
    cases = [
        (httpx.TimeoutException("fixture timeout"), "TIMEOUT"),
        (httpx.ConnectError("fixture connect failure"), "NETWORK_OR_TLS"),
        (malformed_json, "MALFORMED_JSON"),
        (RuntimeError("fixture unknown"), "UNKNOWN"),
    ]
    for exc, category in cases:
        output, _ = _run_with_outcomes([exc, _binance_payload(), _okx_payload()])
        assert output["probes"][0]["error_category"] == category


@pytest.mark.parametrize("payload", [[], {"symbols": "not-list"}, {"unexpected": []}])
def test_wrong_binance_root_or_schema_is_malformed(payload: object) -> None:
    output, _ = _run_with_outcomes([payload, _binance_payload(), _okx_payload()])

    assert output["probes"][0]["outcome"] == "FAILED"
    assert output["probes"][0]["error_category"] == "MALFORMED_JSON"


@pytest.mark.parametrize("payload", [[], {"data": "not-list"}, {"unexpected": []}])
def test_wrong_okx_root_or_schema_is_malformed(payload: object) -> None:
    output, _ = _run_with_outcomes([_binance_payload(), _binance_payload(), payload])

    assert output["probes"][2]["outcome"] == "FAILED"
    assert output["probes"][2]["error_category"] == "MALFORMED_JSON"


def test_final_classification_timeout_then_success() -> None:
    output, _ = _run_with_outcomes(
        [httpx.TimeoutException("fixture timeout"), _binance_payload(), _okx_payload()]
    )

    assert output["final_classification"] == "BINANCE_TIMEOUT_AT_3S_BUT_OK_AT_10S"


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (_provider_error(451), "BINANCE_ACCESS_RESTRICTED"),
        (_provider_error(403), "BINANCE_ACCESS_RESTRICTED"),
        (_provider_error(429), "BINANCE_RATE_LIMITED"),
        (_provider_error(503), "BINANCE_SERVER_FAILURE"),
        (
            ProviderError(
                "SCHEMA_VALIDATION_FAILED",
                "malformed fixture",
                provider="BINANCE_USDM",
                error_code="MALFORMED_JSON",
                error_type="SCHEMA",
            ),
            "BINANCE_MALFORMED_RESPONSE",
        ),
    ],
)
def test_final_classification_priority(exc: BaseException, expected: str) -> None:
    output, _ = _run_with_outcomes([exc, _binance_payload(), _okx_payload()])

    assert output["final_classification"] == expected


def test_both_network_failures_classify_as_network() -> None:
    output, _ = _run_with_outcomes(
        [
            httpx.ConnectError("fixture connect failure"),
            httpx.ConnectError("fixture connect failure"),
            _okx_payload(),
        ]
    )

    assert output["final_classification"] == "BINANCE_NETWORK_OR_TLS_FAILURE"


def test_output_contract_and_compact_json_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    outcomes = [_provider_error(451), _binance_payload(), _okx_payload()]
    calls: list[dict] = []

    def factory(timeout: float) -> _FakeClient:
        return _FakeClient(timeout, outcomes, calls)

    exit_code = diagnostic.main(
        client_factory=factory,
        environ={},
        monotonic=_StepClock(),
    )
    stdout = capsys.readouterr().out
    output = json.loads(stdout)

    assert exit_code == 0
    assert stdout == json.dumps(output, sort_keys=True, separators=(",", ":")) + "\n"
    assert set(output) == diagnostic.TOP_LEVEL_KEYS
    assert len(output["probes"]) == 3
    assert all(set(probe) == diagnostic.PROBE_KEYS for probe in output["probes"])
    encoded = json.dumps(output)
    assert "https://" not in encoded
    assert "symbols\": [" not in encoded
    assert "data\": [" not in encoded
    assert "headers" not in encoded.lower()
    assert "traceback" not in encoded.lower()
    assert "secret" not in encoded.lower()


def test_step_summary_is_sanitized(tmp_path: Path) -> None:
    summary = tmp_path / "summary.md"
    output, _ = _run_with_outcomes([_provider_error(429), _binance_payload(), _okx_payload()])

    diagnostic.append_step_summary(str(summary), output)
    text = summary.read_text()

    assert "BINANCE_USDM" in text
    assert "/fapi/v1/exchangeInfo" in text
    assert "RATE_LIMITED" in text
    assert "https://" not in text
    assert "secret" not in text.lower()
    assert "traceback" not in text.lower()


def test_source_scan_blocks_collector_persistence_and_secret_coupling() -> None:
    source = (ROOT / "scripts/diagnose_binance_registry.py").read_text()
    forbidden = [
        "collect_derivatives_evidence",
        "analyze_request",
        "persist_analysis_now",
        "SUPABASE_DB_URL",
        "UCPE_ENABLE_DERIVATIVES_INTEL",
        "UCPE_DERIV_CADENCE_ENABLED",
        "HF_TOKEN",
        "Authorization",
        "Cookie",
        "printenv",
        "save_prediction",
        "save_derivatives_snapshot",
        "INSERT INTO",
        "UPDATE public",
    ]
    for value in forbidden:
        assert value not in source
    assert "response_body" not in source
    assert "repr(" not in source


def test_workflow_contract_and_collector_workflow_unchanged() -> None:
    text = (ROOT / ".github/workflows/derivatives-registry-diagnostic.yml").read_text()

    assert text.startswith("name: UCPE Derivatives Registry Diagnostic\n")
    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "cron:" not in text
    assert "contents: read" in text
    assert "group: derivatives-registry-diagnostic" in text
    assert "cancel-in-progress: false" in text
    assert "timeout-minutes: 5" in text
    assert "actions/checkout@v4" in text
    assert "actions/setup-python@v5" in text
    assert 'python-version: "3.11"' in text
    assert "PYTHONPATH: src" in text
    assert "SUPABASE" not in text
    assert "HF_TOKEN" not in text
    assert "secrets." not in text
    assert "UCPE_ENABLE_DERIVATIVES_INTEL" not in text
    assert "UCPE_DERIV_CADENCE_ENABLED" not in text

    run_step = text.split("- name: Run Binance registry diagnostic", 1)[1]
    env_block = run_step.split("run: |", 1)[0]
    assert env_block.count("PYTHONPATH: src") == 1
    assert "PYTHONPATH=src python3 scripts/diagnose_binance_registry.py" in run_step

    collector_workflow = (
        ROOT / ".github/workflows/derivatives-evidence-cadence.yml"
    ).read_text()
    assert "Run manual derivatives evidence collector without write secret" in collector_workflow
    assert "Run confirmed manual derivatives evidence collector write" in collector_workflow
