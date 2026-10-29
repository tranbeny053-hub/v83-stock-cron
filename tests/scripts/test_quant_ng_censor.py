from __future__ import annotations

import ast
import hashlib
import importlib.util
import itertools
import json
import random
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/quant_ng_censor.py"
T = datetime(2025, 1, 1, tzinfo=UTC)
DELTA = timedelta(minutes=15)
PROBS = {"p_up_frac": "0.60", "p_down_frac": "0.25", "p_timeout_frac": "0.15"}


def stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def base_input(
    *,
    bars: list[tuple[datetime, datetime]] | None = None,
    rows=None,
    members=None,
    series=None,
    end=None,
):
    if members is None:
        members = [{"symbol": "AAA", "lineage": "ONE"}]
    if series is None:
        series = [
            {
                "symbol": "AAA",
                "lineage": "ONE",
                "bars": [{"open_utc": stamp(a), "close_utc": stamp(b)} for a, b in (bars or [])],
            }
        ]
    return {
        "input_id": "ucpe.quant_ng.censor_input.v1",
        "source": "synthetic",
        "quarter_as_of_utc": stamp(T),
        "corpus_end_utc": stamp(end or T + timedelta(days=90)),
        "timeframe": "15m",
        "members": members,
        "series": series,
        "rows": rows or [],
    }


def instant(t0: datetime, *, symbol="AAA", lineage="ONE", label=None, probs=None):
    return {
        "symbol": symbol,
        "lineage": lineage,
        "reference_close_utc": stamp(t0),
        "label": label,
        "candidate": probs or PROBS,
        "baseline": probs or {"p_up_frac": "0.30", "p_down_frac": "0.50", "p_timeout_frac": "0.20"},
    }


def invoke(tmp_path: Path, data: dict, *, horizon=2, output_name="out", plan_changes=None):
    input_path = tmp_path / "input.json"
    raw = json.dumps(data, separators=(",", ":")).encode()
    input_path.write_bytes(raw)
    output = tmp_path / output_name
    plan = {
        "plan_id": "ucpe.quant_ng.censor.v1",
        "input": {"path": str(input_path), "sha256": hashlib.sha256(raw).hexdigest()},
        "horizon": {"bars": horizon, "ruling": "SYNTHETIC_TEST_ONLY"},
        "output_dir": str(output),
    }
    plan.update(plan_changes or {})
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, separators=(",", ":")))
    proc = subprocess.run(
        [sys.executable, "-I", "-B", str(SCRIPT), str(plan_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return proc, output


@pytest.mark.parametrize(
    "name,bars,t0,end,label,status,reason",
    [
        (
            "resolved",
            [(T - DELTA, T), (T + DELTA, T + 2 * DELTA)],
            T,
            T + timedelta(days=90),
            "UP",
            "RESOLVED",
            None,
        ),
        ("span_end", [(T - DELTA, T)], T, T + DELTA, None, "CENSORED", "span_end"),
        (
            "halt",
            [(T - DELTA, T), (T + 3 * DELTA, T + 4 * DELTA)],
            T,
            T + timedelta(days=90),
            None,
            "CENSORED",
            "halt",
        ),
        ("delisting", [(T - DELTA, T)], T, T + timedelta(days=3), None, "CENSORED", "delisting"),
        ("reuse", [(T - DELTA, T)], T, T + timedelta(days=90), None, "CENSORED", "unknown"),
        ("recent", [(T - DELTA, T), (T, T + DELTA)], T, T + 2 * DELTA, None, "CENSORED", "unknown"),
        (
            "maintenance",
            [(T - DELTA, T), (T + DELTA, T + 2 * DELTA - timedelta(seconds=1))],
            T,
            T + timedelta(days=90),
            None,
            "CENSORED",
            "delisting",
        ),
        (
            "irregular_after",
            [
                (T - DELTA, T),
                (T + 2 * DELTA, T + 3 * DELTA - timedelta(seconds=1)),
            ],
            T,
            T + timedelta(days=90),
            None,
            "CENSORED",
            "unknown",
        ),
        ("span_precedence", [(T - DELTA, T)], T, T + DELTA, None, "CENSORED", "span_end"),
        (
            "halt_precedence",
            [(T - DELTA, T), (T + 3 * DELTA, T + 4 * DELTA)],
            T,
            T + timedelta(days=90),
            None,
            "CENSORED",
            "halt",
        ),
    ],
    ids=[
        "resolved",
        "span end",
        "halt",
        "delisting",
        "reuse",
        "recent",
        "maintenance",
        "irregular after",
        "span precedence",
        "halt precedence",
    ],
)
def test_taxonomy_and_order(
    tmp_path: Path, name, bars, t0, end, label, status, reason
):
    members = [{"symbol": "AAA", "lineage": "ONE"}]
    if name in {"reuse", "halt_precedence", "span_precedence"}:
        members.append({"symbol": "AAA", "lineage": "TWO"})
        series = [
            {
                "symbol": "AAA",
                "lineage": "ONE",
                "bars": [{"open_utc": stamp(a), "close_utc": stamp(b)} for a, b in bars],
            },
            {"symbol": "AAA", "lineage": "TWO", "bars": []},
        ]
    else:
        series = None
    data = base_input(
        bars=bars, rows=[instant(t0, label=label)], members=members, series=series, end=end
    )
    proc, output = invoke(tmp_path, data)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    row = json.loads((output / "CENSOR_ACCOUNTING.json").read_bytes())["rows"][0]
    assert (row["status"], row["censor_reason"]) == (status, reason), name


def test_quarter_partition_and_no_rows(tmp_path: Path):
    q = T + timedelta(days=90)
    data = base_input(
        rows=[
            instant(q - 2 * DELTA, label="UP"),
            instant(q - DELTA),
            instant(T + 10 * DELTA),
            instant(q - DELTA, symbol="BBB"),
        ],
        bars=[(q - 3 * DELTA, q - 2 * DELTA), (q - DELTA, q)],
        members=[{"symbol": "AAA", "lineage": "ONE"}, {"symbol": "BBB", "lineage": "ONE"}],
        series=[
            {
                "symbol": "AAA",
                "lineage": "ONE",
                "bars": [
                    {"open_utc": stamp(q - 3 * DELTA), "close_utc": stamp(q - 2 * DELTA)},
                    {"open_utc": stamp(q - DELTA), "close_utc": stamp(q)},
                ],
            },
            {"symbol": "BBB", "lineage": "ONE", "bars": []},
        ],
    )
    proc, output = invoke(tmp_path, data, horizon=2)
    assert proc.returncode == 0
    body = json.loads((output / "CENSOR_ACCOUNTING.json").read_bytes())
    counts = body["counts"]
    assert counts["quarter_end"] == 2 and counts["no_reference_bar"] == 1
    assert counts["instants"] == counts["quarter_end"] + counts["no_reference_bar"] + counts["rows"]
    assert counts["rows"] == counts["resolved"] + counts["censored"]
    assert counts["censored"] == sum(counts["censored_by_reason"].values())
    assert body["no_rows_in_quarter"] == [{"symbol": "BBB", "lineage": "ONE"}]


def test_classification_read_limit(tmp_path: Path):
    q = T + timedelta(days=90)
    t0 = q - 2 * DELTA
    # The bar after the quarter is invisible; the latest visible close is
    # within H * delta of Q, so censoring stays unknown instead of halt.
    data = base_input(
        rows=[instant(t0)],
        bars=[
            (t0 - DELTA, t0),
            (q - DELTA, q - DELTA + timedelta(seconds=1)),
            (q, q + DELTA),
        ],
        end=q + timedelta(days=2),
    )
    proc, output = invoke(tmp_path, data, horizon=2)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    body = json.loads((output / "CENSOR_ACCOUNTING.json").read_bytes())
    assert body["classification_read_limit_utc"] == stamp(q)
    assert body["rows"][0]["censor_reason"] == "unknown"

    # A later regular close inside W still identifies a halt.
    t0 = q - 5 * DELTA
    data = base_input(
        rows=[instant(t0)],
        bars=[(t0 - DELTA, t0), (t0 + 3 * DELTA, t0 + 4 * DELTA)],
        end=q + timedelta(days=2),
    )
    proc, output = invoke(tmp_path, data, horizon=2, output_name="inside")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    body = json.loads((output / "CENSOR_ACCOUNTING.json").read_bytes())
    assert body["rows"][0]["censor_reason"] == "halt"
    assert body["classification_read_limit_utc"] == stamp(q)

    # When corpus end precedes quarter end, W is E.
    e = T + timedelta(days=3)
    data = base_input(rows=[instant(T)], bars=[(T - DELTA, T)], end=e)
    proc, output = invoke(tmp_path, data, horizon=2, output_name="corpus")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    body = json.loads((output / "CENSOR_ACCOUNTING.json").read_bytes())
    assert body["classification_read_limit_utc"] == stamp(e)


@pytest.mark.parametrize("offset", [-1, 90], ids=["before quarter", "at quarter"])
def test_reference_instant_must_be_inside_quarter(tmp_path: Path, offset: int):
    t0 = T + timedelta(days=offset)
    data = base_input(rows=[instant(t0)])
    proc, output = invoke(tmp_path, data)
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["reason"] == "row outside the quarter"
    assert not output.exists()


@pytest.mark.parametrize(
    "case",
    [
        "censored_label",
        "quarter_label",
        "missing_ref_label",
        "resolved_missing",
        "sum_low",
        "sum_high",
        "real_source",
        "wrong_horizon",
        "digest",
        "uppercase_digest",
        "duplicate_bar",
        "bar_after_end",
        "off_grid",
        "nonmember",
    ],
    ids=[
        "censored label",
        "quarter label",
        "missing reference label",
        "resolved missing",
        "sum low",
        "sum high",
        "real source",
        "wrong horizon",
        "digest mismatch",
        "uppercase digest",
        "duplicate bar",
        "bar after end",
        "off grid",
        "nonmember",
    ],
)
def test_refusals(tmp_path: Path, case: str):
    bars = [(T - DELTA, T)]
    data = base_input(bars=bars, rows=[instant(T, label=None)])
    changes = None
    expected = "invalid input"
    if case == "censored_label":
        data["rows"] = [instant(T, label="UP")]
        expected = "label on an unresolved row"
    elif case == "quarter_label":
        data["rows"] = [instant(T + timedelta(days=90) - DELTA, label="UP")]
        expected = "label on an unresolved row"
    elif case == "missing_ref_label":
        data["rows"] = [instant(T + 10 * DELTA, label="UP")]
        expected = "label on an unresolved row"
    elif case == "resolved_missing":
        data["series"][0]["bars"].append(
            {"open_utc": stamp(T + DELTA), "close_utc": stamp(T + 2 * DELTA)}
        )
        expected = "resolved row without a label"
    elif case in {"sum_low", "sum_high"}:
        data["rows"][0]["candidate"] = {
            "p_up_frac": "0.30",
            "p_down_frac": "0.30",
            "p_timeout_frac": "0.39" if case == "sum_low" else "0.41",
        }
        expected = "probabilities do not sum to one"
    elif case == "real_source":
        data["source"] = "real"
        expected = "source must be synthetic"
    elif case == "wrong_horizon":
        changes = {"horizon": {"bars": 2, "ruling": "UNRULED"}}
        expected = "horizon requires SYNTHETIC_TEST_ONLY"
    elif case in {"digest", "uppercase_digest"}:
        digest = "A" * 64 if case == "uppercase_digest" else "0" * 64
        changes = {"input": {"path": str(tmp_path / "input.json"), "sha256": digest}}
        expected = "invalid plan" if case == "uppercase_digest" else "input digest mismatch"
    elif case == "duplicate_bar":
        data["series"][0]["bars"].append(data["series"][0]["bars"][0])
        expected = "duplicate bar"
    elif case == "bar_after_end":
        data["corpus_end_utc"] = stamp(T + DELTA)
        data["series"][0]["bars"].append(
            {"open_utc": stamp(T + DELTA), "close_utc": stamp(T + 2 * DELTA)}
        )
        expected = "bar after corpus end"
    elif case == "off_grid":
        data["rows"] = [instant(T + timedelta(minutes=1))]
        expected = "reference instant off grid"
    elif case == "nonmember":
        data["rows"] = [instant(T, symbol="BBB")]
        expected = "row is not a member"
    proc, output = invoke(tmp_path, data, plan_changes=changes)
    assert proc.returncode == 2
    assert json.loads(proc.stdout) == {"status": "REFUSAL", "reason": expected}
    assert not output.exists()


def _load_tool():
    spec = importlib.util.spec_from_file_location("quant_ng_censor_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _independent_helpers():
    sys.path.insert(0, str(ROOT / "src"))
    from crypto_probability_engine.calibration.schemas import (
        RELIABILITY_BUCKETS,
        TOP_LABEL_TIE_ORDER,
    )

    labels = tuple(TOP_LABEL_TIE_ORDER)
    buckets = tuple((Fraction(str(a)), Fraction(str(b))) for a, b in RELIABILITY_BUCKETS)

    def brier(probabilities, label):
        return sum(((probabilities[name] - int(name == label)) ** 2 for name in labels), Fraction())

    def top_label(probabilities):
        chosen = labels[0]
        for name in labels[1:]:
            if probabilities[name] > probabilities[chosen]:
                chosen = name
        return chosen

    def bucket(probability):
        if probability == 1:
            return len(buckets) - 1
        return next(i for i, (start, end) in enumerate(buckets) if start <= probability < end)

    def ece(rows, arm):
        gaps = [Fraction() for _ in buckets]
        for row in rows:
            probs = row[arm]
            top = top_label(probs)
            gaps[bucket(probs[top])] += probs[top] - int(row["label"] == top)
        return sum(map(abs, gaps), Fraction()) / len(rows)

    return labels, buckets, brier, top_label, bucket, ece


def test_exact_bounds_against_independent_enumeration():
    tool = _load_tool()
    labels, _, brier, top_label, bucket, ece = _independent_helpers()
    corner_is_loose = False
    for seed in range(25):
        rng = random.Random(seed)
        rows = []
        resolved_count = rng.randint(3, 6)
        censored_count = rng.randint(0, 4)
        for i in range(resolved_count + censored_count):

            def random_probs(randomizer):
                cuts = sorted(randomizer.sample(range(101), 2))
                cents = [cuts[0], cuts[1] - cuts[0], 100 - cuts[1]]
                randomizer.shuffle(cents)
                return dict(zip(labels, (Fraction(v, 100) for v in cents), strict=True))

            candidate = random_probs(rng)
            baseline = random_probs(rng)
            while top_label(candidate) == top_label(baseline) or bucket(
                candidate[top_label(candidate)]
            ) == bucket(baseline[top_label(baseline)]):
                baseline = random_probs(rng)
            rows.append(
                {
                    "candidate": candidate,
                    "baseline": baseline,
                    "label": rng.choice(labels) if i < resolved_count else None,
                    "status": "RESOLVED" if i < resolved_count else "CENSORED",
                }
            )
        resolved = [r for r in rows if r["status"] == "RESOLVED"]
        censored = [r for r in rows if r["status"] == "CENSORED"]
        full_scores = []
        for assignment in itertools.product(labels, repeat=len(censored)):
            complete = [dict(r) for r in resolved]
            complete += [dict(r, label=y) for r, y in zip(censored, assignment, strict=True)]
            cb = sum((brier(r["candidate"], r["label"]) for r in complete), Fraction()) / len(
                complete
            )
            bb = sum((brier(r["baseline"], r["label"]) for r in complete), Fraction()) / len(
                complete
            )
            ce, be = ece(complete, "candidate"), ece(complete, "baseline")
            full_scores.append((cb, bb, ce, be, ce - be, cb - bb))
        result = tool._metrics(rows)
        for arm, bcol, ecol in (("candidate", 0, 2), ("baseline", 1, 3)):
            assert Fraction(result[arm]["brier"]["best"]) == min(s[bcol] for s in full_scores)
            assert Fraction(result[arm]["brier"]["worst"]) == max(s[bcol] for s in full_scores)
            assert Fraction(result[arm]["ece"]["best"]) == min(s[ecol] for s in full_scores)
            assert Fraction(result[arm]["ece"]["worst"]) == max(s[ecol] for s in full_scores)
        paired = result["paired"]["brier_difference"]
        assert Fraction(paired["favourable"]) == min(s[5] for s in full_scores)
        assert Fraction(paired["adverse"]) == max(s[5] for s in full_scores)
        corner = result["paired"]["ece_difference_corner"]
        assert Fraction(corner["favourable"]) <= min(s[4] for s in full_scores)
        assert Fraction(corner["adverse"]) >= max(s[4] for s in full_scores)
        corner_is_loose |= Fraction(corner["favourable"]) < min(
            s[4] for s in full_scores
        ) or Fraction(corner["adverse"]) > max(s[4] for s in full_scores)
        if not censored:
            for arm, bcol, ecol in (("candidate", 0, 2), ("baseline", 1, 3)):
                for metric, col in (("brier", bcol), ("ece", ecol)):
                    point = Fraction(result[arm][metric]["point"])
                    assert (
                        Fraction(result[arm][metric]["best"])
                        == Fraction(result[arm][metric]["worst"])
                        == point
                        == full_scores[0][col]
                    )
            for metric in ("brier_difference", "ece_difference_corner"):
                values = result["paired"][metric]
                assert (
                    Fraction(values["favourable"])
                    == Fraction(values["adverse"])
                    == Fraction(values["point"])
                )
    # The enumerator must use the tool only for its production metrics result.
    test_ast = ast.parse(
        __import__("inspect").getsource(test_exact_bounds_against_independent_enumeration)
    )
    tool_attrs = {
        node.attr
        for node in ast.walk(test_ast)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "tool"
    }
    assert tool_attrs == {"_metrics"}
    assert corner_is_loose


def test_fixed_boundaries_ties_zero_collapse_and_integer_ece():
    tool = _load_tool()
    labels, _, _, top_label, bucket, _ = _independent_helpers()
    candidates = []
    for edge in (40, 50, 60, 70, 80, 90, 100):
        rest = 100 - edge
        values = [edge, rest // 2, rest - rest // 2]
        candidates.append(dict(zip(labels, (Fraction(v, 100) for v in values), strict=True)))
    ties = [
        {"UP": Fraction(40, 100), "DOWN": Fraction(40, 100), "TIMEOUT": Fraction(20, 100)},
        {"UP": Fraction(34, 100), "DOWN": Fraction(33, 100), "TIMEOUT": Fraction(33, 100)},
        {"UP": Fraction(33, 100), "DOWN": Fraction(34, 100), "TIMEOUT": Fraction(33, 100)},
        {"UP": Fraction(33, 100), "DOWN": Fraction(33, 100), "TIMEOUT": Fraction(34, 100)},
    ]
    fixed = [
        {
            "candidate": p,
            "baseline": candidates[-1 - i % len(candidates)],
            "label": labels[i % 3],
            "status": "RESOLVED",
        }
        for i, p in enumerate(candidates + ties)
    ]
    assert [bucket(p[top_label(p)]) for p in candidates] == [1, 2, 3, 4, 5, 6, 6]
    assert [top_label(p) for p in ties] == ["UP", "UP", "DOWN", "TIMEOUT"]
    collapsed = tool._metrics(fixed)
    for arm in ("candidate", "baseline"):
        for metric in ("brier", "ece"):
            values = collapsed[arm][metric]
            assert values["best"] == values["worst"] == values["point"]
    for metric in ("brier_difference", "ece_difference_corner"):
        values = collapsed["paired"][metric]
        assert values["favourable"] == values["adverse"] == values["point"]

    lone = {
        "candidate": {
            "UP": Fraction(45, 100),
            "DOWN": Fraction(30, 100),
            "TIMEOUT": Fraction(25, 100),
        },
        "baseline": {
            "UP": Fraction(45, 100),
            "DOWN": Fraction(30, 100),
            "TIMEOUT": Fraction(25, 100),
        },
        "label": None,
        "status": "CENSORED",
    }
    bounds = tool._metrics([lone])
    assert Fraction(bounds["candidate"]["ece"]["best"]) == Fraction(45, 100)


def test_deterministic_mode_product_constants_and_crosscheck(tmp_path: Path):
    def encode(dist):
        return {
            f"p_{name.lower()}_frac": "1.00" if value == 1 else f"0.{int(value * 100):02d}"
            for name, value in dist.items()
        }

    edges = (40, 50, 60, 70, 80, 90, 100)
    probabilities = []
    rows = []
    for i in range(21):
        top = edges[i % len(edges)]
        values = [top, (100 - top) // 2, 100 - top - (100 - top) // 2]
        if i % 2:
            values = [values[1], values[0], values[2]]
        p = dict(zip(("UP", "DOWN", "TIMEOUT"), (Fraction(v, 100) for v in values), strict=True))
        probabilities.append(p)
        label = ("UP", "DOWN", "TIMEOUT")[i % 3]
        base_values = [values[1], values[2], values[0]]
        baseline_p = dict(
            zip(("UP", "DOWN", "TIMEOUT"), (Fraction(v, 100) for v in base_values), strict=True)
        )
        item = instant(T + i * 3 * DELTA, label=label, probs=encode(p))
        item["baseline"] = encode(baseline_p)
        rows.append(item)
        probabilities[-1] = (p, baseline_p)
    bars = []
    for row in rows:
        t0 = datetime.fromisoformat(row["reference_close_utc"].replace("Z", "+00:00"))
        bars.extend([(t0 - DELTA, t0), (t0 + DELTA, t0 + 2 * DELTA)])
    data = base_input(bars=bars, rows=rows)
    first, out1 = invoke(tmp_path, data, output_name="first")
    second, out2 = invoke(tmp_path, data, output_name="second")
    assert first.returncode == second.returncode == 0
    raw = (out1 / "CENSOR_ACCOUNTING.json").read_bytes()
    assert raw == (out2 / "CENSOR_ACCOUNTING.json").read_bytes()
    assert (out1 / "CENSOR_ACCOUNTING.json").stat().st_mode & 0o777 == 0o444
    assert _load_tool().BUCKETS == tuple(
        (Fraction(str(a)), Fraction(str(b)))
        for a, b in (
            (0.00, 0.40),
            (0.40, 0.50),
            (0.50, 0.60),
            (0.60, 0.70),
            (0.70, 0.80),
            (0.80, 0.90),
            (0.90, 1.00),
        )
    )
    sys.path.insert(0, str(ROOT / "src"))
    from crypto_probability_engine.calibration.metrics import brier_score, top_prediction_label
    from crypto_probability_engine.calibration.schemas import (
        RELIABILITY_BUCKETS,
        TOP_LABEL_TIE_ORDER,
    )
    from crypto_probability_engine.oos.evaluation.scoring import ece

    assert tuple(TOP_LABEL_TIE_ORDER) == ("UP", "DOWN", "TIMEOUT")
    assert tuple(_load_tool().TIE_ORDER) == tuple(TOP_LABEL_TIE_ORDER)
    assert (
        tuple((Fraction(str(a)), Fraction(str(b))) for a, b in RELIABILITY_BUCKETS)
        == _load_tool().BUCKETS
    )
    body = json.loads(raw)
    product_rows = []
    candidate_briers = []
    baseline_briers = []
    baseline_product_rows = []
    for row, (p, bp) in zip(rows, probabilities, strict=True):
        label = row["label"]
        candidate_briers.append(brier_score({k: float(v) for k, v in p.items()}, label))
        baseline_briers.append(brier_score({k: float(v) for k, v in bp.items()}, label))
        product_rows.append(
            {
                "p_up_frac": row["candidate"]["p_up_frac"],
                "p_down_frac": row["candidate"]["p_down_frac"],
                "p_timeout_frac": row["candidate"]["p_timeout_frac"],
                "realized_label": label,
                "terminal_return_frac": None,
            }
        )
        baseline_product_rows.append(
            {
                "p_up_frac": row["baseline"]["p_up_frac"],
                "p_down_frac": row["baseline"]["p_down_frac"],
                "p_timeout_frac": row["baseline"]["p_timeout_frac"],
                "realized_label": label,
                "terminal_return_frac": None,
            }
        )
    assert top_prediction_label({"UP": 0.6, "DOWN": 0.25, "TIMEOUT": 0.15}) == "UP"
    assert (
        abs(
            float(Fraction(body["metrics"]["candidate"]["brier"]["point"]))
            - sum(candidate_briers) / len(rows)
        )
        < 1e-12
    )
    assert (
        abs(
            float(Fraction(body["metrics"]["baseline"]["brier"]["point"]))
            - sum(baseline_briers) / len(rows)
        )
        < 1e-12
    )
    assert (
        abs(float(Fraction(body["metrics"]["candidate"]["ece"]["point"])) - ece(product_rows))
        < 1e-12
    )
    assert (
        abs(
            float(Fraction(body["metrics"]["baseline"]["ece"]["point"]))
            - ece(baseline_product_rows)
        )
        < 1e-12
    )


def test_source_scan_and_duplicate_plan_key(tmp_path: Path):
    tree = ast.parse(SCRIPT.read_text())
    forbidden = {
        "socket",
        "ssl",
        "urllib",
        "http",
        "requests",
        "httpx",
        "ftplib",
        "asyncio",
        "subprocess",
        "multiprocessing",
        "os",
    }
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports |= {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert imports.isdisjoint(forbidden)
    assert "subprocess" not in SCRIPT.read_text()
    raw_plan = '{"plan_id":"ucpe.quant_ng.censor.v1","plan_id":"ucpe.quant_ng.censor.v1"}'
    p = tmp_path / "bad.json"
    p.write_text(raw_plan)
    proc = subprocess.run(
        [sys.executable, "-I", "-B", str(SCRIPT), str(p)], cwd=ROOT, capture_output=True, text=True
    )
    assert proc.returncode == 2 and json.loads(proc.stdout)["reason"] == "invalid plan"
