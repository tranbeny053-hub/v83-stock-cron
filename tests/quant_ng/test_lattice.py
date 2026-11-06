import ast
import json
import os
import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from crypto_probability_engine.execution_realism.realism import compute_execution_realism
from crypto_probability_engine.features.liquidity_depth import compute_liquidity_depth
from crypto_probability_engine.quant_ng import lattice, reference, reference_v1d, windows
from crypto_probability_engine.targets.contract_v1 import validate_v1
from tests.fixtures.market_data import make_snapshot
from tests.quant_ng.test_reference import SPEC
from tests.quant_ng.test_reference import _candles as intraday_candles
from tests.quant_ng.test_reference_v1d import _candles as daily_candles

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "lattice_row_v1.json"
FIXED_CORE = datetime(2026, 10, 1, 0, 0, 6, tzinfo=UTC)
FIXED_ISSUED = datetime(2026, 10, 1, 0, 0, 7, tzinfo=UTC)
TEST_PRIORS = reference.ReferencePriors((0.4, 0.4, 0.4))


def real_inputs():
    cell = lattice.LatticeCell("SOL/USDT", "binance", "4H")
    instant = lattice.LATTICE_ANCHOR_UTC + timedelta(hours=12 * 20)
    snapshot = make_snapshot(provider="binance", symbol="SOL/USDT", timeframe="4H")
    shift = instant - snapshot.candles[-1].close_time_utc
    candles = tuple(
        replace(
            candle,
            open_time_utc=candle.open_time_utc + shift,
            close_time_utc=candle.close_time_utc + shift,
        )
        for candle in snapshot.candles
    )
    snapshot = replace(snapshot, candles=candles, as_of_utc=instant + timedelta(seconds=5))
    window = windows.Window(
        provider=snapshot.provider,
        normalized_symbol="SOL/USDT",
        timeframe="4H",
        candles=candles,
        source=windows.WindowSource.SNAPSHOT,
        requests=0,
    )
    spec = reference.load_reference_spec(
        json.loads((ROOT / "ops/quant_ng/REFERENCE_SPEC_v1.json").read_text())
    )
    config = lattice.PilotConfig(
        cells=(cell,),
        priors={cell: TEST_PRIORS},
        reference_prior_id="test-prior",
        recipe_id="test-recipe",
        reference_spec=spec,
        reference_spec_v1d=None,
    )
    triplet = reference.compute_reference(
        candles,
        timeframe="4H",
        band_frac=lattice.decision_band_frac(snapshot),
        spec=spec,
        priors=TEST_PRIORS,
    )
    return cell, instant, snapshot, window, config, triplet


def build_real_row():
    cell, instant, snapshot, window, config, triplet = real_inputs()
    return lattice.build_lattice_row(
        cell,
        instant,
        snapshot,
        window,
        triplet,
        config=config,
        core_computed_at=FIXED_CORE,
        issued_at=FIXED_ISSUED,
    )


def generate_lattice_row_fixture():
    if os.environ.get("UCPE_GENERATE_NG4_FIXTURE") != "1":
        raise RuntimeError("Set UCPE_GENERATE_NG4_FIXTURE=1 to generate this fixture")
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(
        json.dumps(
            {"schema": "ucpe.lattice_row_fixture.v1", "store_row": build_real_row()}, indent=2
        )
        + "\n"
    )


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


def test_store_key_constants_match_authored_migration() -> None:
    sql = (ROOT / "migrations/authored/0019_lattice_evidence.sql").read_text()
    arrays = re.findall(r"v_keys\s+text\[\]\s*:=\s*ARRAY\[(.*?)\];", sql, re.S)
    assert len(arrays) == 2
    parsed = [tuple(re.findall(r"'([^']+)'", array)) for array in arrays]
    assert parsed == [lattice.STORE_ROW_KEYS, lattice.MISSED_ENTRY_KEYS]


def test_builder_matches_store_contract_and_tc_v1() -> None:
    row = build_real_row()
    cell, instant, snapshot, *_ = real_inputs()
    assert tuple(row) == lattice.STORE_ROW_KEYS
    json.dumps(row)
    expected_band = compute_execution_realism(compute_liquidity_depth(snapshot.order_book))[
        "round_trip_cost_frac"
    ]
    assert row["decision_band_frac"] == expected_band
    assert row["evaluation_population"] == "E1_OPERATIONAL"
    assert row["timing_class"] == "NOT_APPLICABLE"
    assert row["evidence_use"] == "TEST_ONLY"
    assert row["arm"] == "REF"
    assert row["protocol_version"] == "E3_LATTICE_V1"
    assert row["reference_close_utc"] == row["lattice_instant_utc"] == instant.isoformat()
    assert row["data_source"] == row["reference_venue"] == "BINANCE_PUBLIC"
    assert validate_v1(row) == ()
    assert cell.venue == snapshot.provider


def test_frozen_fixture_matches_builder() -> None:
    assert json.loads(FIXTURE.read_text())["store_row"] == build_real_row()


def test_pilot_bars_required_exact_boundary():
    priors = reference.ReferencePriors((0.5, 0.5, 0.5))
    for timeframe in ("15m", "1H", "4H"):
        count = lattice.PILOT_BARS_REQUIRED[timeframe]
        candles = intraday_candles(count, timeframe)
        assert reference.compute_reference(candles, timeframe=timeframe, band_frac=0.05,
                                           spec=SPEC, priors=priors)
        with pytest.raises(reference.ReferenceUnavailable, match="full reference memory"):
            reference.compute_reference(candles[:-1], timeframe=timeframe, band_frac=0.05,
                                       spec=SPEC, priors=priors)
    spec_path = ROOT / "ops/quant_ng/REFERENCE_SPEC_v1d.json"
    spec_1d = reference_v1d.load_reference_spec_v1d(json.loads(spec_path.read_text()))
    daily = daily_candles([100.0 + i for i in range(371)])
    assert reference_v1d.compute_reference_v1d(daily, timeframe="1D", band_frac=0.05,
                                               spec=spec_1d, prior=0.5)
    with pytest.raises(reference.ReferenceUnavailable, match="full reference memory"):
        reference_v1d.compute_reference_v1d(daily[:-1], timeframe="1D", band_frac=0.05,
                                             spec=spec_1d, prior=0.5)


def test_planned_slots_cover_every_15m_alignment_and_prior_prefix():
    start = datetime(2026, 11, 9, tzinfo=UTC)
    totals = set()
    for offset in range(0, 3 * 24 * 60, 15):
        counts = lattice.planned_slots(start + timedelta(minutes=offset))
        assert counts["15m"] == 448
        assert counts["1H"] == 112
        assert counts["4H"] == 28
        assert counts["1D"] in (4, 5)
        total = sum(counts.values())
        totals.add(total)
        assert total < lattice.PILOT_CAPACITY_WARN < lattice.PILOT_CAPACITY_MAX
    assert totals <= {592, 593}
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(lattice, "PILOT_PRIOR_ID", "bad-prior")
        with pytest.raises(ValueError, match="placeholder prefix"):
            lattice.pilot_config(None, None)
    finally:
        monkeypatch.undo()


def test_store_contract_rejects_late_window_and_snapshot_mismatch() -> None:
    cell, instant, snapshot, window, config, triplet = real_inputs()
    late = replace(
        window,
        candles=tuple(
            replace(
                candle,
                open_time_utc=candle.open_time_utc + timedelta(hours=4),
                close_time_utc=candle.close_time_utc + timedelta(hours=4),
            )
            for candle in window.candles
        ),
    )
    with pytest.raises(lattice.LatticeIssue) as issue:
        lattice.build_lattice_row(
            cell,
            instant,
            snapshot,
            late,
            triplet,
            config=config,
            core_computed_at=FIXED_CORE,
            issued_at=FIXED_ISSUED,
        )
    assert issue.value.reason == "WINDOW_UNAVAILABLE"


def test_missed_entry_has_exact_store_shape() -> None:
    cell, instant, *_ = real_inputs()
    entry = lattice.build_missed_entry(cell, instant, "FETCH_FAILED")
    assert tuple(entry) == lattice.MISSED_ENTRY_KEYS
    assert entry["lattice_run_id"] == lattice.lattice_row_id(cell, instant).split(":")[0]
    assert entry["normalized_symbol"] == "SOL/USDT"
    assert entry["reference_venue"] == "BINANCE_PUBLIC"


def test_lattice_guards() -> None:
    module = ROOT / "src"
    scripts = ROOT / "scripts"
    for base in (module, scripts):
        for path in base.rglob("*.py"):
            if path.name == "lattice.py" and "quant_ng" in path.parts:
                continue
            # The NG4 pilot build (owner NG4-PILOT INPUTS, 2026-11-06): its dormant runner is
            # the one importer of the lattice and its store.
            if path == module / "crypto_probability_engine/lattice_pilot.py":
                continue
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    assert not (node.module or "").endswith(
                        ("quant_ng.lattice", "persistence.lattice_store")
                    )
                elif isinstance(node, ast.Import):
                    assert all(
                        not alias.name.endswith(("quant_ng.lattice", "persistence.lattice_store"))
                        for alias in node.names
                    )
    texts = {path: path.read_text() for path in module.rglob("*.py")}
    hits = [str(path.relative_to(module)) for path, text in texts.items() if "ucpe_lattice" in text]
    assert hits == ["crypto_probability_engine/persistence/lattice_store.py"]
    # The only prior values in src/ are the owner's TEST_ONLY placeholders (2026-11-06), in
    # quant_ng/lattice.py.
    prior_lines = [
        (str(path.relative_to(module)), line)
        for path, text in texts.items()
        for line in text.splitlines()
        if "ReferencePriors(" in line or "pi0=" in line
    ]
    assert [line for _path, line in prior_lines if "class ReferencePriors" not in line] == [
        "PILOT_PRIOR_INTRADAY = reference.ReferencePriors((0.5, 0.5, 0.5))"
    ]
    assert {path for path, line in prior_lines if "class ReferencePriors" not in line} == {
        "crypto_probability_engine/quant_ng/lattice.py"
    }
    source = (module / "crypto_probability_engine/quant_ng/lattice.py").read_text()
    assert "LATTICE_ENABLED = False" in source
    assert "DECLARED_CELLS: tuple = ()" in source


class FakeStore:
    def __init__(self, row_status="INSERTED", missed_status="LOGGED"):
        self.row_status = row_status
        self.missed_status = missed_status
        self.rows = []
        self.missed = []
        self.receipts = []

    def record_row(self, row):
        json.dumps(row)
        assert tuple(row) == lattice.STORE_ROW_KEYS
        self.rows.append(row)
        return self.row_status

    def record_missed(self, entry):
        json.dumps(entry)
        assert tuple(entry) == lattice.MISSED_ENTRY_KEYS
        self.missed.append(entry)
        return self.missed_status

    def capture_commit_receipts(self, limit):
        self.receipts.append(limit)
        return 0


def run_step(
    monkeypatch,
    *,
    config,
    snapshot_fn=None,
    window_fn=None,
    store=None,
    state=None,
    now=None,
    inputs=None,
    fresh_after=None,
):
    cell, instant, snapshot, window = (inputs or real_inputs())[:4]
    monkeypatch.setattr(lattice, "LATTICE_ENABLED", True)
    store = store or FakeStore()
    result = lattice.lattice_step(
        now or instant + timedelta(seconds=5),
        config=config,
        fetch_snapshot=snapshot_fn or (lambda _: snapshot),
        fetch_window=window_fn or (lambda *_: window),
        store=store,
        app_clock=lambda: FIXED_CORE,
        state=state if state is not None else {},
        fresh_after=fresh_after,
    )
    assert store.receipts == [1000]
    return cell, instant, store, result


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("stale", "STALE_SNAPSHOT"),
        ("fetch", "FETCH_FAILED"),
        ("window", "WINDOW_UNAVAILABLE"),
        ("late", "WINDOW_UNAVAILABLE"),
        ("no_prior", "REFERENCE_UNAVAILABLE"),
        ("bad_band", "REFERENCE_UNAVAILABLE"),
    ],
)
def test_step_records_contract_missed_entries(monkeypatch, failure, expected):
    cell, instant, snapshot, window, config, _ = real_inputs()

    def snap_fn(_):
        return snapshot

    def win_fn(*_):
        return window

    if failure == "stale":

        def snap_fn(_):
            return replace(snapshot, as_of_utc=instant - timedelta(seconds=1))
    elif failure == "fetch":

        def snap_fn(_):
            raise RuntimeError("offline fake")
    elif failure == "window":

        def win_fn(*_):
            raise windows.WindowUnavailable(windows.UnavailableReason.WINDOW_MALFORMED, "fake")
    elif failure == "late":
        shifted = tuple(
            replace(
                c,
                open_time_utc=c.open_time_utc + timedelta(hours=4),
                close_time_utc=c.close_time_utc + timedelta(hours=4),
            )
            for c in window.candles
        )

        def win_fn(*_):
            return replace(window, candles=shifted)
    elif failure == "no_prior":
        config = replace(config, priors={})
    elif failure == "bad_band":

        def bad_band(_):
            raise lattice.LatticeIssue("REFERENCE_UNAVAILABLE")

        monkeypatch.setattr(lattice, "decision_band_frac", bad_band)
    _, _, store, _ = run_step(
        monkeypatch,
        config=config,
        snapshot_fn=snap_fn,
        window_fn=win_fn,
        inputs=(cell, instant, snapshot, window),
    )
    assert [entry["reason"] for entry in store.missed] == [expected]
    assert store.rows == []


@pytest.mark.parametrize("status", ["CAPACITY_STOP", "CAPACITY_UNSET"])
def test_step_stops_on_capacity_and_captures_once(monkeypatch, status):
    _, _, store, result = run_step(
        monkeypatch, config=real_inputs()[4], store=FakeStore(row_status=status)
    )
    assert result["stopped"] is True
    assert len(store.rows) == 1
    assert store.receipts == [1000]


def test_step_skipped_instants_are_bounded_and_row_id_ignores_prior(monkeypatch):
    cell, instant, _, _, config, _ = real_inputs()
    store = FakeStore(row_status="CAPACITY_STOP")
    state = {cell: instant - timedelta(days=1000)}
    _, _, store, result = run_step(monkeypatch, config=config, store=store, state=state)
    assert len(store.missed) == 1000
    assert all(entry["reason"] == "NOT_ISSUED" for entry in store.missed)
    assert result["stopped"] is True
    other = replace(config, priors={cell: reference.ReferencePriors((0.1, 0.2, 0.3))})
    assert lattice.lattice_row_id(cell, instant) == lattice.lattice_row_id(other.cells[0], instant)


def test_pilot_recipe_and_methodology_identities():
    assert lattice.PILOT_RECIPE_ID == "reference-daytype-v1"
    assert lattice.PILOT_RECIPE_ID_1D == "reference-daytype-v1d"
    cell = replace(real_inputs()[0], timeframe="1D")
    config = replace(real_inputs()[4], cells=(cell,), recipe_id_1d="custom-v1d")
    row = lattice.build_lattice_row(
        cell, *real_inputs()[1:4], real_inputs()[5], config=config,
        core_computed_at=FIXED_CORE, issued_at=FIXED_ISSUED,
    )
    assert row["recipe_id"] == "custom-v1d"
    assert row["methodology_version"] == "reference-daytype-v1d"


def test_planned_slot_counts():
    start = datetime(2026, 11, 9, tzinfo=UTC)
    slots = lattice.planned_slots(start)
    assert slots == {"15m": 448, "1H": 112, "4H": 28, "1D": 4}
    assert sum(slots.values()) == 592 < 600 < 1200


def test_cold_start_fresh_after_boundary(monkeypatch):
    cell, instant, _, _, config, _ = real_inputs()
    # A process that began before this instant's wake (fresh_after < instant) issues it.
    state = {}
    _, _, store, _ = run_step(monkeypatch, config=config, state=state,
                              now=instant + timedelta(seconds=25),
                              fresh_after=instant - timedelta(seconds=1))
    assert len(store.rows) == 1
    # One that began after it (fresh_after >= instant) leaves it a gap and seeds the state.
    state = {}
    _, _, store, _ = run_step(monkeypatch, config=config, state=state,
                              now=instant + timedelta(seconds=25), fresh_after=instant)
    assert store.rows == [] and store.missed == []
    assert state[cell] == instant
