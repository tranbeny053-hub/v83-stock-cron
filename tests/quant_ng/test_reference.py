"""Synthetic contract tests for the dormant generation-2 reference module."""

from __future__ import annotations

import copy
import hashlib
import json
import random
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from crypto_probability_engine.adapters.types import MarketCandle
from crypto_probability_engine.quant_ng import windows
from crypto_probability_engine.quant_ng.reference import (
    REFERENCE_SPEC_V1_SHA256,
    Anchor,
    DayType,
    Label,
    ReferenceNotFrozenError,
    ReferencePriors,
    ReferenceSpec,
    ReferenceUnavailable,
    ReferenceUnavailableReason,
    anchors_from_candles,
    compute_reference,
    label,
    load_reference_spec,
    n0_rows,
    reference_from_anchors,
)
from crypto_probability_engine.quant_ng.reference import (
    day_type as classify_day_type,
)

ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = ROOT / "ops/quant_ng/REFERENCE_SPEC_v1.json"
SPEC_PAYLOAD = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
SPEC = load_reference_spec(SPEC_PAYLOAD)
def test_spec_hash_constants_and_values() -> None:
    raw = SPEC_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == REFERENCE_SPEC_V1_SHA256
    assert dict(SPEC.memory_days) == {"15m": 7, "1H": 28, "4H": 28}
    assert SPEC.n0_days == 3
    assert SPEC.lattice_bars == 3
    assert SPEC.horizon_bars == 6
    assert dict(SPEC.bar_seconds) == dict(windows.TIMEFRAME_SECONDS)


@pytest.mark.parametrize(
    ("mutate"),
    [
        lambda payload: payload.update(unexpected=True),
        lambda payload: payload.pop("formula"),
        lambda payload: payload.update(schema_version="wrong"),
        lambda payload: payload.update(spec_id="reference-daytype-v2"),
        lambda payload: payload.update(n0_days=True),
        lambda payload: payload.update(n0_days=0),
        lambda payload: payload["timeframes"].update(
            {"1D": {"bar_seconds": 86_400, "memory_days": 28}}
        ),
        lambda payload: payload["provenance"].update(
            r4_reference_py_sha256="bad"
        ),
    ],
)
def test_spec_loader_is_strict(mutate) -> None:
    payload = copy.deepcopy(SPEC_PAYLOAD)
    mutate(payload)
    with pytest.raises(ValueError):
        load_reference_spec(payload)


def test_n0_rows() -> None:
    assert [n0_rows(SPEC, timeframe) for timeframe in ("15m", "1H", "4H")] == [
        96, 24, 6
    ]


def test_day_type_week_and_utc_midnight_boundaries() -> None:
    monday = datetime(2025, 1, 6, tzinfo=UTC)
    assert [classify_day_type(monday + timedelta(days=offset)) for offset in range(7)] == [
        DayType.WEEKDAY,
        DayType.WEEKDAY,
        DayType.WEEKDAY,
        DayType.WEEKDAY,
        DayType.WEEKDAY,
        DayType.SATURDAY,
        DayType.SUNDAY,
    ]
    assert classify_day_type(datetime(2025, 1, 10, 23, 59, 59, tzinfo=UTC)) == DayType.WEEKDAY
    assert classify_day_type(datetime(2025, 1, 11, tzinfo=UTC)) == DayType.SATURDAY
    assert classify_day_type(datetime(2025, 1, 13, tzinfo=UTC)) == DayType.WEEKDAY


def test_label_thresholds_and_refusals() -> None:
    assert label(0.1, 0.1) is Label.TIMEOUT
    assert label(-0.1, 0.1) is Label.TIMEOUT
    assert label(0.100001, 0.1) is Label.UP
    assert label(-0.100001, 0.1) is Label.DOWN
    assert label(0.0, 0.0) is Label.TIMEOUT
    for result in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(ValueError):
            label(result, 0.1)
    with pytest.raises(ValueError):
        label(0.0, -0.1)


def _anchor(ref: datetime, end: datetime, outcome: Label) -> Anchor:
    return Anchor(ref, end, outcome)


def test_reference_counts_boundaries_day_type_and_deployment() -> None:
    ref = datetime(2025, 1, 8, 12, tzinfo=UTC)
    memory_start = ref - timedelta(days=7)
    anchors = [
        _anchor(ref - timedelta(days=1), ref - timedelta(hours=1), Label.TIMEOUT),
        _anchor(ref - timedelta(days=2), ref, Label.UP),  # tie is included
        _anchor(ref - timedelta(days=14), memory_start, Label.TIMEOUT),  # edge excluded
        _anchor(
            ref - timedelta(days=14), memory_start + timedelta(seconds=1), Label.DOWN
        ),
        # A Saturday anchor, known and inside the memory: only its day type excludes it.
        _anchor(
            datetime(2025, 1, 4, 12, tzinfo=UTC),
            datetime(2025, 1, 4, 13, 30, tzinfo=UTC),
            Label.TIMEOUT,
        ),
    ]
    result = reference_from_anchors(
        anchors,
        reference_close_utc=ref,
        timeframe="15m",
        spec=SPEC,
        priors=ReferencePriors((0.2, 0.3, 0.4)),
    )
    assert (result.k_same_type, result.t_same_type) == (3, 1)
    assert result.p_timeout_frac == (96 * 0.2 + 1) / (96 + 3)
    assert result.p_up_frac == result.p_down_frac
    assert result.window_covers_memory is None

    deployment_start = ref - timedelta(days=2)
    deployment_rows = (
        _anchor(deployment_start - timedelta(days=3), ref, Label.TIMEOUT),
        _anchor(deployment_start, ref, Label.UP),
    )
    deployed = reference_from_anchors(
        deployment_rows,
        reference_close_utc=ref,
        timeframe="15m",
        spec=SPEC,
        priors=ReferencePriors((0.2, 0.3, 0.4)),
        deployment_start_utc=deployment_start,
    )
    assert (deployed.k_same_type, deployed.t_same_type) == (1, 0)


def test_reference_k_zero_preserves_prior_float_exactly() -> None:
    prior = 0.123456789012345
    result = reference_from_anchors(
        (), reference_close_utc=datetime(2025, 1, 8, tzinfo=UTC),
        timeframe="1H", spec=SPEC, priors=ReferencePriors((prior, 0.3, 0.4)),
    )
    assert result.p_timeout_frac is prior
    assert result.p_up_frac == result.p_down_frac
    assert result.k_same_type == result.t_same_type == 0


def test_integer_priors_are_normalized_to_float_for_k_zero() -> None:
    priors = ReferencePriors((0, 1, 0))
    assert priors.pi0 == (0.0, 1.0, 0.0)
    result = reference_from_anchors(
        (), reference_close_utc=datetime(2025, 1, 8, tzinfo=UTC),
        timeframe="1H", spec=SPEC, priors=priors,
    )
    assert type(result.p_timeout_frac) is float


def test_reference_refusals() -> None:
    ref = datetime(2025, 1, 8, tzinfo=UTC)
    with pytest.raises(ReferenceNotFrozenError):
        reference_from_anchors(
            (), reference_close_utc=ref, timeframe="15m", spec=SPEC, priors=None
        )
    for invalid in ((0.1, 0.2), (True, 0.2, 0.3), (float("nan"), 0.2, 0.3),
                    (-0.1, 0.2, 0.3), (1.1, 0.2, 0.3)):
        with pytest.raises(ValueError):
            ReferencePriors(invalid)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        reference_from_anchors(
            (), reference_close_utc=ref, timeframe="1D", spec=SPEC,
            priors=ReferencePriors((0.2, 0.3, 0.4)),
        )
    with pytest.raises(ValueError):
        reference_from_anchors(
            (), reference_close_utc=datetime(2025, 1, 8), timeframe="15m",
            spec=SPEC, priors=ReferencePriors((0.2, 0.3, 0.4)),
        )


def _candles(count: int, timeframe: str, *, first_open: datetime | None = None):
    seconds = SPEC.bar_seconds[timeframe]
    first_open = first_open or datetime(2025, 1, 6, tzinfo=UTC)
    result = []
    for index in range(count):
        opened = first_open + timedelta(seconds=index * seconds)
        close = 100.0 + index
        result.append(
            MarketCandle(opened, opened + timedelta(seconds=seconds), close, close,
                         close, close, 1.0)
        )
    return tuple(result)


def test_anchors_from_candles_lattice_horizon_and_label() -> None:
    candles = _candles(20, "15m")
    anchors = anchors_from_candles(
        candles, timeframe="15m", band_frac=0.05, spec=SPEC
    )
    expected = []
    for index in range(len(candles) - SPEC.horizon_bars):
        candle = candles[index]
        if int(candle.close_time_utc.timestamp()) % (3 * 900) == 0:
            expected.append(index)
    assert len(anchors) == len(expected)
    assert all(int(anchor.reference_close_utc.timestamp()) % 2700 == 0 for anchor in anchors)
    assert anchors[0].label is Label.UP
    assert all(anchor.horizon_end_utc > anchor.reference_close_utc for anchor in anchors)
    malformed = list(candles)
    malformed[3] = replace(
        malformed[3], open_time_utc=malformed[3].open_time_utc + timedelta(seconds=1)
    )
    with pytest.raises(windows.WindowUnavailable):
        anchors_from_candles(malformed, timeframe="15m", band_frac=0.1, spec=SPEC)


def test_compute_reference_fields_and_memory_coverage() -> None:
    priors = ReferencePriors((0.2, 0.3, 0.4))
    candles = _candles(678, "15m")
    anchors = anchors_from_candles(candles, timeframe="15m", band_frac=0.01, spec=SPEC)
    expected = reference_from_anchors(
        anchors, reference_close_utc=candles[-1].close_time_utc,
        timeframe="15m", spec=SPEC, priors=priors,
    )
    actual = compute_reference(
        candles, timeframe="15m", band_frac=0.01, spec=SPEC, priors=priors
    )
    assert replace(actual, window_covers_memory=None) == expected
    assert actual.window_covers_memory is True
    shorter = _candles(677, "15m")
    with pytest.raises(ReferenceUnavailable) as error:
        compute_reference(shorter, timeframe="15m", band_frac=0.01,
                          spec=SPEC, priors=priors)
    assert error.value.reason is ReferenceUnavailableReason.WINDOW_SHORT
    assert compute_reference(shorter, timeframe="15m", band_frac=0.01,
                              spec=SPEC, priors=priors,
                              allow_partial_memory=True).window_covers_memory is False


def test_saturday_midnight_deployment_matches_r4_oracle() -> None:
    refs = [datetime(2025, 1, 4, tzinfo=UTC) + timedelta(hours=3 * i) for i in range(5)]
    ends = [ref + timedelta(hours=6) for ref in refs]
    labels = [Label.DOWN, Label.TIMEOUT, Label.UP, Label.TIMEOUT, Label.DOWN]
    anchors = tuple(Anchor(ref, end, outcome)
                    for ref, end, outcome in zip(refs, ends, labels, strict=True))
    deployment_start = refs[0]
    deployed_refs = refs
    expected = reference_probs(
        np.array([int(ref.timestamp() * 1000) for ref in deployed_refs], dtype=np.int64),
        np.array([int(end.timestamp() * 1000) for end in ends], dtype=np.int64),
        np.array([int(outcome) for outcome in labels], dtype=np.int64),
        n0=n0_rows(SPEC, "1H"), prior={0: 0.2, 1: 0.3, 2: 0.4},
        memory_days=28, day_types=True,
    )
    assert classify_day_type(refs[0]) is DayType.SATURDAY
    for index, ref in enumerate(deployed_refs):
        actual = reference_from_anchors(
            anchors, reference_close_utc=ref, timeframe="1H", spec=SPEC,
            priors=ReferencePriors((0.2, 0.3, 0.4)),
            deployment_start_utc=deployment_start,
        )
        assert actual.day_type is DayType.SATURDAY
        assert (actual.p_up_frac, actual.p_down_frac, actual.p_timeout_frac) == tuple(
            expected[index]
        )


def _closes_candles(closes: tuple[float, ...]):
    first = datetime(2025, 1, 8, tzinfo=UTC)
    return tuple(
        MarketCandle(
            first + timedelta(hours=index), first + timedelta(hours=index + 1),
            close, close, close, close, 1.0,
        )
        for index, close in enumerate(closes)
    )


def test_hand_worked_reference_golden_and_literal_candle_anchors() -> None:
    # Lattice closes are 03:00, 06:00, 09:00, 12:00, 15:00Z. Anchors fit only when
    # j + 6 < 16, so indices 0, 1, 2 (03:00, 06:00, 09:00) fit. Their returns and
    # labels at band 0.002 are 99/100 - 1 (DOWN), 101.1/101 - 1 (TIMEOUT),
    # and 101.4/99 - 1 (UP). By the final close at 16:00Z all three are known;
    # K=3 and T=1, all are Wednesday WEEKDAY. For 1H, n0 = 3 * 8 = 24, hence
    # p_timeout = (24 * 0.4 + T) / (24 + K).
    closes = (100, 100, 100, 100, 101, 101, 100, 99.5,
              99, 98.9, 99, 101.1, 101, 101.5, 101.4, 101.3)
    candles = _closes_candles(closes)
    anchors = anchors_from_candles(candles, timeframe="1H", band_frac=0.002, spec=SPEC)
    expected_anchors = [
        (datetime(2025, 1, 8, 3, tzinfo=UTC), datetime(2025, 1, 8, 9, tzinfo=UTC), Label.DOWN),
        (datetime(2025, 1, 8, 6, tzinfo=UTC), datetime(2025, 1, 8, 12, tzinfo=UTC), Label.TIMEOUT),
        (datetime(2025, 1, 8, 9, tzinfo=UTC), datetime(2025, 1, 8, 15, tzinfo=UTC), Label.UP),
    ]
    actual_anchors = [(a.reference_close_utc, a.horizon_end_utc, a.label) for a in anchors]
    assert actual_anchors == expected_anchors

    result = compute_reference(
        candles, timeframe="1H", band_frac=0.002, spec=SPEC,
        priors=ReferencePriors((0.4, 0.3, 0.2)), allow_partial_memory=True,
    )
    assert result.k_same_type == 3
    assert result.t_same_type == 1
    assert result.p_timeout_frac == (24 * 0.4 + 1) / (24 + 3)
    assert result.p_up_frac == result.p_down_frac == (1 - result.p_timeout_frac) / 2
    assert result.window_covers_memory is False


def test_reference_direct_spec_loader_and_default_memory_refusals() -> None:
    direct = ReferenceSpec(SPEC.spec_id, SPEC.bar_seconds, SPEC.memory_days,
                           SPEC.n0_days, SPEC.lattice_bars, SPEC.horizon_bars)
    with pytest.raises(ValueError):
        reference_from_anchors((), reference_close_utc=datetime(2025, 1, 8, tzinfo=UTC),
                               timeframe="1H", spec=direct,
                               priors=ReferencePriors((0.2, 0.3, 0.4)))
    with pytest.raises(ValueError):
        n0_rows(direct, "1H")
    for mutate in (
        lambda payload: payload.update(n0_days=50),
        lambda payload: payload["timeframes"]["15m"].update(memory_days=1),
        lambda payload: payload.update(lattice_bars=1),
    ):
        payload = copy.deepcopy(SPEC_PAYLOAD)
        mutate(payload)
        with pytest.raises(ValueError):
            load_reference_spec(payload)
    priors = ReferencePriors((0.2, 0.3, 0.4))
    full_window = _candles(678, "15m")
    assert compute_reference(full_window, timeframe="15m", band_frac=0.01,
                             spec=SPEC, priors=priors).window_covers_memory is True


# Verbatim port of R4's research reference
# (.work/research3/wave2/gate/reference.py, sha256 cb45a388…), research-only parity oracle.
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


@pytest.mark.parametrize("timeframe,memory", [("15m", 7), ("1H", 28), ("4H", 28)])
def test_r4_synthetic_bit_exact_parity(timeframe: str, memory: int) -> None:
    rng = random.Random(923_000 + SPEC.bar_seconds[timeframe])
    cases = 0
    seconds = SPEC.bar_seconds[timeframe]
    for _deployment in range(100):
        count = rng.randint(2, 35)
        start = datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=rng.randint(0, 90))
        start = start.replace(hour=0, minute=0, second=0)
        epoch = int(start.timestamp())
        lattice = 3 * seconds
        start += timedelta(seconds=(-epoch) % lattice)
        refs = [start + timedelta(seconds=i * 3 * seconds) for i in range(count)]
        ends = [
            ref + timedelta(seconds=(6 + (rng.random() < 0.01)) * seconds)
            for ref in refs
        ]
        labels = [rng.randrange(3) for _ in refs]
        pi0 = [rng.random() for _ in range(3)]
        ref_ms = np.array([int(ref.timestamp() * 1000) for ref in refs], dtype=np.int64)
        end_ms = np.array([int(end.timestamp() * 1000) for end in ends], dtype=np.int64)
        deployment_index = 1
        expected = reference_probs(
            ref_ms[deployment_index:], end_ms[deployment_index:],
            labels[deployment_index:], n0=n0_rows(SPEC, timeframe),
            prior={0: pi0[0], 1: pi0[1], 2: pi0[2]},
            memory_days=memory, day_types=True,
        )
        first_ref = refs[deployment_index]
        anchors = tuple(
            Anchor(ref, end, Label(outcome))
            for ref, end, outcome in zip(refs, ends, labels, strict=True)
        )
        for index, ref in enumerate(refs[deployment_index:]):
            actual = reference_from_anchors(
                anchors, reference_close_utc=ref, timeframe=timeframe, spec=SPEC,
                priors=ReferencePriors(tuple(pi0)), deployment_start_utc=first_ref,
            )
            if actual.p_timeout_frac != expected[index, 2]:
                pytest.fail(
                    f"first R4 parity mismatch: timeframe={timeframe}, deployment={_deployment}, "
                    f"row={index + deployment_index}, actual={actual.p_timeout_frac!r}, "
                    f"expected={expected[index, 2]!r}"
                )
            cases += 1
    assert cases >= 300


@pytest.mark.parametrize("timeframe,memory", [("15m", 7), ("1H", 28), ("4H", 28)])
def test_r4_synthetic_bit_exact_parity_long_deployments(timeframe: str, memory: int) -> None:
    rng = random.Random(924_000 + SPEC.bar_seconds[timeframe])
    seconds = SPEC.bar_seconds[timeframe]
    lattice = 3 * seconds
    memory_rows = memory * 86_400 // lattice
    saw_types: set[DayType] = set()
    deployments = 10
    for deployment in range(deployments):
        count = memory_rows + 60
        # Random weekday start; all weekday/weekend types occur in each long span.
        start = datetime(2025, 1, 6, tzinfo=UTC) + timedelta(
            days=7 * rng.randint(0, 8) + rng.randrange(5), hours=rng.randint(0, 23)
        )
        start = start.replace(minute=0, second=0, microsecond=0)
        epoch = int(start.timestamp())
        start += timedelta(seconds=(-epoch) % lattice)
        refs = [start + timedelta(seconds=i * lattice) for i in range(count)]
        ends = [ref + timedelta(seconds=(6 + (rng.random() < 0.01)) * seconds)
                for ref in refs]
        labels = [rng.randrange(3) for _ in refs]
        pi0 = [rng.random() for _ in range(3)]
        ref_ms = np.array([int(ref.timestamp() * 1000) for ref in refs], dtype=np.int64)
        end_ms = np.array([int(end.timestamp() * 1000) for end in ends], dtype=np.int64)
        deployment_index = 1
        expected = reference_probs(
            ref_ms[deployment_index:], end_ms[deployment_index:],
            labels[deployment_index:], n0=n0_rows(SPEC, timeframe),
            prior=dict(enumerate(pi0)), memory_days=memory, day_types=True,
        )
        anchors = tuple(Anchor(ref, end, Label(outcome))
                        for ref, end, outcome in zip(refs, ends, labels, strict=True))
        deployment_start = refs[deployment_index]
        memory_exercised = False
        for index, ref in enumerate(refs[deployment_index:]):
            index += deployment_index
            known_anchors = tuple(anchor for anchor in anchors
                                  if anchor.horizon_end_utc <= ref)
            known_same_type = [
                anchor for anchor in anchors
                if anchor.reference_close_utc >= deployment_start
                and classify_day_type(anchor.reference_close_utc) == classify_day_type(ref)
                and anchor.horizon_end_utc <= ref
            ]
            actual = reference_from_anchors(
                known_anchors, reference_close_utc=ref, timeframe=timeframe, spec=SPEC,
                priors=ReferencePriors(tuple(pi0)), deployment_start_utc=deployment_start,
            )
            assert actual.p_timeout_frac == expected[index - deployment_index, 2]
            saw_types.add(actual.day_type)
            if len(known_same_type) > actual.k_same_type:
                memory_exercised = True
        assert memory_exercised, (
            f"memory exclusion not exercised: {timeframe} deployment {deployment}"
        )
    assert saw_types == {DayType.WEEKDAY, DayType.SATURDAY, DayType.SUNDAY}
