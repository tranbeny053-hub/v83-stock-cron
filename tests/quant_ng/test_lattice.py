from datetime import UTC, datetime, timedelta

import pytest

from crypto_probability_engine.quant_ng import lattice


def test_default_dormancy_and_grid() -> None:
    assert lattice.LATTICE_ENABLED is False
    assert lattice.DECLARED_CELLS == ()
    anchor = lattice.LATTICE_ANCHOR_UTC
    assert lattice.lattice_instants("15m", anchor, anchor + timedelta(hours=2)) == tuple(
        anchor + timedelta(minutes=45 * i) for i in range(3)
    )
    assert lattice.latest_due_instant("15m", anchor + timedelta(minutes=44)) == anchor
    with pytest.raises(ValueError):
        lattice.lattice_instants("1M", anchor, anchor)
    with pytest.raises(ValueError):
        lattice.lattice_instants("15m", datetime(2026, 9, 21), anchor)


@pytest.mark.parametrize(
    "symbol",
    [
        "BTCUSDT",
        "ETHUSDT",
        "WBTCUSDT",
        "BTCUPUSDT",
        "ETHDOWNUSDT",
        "WBETHUSDT",
        "STETHUSDT",
        "SOLBTC",
    ],
)
def test_excluded_bases(symbol: str) -> None:
    with pytest.raises(ValueError):
        lattice.validate_cell(lattice.LatticeCell(symbol, "binance", "15m"))


def test_unmapped_venue_and_valid_cell() -> None:
    with pytest.raises(ValueError):
        lattice.validate_cell(lattice.LatticeCell("SOLUSDT", "unknown", "15m"))
    lattice.validate_cell(lattice.LatticeCell("SOLUSDT", "binance", "15m"))


def test_id_and_gap_reconstruction() -> None:
    cell = lattice.LatticeCell("SOLUSDT", "binance", "15m")
    instant = lattice.LATTICE_ANCHOR_UTC
    ident = lattice.lattice_row_id(cell, instant)
    assert ident.startswith("e3l-") and ident.endswith(":15m:REF")
    assert lattice.lattice_row_id(cell, instant) == ident
    assert (
        lattice.lattice_row_id(lattice.LatticeCell("ADAUSDT", "binance", "15m"), instant) != ident
    )
    grid = (instant, instant + timedelta(minutes=45), instant + timedelta(minutes=90))
    assert lattice.reconstruct_gaps(grid, (grid[0],), (grid[1],)) == (grid[2],)


def test_step_disabled() -> None:
    with pytest.raises(lattice.LatticeDisabled):
        lattice.lattice_step(
            datetime.now(UTC),
            config=None,
            fetch_snapshot=None,
            fetch_window=None,
            store=None,
            app_clock=None,
            state={},
        )
