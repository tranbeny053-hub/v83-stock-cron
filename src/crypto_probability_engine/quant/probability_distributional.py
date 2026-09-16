"""Frozen B3 distributional probability construction."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from math import isfinite, sqrt
from types import MappingProxyType

from crypto_probability_engine.adapters.types import MarketCandle
from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A
from crypto_probability_engine.utils.invariants import validate_probability_triplet

_SCALE_FLOOR = 1e-9

_Z_15M = (
    -15.9925590749, -2.8043074687, -2.1953625584, -1.868836186, -1.6513681587,
    -1.4881066578, -1.3633627885, -1.2588832235, -1.1708044083, -1.0962381679,
    -1.0294052244, -0.9673982036, -0.9165312321, -0.8670655626, -0.8224884233,
    -0.7787278572, -0.7393748292, -0.7013909064, -0.6671714035, -0.6353599107,
    -0.605142351, -0.5751822629, -0.5465800315, -0.5193067133, -0.494554354,
    -0.4696556143, -0.4457335931, -0.4219104846, -0.3986262509, -0.3760390641,
    -0.3552482413, -0.3338776895, -0.3125902793, -0.2923037016, -0.2716999714,
    -0.2519582421, -0.2324140347, -0.2135405733, -0.1944546175, -0.1768294751,
    -0.1587597415, -0.1407256741, -0.1225515771, -0.105837022, -0.0891134861,
    -0.0726580602, -0.0554959741, -0.0387177162, -0.021694452, -0.0044576432,
    0.0117478422, 0.028438706, 0.0455735324, 0.0621080984, 0.0790147158,
    0.0959384495, 0.1131809374, 0.1309548584, 0.148368247, 0.1658840505,
    0.1833666159, 0.2018041677, 0.2211917456, 0.238857035, 0.2572665405,
    0.2757504644, 0.2937204686, 0.3130578485, 0.3323482508, 0.3529128156,
    0.3734828462, 0.3945519696, 0.4162358405, 0.4386190112, 0.4604080174,
    0.4830371274, 0.5063766725, 0.5315702784, 0.556775385, 0.5826864031,
    0.6118211149, 0.6395598322, 0.670282819, 0.7030603028, 0.7365587273,
    0.771669116, 0.8107780849, 0.8508455897, 0.8959687939, 0.9450672815,
    0.9986834041, 1.0618452731, 1.1312207493, 1.2135530574, 1.311181593,
    1.429163801, 1.5768078798, 1.8052479698, 2.1427680436, 2.8324985066,
    16.9436297632,
)

_Z_1H = (
    -9.6521308236, -3.0685547774, -2.3557397214, -2.0064259833, -1.7608348174,
    -1.5833164143, -1.4407922865, -1.3139635463, -1.2104716954, -1.1229702152,
    -1.0465164921, -0.9795818104, -0.9151307777, -0.8586948678, -0.8060123493,
    -0.7579685505, -0.7136526922, -0.6722449999, -0.6348179449, -0.6017738683,
    -0.5695322997, -0.5386476371, -0.5083900296, -0.4812019094, -0.4554896083,
    -0.4298546898, -0.4071321268, -0.3849311931, -0.3616226811, -0.3403159599,
    -0.3195607085, -0.3008412138, -0.2806990851, -0.2617419374, -0.2426901094,
    -0.224703195, -0.2067975073, -0.1888645805, -0.1720339067, -0.1551740669,
    -0.1383586794, -0.1223717822, -0.1066714792, -0.0918990112, -0.0772032203,
    -0.0622338363, -0.0474127752, -0.0322261798, -0.0174764043, -0.0024507303,
    0.0129287361, 0.0275204667, 0.0430503899, 0.0570205955, 0.0712843715,
    0.0872753955, 0.1031272246, 0.117916957, 0.1350915484, 0.1516583347,
    0.1673274527, 0.184373837, 0.2011025985, 0.2188855066, 0.2365642204,
    0.2541853046, 0.2722053069, 0.2913440154, 0.3098274336, 0.3302158647,
    0.3521946861, 0.3742951942, 0.3957114256, 0.4184348106, 0.4425998214,
    0.4676775736, 0.4932081128, 0.522349056, 0.5518642051, 0.5809415916,
    0.6118422198, 0.6440038238, 0.6813210649, 0.7201803949, 0.7600260212,
    0.8027564686, 0.8496599169, 0.8998272646, 0.9550560739, 1.0164801039,
    1.0857989538, 1.1627744617, 1.2468113349, 1.3443969492, 1.4692697727,
    1.6114346746, 1.7894577126, 2.044870838, 2.4102481169, 3.0530762577,
    15.7216018354,
)

_Z_4H = (
    -7.779973774, -2.8849039697, -2.3089210983, -1.9858578983, -1.7716938911,
    -1.6029198244, -1.4703604282, -1.361398731, -1.2575310782, -1.1842516353,
    -1.1152541679, -1.0440101297, -0.9846374663, -0.9371352875, -0.8865114556,
    -0.8399443168, -0.7988361501, -0.7572589218, -0.7237430817, -0.6838414856,
    -0.6492157593, -0.6156433438, -0.5805950542, -0.5513044362, -0.5180170945,
    -0.4894936607, -0.4631440944, -0.4374199678, -0.4111921375, -0.3862517271,
    -0.3595318302, -0.3359882202, -0.3111984367, -0.2896418384, -0.267852973,
    -0.2430648768, -0.2224842095, -0.2004048392, -0.1804736401, -0.1620573728,
    -0.1432696607, -0.124620793, -0.1072772067, -0.0877079782, -0.0709693701,
    -0.0539709663, -0.0374015515, -0.0199243219, -0.0029029821, 0.015533951,
    0.0326363512, 0.0501049516, 0.0666002828, 0.0839523282, 0.0989174203,
    0.1166023819, 0.1338225366, 0.1506188117, 0.1681468862, 0.1880655548,
    0.2055082259, 0.2255807676, 0.2439178952, 0.2633975158, 0.2855133998,
    0.3056563094, 0.3273158064, 0.3497710435, 0.3739307371, 0.3990960471,
    0.4235392089, 0.4498472361, 0.476739952, 0.5031471624, 0.5343605825,
    0.5625714271, 0.5942726663, 0.6270928249, 0.6613740015, 0.6943019485,
    0.7349798014, 0.7680660433, 0.8105437415, 0.8531079138, 0.8942360867,
    0.9390434199, 0.9859022107, 1.0320877652, 1.089168264, 1.1534517912,
    1.2162202863, 1.2912583134, 1.3790468853, 1.4681196553, 1.5959667508,
    1.7256628138, 1.8919284347, 2.0958033318, 2.4074650002, 2.9829586356,
    9.8282838936,
)


def _quantile_table(z_values: tuple[float, ...]) -> tuple[tuple[float, float], ...]:
    return tuple((z_value, index / 100.0) for index, z_value in enumerate(z_values))


FROZEN_B3_PARAMETERS = MappingProxyType(
    {
        "15m": MappingProxyType(
            {
                "decay": 0.90,
                "alpha": 0.60,
                "n": 140100,
                "table": _quantile_table(_Z_15M),
            }
        ),
        "1H": MappingProxyType(
            {
                "decay": 0.99,
                "alpha": 0.50,
                "n": 70018,
                "table": _quantile_table(_Z_1H),
            }
        ),
        "4H": MappingProxyType(
            {
                "decay": 0.99,
                "alpha": 0.50,
                "n": 26220,
                "table": _quantile_table(_Z_4H),
            }
        ),
    }
)
SUPPORTED_TIMEFRAMES = frozenset(FROZEN_B3_PARAMETERS)


@dataclass(frozen=True)
class DistributionalProbability:
    p_up_frac: float
    p_down_frac: float
    p_timeout_frac: float
    sigma_bar: float
    sigma_h: float
    band_frac: float


def _simple_returns(candles: tuple[MarketCandle, ...]) -> tuple[float, ...]:
    returns: list[float] = []
    for previous, current in zip(candles, candles[1:], strict=False):
        if previous.close <= 0.0:
            returns.append(0.0)
        else:
            returns.append((current.close - previous.close) / previous.close)
    return tuple(returns)


def _ewma_sigma(returns: tuple[float, ...], decay: float) -> float:
    finite = [float(value) for value in returns if isfinite(float(value))]
    if not finite:
        return _SCALE_FLOOR
    variance = finite[0] * finite[0]
    for value in finite[1:]:
        variance = decay * variance + (1.0 - decay) * value * value
    return max(sqrt(max(variance, 0.0)), _SCALE_FLOOR)


def _empirical_cdf(
    value: float,
    table: tuple[tuple[float, float], ...],
    sample_size: int,
) -> float:
    lower_tail = 1.0 / (sample_size + 1)
    upper_tail = sample_size / (sample_size + 1)
    z_values = tuple(knot[0] for knot in table)
    if value < z_values[0]:
        return lower_tail
    if value >= z_values[-1]:
        return upper_tail
    right = bisect_right(z_values, value)
    left = right - 1
    z_left, probability_left = table[left]
    z_right, probability_right = table[right]
    weight = (value - z_left) / (z_right - z_left)
    interpolated = probability_left + weight * (
        probability_right - probability_left
    )
    return min(max(interpolated, lower_tail), upper_tail)


def compute_distributional_probabilities(
    candles: tuple[MarketCandle, ...],
    *,
    timeframe: str,
    band_frac: float,
) -> DistributionalProbability:
    """Compute frozen B3 probabilities from closed candles and the live execution band."""

    try:
        parameters = FROZEN_B3_PARAMETERS[timeframe]
    except KeyError as exc:
        raise ValueError(
            f"Distributional methodology does not support timeframe: {timeframe}"
        ) from exc
    band = float(band_frac)
    if not isfinite(band) or band < 0.0:
        raise ValueError("Distributional methodology requires a finite non-negative band")
    decay = float(parameters["decay"])
    alpha = float(parameters["alpha"])
    sample_size = int(parameters["n"])
    table = parameters["table"]
    if not isinstance(table, tuple):
        raise TypeError("Frozen B3 quantile table must be a tuple")
    sigma_bar = _ewma_sigma(_simple_returns(candles), decay)
    sigma_h = max(sigma_bar * (DEFAULT_PHASE1A.h_primary_bars**alpha), _SCALE_FLOOR)
    cdf_lo = _empirical_cdf(-band / sigma_h, table, sample_size)
    cdf_hi = _empirical_cdf(band / sigma_h, table, sample_size)
    lower_tail = 1.0 / (sample_size + 1)
    upper_tail = sample_size / (sample_size + 1)
    p_down = cdf_lo
    p_up = lower_tail if cdf_hi == upper_tail else 1.0 - cdf_hi
    p_timeout = (
        (sample_size - 1) / (sample_size + 1)
        if cdf_lo == lower_tail and cdf_hi == upper_tail
        else cdf_hi - cdf_lo
    )
    validate_probability_triplet(p_up, p_down, p_timeout)
    return DistributionalProbability(
        p_up_frac=p_up,
        p_down_frac=p_down,
        p_timeout_frac=p_timeout,
        sigma_bar=sigma_bar,
        sigma_h=sigma_h,
        band_frac=band,
    )


def build_distributional_probability_state(
    probability: DistributionalProbability,
    *,
    epistemic_state: dict,
) -> dict:
    status = "OK" if epistemic_state.get("action") == "ALLOW" else "NULL"
    null_reason = None if status == "OK" else epistemic_state.get("reason", "EPISTEMIC_VOID")
    if status == "NULL":
        p_timeout = probability.p_timeout_frac
        p_up = p_down = (1.0 - p_timeout) / 2.0
        up_user = down_user = 0.5
    else:
        p_up = probability.p_up_frac
        p_down = probability.p_down_frac
        p_timeout = probability.p_timeout_frac
        non_timeout_mass = p_up + p_down
        if non_timeout_mass <= 0.0:
            up_user = down_user = 0.5
        else:
            up_user = p_up / non_timeout_mass
            down_user = p_down / non_timeout_mass
    horizon = {
        "p_up_frac": p_up,
        "p_down_frac": p_down,
        "p_timeout_frac": p_timeout,
        "p_up_user_norm_frac": up_user,
        "p_down_user_norm_frac": down_user,
        "confidence_frac": 0.0 if status == "NULL" else 0.5,
        "news_confidence_adj_frac": 0.0,
        "status": status,
        "null_reason": null_reason,
    }
    return {
        "schema_version": "1.1-crypto-probability",
        "horizons": {
            "H_primary": horizon,
            "H_extended": {
                **horizon,
                "confidence_frac": horizon["confidence_frac"]
                * DEFAULT_PHASE1A.probability_extended_confidence_multiplier,
            },
        },
        "calibration_status": DEFAULT_PHASE1A.calibration_status,
        "null_reason": null_reason,
    }
