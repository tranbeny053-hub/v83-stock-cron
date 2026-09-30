"""An unstamped (v0) row with a venue data_source, which is every legacy row, resolves exactly as
resolver-v2a did: the same provider window, reason, error and outcome values, with only
resolver_version changed. The reference is resolver-v2a's _evaluate_outcome_row and helpers as
merged in #132 (scripts/resolve_outcomes.py at b11a8e53), copied verbatim. They run over the
existing fixtures of test_resolve_outcomes.py and test_resolver_selection_budget.py, in both row
shapes: the pinned query's, and Route C's, which adds the four stamp columns as NULL."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from math import isfinite

import pytest

from crypto_probability_engine.adapters.types import MarketCandle, ProviderError
from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A, TIMEFRAME_SECONDS
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.targets.contract_v1 import STAMP_FIELDS
from scripts import resolve_outcomes as ro
from tests.resolver import test_resolve_outcomes as v2a_tests
from tests.resolver import test_resolver_selection_budget as n2_tests

V2A_VERSION = "resolver-v2a-exact-eligibility"
SETTINGS = Settings()


# --------------------------------------------------------------------------- resolver-v2a


def _v2a_evaluate(prediction, *, now_utc, settings, fetch_candles, progress):
    """resolver-v2a's _evaluate_outcome_row, verbatim but for the module prefix."""

    source = prediction.get("data_source")
    if not isinstance(source, str) or source not in ro.EXACT_SOURCE_PROVIDERS:
        return None, "skip_ineligible"
    timeframe = prediction.get("timeframe")
    if not isinstance(timeframe, str) or timeframe not in ro.EXACT_TIMEFRAMES:
        return None, "skip_ineligible"
    reference_close_utc = _parse_utc(prediction["reference_close_utc"])
    reference_price = float(prediction["reference_price"])
    horizon_end_utc = _parse_utc(prediction["horizon_end_utc"])
    if not isfinite(reference_price) or reference_price <= 0.0:
        return None, "skip_invalid_target"
    interval = timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
    span = horizon_end_utc - reference_close_utc
    if span <= timedelta(0) or span % interval != timedelta(0):
        return None, "skip_invalid_target"
    bars = span // interval
    if bars > ro.MAX_WINDOW_BARS:
        return None, "skip_invalid_target"
    if prediction.get("horizon_bars") is not None:
        try:
            if int(prediction["horizon_bars"]) != bars:
                return None, "skip_invalid_target"
        except (TypeError, ValueError, OverflowError):
            return None, "skip_invalid_target"
    now = _coerce_utc(now_utc)
    if now <= horizon_end_utc:
        return None, "skip_not_due"
    window = ro.CandleWindow(
        provider=ro.EXACT_SOURCE_PROVIDERS[source],
        data_source=source,
        normalized_symbol=str(prediction["normalized_symbol"]),
        timeframe=timeframe,
        first_open_utc=reference_close_utc,
        terminal_open_utc=horizon_end_utc - interval,
        terminal_close_utc=horizon_end_utc,
        bars=bars,
        now_utc=now,
    )
    progress.stage = "fetch"
    candles = fetch_candles(window, settings)
    progress.stage = "candles"
    by_close: dict[datetime, MarketCandle] = {}
    for candle in candles:
        close = _coerce_utc(candle.close_time_utc)
        if not reference_close_utc < close <= horizon_end_utc:
            continue
        open_time = _coerce_utc(candle.open_time_utc)
        if close - open_time != interval:
            raise ValueError("resolver candle does not span exactly one bar")
        if close in by_close and by_close[close] != candle:
            raise ValueError("conflicting duplicate candles in resolver window")
        by_close[close] = candle
    outcome_candle = by_close.get(horizon_end_utc)
    if outcome_candle is None:
        return None, "skip_terminal_bar_missing"
    progress.stage = "build"
    observed = [by_close[close] for close in sorted(by_close)]
    terminal_return_frac = (float(outcome_candle.close) - reference_price) / reference_price
    decision_band_frac = _decision_band(prediction)
    return {
        "prediction_id": str(prediction["prediction_id"]),
        "resolved_at_utc": _iso_utc(now_utc),
        "outcome_close_utc": _iso_utc(horizon_end_utc),
        "outcome_reference_price": float(outcome_candle.close),
        "terminal_return_frac": terminal_return_frac,
        "realized_label": _realized_label(terminal_return_frac, decision_band_frac),
        "decision_band_frac": decision_band_frac,
        "max_favorable_frac": (max(float(candle.high) for candle in observed) - reference_price)
        / reference_price,
        "max_adverse_frac": (min(float(candle.low) for candle in observed) - reference_price)
        / reference_price,
        "candles_observed": len(observed),
        "resolver_version": V2A_VERSION,
        "data_source": window.data_source,
        "is_live_data": True,
    }, None


def _decision_band(prediction):
    value = prediction.get("decision_band_frac")
    try:
        band = float(value)
    except (TypeError, ValueError):
        band = 0.0
    if band <= 0.0:
        return 2.0 * DEFAULT_PHASE1A.taker_fee_frac
    return band


def _realized_label(terminal_return_frac, decision_band_frac):
    if terminal_return_frac > decision_band_frac:
        return "UP"
    if terminal_return_frac < -decision_band_frac:
        return "DOWN"
    return "TIMEOUT"


def _parse_utc(value):
    if isinstance(value, datetime):
        return _coerce_utc(value)
    return _coerce_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))


def _coerce_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso_utc(value):
    return _coerce_utc(value).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------- the fixtures


def _params(test, name):
    """The values a parametrized test of the existing modules runs with."""

    (values,) = [mark.args[1] for mark in test.pytestmark if mark.args[0] == name]
    return list(values)


def _without(row, key, value):
    changed = deepcopy(row)
    if value is v2a_tests.MISSING:
        del changed[key]
    else:
        changed[key] = value
    return changed


def _fixture_rows():
    base = v2a_tests._prediction()
    rows = {"prediction": base}
    for venue in ro.EXACT_SOURCE_PROVIDERS:
        for timeframe in sorted(ro.EXACT_TIMEFRAMES):
            row = {**v2a_tests._prediction_for_timeframe(timeframe), "data_source": venue}
            rows[f"{venue}-{timeframe}"] = row
    for index, source in enumerate(
        _params(v2a_tests.test_ambiguous_source_skips_without_fetch_or_save, "source")
    ):
        rows[f"source-{index}"] = _without(base, "data_source", source)
    for index, updates in enumerate(
        _params(v2a_tests.test_malformed_target_skips_before_fetch, "updates")
    ):
        rows[f"malformed-{index}"] = {**base, **updates}
    for field in _params(
        v2a_tests.test_parse_errors_propagate_and_count_failed_without_fetch, "field"
    ):
        rows[f"unreadable-{field}"] = {**base, field: "invalid"}
    for index, bars in enumerate(
        _params(v2a_tests.test_maximum_window_and_optional_horizon_bars, "horizon_bars")
    ):
        row = {**base, "horizon_end_utc": "2026-06-23T00:00:00Z"}
        rows[f"window-{index}"] = _without(row, "horizon_bars", bars)
    rows["band-missing"] = {**base, "decision_band_frac": None}
    rows["golden"] = n2_tests._row("golden")
    for index, (_, overrides, _, _, _) in enumerate(n2_tests.REASON_CASES):
        rows[f"n2-{index}"] = n2_tests._row("r", **overrides)
    return rows


def _window_candles(window):
    """Every bar of the window, one past it, one before it; OHLC vary per bar."""

    interval = window.terminal_close_utc - window.terminal_open_utc
    return tuple(
        MarketCandle(
            open_time_utc=window.first_open_utc + (k - 1) * interval,
            close_time_utc=window.first_open_utc + k * interval,
            open=100.0,
            high=100.0 + k + 1,
            low=100.0 - k,
            close=100.0 + 0.25 * k * (-1) ** k,
            volume=1.0,
        )
        for k in range(0, window.bars + 2)
    )


def _duplicate(window):
    candles = _window_candles(window)
    return (*candles, replace(candles[-2], close=55.0))


BEHAVIOURS = {
    "terminal-only": lambda window: v2a_tests._terminal_candles(window, SETTINGS),
    "whole-window": _window_candles,
    "golden": n2_tests._golden_window,
    "terminal-missing": lambda window: _window_candles(window)[:-2],
    "conflicting-duplicate": _duplicate,
    "provider-rejected": n2_tests._raising(ProviderError("INVALID_SYMBOL", "x", provider="okx")),
    "provider-unavailable": n2_tests._raising(
        ProviderError("PROVIDER_DEGRADED", "x", provider="binance")
    ),
}
ROWS = _fixture_rows()
NOWS = {
    "due": datetime(2026, 7, 1, tzinfo=UTC),
    "just-due": datetime(2026, 6, 8, 0, 0, 0, 1, tzinfo=UTC),
    "n2": n2_tests.NOW,
}


def _evaluate(evaluate, prediction, behaviour, now):
    windows = []

    def fetch_candles(window, settings):
        windows.append(window)
        return behaviour(window)

    progress = ro._Progress()
    try:
        outcome, reason = evaluate(
            deepcopy(prediction),
            now_utc=now,
            settings=SETTINGS,
            fetch_candles=fetch_candles,
            progress=progress,
        )
    except Exception as exc:
        return windows, ("raised", type(exc), str(exc), ro._error_reason(exc, progress.stage))
    return windows, ("returned", outcome, reason)


# --------------------------------------------------------------------------- the equivalence


@pytest.mark.parametrize("name", sorted(ROWS))
def test_a_v0_row_resolves_exactly_as_resolver_v2a_did(name) -> None:
    """Every provider behaviour, run time and row shape; only resolver_version may differ."""

    for shape in ("pinned-query", "route-c-scan"):
        prediction = ROWS[name]
        if shape == "route-c-scan":
            prediction = {**prediction, **dict.fromkeys(STAMP_FIELDS)}
        for behaviour_name, behaviour in BEHAVIOURS.items():
            for now_name, now in NOWS.items():
                case = (shape, behaviour_name, now_name)
                old_windows, old = _evaluate(_v2a_evaluate, prediction, behaviour, now)
                new_windows, new = _evaluate(ro._evaluate_outcome_row, prediction, behaviour, now)

                assert new_windows == old_windows, case
                if old[0] == "raised" or old[1] is None:
                    assert new == old, case
                    continue
                assert old[1]["resolver_version"] == V2A_VERSION, case
                expected = {**old[1], "resolver_version": ro.RESOLVER_VERSION}
                assert new == ("returned", expected, None), case


def test_the_matrix_reaches_every_outcome_path() -> None:
    """The comparison above is not vacuous: it resolves rows, skips them for every v2a reason,
    and meets every error class that v2a could raise before or after the provider call."""

    returned, raised = set(), set()
    for prediction in ROWS.values():
        for behaviour in BEHAVIOURS.values():
            for now in NOWS.values():
                _, result = _evaluate(_v2a_evaluate, prediction, behaviour, now)
                if result[0] == "raised":
                    raised.add(result[3])
                else:
                    returned.add("resolved" if result[1] is not None else result[2])
    assert returned == {
        "resolved",
        "skip_ineligible",
        "skip_invalid_target",
        "skip_not_due",
        "skip_terminal_bar_missing",
    }
    assert raised == {
        "error_row_unreadable",
        "error_provider_rejected",
        "error_provider_unavailable",
        "error_candle_invalid",
    }


@pytest.mark.parametrize("row", [None, "not-a-row", 7, ["prediction_id"]])
def test_a_row_that_is_not_a_mapping_is_still_unreadable(row) -> None:
    for evaluate in (_v2a_evaluate, ro._evaluate_outcome_row):
        _, result = _evaluate(evaluate, row, BEHAVIOURS["terminal-only"], NOWS["due"])
        assert result[0] == "raised" and result[3] == "error_row_unreadable"
