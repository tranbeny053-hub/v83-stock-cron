"""W26: the writer stamps tc-v1 on live rows from an injected app clock; nothing else changes.

- A live USER_REQUESTED or CONTROLLED_SMOKE row that passes validate_v1 is stamped. The
  core-finished instant is read right after run_quant_pipeline, the issued instant after both
  snapshot builders.
- OOS arm rows and SCHEDULED_SHADOW_EVIDENCE rows are never stamped; stamp_v1 is not even called.
- A row that fails validate_v1 stays exactly as _prediction_row built it.
- The response carries no stamp key and is identical whether or not the row was stamped, and so
  are both snapshots.
The clock is always frozen, because stamping depends on "now" through I1 and I3.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

import pytest

from crypto_probability_engine.adapters.provider_selection import ProviderSelectionResult
from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.config.defaults import (
    DISTRIBUTIONAL_METHODOLOGY_VERSION,
    METHODOLOGY_VERSION,
)
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.config.unit_discipline import utc_now
from crypto_probability_engine.oos.pair_context import OOSArm, build_oos_pair_context
from crypto_probability_engine.persistence.repository import InMemoryPersistenceRepository
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from crypto_probability_engine.targets import contract_v1 as tc
from tests.fixtures.market_data import FIXED_NOW, make_snapshot

# make_snapshot: the last candle closes at FIXED_NOW, which is also as_of (predicted_at_utc).
CORE_DONE = FIXED_NOW + timedelta(seconds=2, microseconds=500_000)
ISSUED = CORE_DONE + timedelta(milliseconds=600)
HORIZON_END_4H = FIXED_NOW + timedelta(hours=24)  # 6 bars of 4H after the reference close
STAMP_KEYS = frozenset(tc.STAMP_FIELDS)
SKILL_EVIDENCE = {
    "verdict": "INSUFFICIENT_EVIDENCE",
    "n": 0,
    "observed_directional_rate": None,
}
_iso = analysis_service._iso_utc  # noqa: SLF001 - the writer's own timestamp format


class _Clock:
    """A frozen app clock: it returns the given instants in order, then repeats the last one."""

    def __init__(self, *instants: datetime) -> None:
        self._instants = instants
        self.calls = 0

    def __call__(self) -> datetime:
        instant = self._instants[min(self.calls, len(self._instants) - 1)]
        self.calls += 1
        return instant


def _selection(
    *,
    provider: str = "binance",
    data_source: str = "BINANCE_PUBLIC",
    cross_provider_state: str = "UNAVAILABLE",
    active_provider: str | None = None,
):
    def select(symbol, timeframe, *, settings):
        del settings
        return ProviderSelectionResult(
            snapshot=make_snapshot(
                provider=provider,
                symbol=symbol.display,
                timeframe=timeframe,
            ),
            provider_state={
                "status": "OK",
                "active_provider": active_provider or provider,
                "cross_provider_state": cross_provider_state,
                "providers": {provider: {"status": "OK"}},
            },
            data_quality={
                "status": "OK",
                "warnings": [],
                "freshness_budget": "DEFAULT_PHASE1A",
                "is_live_data": True,
                "data_source": data_source,
                "latest_candle_age_seconds": 0,
                "provider_failures": {},
                "cross_provider_state": cross_provider_state,
            },
        )

    return select


@pytest.fixture
def stamp_spy(monkeypatch) -> list[dict]:
    calls: list[dict] = []
    real_stamp = analysis_service.stamp_v1

    def spy(row, **kwargs):
        calls.append({"row": dict(row), **kwargs})
        return real_stamp(row, **kwargs)

    monkeypatch.setattr(analysis_service, "stamp_v1", spy)
    return calls


def _setup(monkeypatch, clock: _Clock, **selection: str) -> None:
    monkeypatch.setattr(analysis_service, "_stamp_clock", clock)
    monkeypatch.setattr(analysis_service, "select_market_data", _selection(**selection))
    monkeypatch.setattr(analysis_service, "uuid4", lambda: UUID(int=26))
    monkeypatch.setattr(
        analysis_service, "get_cached_skill_evidence", lambda _timeframe: SKILL_EVIDENCE
    )


def _analyze(
    *,
    timeframe: str = "4H",
    prediction_origin: str = "USER_REQUESTED",
    deterministic_identity: bool = False,
) -> tuple[dict, dict, dict, dict | None]:
    payload = analysis_service.analyze_request(
        AnalysisRequest(symbol="BTC", timeframe=timeframe),
        settings=Settings(data_mode="fixture"),
        run_store=InMemoryRunStore(),
        prediction_origin=prediction_origin,
        deterministic_identity=deterministic_identity,
    )
    return (payload, *_pop_single(payload))


def _pop_single(payload: dict) -> tuple[dict, dict, dict | None]:
    rows, features, failed, derivatives, derivatives_failed = (
        analysis_service._pop_prediction_persistence(payload)  # noqa: SLF001
    )
    assert not failed
    assert not derivatives_failed
    assert len(rows) == 1
    assert len(features) == 1
    assert len(derivatives) <= 1
    return rows[0], features[0], derivatives[0] if derivatives else None


def _keys_anywhere(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        found.update(str(key) for key in value)
        items = list(value.values())
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        return found
    for item in items:
        found |= _keys_anywhere(item)
    return found


def _unstamped(row: dict) -> dict:
    return {key: value for key, value in row.items() if key not in STAMP_KEYS}


@pytest.mark.parametrize("origin", ["USER_REQUESTED", "CONTROLLED_SMOKE"])
def test_a_live_row_is_stamped_from_the_frozen_clock(monkeypatch, stamp_spy, origin) -> None:
    clock = _Clock(CORE_DONE, ISSUED)
    _setup(monkeypatch, clock)

    payload, row, _, _ = _analyze(prediction_origin=origin)

    assert clock.calls == 2
    assert len(stamp_spy) == 1
    assert stamp_spy[0]["row"] == _unstamped(row)
    assert stamp_spy[0]["snapshot_provider"] == "binance"
    assert row["target_version"] == "tc-v1"
    assert row["reference_venue"] == "BINANCE_PUBLIC"
    assert row["core_computed_at_utc"] == _iso(CORE_DONE)
    assert row["issued_at_utc"] == _iso(ISSUED)
    assert row["prediction_origin"] == origin
    # predicted_at_utc stays snapshot.as_of_utc; the stamp only adds its four keys.
    assert row["predicted_at_utc"] == _iso(FIXED_NOW)
    assert tc.validate_v1(row) == ()
    assert tc.classify_row(row) == tc.CLASS_TC_V1
    assert not STAMP_KEYS & _keys_anywhere(payload)


def test_an_okx_row_is_stamped_with_the_okx_venue(monkeypatch) -> None:
    _setup(monkeypatch, _Clock(CORE_DONE, ISSUED), provider="okx", data_source="OKX_PUBLIC")

    _, row, _, _ = _analyze()

    assert row["reference_venue"] == "OKX_PUBLIC"
    assert tc.validate_v1(row) == ()


def test_a_coherent_cross_provider_row_records_the_snapshot_venue(monkeypatch) -> None:
    # A coherent two-venue selection: active_provider is "cross_provider", never a venue, so the
    # stamp takes the venue of the snapshot whose candles gave the reference close.
    _setup(
        monkeypatch,
        _Clock(CORE_DONE, ISSUED),
        provider="okx",
        data_source="CROSS_PROVIDER",
        cross_provider_state="COHERENT",
        active_provider="cross_provider",
    )

    _, row, _, _ = _analyze()

    assert row["data_source"] == "CROSS_PROVIDER"
    assert row["cross_provider_state"] == "COHERENT"
    assert row["reference_venue"] == "OKX_PUBLIC"
    assert tc.validate_v1(row) == ()
    assert tc.resolution_venue(row) == "OKX_PUBLIC"


def test_core_is_read_after_the_quant_core_and_issue_after_both_snapshots(monkeypatch) -> None:
    clock = _Clock(CORE_DONE, ISSUED)
    _setup(monkeypatch, clock)
    seen: dict[str, object] = {}
    real_pipeline = analysis_service.run_quant_pipeline
    real_feature_builder = analysis_service.build_feature_snapshot
    real_derivatives_builder = analysis_service.build_derivatives_snapshot

    def pipeline(*args, **kwargs):
        seen["clock_calls_before_core"] = clock.calls
        result = real_pipeline(*args, **kwargs)
        seen["clock_calls_after_core"] = clock.calls
        return result

    def skill_evidence(_timeframe):
        # The first thing analyze_request does after the quant core returns.
        seen["clock_calls_at_skill_evidence"] = clock.calls
        return SKILL_EVIDENCE

    def feature_builder(prediction_row, quant_v2):
        seen["feature_row_keys"] = set(prediction_row)
        seen["clock_calls_at_feature_snapshot"] = clock.calls
        return real_feature_builder(prediction_row, quant_v2)

    def derivatives_builder(prediction_row, block):
        seen["derivatives_row_keys"] = set(prediction_row)
        seen["clock_calls_at_derivatives_snapshot"] = clock.calls
        return real_derivatives_builder(prediction_row, block)

    monkeypatch.setattr(analysis_service, "run_quant_pipeline", pipeline)
    monkeypatch.setattr(analysis_service, "get_cached_skill_evidence", skill_evidence)
    monkeypatch.setattr(analysis_service, "build_feature_snapshot", feature_builder)
    monkeypatch.setattr(analysis_service, "build_derivatives_snapshot", derivatives_builder)

    _, row, _, _ = _analyze()

    assert seen["clock_calls_before_core"] == 0
    assert seen["clock_calls_after_core"] == 0
    assert seen["clock_calls_at_skill_evidence"] == 1  # read right after the core returned
    assert seen["clock_calls_at_feature_snapshot"] == 1  # the core instant only
    assert seen["clock_calls_at_derivatives_snapshot"] == 1
    assert not STAMP_KEYS & seen["feature_row_keys"]
    assert not STAMP_KEYS & seen["derivatives_row_keys"]
    assert clock.calls == 2
    assert row["core_computed_at_utc"] == _iso(CORE_DONE)
    assert row["issued_at_utc"] == _iso(ISSUED)


def test_the_response_and_snapshots_are_identical_whether_or_not_stamped(monkeypatch) -> None:
    _setup(monkeypatch, _Clock(CORE_DONE, ISSUED))
    stamped_payload, stamped_row, stamped_features, stamped_derivatives = _analyze()
    # The same run issued at the horizon end: I3 fails, so the row stays unstamped.
    _setup(monkeypatch, _Clock(CORE_DONE, HORIZON_END_4H))
    plain_payload, plain_row, plain_features, plain_derivatives = _analyze()

    assert tc.classify_row(stamped_row) == tc.CLASS_TC_V1
    assert tc.classify_row(plain_row) == tc.CLASS_V0_LEGACY
    assert not STAMP_KEYS & set(plain_row)
    assert _unstamped(stamped_row) == plain_row
    assert stamped_payload == plain_payload
    assert stamped_payload["analysis_hash"] == plain_payload["analysis_hash"]
    assert stamped_payload["detail_view"] == plain_payload["detail_view"]
    assert stamped_features == plain_features
    assert stamped_derivatives == plain_derivatives
    assert not STAMP_KEYS & _keys_anywhere(stamped_payload)
    assert not STAMP_KEYS & _keys_anywhere(stamped_features)
    assert not STAMP_KEYS & _keys_anywhere(stamped_derivatives)


def test_the_stamped_row_is_the_row_handed_to_the_repository(monkeypatch) -> None:
    _setup(monkeypatch, _Clock(CORE_DONE, ISSUED))
    saved: list[dict] = []

    class RecordingRepository(InMemoryPersistenceRepository):
        def save_prediction(self, row):
            saved.append(dict(row))
            return super().save_prediction(row)

    payload = analysis_service.analyze_request(
        AnalysisRequest(symbol="BTC", timeframe="4H"),
        settings=Settings(data_mode="fixture"),
        run_store=InMemoryRunStore(),
    )
    try:
        result = analysis_service.persist_analysis_now(payload, RecordingRepository())
    finally:
        row, _, _ = _pop_single(payload)

    assert result["prediction"] == "STATELESS"
    assert saved == [row]
    assert saved[0]["issued_at_utc"] == _iso(ISSUED)
    assert tc.classify_row(saved[0]) == tc.CLASS_TC_V1


@pytest.mark.parametrize("deterministic_identity", [False, True])
def test_a_scheduled_shadow_row_is_never_stamped(
    monkeypatch, stamp_spy, deterministic_identity
) -> None:
    clock = _Clock(CORE_DONE, ISSUED)
    _setup(monkeypatch, clock)

    payload, row, _, _ = _analyze(
        prediction_origin="SCHEDULED_SHADOW_EVIDENCE",
        deterministic_identity=deterministic_identity,
    )

    assert stamp_spy == []
    assert not STAMP_KEYS & set(row)
    assert tc.classify_row(row) == tc.CLASS_V0_LEGACY
    assert clock.calls == 1  # the core instant only; no issued instant is read
    assert not STAMP_KEYS & _keys_anywhere(payload)


def test_oos_arm_rows_are_never_stamped(monkeypatch, stamp_spy) -> None:
    clock = _Clock(CORE_DONE, ISSUED)
    _setup(monkeypatch, clock)
    snapshot = make_snapshot(provider="binance")
    selection = _selection()(
        type("Symbol", (), {"display": snapshot.normalized_symbol})(),
        snapshot.timeframe,
        settings=Settings(data_mode="fixture"),
    )
    pair = build_oos_pair_context(
        market_snapshot=snapshot,
        provider_state=selection.provider_state,
        data_quality=selection.data_quality,
        resolved_skill_evidence=SKILL_EVIDENCE,
        information_cutoff=snapshot.as_of_utc,
        decision_band_frac=0.002,
    )

    payloads = [
        analysis_service.analyze_request(
            AnalysisRequest(symbol="BTC", timeframe="4H"),
            settings=Settings(data_mode="fixture"),
            run_store=InMemoryRunStore(),
            prediction_origin="SCHEDULED_SHADOW_EVIDENCE",
            methodology_version=methodology_version,
            pair_context=pair,
            arm=arm,
        )
        for arm, methodology_version in (
            (OOSArm.BASELINE, METHODOLOGY_VERSION),
            (OOSArm.CANDIDATE, DISTRIBUTIONAL_METHODOLOGY_VERSION),
        )
    ]
    rows, _, failed, _, derivatives_failed = (
        analysis_service._pop_prediction_persistence(payloads[0])  # noqa: SLF001
    )

    assert not failed
    assert not derivatives_failed
    assert [row["prediction_id"].rsplit(":", 1)[1] for row in rows] == [
        "BASELINE",
        "CANDIDATE",
    ]
    assert stamp_spy == []
    assert clock.calls == 2  # one core instant per arm; no issued instant is read
    for row in rows:
        assert not STAMP_KEYS & set(row)
        assert tc.classify_row(row) == tc.CLASS_V0_LEGACY
    for payload in payloads:
        assert not STAMP_KEYS & _keys_anywhere(payload)


@pytest.mark.parametrize(
    ("clock", "selection", "timeframe"),
    [
        pytest.param((CORE_DONE, HORIZON_END_4H), {}, "4H", id="I3_issued_at_horizon_end"),
        pytest.param(
            (FIXED_NOW - timedelta(seconds=1), ISSUED), {}, "4H", id="I1_core_before_as_of"
        ),
        pytest.param((ISSUED, CORE_DONE), {}, "4H", id="I1_issued_before_core"),
        pytest.param((CORE_DONE, ISSUED), {"provider": "fixture"}, "4H", id="unknown_provider"),
        pytest.param(
            (CORE_DONE, ISSUED), {"data_source": "OKX_PUBLIC"}, "4H", id="I8_venue_mismatch"
        ),
        pytest.param(
            (CORE_DONE, ISSUED),
            {"data_source": "CROSS_PROVIDER", "cross_provider_state": "DATA_CONFLICT"},
            "4H",
            id="I8_cross_provider_not_coherent",
        ),
        pytest.param((CORE_DONE, ISSUED), {}, "1M", id="I9_monthly_timeframe"),
    ],
)
def test_a_row_that_fails_validate_v1_stays_unstamped(
    monkeypatch, stamp_spy, clock, selection, timeframe
) -> None:
    frozen = _Clock(*clock)
    _setup(monkeypatch, frozen, **selection)

    payload, row, _, _ = _analyze(timeframe=timeframe)

    assert len(stamp_spy) == 1
    assert stamp_spy[0]["row"] == row
    assert not STAMP_KEYS & set(row)
    assert tc.classify_row(row) == tc.CLASS_V0_LEGACY
    assert frozen.calls == 2
    assert not STAMP_KEYS & _keys_anywhere(payload)


def test_the_stamp_clock_defaults_to_the_app_clock() -> None:
    assert analysis_service._stamp_clock is utc_now  # noqa: SLF001
