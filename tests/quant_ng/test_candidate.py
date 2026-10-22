"""Synthetic-only contracts for the dormant C1 candidate adapter."""

from __future__ import annotations

import hashlib
import json
import random
from datetime import UTC, datetime, timedelta

import pytest

from crypto_probability_engine.adapters.types import MarketCandle
from crypto_probability_engine.quant import candidate_r4_c1 as c1
from crypto_probability_engine.quant_ng import artifact, candidate, windows


def _constants() -> dict:
    cells = {}
    for timeframe in ("15m", "1H"):
        coefficients = [-6.0] + [0.01] * (len(c1.HAR_FEATURES[timeframe]) + 1)
        cells.setdefault("BTC/USDT", {})[timeframe] = {
            "coefficients": coefficients,
            "profile": [1.0 + i * 0.001 for i in range(48)],
            "knots": [float(i) / 10 for i in range(-50, 51)],
            "sample_size": 1000,
        }
    return {"candidate": c1.CANDIDATE_NAME, "recipe_sha256": c1.RECIPE_SHA256,
            "cells": cells}


def _manifest(timeframe: str = "15m", *, symbol: str = "BTC/USDT",
              venue: str = "BINANCE_PUBLIC", low: float = 0.001, high: float = 0.2,
              central_quantile: float = 0.9, constants: dict | None = None):
    payload = {
        "schema_version": artifact.SCHEMA_VERSION, "artifact_id": "synthetic-c1",
        "recipe_id": c1.CANDIDATE_NAME, "recipe_sha256": c1.RECIPE_SHA256,
        "symbol": symbol, "venue": venue, "timeframe": timeframe,
        "horizon_bars": c1.HORIZON_BARS,
        "training_start_utc": "2024-01-01T00:00:00Z",
        "training_end_utc": "2025-01-01T00:00:00Z", "band_low": low,
        "band_high": high, "staleness_cap_days": 30,
        "fitted_at_utc": "2025-01-02T00:00:00Z", "fit_code_sha256": "1" * 64,
        "corpus_manifest_sha256": "2" * 64, "central_quantile": central_quantile,
        "exposures": [symbol], "custody_location": "synthetic fixture",
        "independent_copy": "NONE_PENDING_OWNER_CUSTODY_RULING",
        "freeze_anchor_kind": "NONE", "freeze_anchor_ref": None, "freeze_anchor_utc": None,
        "constants": _constants() if constants is None else constants,
    }
    return artifact.load_manifest(payload)


def _window(timeframe: str = "15m", *, provider: str = "binance",
            symbol: str = "BTC/USDT") -> windows.Window:
    count = c1.REQUIRED_CANDLES[timeframe]
    seconds = c1.BAR_SECONDS[timeframe]
    start = datetime(2025, 1, 1, tzinfo=UTC)
    candles = []
    close = 100.0
    for index in range(count):
        opened = start + timedelta(seconds=index * seconds)
        close *= 1.0 + (0.0002 if index % 2 else -0.0001)
        candles.append(MarketCandle(opened, opened + timedelta(seconds=seconds),
                                    close, close * 1.002, close * 0.998, close, 1.0))
    return windows.Window(provider, symbol, timeframe, tuple(candles),
                          windows.WindowSource.SNAPSHOT, 0)


@pytest.mark.parametrize("timeframe", ("15m", "1H"))
def test_candidate_bit_exact_parity(timeframe: str) -> None:
    rng = random.Random(924_000 + c1.BAR_SECONDS[timeframe])
    win = _window(timeframe)
    manifest = _manifest(timeframe)
    now = datetime(2025, 1, 10, tzinfo=UTC)
    cells = c1.validate_constants(manifest.constants)
    cases = 0
    for _ in range(100):
        band = rng.choice((0.001, 0.005, 0.01, 0.03, 0.08))
        result = c1.compute_r4_c1_probabilities(
            win.candles, symbol="BTC/USDT", timeframe=timeframe,
            band_frac=band, constants=cells,
        )
        actual = candidate.compute_candidate(win, manifest=manifest, now_utc=now,
                                             band_frac=band)
        assert actual.p_up_frac == result.p_up_frac
        assert actual.p_down_frac == result.p_down_frac
        assert actual.p_timeout_frac == result.p_timeout_frac
        assert actual.sigma_h == result.sigma_h
        assert actual.profile_mean == result.profile_mean
        assert actual.central_half_width_frac == result.central_range_half_width_frac
        cases += 1
    assert cases >= 100


def test_central_half_width_grid_interpolation_and_domain() -> None:
    knots = tuple(float(i) / 10 for i in range(-50, 51))
    assert candidate.central_half_width(knots, 1000, 0.1, 0.9) == knots[90] * 0.1
    q = 0.905
    z = knots[90] + 0.5 * (knots[91] - knots[90])
    assert candidate.central_half_width(knots, 1000, 0.1, q) == z * 0.1
    for q_bad in (0.5, 1.0, float("nan"), True):
        with pytest.raises(ValueError):
            candidate.central_half_width(knots, 1000, 0.1, q_bad)
    with pytest.raises(candidate.CandidateUnavailable) as error:
        candidate.central_half_width(knots, 9, 0.1, 0.95)
    assert error.value.reason is candidate.CandidateUnavailableReason.CENTRAL_QUANTILE_OUT_OF_TABLE
    assert candidate.central_half_width(knots, 9, 0.1, 0.9) > 0
    with pytest.raises(candidate.CandidateUnavailable) as error:
        candidate.central_half_width(knots, 1000, 2.0, 0.9)
    assert error.value.reason is candidate.CandidateUnavailableReason.CENTRAL_RANGE_DOMAIN


def test_sigma_guard_threshold() -> None:
    knots = (-2.0, 0.0, 2.0)
    with pytest.raises(candidate.CandidateUnavailable) as error:
        candidate.sigma_guard(knots, 0.5)
    assert error.value.reason is candidate.CandidateUnavailableReason.SIGMA_GUARD
    candidate.sigma_guard(knots, 0.499999)


def test_manifest_status_mapping_and_zero_probability_contract() -> None:
    win, manifest = _window(), _manifest()
    now = datetime(2025, 1, 10, tzinfo=UTC)
    sweep = [candidate.compute_candidate(win, manifest=manifest, now_utc=now, band_frac=b)
             for b in (0.001, 0.01, 0.05, 0.1, 0.2)]
    assert all(item.p_up_frac >= 1 / 1001 and item.p_down_frac >= 1 / 1001 for item in sweep)
    zero = c1.compute_r4_c1_probabilities(
        win.candles, symbol="BTC/USDT", timeframe="15m", band_frac=0.0,
        constants=c1.validate_constants(manifest.constants),
    )
    assert zero.p_timeout_frac == 0.0
    cases = [
        (_window(), manifest, datetime(2025, 3, 5, tzinfo=UTC), 0.01,
         candidate.CandidateUnavailableReason.ARTIFACT_STALE),
        (_window(), manifest, now, 0.3,
         candidate.CandidateUnavailableReason.BAND_OUT_OF_RANGE),
        (_window(symbol="ETH/USDT"), manifest, now, 0.01,
         candidate.CandidateUnavailableReason.CELL_MISMATCH),
        (_window(provider="kraken"), manifest, now, 0.01,
         candidate.CandidateUnavailableReason.VENUE_UNKNOWN),
        (_window(provider="okx"), manifest, now, 0.01,
         candidate.CandidateUnavailableReason.CELL_MISMATCH),
    ]
    for window, artifact_manifest, instant, band, reason in cases:
        with pytest.raises(candidate.CandidateUnavailable) as error:
            candidate.compute_candidate(window, manifest=artifact_manifest,
                                        now_utc=instant, band_frac=band)
        assert error.value.reason is reason


def test_compute_candidate_public_guards_and_manifest_quantile() -> None:
    now = datetime(2025, 1, 10, tzinfo=UTC)
    win = _window()
    manifest = _manifest()

    unsafe_constants = _constants()
    unsafe_constants["cells"]["BTC/USDT"]["15m"]["coefficients"][0] = 10.0
    unsafe_manifest = _manifest(constants=unsafe_constants)
    with pytest.raises(candidate.CandidateUnavailable) as error:
        candidate.compute_candidate(win, manifest=unsafe_manifest, now_utc=now, band_frac=0.01)
    assert error.value.reason is candidate.CandidateUnavailableReason.SIGMA_GUARD

    quantile_manifest = _manifest(central_quantile=0.85)
    result = candidate.compute_candidate(win, manifest=quantile_manifest,
                                         now_utc=now, band_frac=0.01)
    cell = c1.validate_constants(quantile_manifest.constants)[("BTC/USDT", "15m")]
    expected = candidate.central_half_width(cell.knots, cell.sample_size,
                                             result.sigma_h, 0.85)
    standard = candidate.central_half_width(cell.knots, cell.sample_size,
                                             result.sigma_h, 0.90)
    assert result.central_half_width_frac == expected
    assert result.central_half_width_frac != standard

    short = windows.Window(win.provider, win.normalized_symbol, win.timeframe,
                           win.candles[:-1], win.source, win.requests)
    with pytest.raises(candidate.CandidateUnavailable) as error:
        candidate.compute_candidate(short, manifest=manifest, now_utc=now, band_frac=0.01)
    assert error.value.reason is candidate.CandidateUnavailableReason.WINDOW_UNAVAILABLE

    for band in (float("nan"), float("inf"), True, -0.01):
        with pytest.raises(candidate.CandidateUnavailable) as error:
            candidate.compute_candidate(win, manifest=manifest, now_utc=now, band_frac=band)
        assert error.value.reason is candidate.CandidateUnavailableReason.BAND_OUT_OF_RANGE


def test_varied_candidate_bit_exact_parity_distinct_cases() -> None:
    rng = random.Random(926_000)
    now = datetime(2025, 1, 10, tzinfo=UTC)
    seen: set[str] = set()
    for timeframe in ("15m", "1H"):
        for _ in range(100):
            base = _constants()
            cell_payload = base["cells"]["BTC/USDT"][timeframe]
            count = c1.REQUIRED_CANDLES[timeframe]
            seconds = c1.BAR_SECONDS[timeframe]
            start = datetime(2025, 1, 1, tzinfo=UTC)
            candles = []
            close = rng.uniform(60.0, 140.0)
            for index in range(count):
                opened = start + timedelta(seconds=index * seconds)
                close *= 1.0 + rng.uniform(-0.0015, 0.0015)
                high = close * (1.0 + rng.uniform(0.0001, 0.004))
                low = close * (1.0 - rng.uniform(0.0001, 0.004))
                candles.append(MarketCandle(opened, opened + timedelta(seconds=seconds),
                                            close, high, low, close, 1.0))
            win = windows.Window("binance", "BTC/USDT", timeframe, tuple(candles),
                                 windows.WindowSource.SNAPSHOT, 0)
            coefficients = [rng.uniform(-0.015, 0.015)
                            for _ in range(len(c1.HAR_FEATURES[timeframe]) + 2)]
            coefficients[0] = rng.uniform(-5.5, -3.5)
            cell_payload["coefficients"] = coefficients
            cell_payload["profile"] = [rng.uniform(0.2, 2.0) for _ in range(48)]
            positive = sorted(rng.uniform(0.001, 0.9) for _ in range(50))
            cell_payload["knots"] = [-value for value in reversed(positive)] + [0.0] + positive
            cell_payload["sample_size"] = rng.randint(50, 5000)
            band = rng.uniform(0.001, 0.2)
            digest = hashlib.sha256(json.dumps(
                {"timeframe": timeframe, "candles": [
                    [c.open_time_utc.isoformat(), c.close_time_utc.isoformat(),
                     c.open, c.high, c.low, c.close] for c in candles],
                 "constants": base, "band": band}, sort_keys=True,
            ).encode()).hexdigest()
            seen.add(digest)
            manifest = _manifest(timeframe, constants=base)
            expected = c1.compute_r4_c1_probabilities(
                win.candles, symbol="BTC/USDT", timeframe=timeframe,
                band_frac=band, constants=c1.validate_constants(manifest.constants),
            )
            actual = candidate.compute_candidate(win, manifest=manifest,
                                                 now_utc=now, band_frac=band)
            assert actual.p_up_frac == expected.p_up_frac
            assert actual.p_down_frac == expected.p_down_frac
            assert actual.p_timeout_frac == expected.p_timeout_frac
            assert actual.sigma_h == expected.sigma_h
            assert actual.profile_mean == expected.profile_mean
            assert actual.central_half_width_frac == expected.central_range_half_width_frac
    assert len(seen) >= 200
