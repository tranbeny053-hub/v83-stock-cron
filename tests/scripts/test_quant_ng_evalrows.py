from __future__ import annotations

import hashlib
import json
import random
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from pathlib import Path

import pytest

from scripts import resolve_outcomes

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/quant_ng_evalrows.py"
CENSOR = ROOT / "scripts/quant_ng_censor.py"
T = datetime(2025, 1, 1, tzinfo=UTC)
PROBS = {"p_up_frac": "0.60", "p_down_frac": "0.25", "p_timeout_frac": "0.15"}
BASE = {"p_up_frac": "0.30", "p_down_frac": "0.50", "p_timeout_frac": "0.20"}


def stamp(value):
    return value.isoformat().replace("+00:00", "Z")


def _when(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def defaults(tf="1H", horizon=2, cadence=1, band="0.010", end_days=90):
    delta = timedelta(seconds={"15m": 900, "1H": 3600, "4H": 14400, "1D": 86400}[tf])
    q = T + timedelta(days=90)
    end = T + timedelta(days=end_days)
    members = [{"symbol": "AAA", "lineage": "ONE"}]
    forecasts = []
    for j in range(0, 90 * 24, cadence):
        t0 = T + j * delta
        if t0 >= q:
            break
        forecasts.append(
            {
                "symbol": "AAA",
                "lineage": "ONE",
                "reference_close_utc": stamp(t0),
                "candidate": dict(PROBS),
                "baseline": dict(BASE),
            }
        )
    bars = []
    slot = T
    while slot <= end:
        bars.append(
            {"open_utc": stamp(slot - delta), "close_utc": stamp(slot), "close_price": "100"}
        )
        slot += delta
    return {
        "input_id": "ucpe.quant_ng.censor_input.v1",
        "source": "synthetic",
        "quarter_as_of_utc": stamp(T),
        "corpus_end_utc": stamp(end),
        "timeframe": tf,
        "members": members,
        "series": [{"symbol": "AAA", "lineage": "ONE", "bars": bars}],
        "forecasts": forecasts,
    }


def invoke(tmp_path, data=None, *, params=None, edits=None, output_name="out"):
    data = defaults() if data is None else data
    raw = json.dumps(data, separators=(",", ":")).encode()
    ip = tmp_path / "input.json"
    ip.write_bytes(raw)
    output = tmp_path / output_name
    plan = {
        "plan_id": "ucpe.quant_ng.evalrows.v1",
        "input": {"path": str(ip), "sha256": hashlib.sha256(raw).hexdigest()},
        "parameters": params
        or {
            "horizon_bars": 2,
            "cadence_bars": 1,
            "band_frac": "0.010",
            "ruling": "SYNTHETIC_TEST_ONLY",
        },
        "output_dir": str(output),
    }
    plan.update(edits or {})
    pp = tmp_path / "plan.json"
    pp.write_text(json.dumps(plan, separators=(",", ":")))
    proc = subprocess.run(
        [sys.executable, "-I", "-B", str(SCRIPT), str(pp)], cwd=ROOT, capture_output=True, text=True
    )
    return proc, output


def test_labels_match_strict_exact_rule(tmp_path):
    for terminal, expected in [
        ("102", "UP"),
        ("98", "DOWN"),
        ("100", "TIMEOUT"),
        ("101", "TIMEOUT"),
        ("99", "TIMEOUT"),
        ("101.01", "UP"),
        ("98.99", "DOWN"),
    ]:
        data = defaults(horizon=1)
        data["forecasts"] = [data["forecasts"][0]]
        data["series"][0]["bars"] = [
            {
                "open_utc": stamp(T - timedelta(hours=1)),
                "close_utc": stamp(T),
                "close_price": "100",
            },
            {
                "open_utc": stamp(T),
                "close_utc": stamp(T + timedelta(hours=1)),
                "close_price": terminal,
            },
        ]
        data["corpus_end_utc"] = stamp(T + timedelta(days=90))
        proc, out = invoke(
            tmp_path,
            data,
            params={
                "horizon_bars": 1,
                "cadence_bars": 2160,
                "band_frac": "0.01",
                "ruling": "SYNTHETIC_TEST_ONLY",
            },
            output_name="o" + str(len(terminal)) + terminal.replace(".", "x"),
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert json.loads((out / "CENSOR_INPUT.json").read_bytes())["rows"][0]["label"] == expected
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("evalrows_module", SCRIPT)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    rng = random.Random(986)
    checked = 0
    for _ in range(300):
        band = Fraction(rng.randint(1, 100), 10000)
        r = Fraction(rng.randint(-5000, 5000), 100000)
        if abs(abs(r) - band) < Fraction(1, 10**9):
            continue
        exact = module._label(Fraction(1), Fraction(1) + r, band)
        assert resolve_outcomes._realized_label(float(r), float(band)) == exact
        checked += 1
    assert checked >= 200


@pytest.mark.parametrize(
    "case",
    [
        "missing reference",
        "maintenance reference",
        "off grid reference",
        "missing terminal",
        "maintenance terminal",
        "off grid terminal",
        "past quarter",
        "at quarter",
    ],
    ids=[
        "missing reference", "maintenance reference", "off grid reference", "missing terminal",
        "maintenance terminal", "off grid terminal", "past quarter", "at quarter",
    ],
)
def test_resolution_requires_regular_bars_within_quarter(tmp_path, case):
    d = defaults(horizon=1, end_days=91 if case == "past quarter" else 90)
    quarter_case = case in ("past quarter", "at quarter")
    if not quarter_case:
        d["forecasts"] = [d["forecasts"][0]]
    delta = timedelta(hours=1)
    t0 = T if case not in ("past quarter", "at quarter") else T + timedelta(days=90) - delta
    horizon = 2 if case == "past quarter" else 1
    h = t0 + horizon * delta
    forecast = next((f for f in d["forecasts"] if f["reference_close_utc"] == stamp(t0)), None)
    if forecast is None:
        d["forecasts"] = [f for f in d["forecasts"] if f["reference_close_utc"] == stamp(t0)]
    bars = []
    if case not in ("missing reference", "maintenance reference", "off grid reference"):
        bars.append({"open_utc": stamp(t0 - delta), "close_utc": stamp(t0), "close_price": "100"})
    if case == "maintenance reference":
        bars.append(
            {
                "open_utc": stamp(t0 - delta),
                "close_utc": stamp(t0 - timedelta(seconds=1)),
                "close_price": "1",
            }
        )
    if case == "off grid reference":
        bars.append(
            {
                "open_utc": stamp(t0 - delta + timedelta(minutes=7)),
                "close_utc": stamp(t0),
                "close_price": "1",
            }
        )
    if case not in ("missing terminal", "maintenance terminal", "off grid terminal"):
        bars.append({"open_utc": stamp(h - delta), "close_utc": stamp(h), "close_price": "500"})
    if case == "maintenance terminal":
        bars.append(
            {
                "open_utc": stamp(h - delta),
                "close_utc": stamp(h - timedelta(seconds=1)),
                "close_price": "500",
            }
        )
    if case == "off grid terminal":
        bars.append(
            {
                "open_utc": stamp(h - delta + timedelta(minutes=7)),
                "close_utc": stamp(h),
                "close_price": "500",
            }
        )
    d["series"][0]["bars"] = bars
    p, out = invoke(
        tmp_path,
        d,
        params={
            "horizon_bars": horizon,
            "cadence_bars": 1 if quarter_case else 2160,
            "band_frac": "0.01",
            "ruling": "SYNTHETIC_TEST_ONLY",
        },
        output_name="case",
    )
    assert p.returncode == 0, p.stdout + p.stderr
    row = next(
        r
        for r in json.loads((out / "CENSOR_INPUT.json").read_bytes())["rows"]
        if r["reference_close_utc"] == stamp(t0)
    )
    assert row["label"] == ("UP" if case == "at quarter" else None)


def test_record_counts_match_censor_input(tmp_path):
    p, out = invoke(tmp_path)
    assert p.returncode == 0, p.stdout + p.stderr
    rows = json.loads((out / "CENSOR_INPUT.json").read_bytes())["rows"]
    counts = json.loads((out / "EVALROWS_RECORD.json").read_bytes())["counts"]
    labels = [row["label"] for row in rows]
    assert counts["labelled"] == sum(label is not None for label in labels)
    assert counts["unlabelled"] == sum(label is None for label in labels)
    assert counts["labels"] == {label: labels.count(label) for label in ("UP", "DOWN", "TIMEOUT")}


def test_irregular_bar_price_does_not_change_output(tmp_path):
    d = defaults(horizon=1)
    d["forecasts"] = [d["forecasts"][0]]
    d["series"][0]["bars"] = [
        {"open_utc": stamp(T - timedelta(hours=1)), "close_utc": stamp(T), "close_price": "100"},
        {
            "open_utc": stamp(T),
            "close_utc": stamp(T + timedelta(hours=1) - timedelta(seconds=1)),
            "close_price": "1",
        },
    ]
    params = {
        "horizon_bars": 1,
        "cadence_bars": 2160,
        "band_frac": "0.01",
        "ruling": "SYNTHETIC_TEST_ONLY",
    }
    p, a = invoke(tmp_path, d, params=params, output_name="a")
    raw = (a / "CENSOR_INPUT.json").read_bytes()
    d["series"][0]["bars"][1]["close_price"] = "99999"
    p, b = invoke(tmp_path, d, params=params, output_name="b")
    assert p.returncode == 0 and (b / "CENSOR_INPUT.json").read_bytes() == raw


@pytest.mark.parametrize("cadence", [1, 3], ids=["every bar", "every third bar"])
def test_schedule_cadence(tmp_path, cadence):
    d = defaults(tf="1H", cadence=cadence)
    p, o = invoke(
        tmp_path,
        d,
        params={
            "horizon_bars": 2,
            "cadence_bars": cadence,
            "band_frac": "0.01",
            "ruling": "SYNTHETIC_TEST_ONLY",
        },
    )
    assert p.returncode == 0, p.stdout
    rows = json.loads((o / "CENSOR_INPUT.json").read_bytes())["rows"]
    assert len(rows) == (90 * 24 + cadence - 1) // cadence
    assert rows[0]["reference_close_utc"] == stamp(T)
    assert datetime.fromisoformat(
        rows[-1]["reference_close_utc"].replace("Z", "+00:00")
    ) < T + timedelta(days=90)


def test_daily_timeframe_schedule(tmp_path):
    d = defaults(tf="1D", horizon=2, cadence=3)
    p, out = invoke(
        tmp_path,
        d,
        params={
            "horizon_bars": 2,
            "cadence_bars": 3,
            "band_frac": "0.010",
            "ruling": "SYNTHETIC_TEST_ONLY",
        },
    )
    assert p.returncode == 0, p.stdout
    rows = json.loads((out / "CENSOR_INPUT.json").read_bytes())["rows"]
    assert len(rows) == 30
    assert rows[0]["reference_close_utc"] == stamp(T)
    assert rows[-1]["reference_close_utc"] == stamp(T + timedelta(days=87))


def test_composition_with_censor_randomized(tmp_path):
    observed = set()
    for seed in range(25):
        rng = random.Random(seed)
        tf = "1H" if seed % 2 else "4H"
        delta = timedelta(seconds=3600 if tf == "1H" else 14400)
        horizon = rng.randint(1, 6)
        cadence = rng.randint(1, 12)
        d = defaults(tf=tf, horizon=horizon, cadence=cadence, end_days=60 if seed % 2 else 100)
        d["corpus_end_utc"] = stamp(T + timedelta(days=60 if seed % 2 else 100))
        corpus_end = T + timedelta(days=60 if seed % 2 else 100)
        d["series"][0]["bars"] = [
            b
            for b in d["series"][0]["bars"]
            if datetime.fromisoformat(b["close_utc"].replace("Z", "+00:00")) <= corpus_end
        ]
        # Random positive closes exercise each outcome across the fixed seed set.
        for bar in d["series"][0]["bars"]:
            bar["close_price"] = str(rng.randint(50, 150))
        # Add deterministic gaps, maintenance closes and off-grid bars.
        bars = d["series"][0]["bars"]
        d["series"][0]["bars"] = [b for i, b in enumerate(bars) if i % 17 != 0]
        for i in range(1, 5):
            op_grid = T + i * 100 * delta
            d["series"][0]["bars"] = [
                b for b in d["series"][0]["bars"] if b["open_utc"] != stamp(op_grid)
            ]
            d["series"][0]["bars"].append(
                {
                    "open_utc": stamp(op_grid),
                    "close_utc": stamp(op_grid + delta - timedelta(seconds=1)),
                    "close_price": str(rng.randint(1, 300)),
                }
            )
            op = T + i * 100 * delta + timedelta(minutes=7)
            d["series"][0]["bars"].append(
                {
                    "open_utc": stamp(op),
                    "close_utc": stamp(op + delta - timedelta(minutes=1)),
                    "close_price": str(rng.randint(1, 300)),
                }
            )
        # Reuse one ticker across two non-overlapping lineages and include a
        # separate series with a halt followed by resumed bars.
        scheduled_forecasts = d["forecasts"]
        members = [("AAA", "OLD"), ("AAA", "NEW"), ("BBB", "ONE")]
        reuse_date = T + timedelta(days=20)
        old_bars = [b for b in d["series"][0]["bars"] if _when(b["close_utc"]) <= reuse_date]
        new_bars = [b for b in d["series"][0]["bars"] if _when(b["close_utc"]) > reuse_date]
        halt_start = T + timedelta(days=10)
        halt_end = halt_start + 2 * delta
        bbb_bars = [
            b for b in d["series"][0]["bars"]
            if not halt_start < _when(b["close_utc"]) <= halt_end
        ]
        d["members"] = [{"symbol": s, "lineage": line} for s, line in members]
        d["series"] = [
            {"symbol": "AAA", "lineage": "OLD", "bars": old_bars},
            {"symbol": "AAA", "lineage": "NEW", "bars": new_bars},
            {"symbol": "BBB", "lineage": "ONE", "bars": bbb_bars},
        ]
        d["forecasts"] = [
            {**f, "symbol": symbol, "lineage": lineage}
            for f in scheduled_forecasts
            for symbol, lineage in members
        ]
        p, o = invoke(
            tmp_path,
            d,
            params={
                "horizon_bars": horizon,
                "cadence_bars": cadence,
                "band_frac": "0.010",
                "ruling": "SYNTHETIC_TEST_ONLY",
            },
            output_name="p" + str(seed),
        )
        assert p.returncode == 0, p.stdout + p.stderr
        censor_in = json.loads((o / "CENSOR_INPUT.json").read_bytes())
        raw = json.dumps(censor_in, separators=(",", ":")).encode()
        ip = tmp_path / ("ci" + str(seed) + ".json")
        ip.write_bytes(raw)
        cp = tmp_path / ("cp" + str(seed) + ".json")
        cout = tmp_path / ("co" + str(seed))
        plan = {
            "plan_id": "ucpe.quant_ng.censor.v1",
            "input": {"path": str(ip), "sha256": hashlib.sha256(raw).hexdigest()},
            "horizon": {"bars": horizon, "ruling": "SYNTHETIC_TEST_ONLY"},
            "output_dir": str(cout),
        }
        cp.write_text(json.dumps(plan))
        c = subprocess.run(
            [sys.executable, "-I", "-B", str(CENSOR), str(cp)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert c.returncode == 0, c.stdout + c.stderr
        account = json.loads((cout / "CENSOR_ACCOUNTING.json").read_bytes())
        rows = censor_in["rows"]
        assert account["counts"]["instants"] == len(rows)
        resolved = {
            (r["symbol"], r["lineage"], r["reference_close_utc"]): r["label"]
            for r in account["rows"]
            if r["status"] == "RESOLVED"
        }
        labelled = {
            (r["symbol"], r["lineage"], r["reference_close_utc"]): r["label"]
            for r in rows
            if r["label"] is not None
        }
        observed.update(labelled.values())
        assert resolved == labelled
        assert account["counts"]["instants"] == len(rows)
        assert (
            account["counts"]["rows"]
            == account["counts"]["resolved"] + account["counts"]["censored"]
        )
        assert b"close_price" not in (o / "CENSOR_INPUT.json").read_bytes()
        assert b"close_price" not in (o / "EVALROWS_RECORD.json").read_bytes()
    assert observed == {"UP", "DOWN", "TIMEOUT"}


@pytest.mark.parametrize(
    "kind,reason",
    [
        ("source", "source must be synthetic"),
        ("ruling", "parameters require SYNTHETIC_TEST_ONLY"),
        ("digest", "input digest mismatch"),
        ("missing", "missing forecast"),
        ("extra", "forecast not on a scheduled instant"),
        ("duplicate", "duplicate forecast"),
        ("probability", "probabilities do not sum to one"),
        ("price", "invalid input"),
        ("horizon", "invalid plan"),
        ("band", "invalid plan"),
        ("band high", "invalid plan"),
        ("cadence", "invalid plan"),
        ("not empty", "output folder is not empty"),
        ("duplicate bar", "duplicate bar"),
        ("late bar", "bar after corpus end"),
        ("no series", "member has no series"),
    ],
    ids=[
        "real source",
        "wrong ruling",
        "digest mismatch",
        "missing forecast",
        "extra forecast",
        "duplicate forecast",
        "bad probabilities",
        "bad price",
        "large horizon",
        "zero band",
        "band above range",
        "zero cadence",
        "nonempty output",
        "duplicate bar",
        "late bar",
        "member without series",
    ],
)
def test_refusals(tmp_path, kind, reason):
    d = defaults()
    params = {
        "horizon_bars": 2,
        "cadence_bars": 1,
        "band_frac": "0.010",
        "ruling": "SYNTHETIC_TEST_ONLY",
    }
    edits = {}
    if kind == "source":
        d["source"] = "real"
    if kind == "ruling":
        params["ruling"] = "OTHER"
    if kind == "digest":
        edits["input"] = {"path": str(tmp_path / "input.json"), "sha256": "0" * 64}
    if kind == "missing":
        d["forecasts"].pop()
    if kind == "extra":
        d["forecasts"].append(
            {**d["forecasts"][0], "reference_close_utc": stamp(T + timedelta(minutes=1))}
        )
    if kind == "duplicate":
        d["forecasts"].append(d["forecasts"][0])
    if kind == "probability":
        d["forecasts"][0]["candidate"]["p_up_frac"] = "0.59"
    if kind == "price":
        d["series"][0]["bars"][0]["close_price"] = "0"
    if kind == "horizon":
        params["horizon_bars"] = 97
    if kind == "band":
        params["band_frac"] = "0.0"
    if kind == "band high":
        params["band_frac"] = "1.0"
    if kind == "cadence":
        params["cadence_bars"] = 0
    if kind == "duplicate bar":
        d["series"][0]["bars"].append(dict(d["series"][0]["bars"][0]))
    if kind == "late bar":
        d["series"][0]["bars"].append(
            {
                "open_utc": stamp(T + timedelta(days=90)),
                "close_utc": stamp(T + timedelta(days=90, hours=1)),
                "close_price": "1",
            }
        )
    if kind == "no series":
        d["series"] = []
    if kind == "not empty":
        outdir = tmp_path / "out"
        outdir.mkdir()
        (outdir / "occupied").write_text("x")
    p, o = invoke(tmp_path, d, params=params, edits=edits, output_name="out")
    assert p.returncode == 2 and json.loads(p.stdout) == {"status": "REFUSAL", "reason": reason}
    if kind == "not empty":
        assert (o / "occupied").read_text() == "x"
    else:
        assert not o.exists() or not any(o.iterdir())


def test_determinism_permissions_and_inventory_source_scan(tmp_path):
    d = defaults()
    p, a = invoke(tmp_path, d, output_name="aa")
    q, b = invoke(tmp_path, d, output_name="bb")
    assert p.returncode == q.returncode == 0
    for name in ("CENSOR_INPUT.json", "EVALROWS_RECORD.json"):
        assert (a / name).read_bytes() == (b / name).read_bytes()
        assert (a / name).stat().st_mode & 0o777 == 0o444
    source = SCRIPT.read_text()
    import ast

    tree = ast.parse(source)
    forbidden = {"socket", "http", "urllib", "subprocess", "multiprocessing", "os"}
    imports = {
        alias.name.split(".")[0]
        for n in ast.walk(tree)
        if isinstance(n, ast.Import)
        for alias in n.names
    }
    imports |= {
        n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module
    }
    assert not imports & forbidden
