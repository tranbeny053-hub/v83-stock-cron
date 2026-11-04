from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator, RefResolver

import crypto_probability_engine.api.analysis_service as service
from crypto_probability_engine.api.schemas import AnalysisRequest, AnalysisResponse
from crypto_probability_engine.config.defaults import (
    DEFAULT_METHODOLOGY_VERSION,
    DISTRIBUTIONAL_METHODOLOGY_VERSION,
)
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.oos.pair_context import (
    OOSArm,
    build_oos_pair_context,
)
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from tests.fixtures.market_data import (
    make_candles,
    make_downtrend_snapshot,
    make_high_volatility_snapshot,
    make_snapshot,
)

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = json.loads((ROOT / "tests/api/fixtures/ng_off_parity_v1.json").read_text())
FROZEN = datetime(2026, 6, 6, 12, tzinfo=UTC)
SHAPES = (
    ("base", make_snapshot),
    ("downtrend", make_downtrend_snapshot),
    ("high_volatility", make_high_volatility_snapshot),
)
METHODS = (DEFAULT_METHODOLOGY_VERSION, DISTRIBUTIONAL_METHODOLOGY_VERSION)


def make_epistemic_void_snapshot(*, provider: str, timeframe: str):
    snapshot = make_snapshot(provider=provider)
    return replace(snapshot, timeframe=timeframe, candles=make_candles(count=10))


ALL_SHAPES = (*SHAPES, ("epistemic_void", make_epistemic_void_snapshot))


def _canonical_sha(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _case_id(tf: str, shape: str, provider_status: str, methodology: str) -> str:
    return f"{tf}_{shape}_{provider_status}_{methodology}"


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(child, key) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, key) for child in value)
    return False


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    tf: str,
    maker,
    provider_status: str,
    *,
    provider: str = "binance",
) -> None:
    snapshot = maker(provider=provider, timeframe=tf)
    monkeypatch.setattr(service, "_stamp_clock", lambda: FROZEN)
    monkeypatch.setattr(service, "uuid4", lambda: SimpleNamespace(hex="1031-frozen-run-id"))
    monkeypatch.setattr(service, "utc_now", lambda: FROZEN)
    monkeypatch.setattr(service.time, "perf_counter", lambda: 42.0)

    def select(symbol, timeframe, *, settings):
        del settings
        selected = replace(snapshot, normalized_symbol=symbol.display, timeframe=timeframe)
        state = {
            "status": provider_status,
            "active_provider": "binance",
            "cross_provider_state": "UNAVAILABLE",
            "providers": {"binance": {"status": provider_status}},
        }
        quality = {
            "status": provider_status,
            "warnings": [],
            "freshness_budget": "DEFAULT_PHASE1A",
            "is_live_data": True,
            "data_source": "BINANCE_PUBLIC",
            "latest_candle_age_seconds": 0,
            "provider_failures": {},
            "cross_provider_state": "UNAVAILABLE",
        }
        return SimpleNamespace(snapshot=selected, provider_state=state, data_quality=quality)

    monkeypatch.setattr(service, "select_market_data", select)


def _analyze(
    methodology: str, *, timeframe: str = "4H", isolated: bool = False
) -> tuple[dict, dict | None]:
    request = AnalysisRequest(symbol="BTC", timeframe=timeframe)
    settings = Settings(data_mode="fixture", provider_priority=("binance",))
    if isolated:
        return service.analyze_request_isolated(
            request, settings=settings, methodology_version=methodology
        ), None
    response = service.analyze_request(
        request,
        settings=settings,
        run_store=InMemoryRunStore(),
        methodology_version=methodology,
    )
    predictions, *_ = service._peek_prediction_persistence(response)
    service._pop_prediction_persistence(response)
    return response, predictions[0]


@pytest.mark.parametrize(
    "timeframe,shape,maker,provider_status,methodology",
    [
        (tf, shape, maker, status, method)
        for tf in ("15m", "1H", "4H", "1D")
        for shape, maker in ALL_SHAPES
        for status in ("OK", "DEGRADED")
        for method in METHODS
        if not (tf == "1D" and method == DISTRIBUTIONAL_METHODOLOGY_VERSION)
        and not (shape == "epistemic_void" and tf != "4H")
    ],
    ids=[
        f"{tf}-{shape}-{status}-{method}"
        for tf in ("15m", "1H", "4H", "1D")
        for shape, _maker in ALL_SHAPES
        for status in ("OK", "DEGRADED")
        for method in METHODS
        if not (tf == "1D" and method == DISTRIBUTIONAL_METHODOLOGY_VERSION)
        and not (shape == "epistemic_void" and tf != "4H")
    ],
)
def test_off_matches_frozen_golden(
    monkeypatch, timeframe, shape, maker, provider_status, methodology
) -> None:
    _setup(monkeypatch, timeframe, maker, provider_status)
    monkeypatch.setattr(service, "NG_PIPELINE_ENABLED", False)
    response, prediction = _analyze(methodology, timeframe=timeframe)
    row = GOLDEN["cases"][_case_id(timeframe, shape, provider_status, methodology)]
    assert response["analysis_hash"] == row["analysis_hash"]
    assert _canonical_sha(response) == row["response_sha256"]
    assert _canonical_sha(prediction) == row["prediction_row_sha256"]


@pytest.mark.parametrize(
    "timeframe,shape,maker,provider_status,methodology",
    [
        (tf, shape, maker, status, method)
        for tf in ("15m", "1H", "4H", "1D")
        for shape, maker in ALL_SHAPES
        for status in ("OK", "DEGRADED")
        for method in METHODS
        if not (tf == "1D" and method == DISTRIBUTIONAL_METHODOLOGY_VERSION)
        and not (shape == "epistemic_void" and tf != "4H")
    ],
    ids=[
        f"on-{tf}-{shape}-{status}-{method}"
        for tf in ("15m", "1H", "4H", "1D")
        for shape, _maker in ALL_SHAPES
        for status in ("OK", "DEGRADED")
        for method in METHODS
        if not (tf == "1D" and method == DISTRIBUTIONAL_METHODOLOGY_VERSION)
        and not (shape == "epistemic_void" and tf != "4H")
    ],
)
def test_on_is_hidden_and_preserves_authority(
    monkeypatch, timeframe, shape, maker, provider_status, methodology
) -> None:
    _setup(monkeypatch, timeframe, maker, provider_status)
    monkeypatch.setattr(service, "NG_PIPELINE_ENABLED", False)
    off, off_row = _analyze(methodology, timeframe=timeframe)
    monkeypatch.setattr(service, "NG_PIPELINE_ENABLED", True)
    on, on_row = _analyze(methodology, timeframe=timeframe)
    off_without_hash = dict(off)
    off_without_hash.pop("analysis_hash")
    on_without_ng = dict(on)
    ng = on_without_ng.pop("ng_serving")
    on_without_ng.pop("analysis_hash")
    assert list(on_without_ng) == list(off_without_hash)
    assert on_without_ng == off_without_hash
    assert on_row == off_row
    assert ng == {
        "schema": "quant-ng-serving.v1",
        "serving_state": {
            "tier": "HEURISTIC",
            "reference": "HIDDEN",
            "status": "NONE",
            "slot_policy": "HOLD_HIDDEN_REFERENCE",
            "reason": (
                "OD-NG-4 KEEP_HOLD: the heuristic stays authoritative; the reference is hidden"
            ),
        },
        "reference_state": "HIDDEN",
        "evidence_status": "NONE",
        "slot_policy": "HOLD_HIDDEN_REFERENCE",
        "policy_id": None,
        "status": "SERVED_HIDDEN",
        "h_extended_context": {"status": "UNAVAILABLE", "reason": "NOT_MODELED"},
    }
    assert not _contains_key(on, "candidate_shadow")
    assert on["debug"] == off["debug"]
    assert on["gate_result"] == off["gate_result"]
    assert on["score_stack"]["disposition"] == off["score_stack"]["disposition"]
    assert on["probability_state"] == off["probability_state"]
    response_schema = json.loads((ROOT / "schemas/response.schema.json").read_text())
    schema_store = {
        "quant.schema.json": json.loads((ROOT / "schemas/quant.schema.json").read_text()),
        "detail_view.schema.json": json.loads(
            (ROOT / "schemas/detail_view.schema.json").read_text()
        ),
    }
    validator = Draft202012Validator(
        response_schema,
        resolver=RefResolver.from_schema(response_schema, store=schema_store),
    )
    validator.validate(on)
    AnalysisResponse.model_validate(on)


def test_off_default_and_isolated_path_never_import_pipeline_call(monkeypatch) -> None:
    _setup(monkeypatch, "4H", make_snapshot, "OK", provider="fixture")
    assert service.NG_PIPELINE_ENABLED is False
    monkeypatch.setattr(service, "NG_PIPELINE_ENABLED", False)
    off, _ = _analyze(DEFAULT_METHODOLOGY_VERSION, isolated=True)
    monkeypatch.setattr(service, "NG_PIPELINE_ENABLED", True)
    monkeypatch.setattr(service, "run_pipeline_ng", lambda *a, **k: pytest.fail("isolated NG call"))
    on, _ = _analyze(DEFAULT_METHODOLOGY_VERSION, isolated=True)
    assert on == off
    assert "ng_serving" not in on


def test_unmapped_provider_fails_closed(monkeypatch) -> None:
    _setup(monkeypatch, "4H", make_snapshot, "OK", provider="fixture")
    monkeypatch.setattr(service, "NG_PIPELINE_ENABLED", False)
    off, _ = _analyze(DEFAULT_METHODOLOGY_VERSION)
    monkeypatch.setattr(service, "NG_PIPELINE_ENABLED", True)
    on, _ = _analyze(DEFAULT_METHODOLOGY_VERSION)
    ng = on.pop("ng_serving")
    on.pop("analysis_hash")
    off.pop("analysis_hash")
    assert ng == {
        "schema": "quant-ng-serving.v1",
        "status": "UNAVAILABLE",
        "reason": "provider not mapped",
    }
    assert on == off


def test_authoritative_gate_actions_vary_across_supported_cases(monkeypatch) -> None:
    actions = set()
    for timeframe in ("15m", "1H", "4H", "1D"):
        for shape, maker in ALL_SHAPES:
            if shape == "epistemic_void" and timeframe != "4H":
                continue
            for provider_status in ("OK", "DEGRADED"):
                _setup(monkeypatch, timeframe, maker, provider_status)
                monkeypatch.setattr(service, "NG_PIPELINE_ENABLED", False)
                response, _ = _analyze(DEFAULT_METHODOLOGY_VERSION, timeframe=timeframe)
                actions.add(response["gate_result"]["action"])
    assert len(actions) >= 2


def test_response_schema_is_only_additive_ng_serving_property() -> None:
    base = json.loads(
        subprocess.run(
            ["git", "show", "8ab729a5:schemas/response.schema.json"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    current_text = (ROOT / "schemas/response.schema.json").read_text()
    current = json.loads(current_text)
    assert "ng_serving" in current["properties"]
    current["properties"].pop("ng_serving")
    assert current == base

    diff = subprocess.run(
        ["git", "diff", "--unified=0", "8ab729a5", "--", "schemas/response.schema.json"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    changed_lines = [
        line
        for line in diff
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    hunks = [line for line in diff if line.startswith("@@")]
    assert changed_lines
    assert len(hunks) == 1 and hunks[0].startswith("@@ -170 +170,")
    assert changed_lines[0] == '-    "analysis_hash": { "type": "string" }'
    assert changed_lines[1] == '+    "analysis_hash": { "type": "string" },'
    assert all(line.startswith("+") for line in changed_lines[2:])


def test_distributional_1d_is_same_legacy_error_with_switch_off_or_on(monkeypatch) -> None:
    _setup(monkeypatch, "1D", make_snapshot, "OK")
    request = AnalysisRequest(symbol="BTC", timeframe="1D")
    settings = Settings(data_mode="fixture", provider_priority=("binance",))
    messages = []
    for enabled in (False, True):
        monkeypatch.setattr(service, "NG_PIPELINE_ENABLED", enabled)
        with pytest.raises(ValueError) as error:
            service.analyze_request(
                request,
                settings=settings,
                run_store=InMemoryRunStore(),
                methodology_version=DISTRIBUTIONAL_METHODOLOGY_VERSION,
            )
        messages.append((type(error.value), str(error.value)))
    assert messages[0] == messages[1]
    assert messages[0][1] == "Distributional methodology does not support timeframe: 1D"


def test_1m_registry_refusal_falls_back_to_legacy_result(monkeypatch) -> None:
    _setup(monkeypatch, "1M", make_snapshot, "OK")
    request = AnalysisRequest(symbol="BTC", timeframe="1M")
    settings = Settings(data_mode="fixture", provider_priority=("binance",))
    monkeypatch.setattr(service, "NG_PIPELINE_ENABLED", False)
    off = service.analyze_request(request, settings=settings, run_store=InMemoryRunStore())
    service._pop_prediction_persistence(off)
    monkeypatch.setattr(service, "NG_PIPELINE_ENABLED", True)
    on = service.analyze_request(request, settings=settings, run_store=InMemoryRunStore())
    service._pop_prediction_persistence(on)
    ng = on.pop("ng_serving")
    on.pop("analysis_hash")
    off.pop("analysis_hash")
    assert ng == {
        "schema": "quant-ng-serving.v1",
        "status": "UNAVAILABLE",
        "reason": "timeframe is unsupported",
    }
    assert on == off


def test_oos_arm_stays_legacy_when_switch_is_on(monkeypatch) -> None:
    _setup(monkeypatch, "4H", make_snapshot, "OK")
    snapshot = make_snapshot(provider="binance", timeframe="4H")
    state = {
        "status": "OK",
        "active_provider": "binance",
        "cross_provider_state": "UNAVAILABLE",
        "providers": {"binance": {"status": "OK"}},
    }
    quality = {
        "status": "OK",
        "warnings": [],
        "freshness_budget": "DEFAULT_PHASE1A",
        "is_live_data": True,
        "data_source": "BINANCE_PUBLIC",
        "latest_candle_age_seconds": 0,
        "provider_failures": {},
        "cross_provider_state": "UNAVAILABLE",
    }
    pair = build_oos_pair_context(
        market_snapshot=snapshot,
        provider_state=state,
        data_quality=quality,
        resolved_skill_evidence={
            "verdict": "INSUFFICIENT_EVIDENCE",
            "n": 0,
            "observed_directional_rate": None,
        },
        information_cutoff=snapshot.as_of_utc,
        decision_band_frac=0.002,
    )
    payloads = []
    for enabled in (False, True):
        monkeypatch.setattr(service, "NG_PIPELINE_ENABLED", enabled)
        payloads.append(
            service.analyze_request(
                AnalysisRequest(symbol="BTC", timeframe="4H"),
                settings=Settings(data_mode="fixture", provider_priority=("binance",)),
                run_store=InMemoryRunStore(),
                prediction_origin="SCHEDULED_SHADOW_EVIDENCE",
                pair_context=pair,
                arm=OOSArm.BASELINE,
            )
        )
    assert payloads[0] == payloads[1]
    assert "ng_serving" not in payloads[1]
    service._pop_prediction_persistence(payloads[-1])


def _off_cases():
    """The supported OFF matrix. Excluded on purpose: 1D x distributional (the pinned pipeline
    rejects it; tested separately as an identical error ON and OFF) and the epistemic-void shape at
    any timeframe but 4H (one void case per method and provider status is enough for the gate)."""
    return [
        (tf, shape, maker, status, method)
        for tf in ("15m", "1H", "4H", "1D")
        for shape, maker in ALL_SHAPES
        for status in ("OK", "DEGRADED")
        for method in METHODS
        if not (tf == "1D" and method == DISTRIBUTIONAL_METHODOLOGY_VERSION)
        and not (shape == "epistemic_void" and tf != "4H")
    ]


def generate_ng_off_parity_golden(path: Path | None = None) -> dict:
    """Not a test: rebuild the OFF golden. Run it only against the base code (M53, before NG3).

    UCPE_GENERATE_NG3_GOLDEN=1 PYTHONPATH=src:. .venv/bin/python -c \
      "from tests.api.test_ng_dormant_switch import generate_ng_off_parity_golden as g; g()"
    """
    if os.environ.get("UCPE_GENERATE_NG3_GOLDEN") != "1":
        raise RuntimeError("set UCPE_GENERATE_NG3_GOLDEN=1 to regenerate the frozen OFF golden")
    target = path or ROOT / "tests/api/fixtures/ng_off_parity_v1.json"
    cases = {}
    with pytest.MonkeyPatch.context() as mp:
        for tf, shape, maker, status, method in _off_cases():
            _setup(mp, tf, maker, status)
            response, prediction = _analyze(method, timeframe=tf)
            cases[_case_id(tf, shape, status, method)] = {
                "analysis_hash": response["analysis_hash"],
                "prediction_row_sha256": _canonical_sha(prediction),
                "response_sha256": _canonical_sha(response),
            }
    data = {
        "cases": cases,
        "generated_from": "M53 8ab729a5 before NG3 code changes",
        "schema": "ng-off-parity.v1",
    }
    target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return data


def test_golden_lists_exactly_the_supported_cases() -> None:
    expected = {
        _case_id(tf, shape, status, method) for tf, shape, _m, status, method in _off_cases()
    }
    assert set(GOLDEN["cases"]) == expected
    assert len(expected) == 46


_SERVED_NG = {
    "schema": "quant-ng-serving.v1",
    "serving_state": {
        "tier": "HEURISTIC",
        "reference": "HIDDEN",
        "status": "NONE",
        "slot_policy": "HOLD_HIDDEN_REFERENCE",
        "reason": "OD-NG-4 KEEP_HOLD: the heuristic stays authoritative; the reference is hidden",
    },
    "reference_state": "HIDDEN",
    "evidence_status": "NONE",
    "slot_policy": "HOLD_HIDDEN_REFERENCE",
    "policy_id": None,
    "status": "SERVED_HIDDEN",
    "h_extended_context": {"status": "UNAVAILABLE", "reason": "NOT_MODELED"},
}
_UNAVAILABLE_NG = {
    "schema": "quant-ng-serving.v1",
    "status": "UNAVAILABLE",
    "reason": "provider not mapped",
}


def _ng_validator() -> Draft202012Validator:
    schema = json.loads((ROOT / "schemas/response.schema.json").read_text())
    return Draft202012Validator(schema["properties"]["ng_serving"])


def _with(base: dict, path: tuple[str, ...], value: object) -> dict:
    copy = json.loads(json.dumps(base))
    target = copy
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return copy


def test_ng_serving_schema_admits_exactly_the_two_shapes() -> None:
    validator = _ng_validator()
    assert validator.is_valid(_SERVED_NG)
    assert validator.is_valid(_UNAVAILABLE_NG)


@pytest.mark.parametrize(
    "path,value",
    [
        (("serving_state", "tier"), "REFERENCE"),
        (("serving_state", "reference"), "SHOWN"),
        (("serving_state", "slot_policy"), "REFERENCE_AUTHORITATIVE"),
        (("reference_state",), "SHOWN"),
        (("evidence_status",), "SUPPORTED"),
        (("slot_policy",), "REFERENCE_AUTHORITATIVE"),
        (("policy_id",), "option-b"),
        (("status",), "SERVED"),
        (("candidate_shadow",), {}),
        (("h_extended_context", "status"), "AVAILABLE"),
    ],
    ids=[
        "tier-not-heuristic",
        "serving-reference-shown",
        "serving-slot-policy-not-hold",
        "reference-state-shown",
        "evidence-status-not-none",
        "slot-policy-not-hold",
        "policy-id-set",
        "unknown-status",
        "extra-candidate-shadow-key",
        "h-extended-available",
    ],
)
def test_ng_serving_schema_refuses_any_unhidden_or_unruled_value(path, value) -> None:
    assert not _ng_validator().is_valid(_with(_SERVED_NG, path, value))

