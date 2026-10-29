#!/usr/bin/env python3
"""Account for censoring in synthetic terminal-close evaluation inputs.

Bars use end-exclusive close instants: a bar opened at ``o`` closes at
``o + timeframe``. A bar fills a slot only when it is on the epoch grid and
has that exact close. Classification never reads a bar closing after
``min(corpus end, quarter end)``. Censor reasons are tested in this exact
order: ``h > E`` gives ``span_end``; a later regular bar gives ``halt``; a
later irregular bar gives ``unknown``; ticker reuse gives ``unknown``; a last
visible bar at most one horizon before the read limit gives ``unknown``;
otherwise ``delisting``. No network or real data is supported. Refusals include:
invalid plan, invalid input, source must be synthetic, input digest mismatch,
horizon requires SYNTHETIC_TEST_ONLY, output folder is not empty, as of is not
UTC midnight, corpus ends before the quarter, member has no series, series is
not a member, duplicate bar, bar after corpus end, probabilities do not sum to
one, row is not a member, reference instant off grid, row outside the quarter,
duplicate row, resolved row without a label, label on an unresolved row, and
accounting identity failed. Guard refusals include filesystem change outside
the output folder: <event>. Unexpected errors are reported as run failed:
<Type>.

Usage: ``python -I -B scripts/quant_ng_censor.py <plan.json>``.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from pathlib import Path
from typing import Any

_FIT_SPEC = importlib.util.spec_from_file_location(
    "quant_ng_fit", Path(__file__).with_name("quant_ng_fit.py")
)
if _FIT_SPEC is None or _FIT_SPEC.loader is None:
    raise RuntimeError("cannot load fit helper")
_FIT = importlib.util.module_from_spec(_FIT_SPEC)
sys.modules["quant_ng_fit"] = _FIT
_PREVIOUS_BYTECODE = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    _FIT_SPEC.loader.exec_module(_FIT)
finally:
    sys.dont_write_bytecode = _PREVIOUS_BYTECODE

Refusal = _FIT.Refusal
_path = _FIT._path
_json_bytes = _FIT._json_bytes
create_readonly = _FIT.create_readonly
install_guard = _FIT.install_guard
_make_output = _FIT._make_output
_unwind = _FIT._unwind
_instant = _FIT._instant
_OUTPUT_HOLDER: list[Path | None] = [None]

PLAN_ID = "ucpe.quant_ng.censor.v1"
INPUT_ID = "ucpe.quant_ng.censor_input.v1"
ACCOUNTING_ID = "ucpe.quant_ng.censor_accounting.v1"
PLAN_KEYS = {"plan_id", "input", "horizon", "output_dir"}
LABELS = ("UP", "DOWN", "TIMEOUT")
TIE_ORDER = LABELS
BUCKETS = tuple(
    (Fraction(a), Fraction(b))
    for a, b in (
        ("0.00", "0.40"),
        ("0.40", "0.50"),
        ("0.50", "0.60"),
        ("0.60", "0.70"),
        ("0.70", "0.80"),
        ("0.80", "0.90"),
        ("0.90", "1.00"),
    )
)
TIMEFRAMES = {"15m": 15 * 60, "1H": 60 * 60, "4H": 4 * 60 * 60, "1D": 24 * 60 * 60}
HEX_RE = re.compile(r"^[0-9a-f]{64}$")
NAME_RE = re.compile(r"^[A-Z0-9]+$")
PROB_RE = re.compile(r"^(?:0(?:\.[0-9]+)?|1(?:\.0+)?)$")
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
REASONS = ("span_end", "delisting", "halt", "unknown")


def _output_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def _utc_text(value: datetime) -> str:
    value = value.astimezone(UTC)
    base = value.strftime("%Y-%m-%dT%H:%M:%S")
    return f"{base}.{value.microsecond:06d}Z" if value.microsecond else f"{base}Z"


def _seconds(value: datetime) -> int:
    delta = value - EPOCH
    return delta.days * 86400 + delta.seconds


def _micros(value: datetime) -> int:
    delta = value - EPOCH
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def _number(value: Fraction | None) -> str | None:
    return None if value is None else f"{value.numerator}/{value.denominator}"


def _probabilities(value: Any) -> dict[str, Fraction]:
    keys = {"p_up_frac", "p_down_frac", "p_timeout_frac"}
    if not isinstance(value, dict) or set(value) != keys:
        raise Refusal("invalid input")
    result = {}
    for key, label in zip(("p_up_frac", "p_down_frac", "p_timeout_frac"), LABELS, strict=True):
        raw = value[key]
        if not isinstance(raw, str) or not PROB_RE.fullmatch(raw):
            raise Refusal("invalid input")
        result[label] = Fraction(raw)
    if sum(result.values(), Fraction()) != 1:
        raise Refusal("probabilities do not sum to one")
    return result


def _top(probs: dict[str, Fraction]) -> str:
    best = TIE_ORDER[0]
    for label in TIE_ORDER[1:]:
        if probs[label] > probs[best]:
            best = label
    return best


def _bucket(probability: Fraction) -> int:
    for index, (start, end) in enumerate(BUCKETS):
        if start <= probability < end:
            return index
    return len(BUCKETS) - 1


def _brier(probs: dict[str, Fraction], label: str) -> Fraction:
    return sum(((probs[key] - int(key == label)) ** 2 for key in LABELS), Fraction())


def _ece(rows: list[dict[str, Any]], arm: str) -> Fraction:
    if not rows:
        return Fraction()
    sums = [Fraction() for _ in BUCKETS]
    hits = [0 for _ in BUCKETS]
    for row in rows:
        probs = row[arm]
        top = _top(probs)
        index = _bucket(probs[top])
        sums[index] += probs[top]
        hits[index] += row["label"] == top
    return sum((abs(sums[i] - hits[i]) for i in range(len(BUCKETS))), Fraction()) / len(rows)


def _ece_bounds(
    rows: list[dict[str, Any]], arm: str, resolved_n: int, censored_n: int
) -> tuple[Fraction, Fraction]:
    sums = [Fraction() for _ in BUCKETS]
    resolved_hits = [0 for _ in BUCKETS]
    censored = [0 for _ in BUCKETS]
    for row in rows:
        probs = row[arm]
        index = _bucket(probs[_top(probs)])
        sums[index] += probs[_top(probs)]
        if row["status"] == "RESOLVED":
            resolved_hits[index] += row["label"] == _top(probs)
        else:
            censored[index] += 1
    if resolved_n + censored_n == 0:
        return Fraction(), Fraction()
    best = worst = Fraction()
    for i in range(len(BUCKETS)):
        base = sums[i] - resolved_hits[i]
        c = censored[i]
        low = min(abs(base - j) for j in range(c + 1))
        high = max(abs(base), abs(base - c))
        best += low
        worst += high
    n = resolved_n + censored_n
    return best / n, worst / n


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    resolved = [r for r in rows if r["status"] == "RESOLVED"]
    censored = [r for r in rows if r["status"] == "CENSORED"]
    n, c = len(resolved), len(censored)
    total = n + c
    arms: dict[str, Any] = {}
    for arm in ("candidate", "baseline"):
        point = sum((_brier(r[arm], r["label"]) for r in resolved), Fraction()) / n if n else None
        if total:
            br = sum((_brier(r[arm], r["label"]) for r in resolved), Fraction())
            mins = sum((min(_brier(r[arm], y) for y in LABELS) for r in censored), Fraction())
            maxs = sum((max(_brier(r[arm], y) for y in LABELS) for r in censored), Fraction())
            best, worst = (br + mins) / total, (br + maxs) / total
            ece_best, ece_worst = _ece_bounds(rows, arm, n, c)
        else:
            best = worst = ece_best = ece_worst = None
        arms[arm] = {
            "brier": {"point": _number(point), "best": _number(best), "worst": _number(worst)},
            "ece": {
                "point": _number(_ece(resolved, arm)) if n else None,
                "best": _number(ece_best),
                "worst": _number(ece_worst),
            },
        }
    point_brier = None
    if n:
        point_brier = (
            sum(
                (
                    _brier(r["candidate"], r["label"]) - _brier(r["baseline"], r["label"])
                    for r in resolved
                ),
                Fraction(),
            )
            / n
        )
    if total:
        base_diff = sum(
            (
                _brier(r["candidate"], r["label"]) - _brier(r["baseline"], r["label"])
                for r in resolved
            ),
            Fraction(),
        )
        lo = sum(
            (
                min(_brier(r["candidate"], y) - _brier(r["baseline"], y) for y in LABELS)
                for r in censored
            ),
            Fraction(),
        )
        hi = sum(
            (
                max(_brier(r["candidate"], y) - _brier(r["baseline"], y) for y in LABELS)
                for r in censored
            ),
            Fraction(),
        )
        favorable, adverse = (base_diff + lo) / total, (base_diff + hi) / total
        cb, cw = _ece_bounds(rows, "candidate", n, c)
        bb, bw = _ece_bounds(rows, "baseline", n, c)
        ece_favorable, ece_adverse = cb - bw, cw - bb
    else:
        favorable = adverse = ece_favorable = ece_adverse = None
    paired_ece_point = _ece(resolved, "candidate") - _ece(resolved, "baseline") if n else None
    return {
        **arms,
        "paired": {
            "brier_difference": {
                "point": _number(point_brier),
                "favourable": _number(favorable),
                "adverse": _number(adverse),
            },
            "ece_difference_corner": {
                "point": _number(paired_ece_point),
                "favourable": _number(ece_favorable),
                "adverse": _number(ece_adverse),
            },
        },
    }


def run(plan_arg: str) -> dict[str, Any]:
    plan_path = _path(plan_arg)
    try:
        _, plan = _json_bytes(plan_path, "invalid plan")
    except Refusal:
        raise Refusal("invalid plan") from None
    if not isinstance(plan, dict) or set(plan) != PLAN_KEYS or plan.get("plan_id") != PLAN_ID:
        raise Refusal("invalid plan")
    inp, horizon = plan.get("input"), plan.get("horizon")
    if (
        not isinstance(inp, dict)
        or set(inp) != {"path", "sha256"}
        or not isinstance(inp.get("path"), str)
        or not isinstance(inp.get("sha256"), str)
        or not HEX_RE.fullmatch(inp["sha256"])
    ):
        raise Refusal("invalid plan")
    if (
        not isinstance(horizon, dict)
        or set(horizon) != {"bars", "ruling"}
        or isinstance(horizon.get("bars"), bool)
        or not isinstance(horizon.get("bars"), int)
        or horizon["bars"] < 1
        or not isinstance(horizon.get("ruling"), str)
        or not isinstance(plan.get("output_dir"), str)
    ):
        raise Refusal("invalid plan")
    if horizon["ruling"] != "SYNTHETIC_TEST_ONLY":
        raise Refusal("horizon requires SYNTHETIC_TEST_ONLY")
    input_path, output = _path(inp["path"]), _path(plan["output_dir"])
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise Refusal("output folder is not empty")
    try:
        input_bytes = input_path.read_bytes()
        data = json.loads(input_bytes, object_pairs_hook=_FIT._no_duplicate_keys)
    except Exception as exc:
        raise Refusal("invalid input") from exc
    if isinstance(data, dict) and data.get("source") != "synthetic":
        raise Refusal("source must be synthetic")
    if hashlib.sha256(input_bytes).hexdigest() != inp["sha256"]:
        raise Refusal("input digest mismatch")
    if (
        not isinstance(data, dict)
        or data.get("input_id") != INPUT_ID
        or set(data)
        != {
            "input_id",
            "source",
            "quarter_as_of_utc",
            "corpus_end_utc",
            "timeframe",
            "members",
            "series",
            "rows",
        }
    ):
        raise Refusal("invalid input")
    try:
        asof = _instant(data["quarter_as_of_utc"])
        end = _instant(data["corpus_end_utc"])
    except Refusal as exc:
        raise Refusal("invalid input") from exc
    if asof.hour or asof.minute or asof.second or asof.microsecond:
        raise Refusal("as of is not UTC midnight")
    if end < asof:
        raise Refusal("corpus ends before the quarter")
    tf = data["timeframe"]
    if not isinstance(tf, str) or tf not in TIMEFRAMES:
        raise Refusal("invalid input")
    delta = timedelta(seconds=TIMEFRAMES[tf])
    delta_s = TIMEFRAMES[tf]
    quarter = asof + timedelta(days=90)
    read_limit = min(end, quarter)
    members_raw, series_raw, rows_raw = data["members"], data["series"], data["rows"]
    if not all(isinstance(x, list) for x in (members_raw, series_raw, rows_raw)):
        raise Refusal("invalid input")
    members: set[tuple[str, str]] = set()
    for item in members_raw:
        if (
            not isinstance(item, dict)
            or set(item) != {"symbol", "lineage"}
            or not all(
                isinstance(item.get(k), str) and NAME_RE.fullmatch(item[k])
                for k in ("symbol", "lineage")
            )
        ):
            raise Refusal("invalid input")
        key = (item["symbol"], item["lineage"])
        if key in members:
            raise Refusal("invalid input")
        members.add(key)
    series: dict[tuple[str, str], list[tuple[datetime, datetime, bool]]] = {}
    for item in series_raw:
        if (
            not isinstance(item, dict)
            or set(item) != {"symbol", "lineage", "bars"}
            or not all(
                isinstance(item.get(k), str) and NAME_RE.fullmatch(item[k])
                for k in ("symbol", "lineage")
            )
            or not isinstance(item.get("bars"), list)
        ):
            raise Refusal("invalid input")
        key = (item["symbol"], item["lineage"])
        if key in series:
            raise Refusal("invalid input")
        if key not in members:
            raise Refusal("series is not a member")
        bars = []
        opens = set()
        for bar in item["bars"]:
            if not isinstance(bar, dict) or set(bar) != {"open_utc", "close_utc"}:
                raise Refusal("invalid input")
            try:
                op, cl = _instant(bar["open_utc"]), _instant(bar["close_utc"])
            except Refusal as exc:
                raise Refusal("invalid input") from exc
            if op in opens:
                raise Refusal("duplicate bar")
            opens.add(op)
            if cl <= op:
                raise Refusal("invalid input")
            if cl > end:
                raise Refusal("bar after corpus end")
            regular = _micros(op) % (delta_s * 1_000_000) == 0 and cl == op + delta
            bars.append((op, cl, regular))
        series[key] = bars
    if any(key not in series for key in members):
        raise Refusal("member has no series")
    parsed_rows = []
    seen_rows = set()
    instant_counts = {"quarter_end": 0, "no_reference_bar": 0}
    for item in rows_raw:
        keys = {"symbol", "lineage", "reference_close_utc", "label", "candidate", "baseline"}
        if (
            not isinstance(item, dict)
            or set(item) != keys
            or not all(
                isinstance(item.get(k), str) and NAME_RE.fullmatch(item[k])
                for k in ("symbol", "lineage")
            )
            or item["label"] not in (None, *LABELS)
        ):
            raise Refusal("invalid input")
        probs = {arm: _probabilities(item[arm]) for arm in ("candidate", "baseline")}
        key = (item["symbol"], item["lineage"])
        if key not in members:
            raise Refusal("row is not a member")
        try:
            t0 = _instant(item["reference_close_utc"])
        except Refusal as exc:
            raise Refusal("invalid input") from exc
        if _micros(t0) % (delta_s * 1_000_000):
            raise Refusal("reference instant off grid")
        if not asof <= t0 < quarter:
            raise Refusal("row outside the quarter")
        rowkey = (*key, t0)
        if rowkey in seen_rows:
            raise Refusal("duplicate row")
        seen_rows.add(rowkey)
        h = t0 + horizon["bars"] * delta
        if h > quarter:
            instant_counts["quarter_end"] += 1
            if item["label"] is not None:
                raise Refusal("label on an unresolved row")
            continue
        bars = series[key]
        if not any(reg and close == t0 for _, close, reg in bars):
            instant_counts["no_reference_bar"] += 1
            if item["label"] is not None:
                raise Refusal("label on an unresolved row")
            continue
        terminal = any(reg and close == h for _, close, reg in bars)
        if terminal:
            if item["label"] is None:
                raise Refusal("resolved row without a label")
            parsed_rows.append(
                {
                    "symbol": key[0],
                    "lineage": key[1],
                    "reference_close_utc": _utc_text(t0),
                    "horizon_end_utc": _utc_text(h),
                    "status": "RESOLVED",
                    "censor_reason": None,
                    "label": item["label"],
                    **probs,
                }
            )
            continue
        if item["label"] is not None:
            raise Refusal("label on an unresolved row")
        if h > end:
            reason = "span_end"
        elif any(reg and h < close <= read_limit for _, close, reg in bars):
            reason = "halt"
        elif any(not reg and h < close <= read_limit for _, close, reg in bars):
            reason = "unknown"
        elif any(symbol == key[0] and lineage != key[1] for symbol, lineage in members):
            reason = "unknown"
        else:
            visible_closes = [close for _, close, _ in bars if close <= read_limit]
            latest = max(visible_closes, default=EPOCH)
            reason = "unknown" if read_limit - latest <= horizon["bars"] * delta else "delisting"
        parsed_rows.append(
            {
                "symbol": key[0],
                "lineage": key[1],
                "reference_close_utc": _utc_text(t0),
                "horizon_end_utc": _utc_text(h),
                "status": "CENSORED",
                "censor_reason": reason,
                "label": None,
                **probs,
            }
        )
    parsed_rows.sort(key=lambda r: (r["symbol"], r["lineage"], r["reference_close_utc"]))
    censored_by = {
        reason: sum(r["censor_reason"] == reason for r in parsed_rows) for reason in REASONS
    }
    resolved_n = sum(r["status"] == "RESOLVED" for r in parsed_rows)
    censored_n = sum(r["status"] == "CENSORED" for r in parsed_rows)
    if (
        len(rows_raw)
        != instant_counts["quarter_end"] + instant_counts["no_reference_bar"] + len(parsed_rows)
        or len(parsed_rows) != resolved_n + censored_n
        or censored_n != sum(censored_by.values())
    ):
        raise Refusal("accounting identity failed")
    metric_rows = [
        {**r, "candidate": r.get("candidate"), "baseline": r.get("baseline")} for r in parsed_rows
    ]
    # Probabilities are internal accounting fields and never emitted in the row ledger.
    result_rows = [
        {
            k: r[k]
            for k in (
                "symbol",
                "lineage",
                "reference_close_utc",
                "horizon_end_utc",
                "status",
                "censor_reason",
                "label",
            )
        }
        for r in parsed_rows
    ]
    no_rows = [
        {"symbol": symbol, "lineage": lineage}
        for symbol, lineage in sorted(members)
        if not any((r["symbol"], r["lineage"]) == (symbol, lineage) for r in parsed_rows)
    ]
    accounting = {
        "accounting_id": ACCOUNTING_ID,
        "status": "SYNTHETIC",
        "ruling": {
            "C10": (
                "A+ owner-ruled 2026-10-29; unknown reported separately from confirmed delisting"
            ),
            "horizon": {"bars": horizon["bars"], "ruling": "SYNTHETIC_TEST_ONLY"},
        },
        "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
        "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "timeframe": tf,
        "quarter_as_of_utc": _utc_text(asof),
        "quarter_end_utc": _utc_text(quarter),
        "classification_read_limit_utc": _utc_text(read_limit),
        "corpus_end_utc": _utc_text(end),
        "counts": {
            "instants": len(rows_raw),
            **instant_counts,
            "rows": len(parsed_rows),
            "resolved": resolved_n,
            "censored": censored_n,
            "censored_by_reason": censored_by,
        },
        "rows": result_rows,
        "no_rows_in_quarter": no_rows,
        "metrics": _metrics(metric_rows),
        "claim_rule": (
            "a claim holds only at the adverse end of its bound; "
            "paired ECE uses the conservative corner"
        ),
        "not_implemented": [
            "censored-share flag (unruled)",
            "stratified metrics (unruled)",
            "inverse-probability censoring weights (unruled)",
            "partial-observation diagnostic",
        ],
    }
    _OUTPUT_HOLDER[0] = output
    created = _make_output(output)
    try:
        payload = _output_bytes(accounting)
        create_readonly(output / "CENSOR_ACCOUNTING.json", payload)
        return {"status": "PASS", "accounting_sha256": hashlib.sha256(payload).hexdigest()}
    except BaseException:
        if output.exists():
            try:
                (output / "CENSOR_ACCOUNTING.json").unlink(missing_ok=True)
            except OSError:
                pass
        _unwind(created)
        raise


def main(argv: list[str] | None = None) -> int:
    install_guard(_OUTPUT_HOLDER)
    parser = argparse.ArgumentParser()
    parser.add_argument("plan")
    try:
        result = run(parser.parse_args(argv).plan)
    except Refusal as exc:
        print(json.dumps({"status": "REFUSAL", "reason": str(exc)}, separators=(",", ":")))
        return 2
    except Exception as exc:
        print(
            json.dumps(
                {"status": "REFUSAL", "reason": f"run failed: {type(exc).__name__}"},
                separators=(",", ":"),
            )
        )
        return 2
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
