"""distributional-v2 (R2 arm CB), prep only: exact, fail-closed, and not wired to anything.

GOLDEN holds the expected probabilities for deterministic synthetic candle windows, computed offline
by R2's own research model (the fitted CB model, R2's feature store with per-window sums) by
.work/816/v2/golden_oracle.py. The module matched it to 3.9e-16 there. The tolerance below allows
platform libm differences only.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from crypto_probability_engine.quant import distributional_v2_tables as tables
from crypto_probability_engine.quant.probability_distributional_v2 import (
    SUPPORTED_SYMBOLS,
    SUPPORTED_TIMEFRAMES,
    calendar_key,
    compute_distributional_v2_probabilities,
)
from tests.quant._distributional_v2_synthetic import (
    BAR_SECONDS,
    GOLDEN_BANDS,
    GOLDEN_WINDOWS,
    epoch_seconds,
    golden_seed,
    synthetic_candles,
)

ROOT = Path(__file__).resolve().parents[2]
TOLERANCE = 1e-12
EXTRA_HISTORY = 30
TABLES_DIGEST = "f0689f292047067b25610ee97e7d001901799d028aa71d5bb0315a666bd377b2"

GOLDEN = {
    'BTC/USDT|15m|0': (
        0.010100199614143837,
        {
            0.001: (
                0.46469386107345534, 0.453337155760401, 0.08196898316614365,
            ),
            0.002: (
                0.4247387562229933, 0.41223517900495726, 0.16302606477204945,
            ),
            0.0045: (
                0.3292246821485879, 0.31850709596187565, 0.35226822188953644,
            ),
        },
    ),
    'BTC/USDT|15m|1': (
        0.0081481238111341,
        {
            0.001: (
                0.4547617943204244, 0.4429486637389387, 0.10228954194063689,
            ),
            0.002: (
                0.4054940148630911, 0.393227525219347, 0.20127845991756188,
            ),
            0.0045: (
                0.29104437207183653, 0.2816750589789638, 0.4272805689491997,
            ),
        },
    ),
    'BTC/USDT|15m|2': (
        0.009733054430525322,
        {
            0.001: (
                0.4631463187526751, 0.4517914003749295, 0.08506228087239542,
            ),
            0.002: (
                0.42177840035682146, 0.4094007673401306, 0.16882083230304795,
            ),
            0.0045: (
                0.3228597735982568, 0.31259493901646757, 0.36454528738527564,
            ),
        },
    ),
    'BTC/USDT|1H|0': (
        0.012007670820385941,
        {
            0.001: (
                0.4694757974425292, 0.46009363841695533, 0.07043056414051546,
            ),
            0.002: (
                0.4333986795735528, 0.42529527465111266, 0.1413060457753345,
            ),
            0.0045: (
                0.3589534881164238, 0.3510870626656441, 0.2899594492179321,
            ),
        },
    ),
    'BTC/USDT|1H|1': (
        0.0073488168815377996,
        {
            0.001: (
                0.45150928296232173, 0.4130053200884471, 0.13548539694923117,
            ),
            0.002: (
                0.38748503069333096, 0.34757439919475125, 0.2649405701119178,
            ),
            0.0045: (
                0.25035054633562737, 0.22211722021042318, 0.5275322334539494,
            ),
        },
    ),
    'BTC/USDT|1H|2': (
        0.005877122938293709,
        {
            0.001: (
                0.4320352960148487, 0.41827800829923, 0.1496866956859213,
            ),
            0.002: (
                0.3657492028050412, 0.3479120947061417, 0.2863387024888171,
            ),
            0.0045: (
                0.22576937452746837, 0.20886189050418333, 0.5653687349683483,
            ),
        },
    ),
    'BTC/USDT|4H|0': (
        0.009208932170719697,
        {
            0.001: (
                0.4742298370624811, 0.43620555497527247, 0.08956460796224641,
            ),
            0.002: (
                0.42665249188821475, 0.39220116322121823, 0.18114634489056702,
            ),
            0.0045: (
                0.3269018628198068, 0.29442875605269303, 0.37866938112750015,
            ),
        },
    ),
    'BTC/USDT|4H|1': (
        0.006967148710144978,
        {
            0.001: (
                0.4585566340361559, 0.4197169797682288, 0.12172638619561532,
            ),
            0.002: (
                0.39948604347649463, 0.3648134386028173, 0.23570051792068808,
            ),
            0.0045: (
                0.27722902463712684, 0.24701733043726326, 0.4757536449256099,
            ),
        },
    ),
    'BTC/USDT|4H|2': (
        0.014557244366462073,
        {
            0.001: (
                0.4901088283705145, 0.4533301652882252, 0.05656100634126032,
            ),
            0.002: (
                0.46120351577095686, 0.4225553826546002, 0.11624110157444295,
            ),
            0.0045: (
                0.39042222075141153, 0.3566566231123531, 0.2529211561362354,
            ),
        },
    ),
    'ETH/USDT|15m|0': (
        0.010828509837649106,
        {
            0.001: (
                0.46807448402911056, 0.4529677167270902, 0.07895779924379925,
            ),
            0.002: (
                0.4290472364196649, 0.4131123485811391, 0.157840414999196,
            ),
            0.0045: (
                0.33780697065908194, 0.3248200998838644, 0.33737292945705366,
            ),
        },
    ),
    'ETH/USDT|15m|1': (
        0.009032371519242344,
        {
            0.001: (
                0.4600512367248053, 0.44501793860940037, 0.09493082466579433,
            ),
            0.002: (
                0.41372447524699063, 0.3985337265768662, 0.18774179817614317,
            ),
            0.0045: (
                0.30612460380067796, 0.2964017191830956, 0.39747367701622643,
            ),
        },
    ),
    'ETH/USDT|15m|2': (
        0.008383310521181344,
        {
            0.001: (
                0.4563764961336838, 0.4412999678756411, 0.10232353599067512,
            ),
            0.002: (
                0.4067004808568224, 0.3917770553778356, 0.201522463765342,
            ),
            0.0045: (
                0.2922847123978247, 0.2841175544479785, 0.4235977331541968,
            ),
        },
    ),
    'ETH/USDT|1H|0': (
        0.009762219596388939,
        {
            0.001: (
                0.4443205669185112, 0.4689594766469558, 0.08671995643453301,
            ),
            0.002: (
                0.40438666892913455, 0.4257599088503907, 0.16985342222047473,
            ),
            0.0045: (
                0.31697449871485495, 0.33285155415771145, 0.3501739471274336,
            ),
        },
    ),
    'ETH/USDT|1H|1': (
        0.007481832438707317,
        {
            0.001: (
                0.4551758118685518, 0.4152620737297818, 0.12956211440166637,
            ),
            0.002: (
                0.3974549239357432, 0.3545620440298053, 0.2479830320344515,
            ),
            0.0045: (
                0.2670921844341537, 0.22965858956089774, 0.5032492260049486,
            ),
        },
    ),
    'ETH/USDT|1H|2': (
        0.007727906438751777,
        {
            0.001: (
                0.4553392581723007, 0.4338002569235384, 0.1108604849041609,
            ),
            0.002: (
                0.4024183509129611, 0.3848002475178551, 0.21278140156918385,
            ),
            0.0045: (
                0.2846265442458735, 0.2680449844079413, 0.4473284713461852,
            ),
        },
    ),
    'ETH/USDT|4H|0': (
        0.009717018264522915,
        {
            0.001: (
                0.47629238319487055, 0.4398247086281766, 0.08388290817695288,
            ),
            0.002: (
                0.433813742808695, 0.3990379393486868, 0.1671483178426182,
            ),
            0.0045: (
                0.3359500662955641, 0.3079942501058386, 0.3560556835985973,
            ),
        },
    ),
    'ETH/USDT|4H|1': (
        0.01010611786682396,
        {
            0.001: (
                0.4779692564516024, 0.4414931811897331, 0.08053756235866455,
            ),
            0.002: (
                0.4365052458332478, 0.4020388754310031, 0.16145587873574913,
            ),
            0.0045: (
                0.3425245825260108, 0.3141195744526719, 0.3433558430213173,
            ),
        },
    ),
    'ETH/USDT|4H|2': (
        0.009964139949353825,
        {
            0.001: (
                0.4773725600021934, 0.44089430239677035, 0.08173313760103623,
            ),
            0.002: (
                0.43554750481622295, 0.40090445014290876, 0.16354804504086828,
            ),
            0.0045: (
                0.34021938209967273, 0.31176517254059954, 0.3480154453597277,
            ),
        },
    ),
}


def _golden_window(symbol: str, timeframe: str, window: int):
    bar = BAR_SECONDS[timeframe]
    count = tables.REQUIRED_CANDLES[timeframe] + EXTRA_HISTORY
    series = synthetic_candles(
        timeframe,
        last_open_seconds=epoch_seconds(GOLDEN_WINDOWS[timeframe][window]) + 6 * bar,
        count=count + 6,
        seed=golden_seed(symbol, timeframe, window),
    )
    return series[:count]


def _window(symbol: str = "BTC/USDT", timeframe: str = "1H", window: int = 0):
    return _golden_window(symbol, timeframe, window)


# --------------------------------------------------------------------------- exactness


@pytest.mark.parametrize("key", sorted(GOLDEN))
def test_golden_windows_match_the_research_model(key: str) -> None:
    symbol, timeframe, window = key.split("|")
    candles = _golden_window(symbol, timeframe, int(window))
    sigma_h, bands = GOLDEN[key]
    assert sorted(bands) == sorted(GOLDEN_BANDS)
    for band, expected in bands.items():
        result = compute_distributional_v2_probabilities(
            candles, symbol=symbol, timeframe=timeframe, band_frac=band
        )
        got = (result.p_up_frac, result.p_down_frac, result.p_timeout_frac)
        assert max(abs(a - b) for a, b in zip(got, expected, strict=True)) <= TOLERANCE, (key, band)
        assert abs(result.sigma_h - sigma_h) <= TOLERANCE * sigma_h
        assert result.candles_used == tables.REQUIRED_CANDLES[timeframe]


def test_the_golden_set_covers_every_cell_calendar_kind_and_session() -> None:
    cells = {tuple(key.split("|")[:2]) for key in GOLDEN}
    assert cells == {(s, t) for s in SUPPORTED_SYMBOLS for t in SUPPORTED_TIMEFRAMES}
    sessions = {
        compute_distributional_v2_probabilities(
            _window(timeframe="1H", window=w), symbol="BTC/USDT", timeframe="1H", band_frac=0.002
        ).session
        for w in range(3)
    }
    assert sessions == {0, 1, 2}
    weekends = {datetime.fromisoformat(iso).weekday() >= 5 for iso in GOLDEN_WINDOWS["15m"]}
    assert weekends == {True, False}


def test_the_constants_are_exactly_the_pinned_tables() -> None:
    assert tables.tables_digest() == tables.TABLES_SHA256 == TABLES_DIGEST


def test_every_cell_has_the_recipe_s_shape() -> None:
    assert SUPPORTED_SYMBOLS == {"BTC/USDT", "ETH/USDT"}
    assert SUPPORTED_TIMEFRAMES == {"15m", "1H", "4H"}
    assert tables.HAR_FEATURES == (
        "rv_1", "rv_6", "rv_24", "rv_day", "rv_week", "parkrv_6", "parkrv_24"
    )
    for symbol, by_timeframe in tables.CELLS.items():
        for timeframe, cell in by_timeframe.items():
            assert len(cell["coefficients"]) == 1 + len(tables.HAR_FEATURES) + 1
            assert len(cell["profile"]) == (42 if timeframe == "4H" else 48)
            assert all(value > 0.0 and math.isfinite(value) for value in cell["profile"])
            expected_shape = "G4_session" if timeframe == "1H" else "G1_emp101"
            assert cell["shape"] == expected_shape, (symbol, timeframe)
            assert len(cell["tables"]) == (3 if timeframe == "1H" else 1)
            for knots, probabilities, sample_size in cell["tables"]:
                assert len(knots) == len(probabilities) == 101
                assert all(a < b for a, b in zip(knots, knots[1:], strict=False))
                assert probabilities[0] == 0.0 and probabilities[-1] == 1.0
                assert all(
                    a < b for a, b in zip(probabilities, probabilities[1:], strict=False)
                )
                assert sample_size > 10_000
            assert tables.REQUIRED_CANDLES[timeframe] == tables.WEEK_BARS[timeframe] + 1


# --------------------------------------------------------------------------- behaviour


def test_only_the_trailing_window_is_read() -> None:
    candles = _window(timeframe="15m")
    required = tables.REQUIRED_CANDLES["15m"]
    exact = candles[-required:]
    older = tuple(
        replace(candle, close=candle.close * 3.0, high=candle.high * 3.0)
        for candle in candles[:-required]
    )
    for band in GOLDEN_BANDS:
        results = {
            compute_distributional_v2_probabilities(
                window, symbol="ETH/USDT", timeframe="15m", band_frac=band
            )
            for window in (exact, older + exact, candles)
        }
        assert len(results) == 1


def test_a_zero_band_gives_exactly_zero_timeout_and_a_valid_triplet() -> None:
    for symbol in sorted(SUPPORTED_SYMBOLS):
        for timeframe in sorted(SUPPORTED_TIMEFRAMES):
            for window in range(3):
                result = compute_distributional_v2_probabilities(
                    _golden_window(symbol, timeframe, window),
                    symbol=symbol,
                    timeframe=timeframe,
                    band_frac=0.0,
                )
                assert result.p_timeout_frac == 0.0
                assert result.p_up_frac >= 0.0 and result.p_down_frac >= 0.0
                assert abs(result.p_up_frac + result.p_down_frac - 1.0) <= 1e-15


def test_a_wider_band_never_lowers_timeout_and_the_triplet_always_sums_to_one() -> None:
    candles = _window(symbol="ETH/USDT", timeframe="4H", window=2)
    previous = -1.0
    for band in (0.0, 0.0005, 0.001, 0.002, 0.004, 0.008, 0.016, 0.05, 0.5, 5.0):
        result = compute_distributional_v2_probabilities(
            candles, symbol="ETH/USDT", timeframe="4H", band_frac=band
        )
        triplet = (result.p_up_frac, result.p_down_frac, result.p_timeout_frac)
        assert all(0.0 <= value <= 1.0 for value in triplet)
        assert abs(sum(triplet) - 1.0) <= 1e-12
        assert result.p_timeout_frac >= previous
        previous = result.p_timeout_frac
    assert previous > 0.99, "an enormous band leaves almost nothing outside it"


def test_calendar_keys_are_r2_s() -> None:
    thursday_midnight = 0  # 1970-01-01T00:00Z
    assert calendar_key(thursday_midnight, "1H") == 0
    assert calendar_key(thursday_midnight + 13 * 3_600, "15m") == 26
    saturday = thursday_midnight + 2 * 86_400
    assert calendar_key(saturday + 21 * 3_600, "1H") == 21 * 2 + 1
    assert calendar_key(saturday + 20 * 3_600, "4H") == 5 * 7 + 5
    monday = thursday_midnight + 4 * 86_400
    assert calendar_key(monday + 4 * 3_600, "4H") == 1 * 7 + 0


# --------------------------------------------------------------------------- fail closed


def _refuses(candles, *, symbol="BTC/USDT", timeframe="1H", band=0.002, match=None) -> None:
    with pytest.raises(ValueError, match=match):
        compute_distributional_v2_probabilities(
            candles, symbol=symbol, timeframe=timeframe, band_frac=band
        )


def test_an_unsupported_symbol_or_timeframe_refuses() -> None:
    candles = _window()
    _refuses(candles, symbol="SOL/USDT", match="does not support")
    _refuses(candles, symbol="BTCUSDT", match="does not support")
    _refuses(candles, timeframe="1D", match="does not support")


@pytest.mark.parametrize("band", [-0.001, math.nan, math.inf])
def test_a_band_that_is_not_finite_and_non_negative_refuses(band: float) -> None:
    _refuses(_window(), band=band, match="band")


def test_too_few_candles_refuse() -> None:
    required = tables.REQUIRED_CANDLES["15m"]
    _refuses(_window(timeframe="15m")[-(required - 1) :], timeframe="15m", match="needs 673")


def test_a_malformed_window_refuses() -> None:
    candles = list(_window())
    gap = candles[:-50] + candles[-49:]
    _refuses(gap, match="adjacent")
    swapped = candles[:-2] + [candles[-1], candles[-2]]
    _refuses(swapped, match="adjacent")
    minute = timedelta(minutes=1)
    shifted = [
        replace(c, open_time_utc=c.open_time_utc + minute, close_time_utc=c.close_time_utc + minute)
        for c in candles
    ]
    _refuses(shifted, match="boundary")
    local = [
        replace(
            c,
            open_time_utc=c.open_time_utc.astimezone(timezone(timedelta(hours=7))),
            close_time_utc=c.close_time_utc.astimezone(timezone(timedelta(hours=7))),
        )
        for c in candles
    ]
    _refuses(local, match="UTC")
    naive_close = candles[:-1] + [
        replace(candles[-1], close_time_utc=candles[-1].close_time_utc.replace(tzinfo=None))
    ]
    _refuses(naive_close, match="UTC")
    last = candles[-1]
    long_bar = candles[:-1] + [
        replace(last, close_time_utc=last.close_time_utc + timedelta(hours=1))
    ]
    _refuses(long_bar, match="one bar")


@pytest.mark.parametrize(
    "change",
    [
        {"close": 0.0},
        {"low": -1.0},
        {"high": math.nan},
        {"open": math.inf},
    ],
    ids=["zero-close", "negative-low", "nan-high", "infinite-open"],
)
def test_a_non_positive_or_non_finite_price_refuses(change: dict) -> None:
    candles = list(_window())
    candles[-10] = replace(candles[-10], **change)
    _refuses(candles, match="finite and positive")


def test_a_low_above_the_high_refuses() -> None:
    candles = list(_window())
    candle = candles[-3]
    candles[-3] = replace(
        candle, low=candle.high * 1.01, open=candle.high * 1.02, close=candle.high * 1.02
    )
    _refuses(candles, match="low exceeds high")


# --------------------------------------------------------------------------- not wired


def test_nothing_in_the_product_uses_distributional_v2() -> None:
    package = ROOT / "src" / "crypto_probability_engine"
    users = sorted(
        str(path.relative_to(package))
        for path in package.rglob("*.py")
        if "distributional_v2" in path.read_text(encoding="utf-8")
    )
    assert users == ["quant/probability_distributional_v2.py"]
    defaults = (package / "config" / "defaults.py").read_text(encoding="utf-8")
    assert "distributional-v2" not in defaults, "no methodology version is assigned in prep"
    assert not (ROOT / "ops" / "distributional_v2_freeze.json").exists()
