"""DecisionView (plan §14.1-§14.3; owner rulings DP-A and DP-F, 2026-10-05).

These tests prove that:
- the precedence holds: unavailable data first, then no accepted claim; an accepted claim and a
  directional permission are reachable only through their (empty) governed registries, and no
  registry may hold an entry while an acceptance blocker remains (RULING-RESIDUALS=A);
- missing evidence never reads as a market signal;
- the honest DEGRADED (DP-F) fires exactly when the configured primary venue was tried and failed,
  or the venues conflict, and only in the view: data_quality and provider_state are untouched;
- the human route carries the view; the isolated automation analysis never builds it, so
  radar_evidence.v1 keeps every data-quality and provider value;
- the view recomputes nothing: its probabilities, band, costs and evidence are the analysis's own,
  and its times are the target contract's (tc-v1), equal to the prediction row's;
- the human payload validates against the JSON schema.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, RefResolver

from crypto_probability_engine.adapters import provider_selection
from crypto_probability_engine.adapters.provider_selection import ProviderSelectionResult
from crypto_probability_engine.adapters.symbol_universe import (
    ProviderSymbolUniverse,
    clear_symbol_universe_cache,
)
from crypto_probability_engine.adapters.types import ProviderError
from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.automation.contract import (
    RadarEvidenceRequest,
    build_radar_evidence,
)
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.detail import decision_view, frontend_display
from crypto_probability_engine.detail.decision_view import STATE_COPY, build_decision_view
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from tests.fixtures.market_data import make_snapshot

ROOT = Path(__file__).resolve().parents[2]
SKILL = {"verdict": "INSUFFICIENT_EVIDENCE", "n": 0, "observed_directional_rate": None}
METHODOLOGY = analysis_service.METHODOLOGY_VERSION
BUILD_INFO = {
    "schema_version": "build-info.v1",
    "release_id": "UCPE-SYNTHETIC-EXAMPLE-V1",
    "release_label": "SYNTHETIC example: no UCPE release serves this identity",
    "environment": "SYNTHETIC_FIXTURE",
    "source_milestone": "synthetic-example",
    "fingerprint": "UCPE SYNTHETIC EXAMPLE · NOT A RELEASE",
}


def selection(
    *,
    active: str = "okx",
    data_source: str = "OKX_PUBLIC",
    providers: dict | None = None,
    cross_provider_state: str = "UNAVAILABLE",
    provider_status: str = "OK",
    snapshots: list | None = None,
):
    """A live-like selection the analysis cannot tell from a real one (no network)."""

    def select(symbol, timeframe, *, settings):
        del settings
        snapshot = make_snapshot(provider=active, symbol=symbol.display, timeframe=timeframe)
        if snapshots is not None:
            snapshots.append(snapshot)
        return ProviderSelectionResult(
            snapshot=snapshot,
            provider_state={
                "status": provider_status,
                "active_provider": active,
                "cross_provider_state": cross_provider_state,
                "providers": providers if providers is not None else {active: {"status": "OK"}},
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


PRIMARY_ABSENT = {"binance": {"status": "QUARANTINED"}, "okx": {"status": "OK"}}
PROBABILITIES = {
    "horizons": {"H_primary": {"p_up_frac": 0.4, "p_down_frac": 0.35, "p_timeout_frac": 0.25}}
}


@pytest.fixture
def live(monkeypatch: pytest.MonkeyPatch):
    def use(**kwargs):
        monkeypatch.setattr(analysis_service, "select_market_data", selection(**kwargs))
        monkeypatch.setattr(analysis_service, "get_cached_skill_evidence", lambda _tf: dict(SKILL))

    return use


def human(timeframe: str = "1H") -> dict:
    return analysis_service.analyze_request(
        AnalysisRequest(symbol="BTC/USDT", timeframe=timeframe),
        settings=Settings(data_mode="fixture"),
        run_store=InMemoryRunStore(limit=10),
    )


def isolated(timeframe: str = "1H") -> dict:
    return analysis_service.analyze_request_isolated(
        AnalysisRequest(symbol="BTC/USDT", timeframe=timeframe),
        settings=Settings(data_mode="fixture"),
    )


def view_for(**overrides) -> dict:
    """The view of a minimal analysis, built directly."""

    arguments = {
        "timeframe": "1H",
        "methodology_version": METHODOLOGY,
        "snapshot": make_snapshot(provider="binance", symbol="BTC/USDT", timeframe="1H"),
        "data_quality": {"is_live_data": True, "data_source": "BINANCE_PUBLIC"},
        "provider_state": {
            "status": "OK",
            "active_provider": "cross_provider",
            "cross_provider_state": "COHERENT",
            "providers": {"binance": {"status": "OK"}, "okx": {"status": "OK"}},
        },
        "quant_result": {"gate_result": {"hard_blocks": ["SKILL_NOT_DEMONSTRATED"]}},
        "decision_brief": {"probability_type": "UNCALIBRATED_HEURISTIC_6BAR_OUTCOME"},
        "skill_evidence": SKILL,
        "primary_venue": "binance",
    }
    arguments.update(overrides)
    return build_decision_view(**arguments)


# --------------------------------------------------------------------------- the precedence
def test_valid_data_with_no_accepted_claim() -> None:
    view = view_for()
    assert view["state"] == "NO_ACCEPTED_CLAIM"
    assert "data are valid" not in view["detail"], "the data state is the view's data, not this"
    assert view["accepted_claim"] is False and view["directional_permission"] is False
    assert view["data"]["state"] == "OK"
    assert "not a market signal" in view["detail"]
    assert view["evidence"]["limitations"][0].startswith("No forecast-quality claim is accepted")


@pytest.mark.parametrize(
    ("hard_blocks", "provider_state", "reason"),
    [
        (["PROVIDER_DEGRADED"], None, "PROVIDER_UNAVAILABLE"),
        (["EPISTEMIC_VOID"], None, "EVIDENCE_VOID"),
        (
            ["SKILL_NOT_DEMONSTRATED"],
            {"status": "PROVIDER_DEGRADED", "providers": {}},
            "PROVIDER_UNAVAILABLE",
        ),
    ],
    ids=["provider gate", "evidence void", "provider status"],
)
def test_unavailable_data_comes_first(
    hard_blocks: list, provider_state: dict | None, reason: str
) -> None:
    quant = {"gate_result": {"hard_blocks": hard_blocks}, "probability_state": PROBABILITIES}
    overrides = {"provider_state": provider_state} if provider_state is not None else {}
    view = view_for(quant_result=quant, **overrides)
    assert view["state"] == "INVALID_OR_UNAVAILABLE_DATA"
    assert view["data"] == view["data"] | {"state": "UNAVAILABLE", "reason": reason}
    # Precedence 1 shows no range or probability, though the analysis computed them.
    assert view["range"]["assessed"] is False
    assert [view["range"][key] for key in ("in_band_frac", "up_frac", "down_frac")] == [None] * 3
    assert view["range"]["meaning"].startswith("Not assessed")
    # The control: the same probabilities on valid data are shown as the analysis has them.
    valid = view_for(quant_result={**quant, "gate_result": {"hard_blocks": []}})["range"]
    assert valid["assessed"] is True
    assert (valid["in_band_frac"], valid["up_frac"], valid["down_frac"]) == (0.25, 0.4, 0.35)


def test_nothing_is_accepted_today() -> None:
    assert decision_view.ACCEPTED_FORECAST_CLAIMS == frozenset()
    assert decision_view.ACCEPTED_DIRECTIONAL_PERMISSIONS == frozenset()


def test_no_claim_is_reachable_while_an_acceptance_blocker_remains() -> None:
    """Owner ruling RULING-RESIDUALS=A (2026-10-07): the accepted-state ruling's three residuals
    are DEFERRED, not accepted. They are mandatory blockers: neither registry may hold an entry
    while any remains, and a blocker leaves only in the change that resolves it. BACKEND_COPY
    (composition review, 2026-10-10) stands beside them: the backend's own data and copy must
    agree with an acceptance too."""

    names = [blocker.split(":", 1)[0] for blocker in decision_view.ACCEPTANCE_BLOCKERS]
    assert names == ["BANNER", "RELIABILITY_LABEL", "RENDER_TEST", "BACKEND_COPY"]
    if decision_view.ACCEPTANCE_BLOCKERS:
        assert decision_view.ACCEPTED_FORECAST_CLAIMS == frozenset()
        assert decision_view.ACCEPTED_DIRECTIONAL_PERMISSIONS == frozenset()
    # Each blocker names a file that still exists, so it cannot go stale unnoticed.
    for blocker in decision_view.ACCEPTANCE_BLOCKERS:
        path = blocker.split(": ", 1)[1].split(" ", 1)[0].removesuffix("'s")
        assert (ROOT / path).is_file(), blocker


def test_accepted_states_are_reachable_only_through_their_registries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = f"UNCALIBRATED_HEURISTIC_6BAR_OUTCOME:{METHODOLOGY}:1H"
    clear = {"gate_result": {"hard_blocks": []}}
    monkeypatch.setattr(decision_view, "ACCEPTED_DIRECTIONAL_PERMISSIONS", frozenset({key}))
    assert view_for(quant_result=clear)["state"] == "NO_ACCEPTED_CLAIM", "a permission alone"
    monkeypatch.setattr(decision_view, "ACCEPTED_FORECAST_CLAIMS", frozenset({key}))
    assert view_for(quant_result=clear)["state"] == "DIRECTIONAL_PERMISSION"
    assert view_for(quant_result=clear, timeframe="4H")["state"] == "NO_ACCEPTED_CLAIM", "per tf"
    other = view_for(quant_result=clear, methodology_version=f"{METHODOLOGY}-next")
    assert other["state"] == "NO_ACCEPTED_CLAIM", "an acceptance never outlives its model"
    # Hard gates outrank everything shown: any hard block caps a permission at the claim.
    capped = view_for(quant_result={"gate_result": {"hard_blocks": ["LIQUIDITY_NOT_VIABLE"]}})
    assert capped["state"] == "ACCEPTED_FORECAST_CLAIM"
    assert capped["directional_permission"] is False and capped["accepted_claim"] is True
    # Bad data outranks a claim and a permission alike.
    for blocks in (["EPISTEMIC_VOID"], ["PROVIDER_DEGRADED"]):
        blocked = view_for(quant_result={"gate_result": {"hard_blocks": blocks}})
        assert blocked["state"] == "INVALID_OR_UNAVAILABLE_DATA"
        assert blocked["accepted_claim"] is False and blocked["directional_permission"] is False
    monkeypatch.setattr(decision_view, "ACCEPTED_DIRECTIONAL_PERMISSIONS", frozenset())
    claim = view_for(quant_result=clear)
    assert claim["state"] == "ACCEPTED_FORECAST_CLAIM"
    assert claim["accepted_claim"] is True and claim["directional_permission"] is False


def test_the_limitations_say_what_the_evidence_is(monkeypatch: pytest.MonkeyPatch) -> None:
    """Owner ruling 2026-10-06: accepted forecast evidence shows its accepted state (never the
    uncalibrated-heuristic line), an accepted directional permission stays explicitly
    non-advisory, and today's states read exactly as before."""

    uncalibrated = (
        "Uncalibrated heuristic: its accuracy has not been established on resolved outcomes."
    )
    today = view_for()["evidence"]["limitations"]
    assert today == [
        "No forecast-quality claim is accepted for this model and timeframe.",
        uncalibrated,
        "No profitability claim.",
    ]
    key = f"UNCALIBRATED_HEURISTIC_6BAR_OUTCOME:{METHODOLOGY}:1H"
    monkeypatch.setattr(decision_view, "ACCEPTED_FORECAST_CLAIMS", frozenset({key}))
    claim = view_for()["evidence"]["limitations"]  # SKILL_NOT_DEMONSTRATED caps it at the claim
    accepted = "Accepted forecast-quality claim for this model and timeframe."
    assert claim == [accepted, "No profitability claim."]
    monkeypatch.setattr(decision_view, "ACCEPTED_DIRECTIONAL_PERMISSIONS", frozenset({key}))
    permission = view_for(quant_result={"gate_result": {"hard_blocks": []}})
    assert permission["state"] == "DIRECTIONAL_PERMISSION"
    assert permission["evidence"]["limitations"] == [
        accepted,
        "No profitability claim.",
        "The directional permission is not financial advice: it never tells you to trade.",
    ]
    for lines in (claim, permission["evidence"]["limitations"]):
        assert uncalibrated not in lines and "No profitability claim." in lines


def test_the_service_names_its_own_methodology(live, monkeypatch: pytest.MonkeyPatch) -> None:
    """An acceptance made for this methodology applies to this analysis, and to no other."""

    live()
    key = f"UNCALIBRATED_HEURISTIC_6BAR_OUTCOME:{METHODOLOGY}:1H"
    monkeypatch.setattr(decision_view, "ACCEPTED_FORECAST_CLAIMS", frozenset({key}))
    assert human()["decision_view"]["state"] == "ACCEPTED_FORECAST_CLAIM"
    monkeypatch.setattr(decision_view, "ACCEPTED_FORECAST_CLAIMS", frozenset({key + "-next"}))
    assert human()["decision_view"]["state"] == "NO_ACCEPTED_CLAIM"


def test_the_four_states_read_differently() -> None:
    """The owner-task scenarios of plan §23 (UX): each state has its own words."""

    headlines = {state: copy[0] for state, copy in STATE_COPY.items()}
    assert len(set(headlines.values())) == 4
    assert set(headlines) == {
        "INVALID_OR_UNAVAILABLE_DATA",
        "NO_ACCEPTED_CLAIM",
        "ACCEPTED_FORECAST_CLAIM",
        "DIRECTIONAL_PERMISSION",
    }


# --------------------------------------------------------------------------- DP-F: honest DEGRADED
@pytest.mark.parametrize(
    ("data_quality", "provider_state", "expected"),
    [
        (
            {"is_live_data": True, "data_source": "OKX_PUBLIC"},
            {"status": "OK", "active_provider": "okx", "providers": PRIMARY_ABSENT},
            ("DEGRADED", "PRIMARY_VENUE_ABSENT"),
        ),
        (
            {"is_live_data": True, "data_source": "OKX_PUBLIC", "symbol_availability": "OKX_ONLY"},
            {"status": "OK", "active_provider": "okx", "providers": {"okx": {"status": "OK"}}},
            ("OK", None),
        ),
        (
            {"is_live_data": True, "data_source": "OKX_PUBLIC"},
            {
                "status": "OK",
                "active_provider": "okx",
                "providers": {
                    "binance": {
                        "status": "QUARANTINED",
                        "quarantine_reason": "INVALID_SYMBOL: Provider rejected symbol.",
                    },
                    "okx": {"status": "OK"},
                },
            },
            ("OK", None),
        ),
        (
            {"is_live_data": True, "data_source": "BINANCE_PUBLIC"},
            {
                "status": "OK",
                "active_provider": "binance",
                "providers": {"binance": {"status": "OK"}, "okx": {"status": "QUARANTINED"}},
            },
            ("OK", None),
        ),
        (
            {
                "is_live_data": True,
                "data_source": "BINANCE_PUBLIC",
                "cross_provider_state": "DATA_CONFLICT",
            },
            {"status": "DEGRADED", "active_provider": "binance", "providers": {}},
            ("DEGRADED", "CROSS_PROVIDER_CONFLICT"),
        ),
        (
            {"is_live_data": False, "data_source": "FIXTURE_DEMO"},
            {"status": "OK", "active_provider": "fixture", "providers": {"fixture": {}}},
            ("DEMO", None),
        ),
    ],
    ids=[
        "primary failed",
        "primary lists no such symbol",
        "primary rejects the symbol",
        "secondary failed",
        "conflict",
        "demo",
    ],
)
def test_the_data_state(data_quality: dict, provider_state: dict, expected: tuple) -> None:
    data = view_for(data_quality=data_quality, provider_state=provider_state)["data"]
    assert (data["state"], data["reason"]) == expected
    assert data["primary_venue"] == "binance"


def test_dp_f_degraded_is_in_the_human_view_only_and_the_radar_keeps_its_values(live) -> None:
    live(providers=PRIMARY_ABSENT)
    payload = human()
    assert payload["decision_view"]["data"]["state"] == "DEGRADED"
    assert payload["decision_view"]["data"]["reason"] == "PRIMARY_VENUE_ABSENT"
    # The analysis's own data quality and provider state are what they were.
    assert payload["data_quality"]["status"] == "OK"
    assert payload["provider_state"]["status"] == "OK"
    automated = isolated()
    assert "decision_view" not in automated
    body = build_radar_evidence(
        automated,
        request=RadarEvidenceRequest(
            "BTC/USDT", "1H", "0b6f2a1c-3d4e-4f5a-8b6c-7d8e9f0a1b2c", 30000
        ),
        build_info=BUILD_INFO,
        issued_at_utc="2026-10-05T00:00:03Z",
    )
    assert body["data_quality"] == {
        "status": "OK",
        "is_live_data": True,
        "data_source": "OKX_PUBLIC",
        "cross_provider_state": "UNAVAILABLE",
    }
    assert "DEGRADED" not in json.dumps(body) and "decision_view" not in json.dumps(body)


def test_the_automation_analysis_never_builds_a_view(live, monkeypatch: pytest.MonkeyPatch) -> None:
    live()

    def refuse(**_: object) -> dict:
        raise AssertionError("the automation analysis must not build a DecisionView")

    monkeypatch.setattr(analysis_service, "build_decision_view", refuse)
    assert "decision_view" not in isolated()
    with pytest.raises(AssertionError, match="must not build"):
        human()


# --------------------------------------------------------------------------- the analysis's values
def test_the_view_reads_the_analysis_and_recomputes_nothing(live) -> None:
    live()
    payload = human()
    view = payload["decision_view"]
    horizon = payload["probability_state"]["horizons"]["H_primary"]
    execution = payload["execution_realism"]
    assert view["range"]["assessed"] is True
    assert view["range"]["in_band_frac"] == horizon["p_timeout_frac"]
    assert view["range"]["up_frac"] == horizon["p_up_frac"]
    assert view["range"]["down_frac"] == horizon["p_down_frac"]
    assert view["range"]["decision_band_frac"] == execution["round_trip_cost_frac"]
    assert view["cost"]["round_trip_cost_frac"] == execution["round_trip_cost_frac"]
    assert view["cost"]["taker_fee_frac"] == execution["taker_fee_frac"]
    assert view["cost"]["slippage_frac"] == execution["slippage_frac"]
    brief = payload["decision_brief"]
    assert view["range"]["evidence_level"] == brief["probability_type"]
    for key in ("model_readiness", "calibration_status", "reliability_status"):
        assert view["evidence"][key] == brief[key]
    assert view["evidence"]["skill_verdict"] == "INSUFFICIENT_EVIDENCE"
    assert view["evidence"]["profitability_claim"] is False


def test_the_times_are_the_target_contracts(live, monkeypatch: pytest.MonkeyPatch) -> None:
    snapshots: list = []
    monkeypatch.setattr(analysis_service, "select_market_data", selection(snapshots=snapshots))
    monkeypatch.setattr(analysis_service, "get_cached_skill_evidence", lambda _tf: dict(SKILL))
    payload = human("4H")
    row = analysis_service._prediction_row(
        run_id=payload["run_id"],
        request_symbol="BTC/USDT",
        normalized_symbol=payload["normalized_symbol"],
        timeframe="4H",
        snapshot=snapshots[0],
        quant_result={
            key: payload[key]
            for key in (
                "probability_state",
                "execution_realism",
                "calibration_state",
                "gate_result",
            )
        },
        data_quality=payload["data_quality"],
        provider_state=payload["provider_state"],
    )
    assert row is not None
    time = payload["decision_view"]["time"]
    assert time["reference_close_utc"] == row["reference_close_utc"]
    assert time["horizon_end_utc"] == row["horizon_end_utc"]
    assert time["horizon_bars"] == row["horizon_bars"] == 6
    assert time["as_of_utc"] == payload["as_of_utc"] and time["close_anchored"] is True


def test_the_hold_withholds_the_legacy_verdict() -> None:
    held = view_for(
        quant_result={
            "gate_result": {
                "hard_blocks": ["SKILL_NOT_DEMONSTRATED"],
                "directional_evidence_hold": {"active": True, "hold_reason": "H2"},
            }
        },
        skill_evidence={
            "verdict": "SKILL_DEMONSTRATED",
            "n": 150,
            "observed_directional_rate": 0.58,
        },
    )
    evidence = held["evidence"]
    assert evidence["skill_verdict"] is None and evidence["resolved_outcomes"] is None
    assert evidence["directional_evidence_hold"] is True
    assert any("hold is active" in line for line in evidence["limitations"])


@pytest.mark.parametrize("active", [True, 1, "yes", False, 0, None, ""])
def test_the_view_and_the_card_agree_on_the_hold(active: object) -> None:
    gate = {
        "hard_blocks": ["SKILL_NOT_DEMONSTRATED"],
        "directional_evidence_hold": {"active": active, "hold_reason": "H2"},
    }
    legacy = {"verdict": "SKILL_DEMONSTRATED", "n": 150, "observed_directional_rate": 0.58}
    view = view_for(quant_result={"gate_result": gate}, skill_evidence=legacy)
    (reason,) = frontend_display._blocking_reasons(gate, legacy)  # noqa: SLF001
    card_holds = reason["headline"] == frontend_display._DIRECTIONAL_EVIDENCE_HOLD_HEADLINE  # noqa: SLF001
    assert view["evidence"]["directional_evidence_hold"] is card_holds
    assert (view["evidence"]["skill_verdict"] is None) is card_holds
    assert card_holds is bool(active)


def test_the_human_payload_validates_against_the_schema(live) -> None:
    live(providers=PRIMARY_ABSENT)
    payload = human()
    load = lambda name: json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))  # noqa: E731
    schema = load("response.schema.json")
    store = {
        name: load(name)
        for name in ("quant.schema.json", "news.schema.json", "detail_view.schema.json")
    }
    Draft202012Validator(schema, resolver=RefResolver.from_schema(schema, store=store)).validate(
        payload
    )


# --------------------------------------------------------------------------- review 2 of lane P
class Venue:
    """A venue for the real selection path, offline: its listing and its candles, up or down."""

    def __init__(
        self,
        name: str,
        *,
        listing: frozenset[str] | None = frozenset({"BTC/USDT"}),
        candles_fail: str | None = None,
    ) -> None:
        self.name = name
        self.listing = listing  # None: even the listing call fails
        self.candles_fail = candles_fail

    def fetch_symbol_universe(self) -> ProviderSymbolUniverse:
        if self.listing is None:
            raise ProviderError(
                "PROVIDER_DEGRADED", "Provider public request failed.", provider=self.name
            )
        return ProviderSymbolUniverse(provider=self.name, symbols=self.listing)

    def fetch_market_snapshot(self, symbol, timeframe: str):
        if self.candles_fail:
            raise ProviderError(self.candles_fail, "venue failure", provider=self.name)
        return make_snapshot(provider=self.name, symbol=symbol.display, timeframe=timeframe)


LIVE = Settings(
    data_mode="live",
    provider_priority=("binance", "okx"),
    candle_cache_ttl_seconds=0,
    symbol_universe_cache_ttl_seconds=0,
)
UNREADABLE = None


@pytest.mark.parametrize(
    ("binance", "okx", "expected"),
    [
        (Venue("binance"), Venue("okx"), ("OK", None)),
        (
            Venue("binance", candles_fail="PROVIDER_DEGRADED"),
            Venue("okx"),
            ("DEGRADED", "PRIMARY_VENUE_ABSENT"),
        ),
        (
            Venue("binance", listing=UNREADABLE, candles_fail="PROVIDER_DEGRADED"),
            Venue("okx"),
            ("DEGRADED", "PRIMARY_VENUE_ABSENT"),
        ),
        (Venue("binance", listing=frozenset({"ETH/USDT"})), Venue("okx"), ("OK", None)),
        (
            Venue("binance", listing=UNREADABLE, candles_fail="INVALID_SYMBOL"),
            Venue("okx", listing=UNREADABLE),
            ("OK", None),
        ),
        (
            Venue("binance", listing=UNREADABLE, candles_fail="PROVIDER_DEGRADED"),
            Venue("okx", listing=UNREADABLE),
            ("DEGRADED", "PRIMARY_VENUE_ABSENT"),
        ),
    ],
    ids=[
        "both up",
        "primary refuses, its listing read",
        "primary unreachable, its listing too",
        "primary does not list the symbol",
        "no listing readable, primary rejects the symbol",
        "no listing readable, primary down",
    ],
)
def test_dp_f_through_the_real_selection_path(
    monkeypatch: pytest.MonkeyPatch, binance: Venue, okx: Venue, expected: tuple
) -> None:
    """The same outage reads the same, whether or not the primary's listing could be read (review 2
    of lane P, finding 1); the analysis's own data_quality and provider_state stay as they were."""

    clear_symbol_universe_cache()
    provider_selection.clear_provider_cache()

    def select(symbol, timeframe, *, settings):
        del settings
        return provider_selection.select_market_data(
            symbol, timeframe, settings=LIVE, providers=[binance, okx]
        )

    monkeypatch.setattr(analysis_service, "select_market_data", select)
    monkeypatch.setattr(analysis_service, "get_cached_skill_evidence", lambda _tf: dict(SKILL))
    try:
        payload = human()
    finally:
        clear_symbol_universe_cache()
        provider_selection.clear_provider_cache()
    data = payload["decision_view"]["data"]
    assert (data["state"], data["reason"]) == expected
    assert payload["data_quality"]["status"] == "OK"
    assert payload["provider_state"]["status"] == "OK"
    analysis_service._pop_prediction_persistence(payload)  # noqa: SLF001 - clean up


def test_the_horizon_ends_six_bars_after_the_reference_close_not_after_as_of() -> None:
    snapshot = make_snapshot(provider="binance", symbol="BTC/USDT", timeframe="1H")
    late = replace(snapshot, as_of_utc=snapshot.as_of_utc + timedelta(minutes=7))
    time = view_for(snapshot=late)["time"]

    def z(value: datetime) -> str:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    close = snapshot.candles[-1].close_time_utc
    assert time["reference_close_utc"] == z(close)
    assert time["horizon_end_utc"] == z(close + timedelta(hours=6))
    assert time["as_of_utc"] == z(late.as_of_utc) != time["reference_close_utc"]
