"""The correction in docs/R2_ZERO_DRIFT_GATE_AND_DISPLAY.md §7, recomputed from the tables.

A model with no location term still carries a directional split, because its empirical shape tables
are skewed. Every figure in the correction's table is recomputed here, so the document cannot drift
from the constants it describes.
"""

from __future__ import annotations

import re
from pathlib import Path

from crypto_probability_engine.quant.distributional_v2_tables import CELLS
from crypto_probability_engine.quant.probability_distributional import (
    FROZEN_B3_PARAMETERS,
)
from crypto_probability_engine.quant.probability_distributional import (
    _empirical_cdf as v1_cdf,
)
from crypto_probability_engine.quant.probability_distributional_v2 import (
    _empirical_cdf as v2_cdf,
)

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "R2_ZERO_DRIFT_GATE_AND_DISPLAY.md"
RATIOS = (0.25, 0.5, 1.0, 2.0)
SESSIONS = ("session 00-07 UTC", "session 08-15 UTC", "session 16-23 UTC")


def _up_share(cdf, ratio: float) -> float:
    down = cdf(-ratio)
    up = 1.0 - cdf(ratio)
    return up / (up + down)


def _computed() -> dict[tuple[str, str, str], tuple[str, ...]]:
    rows = {}
    for symbol, cells in CELLS.items():
        for timeframe, cell in cells.items():
            for index, (knots, probabilities, n) in enumerate(cell["tables"]):
                table = SESSIONS[index] if cell["shape"] == "G4_session" else "one table"

                def cdf(value, knots=knots, probabilities=probabilities, n=n):
                    return v2_cdf(value, knots, probabilities, n)

                rows[("distributional-v2", f"{symbol} {timeframe}", table)] = tuple(
                    f"{_up_share(cdf, ratio):.4f}" for ratio in RATIOS
                )
    for timeframe, parameters in FROZEN_B3_PARAMETERS.items():

        def cdf(value, table=parameters["table"], n=int(parameters["n"])):
            return v1_cdf(value, table, n)

        rows[("distributional-v1", f"every symbol {timeframe}", "one table")] = tuple(
            f"{_up_share(cdf, ratio):.4f}" for ratio in RATIOS
        )
    return rows


def _documented() -> dict[tuple[str, str, str], tuple[str, ...]]:
    section = DOC.read_text(encoding="utf-8").split("## 7. Correction", 1)[1]
    rows = {}
    for line in section.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 7 and cells[0].startswith("distributional-v"):
            rows[tuple(cells[:3])] = tuple(cells[3:])
    return rows


def test_every_documented_split_is_the_one_the_tables_produce() -> None:
    documented = _documented()
    computed = _computed()
    assert documented == computed
    assert len(computed) == 13


def test_the_split_is_never_even_and_leans_both_ways() -> None:
    shares = [float(value) for values in _computed().values() for value in values]
    assert all(share != 0.5 for share in shares)
    assert min(shares) < 0.49 and max(shares) > 0.54
    header = DOC.read_text(encoding="utf-8").split("## 1.", 1)[0]
    assert re.search(r"about 48–54% up", header)


# Where the split leans DOWN (share below 0.5), as the document's prose lists it.
DOWN_LEANING = {
    ("distributional-v2", "BTC/USDT 15m", "one table"): (2.0,),
    ("distributional-v2", "BTC/USDT 1H", "session 08-15 UTC"): (1.0,),
    ("distributional-v2", "ETH/USDT 15m", "one table"): (1.0, 2.0),
    ("distributional-v2", "ETH/USDT 1H", "session 08-15 UTC"): RATIOS,
    ("distributional-v1", "every symbol 15m", "one table"): (1.0, 2.0),
}


def test_the_split_leans_down_exactly_where_the_document_says() -> None:
    leaning = {}
    for key, values in _computed().items():
        ratios = tuple(
            ratio for ratio, value in zip(RATIOS, values, strict=True) if float(value) < 0.5
        )
        if ratios:
            leaning[key] = ratios
    assert leaning == DOWN_LEANING
    prose = DOC.read_text(encoding="utf-8").split("## 7. Correction", 1)[1]
    for line in (
        "15m at z = 1.0 and 2.0 (for BTC under v2, only at 2.0);",
        "ETH 1H in the 08-15 session, at every ratio;",
        "BTC 1H in that session, at z = 1.0.",
    ):
        assert line in prose


def test_the_tables_are_asymmetric_so_zero_location_is_not_symmetry() -> None:
    for cells in CELLS.values():
        for cell in cells.values():
            for knots, _, _ in cell["tables"]:
                assert max(abs(knots[i] + knots[-1 - i]) for i in range(len(knots))) > 0.1
