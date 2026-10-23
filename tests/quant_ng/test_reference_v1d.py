"""Synthetic tests for the dormant, development-only 1D reference v1d."""

from __future__ import annotations

import copy
import hashlib
import importlib
import io
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from crypto_probability_engine.adapters.types import MarketCandle
from crypto_probability_engine.quant_ng.reference import (
    Anchor,
    Label,
    ReferenceNotFrozenError,
    ReferenceUnavailable,
    ReferenceUnavailableReason,
)
from crypto_probability_engine.quant_ng.reference_v1d import (
    REFERENCE_SPEC_V1D_SHA256,
    ReferenceSpecV1d,
    anchors_from_candles_v1d,
    compute_reference_v1d,
    load_reference_spec_v1d,
    reference_from_anchors_v1d,
)
from crypto_probability_engine.quant_ng.windows import UnavailableReason as WindowUnavailableReason
from crypto_probability_engine.quant_ng.windows import WindowUnavailable

ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = ROOT / "ops/quant_ng/REFERENCE_SPEC_v1d.json"
SPEC_PAYLOAD = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
SPEC = load_reference_spec_v1d(SPEC_PAYLOAD)


def test_spec_hash_values_and_n0_derivation() -> None:
    raw = SPEC_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == REFERENCE_SPEC_V1D_SHA256
    assert dict(SPEC.bar_seconds) == {"1D": 86_400}
    assert dict(SPEC.memory_days) == {"1D": 365}
    assert dict(SPEC.n0_rows) == {"1D": 1.0}
    assert 3 * 86_400 / (3 * 86_400) == 1.0
    assert (SPEC.lattice_bars, SPEC.horizon_bars) == (3, 6)


def test_import_does_not_open_json_files(monkeypatch) -> None:
    original_open = io.open

    def reject_json_open(file, *args, **kwargs):
        if str(file).lower().endswith(".json"):
            raise AssertionError(f"unexpected JSON open during import: {file}")
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(io, "open", reject_json_open)
    module = importlib.import_module("crypto_probability_engine.quant_ng.reference_v1d")
    original_namespace = module.__dict__.copy()
    try:
        importlib.reload(module)
    finally:
        module.__dict__.clear()
        module.__dict__.update(original_namespace)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(extra=True),
        lambda p: p.pop("formula"),
        lambda p: p.update(schema_version="wrong"),
        lambda p: p["timeframes"].update({"1W": {"bar_seconds": 604800,
                                                    "memory_days": 365,
                                                    "n0_rows": 1.0}}),
        lambda p: p["timeframes"]["1D"].update(memory_days=364),
        lambda p: p["timeframes"]["1D"].update(n0_rows=0),
        lambda p: p["timeframes"]["1D"].update(n0_rows=3),
        lambda p: p["timeframes"]["1D"].update(n0_rows=True),
        lambda p: p.update(day_types="weekday"),
    ],
)
def test_loader_refuses_unpinned_or_malformed_payload(mutate) -> None:
    payload = copy.deepcopy(SPEC_PAYLOAD)
    mutate(payload)
    with pytest.raises(ValueError):
        load_reference_spec_v1d(payload)


def test_direct_spec_construction_is_refused() -> None:
    direct = ReferenceSpecV1d("reference-daytype-v1d", {"1D": 86400},
                              {"1D": 365}, {"1D": 1.0}, 3, 6)
    with pytest.raises(ValueError):
        reference_from_anchors_v1d(
            [], reference_close_utc=datetime(2025, 1, 1, tzinfo=UTC),
            timeframe="1D", spec=direct, prior=0.2,
        )


# Verbatim port of R4's research reference from test_reference.py.
DAY = 86_400_000
WEEKDAY, SATURDAY, SUNDAY = 0, 1, 2
DAY_TYPES = (WEEKDAY, SATURDAY, SUNDAY)


def day_type(reference_close_ms):
    dow = (np.asarray(reference_close_ms, dtype=np.int64) // DAY + 3) % 7  # Monday = 0
    return np.where(dow == 5, SATURDAY, np.where(dow == 6, SUNDAY, WEEKDAY)).astype(np.int64)


def _counts(ref, end, hits, memory_ms):
    order = np.argsort(end, kind="stable")
    ends = end[order]
    cumulative = np.concatenate(([0.0], np.cumsum(hits[order])))
    upto = np.searchsorted(ends, ref, side="right")  # tie rule `le`: end_j <= ref_i is known
    count, hit_count = upto.astype(np.float64), cumulative[upto]
    if memory_ms is not None:
        before = np.searchsorted(ends, ref - memory_ms, side="right")
        count = count - before
        hit_count = hit_count - cumulative[before]
    return count, hit_count


def reference_probs(ref, end, labels, *, n0, prior, memory_days=None, day_types=False,
                    exact_prior_when_unknown=True):
    ref = np.asarray(ref, dtype=np.int64)
    end = np.asarray(end, dtype=np.int64)
    hits = (np.asarray(labels) == 2).astype(np.float64)
    memory_ms = None if memory_days is None else int(round(memory_days * DAY))
    p_timeout = np.empty(len(ref))
    if day_types:
        types = day_type(ref)
        priors = prior if isinstance(prior, dict) else {t: float(prior) for t in DAY_TYPES}
        for t in DAY_TYPES:
            mask = types == t
            if not np.any(mask):
                continue
            count, hit_count = _counts(ref[mask], end[mask], hits[mask], memory_ms)
            value = (n0 * priors[t] + hit_count) / (n0 + count)
            p_timeout[mask] = (
                np.where(count == 0, priors[t], value)
                if exact_prior_when_unknown else value
            )
    else:
        count, hit_count = _counts(ref, end, hits, memory_ms)
        value = (n0 * prior + hit_count) / (n0 + count)
        p_timeout[:] = np.where(count == 0, prior, value) if exact_prior_when_unknown else value
    side = (1.0 - p_timeout) / 2.0
    return np.column_stack((side, side, p_timeout))


def test_r4_single_type_parity_200_synthetic_deployments() -> None:
    rng = random.Random(932_20261022)
    cases = 0
    memory_exclusion_exercised = False
    longer_horizons = 0
    for _deployment in range(200):
        count = rng.randint(124, 130)
        start_ms = int(datetime(2020, 1, 1, tzinfo=UTC).timestamp() * 1000)
        start_ms += rng.randint(0, 1_000_000) * DAY
        start_ms += rng.randint(0, 999)  # retain exact millisecond precision
        start_ms += (-start_ms) % (3 * DAY)
        refs_ms = np.asarray([start_ms + i * 3 * DAY for i in range(count)], dtype=np.int64)
        ends_ms = np.asarray([
            ref + (7 if rng.random() < 0.01 else 6) * DAY
            for ref in refs_ms
        ], dtype=np.int64)
        longer_horizons += int(np.count_nonzero(ends_ms - refs_ms == 7 * DAY))
        labels = [rng.randrange(3) for _ in refs_ms]
        pi0 = rng.random()
        expected = reference_probs(
            refs_ms, ends_ms, labels, n0=1.0, prior=pi0,
            memory_days=365, day_types=False,
        )
        anchors = [
            Anchor(datetime.fromtimestamp(int(ref) / 1000, UTC),
                   datetime.fromtimestamp(int(end) / 1000, UTC), Label(int(label_value)))
            for ref, end, label_value in zip(refs_ms, ends_ms, labels, strict=True)
        ]
        for index, ref_ms in enumerate(refs_ms):
            reference_close = datetime.fromtimestamp(int(ref_ms) / 1000, UTC)
            result = reference_from_anchors_v1d(
                anchors, reference_close_utc=reference_close,
                timeframe="1D", spec=SPEC, prior=pi0,
            )
            actual = (result.p_up_frac, result.p_down_frac, result.p_timeout_frac)
            assert actual == tuple(expected[index])
            memory_exclusion_exercised |= any(
                anchor.horizon_end_utc <= reference_close - timedelta(days=365)
                for anchor in anchors
            )
            cases += 1
    assert cases >= 200
    assert memory_exclusion_exercised
    assert 0.005 <= longer_horizons / (200 * 124) <= 0.02


def _candles(closes: list[float]) -> list[MarketCandle]:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    candles = []
    for index, close in enumerate(closes):
        opened = start + timedelta(days=index)
        candles.append(MarketCandle(opened, opened + timedelta(days=1), close, close,
                                    close, close, 1.0))
    return candles


def test_compute_golden_partial_memory() -> None:
    # Anchor closes at indices 1, 4, 7, 10, 13. Outcomes: UP, DOWN, TIMEOUT,
    # UP, DOWN. At close 22, K=5 and T=1, so p_timeout=(1*.2+1)/(1+5)
    # = 0.19999999999999998 in binary float, with side probabilities 0.4.
    closes = [100.0] * 21
    closes[7] = 102.0   # anchor close 1 -> UP
    closes[10] = 98.0   # anchor close 4 -> DOWN
    closes[13] = 101.5  # anchor close 7 -> TIMEOUT; near the preceding UP endpoint
    closes[16] = 102.0  # anchor close 10 -> UP
    closes[19] = 98.0   # anchor close 13 -> DOWN
    result = compute_reference_v1d(
        _candles(closes), timeframe="1D", band_frac=0.01, spec=SPEC,
        prior=0.2, allow_partial_memory=True,
    )
    assert (result.k, result.t) == (5, 1)
    assert result.p_timeout_frac == 0.19999999999999998
    assert result.p_up_frac == result.p_down_frac == 0.4
    assert result.window_covers_memory is False


@pytest.mark.parametrize("prior", [None, float("nan"), 1.5, True])
def test_prior_refusals(prior) -> None:
    def call():
        return reference_from_anchors_v1d(
            [], reference_close_utc=datetime(2025, 1, 1, tzinfo=UTC),
            timeframe="1D", spec=SPEC, prior=prior,
        )
    if prior is None:
        with pytest.raises(ReferenceNotFrozenError):
            call()
    else:
        with pytest.raises(ValueError):
            call()


@pytest.mark.parametrize("timeframe", ["1W", "4H"])
def test_unsupported_timeframes_refused(timeframe: str) -> None:
    with pytest.raises(ValueError):
        anchors_from_candles_v1d([], timeframe=timeframe, band_frac=0.01, spec=SPEC)


def test_malformed_candles_and_short_window_refused() -> None:
    candles = _candles([100.0] * 20)
    malformed = list(candles)
    malformed[3] = MarketCandle(candles[3].open_time_utc,
                                candles[3].close_time_utc + timedelta(seconds=1),
                                100, 100, 100, 100, 1)
    with pytest.raises(WindowUnavailable) as error:
        anchors_from_candles_v1d(malformed, timeframe="1D", band_frac=0.01, spec=SPEC)
    assert error.value.reason is WindowUnavailableReason.WINDOW_MALFORMED
    with pytest.raises(ReferenceUnavailable) as short:
        compute_reference_v1d(candles, timeframe="1D", band_frac=0.01,
                               spec=SPEC, prior=0.2)
    assert short.value.reason is ReferenceUnavailableReason.WINDOW_SHORT
