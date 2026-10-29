#!/usr/bin/env python3
"""Schedule synthetic evaluation rows and label exact terminal-close outcomes.

This dormant producer accepts synthetic data only, uses test-only horizon,
cadence and band parameters, and writes the censor tool's input. It assigns no
censor reason; quant_ng_censor.py remains the accounting and bounds authority.
Refusals include: invalid plan, invalid input, source must be synthetic,
parameters require SYNTHETIC_TEST_ONLY, input digest mismatch, output folder is
not empty, as of is not UTC midnight, corpus ends before the quarter, member has
no series, series is not a member, duplicate bar, bar after corpus end, duplicate
forecast, missing forecast, forecast not on a scheduled instant, probabilities
do not sum to one, and accounting identity failed. Shared path and guard
refusals are supplied by quant_ng_censor.py. Guard refusals include
filesystem change outside the output folder: <event>. Unexpected errors are
reported as run failed: <Type>.

Usage: ``python -I -B scripts/quant_ng_evalrows.py <plan.json>``; exit 0 PASS,
exit 2 REFUSAL.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from datetime import datetime, timedelta
from fractions import Fraction
from pathlib import Path
from typing import Any

_CENSOR_SPEC = importlib.util.spec_from_file_location(
    "quant_ng_censor", Path(__file__).with_name("quant_ng_censor.py")
)
if _CENSOR_SPEC is None or _CENSOR_SPEC.loader is None:
    raise RuntimeError("cannot load censor helper")
_CENSOR = importlib.util.module_from_spec(_CENSOR_SPEC)
sys.modules["quant_ng_censor"] = _CENSOR
_PREVIOUS_BYTECODE = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    _CENSOR_SPEC.loader.exec_module(_CENSOR)
finally:
    sys.dont_write_bytecode = _PREVIOUS_BYTECODE

Refusal = _CENSOR.Refusal
_path = _CENSOR._path
_json_bytes = _CENSOR._json_bytes
create_readonly = _CENSOR.create_readonly
install_guard = _CENSOR.install_guard
_make_output = _CENSOR._make_output
_unwind = _CENSOR._unwind
_instant = _CENSOR._instant
_output_bytes = _CENSOR._output_bytes
_utc_text = _CENSOR._utc_text
_micros = _CENSOR._micros
_probabilities = _CENSOR._probabilities
TIMEFRAMES = _CENSOR.TIMEFRAMES
HEX_RE = _CENSOR.HEX_RE
NAME_RE = _CENSOR.NAME_RE
PROB_RE = _CENSOR.PROB_RE
INPUT_ID = _CENSOR.INPUT_ID
_no_duplicate_keys = _CENSOR._FIT._no_duplicate_keys

PLAN_ID = "ucpe.quant_ng.evalrows.v1"
RECORD_ID = "ucpe.quant_ng.evalrows_record.v1"
RULING = "SYNTHETIC_TEST_ONLY"
BAND_RE = re.compile(r"^0\.[0-9]+$")
OUTPUT_HOLDER: list[Path | None] = [None]
PRICE_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")


def _label(reference: Fraction, terminal: Fraction, band: Fraction) -> str:
    change = terminal - reference
    if change > band * reference:
        return "UP"
    if change < -band * reference:
        return "DOWN"
    return "TIMEOUT"


def _invalid() -> Refusal:
    return Refusal("invalid input")


def run(plan_arg: str) -> dict[str, Any]:
    try:
        _, plan = _json_bytes(_path(plan_arg), "invalid plan")
    except Refusal:
        raise Refusal("invalid plan") from None
    if (
        not isinstance(plan, dict)
        or set(plan) != {"plan_id", "input", "parameters", "output_dir"}
        or plan.get("plan_id") != PLAN_ID
    ):
        raise Refusal("invalid plan")
    pin, params = plan.get("input"), plan.get("parameters")
    if (
        not isinstance(pin, dict)
        or set(pin) != {"path", "sha256"}
        or not isinstance(pin.get("path"), str)
        or not isinstance(pin.get("sha256"), str)
        or not HEX_RE.fullmatch(pin["sha256"])
        or not isinstance(params, dict)
        or set(params) != {"horizon_bars", "cadence_bars", "band_frac", "ruling"}
        or isinstance(params.get("horizon_bars"), bool)
        or not isinstance(params.get("horizon_bars"), int)
        or not 1 <= params["horizon_bars"] <= 96
        or isinstance(params.get("cadence_bars"), bool)
        or not isinstance(params.get("cadence_bars"), int)
        or params["cadence_bars"] < 1
        or not isinstance(params.get("band_frac"), str)
        or not BAND_RE.fullmatch(params["band_frac"])
        or not isinstance(plan.get("output_dir"), str)
    ):
        raise Refusal("invalid plan")
    try:
        band = Fraction(params["band_frac"])
    except (ValueError, ZeroDivisionError):
        raise Refusal("invalid plan") from None
    if not 0 < band < 1:
        raise Refusal("invalid plan")
    if params["ruling"] != RULING:
        raise Refusal("parameters require SYNTHETIC_TEST_ONLY")
    input_path, output = _path(pin["path"]), _path(plan["output_dir"])
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise Refusal("output folder is not empty")
    try:
        raw = input_path.read_bytes()
        data = json.loads(raw, object_pairs_hook=_no_duplicate_keys)
    except Exception as exc:
        raise Refusal("invalid input") from exc
    if isinstance(data, dict) and data.get("source") != "synthetic":
        raise Refusal("source must be synthetic")
    if hashlib.sha256(raw).hexdigest() != pin["sha256"]:
        raise Refusal("input digest mismatch")
    keys = {
        "input_id",
        "source",
        "quarter_as_of_utc",
        "corpus_end_utc",
        "timeframe",
        "members",
        "series",
        "forecasts",
    }
    if not isinstance(data, dict) or set(data) != keys or data.get("input_id") != INPUT_ID:
        raise _invalid()
    try:
        asof, end = _instant(data["quarter_as_of_utc"]), _instant(data["corpus_end_utc"])
    except Refusal as exc:
        raise _invalid() from exc
    if asof.hour or asof.minute or asof.second or asof.microsecond:
        raise Refusal("as of is not UTC midnight")
    if end < asof:
        raise Refusal("corpus ends before the quarter")
    tf = data["timeframe"]
    if not isinstance(tf, str) or tf not in TIMEFRAMES:
        raise _invalid()
    delta_s = TIMEFRAMES[tf]
    delta = timedelta(seconds=delta_s)
    quarter = asof + timedelta(days=90)
    members_raw, series_raw, forecasts_raw = data["members"], data["series"], data["forecasts"]
    if not all(isinstance(v, list) for v in (members_raw, series_raw, forecasts_raw)):
        raise _invalid()
    members: list[tuple[str, str]] = []
    member_set = set()
    for item in members_raw:
        if (
            not isinstance(item, dict)
            or set(item) != {"symbol", "lineage"}
            or not all(
                isinstance(item.get(k), str) and NAME_RE.fullmatch(item[k])
                for k in ("symbol", "lineage")
            )
        ):
            raise _invalid()
        key = (item["symbol"], item["lineage"])
        if key in member_set:
            raise _invalid()
        members.append(key)
        member_set.add(key)
    series: dict[tuple[str, str], list[tuple[datetime, datetime, bool, Fraction | None]]] = {}
    output_series = []
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
            raise _invalid()
        key = (item["symbol"], item["lineage"])
        if key in series:
            raise _invalid()
        if key not in member_set:
            raise Refusal("series is not a member")
        parsed, opens, outbars = [], set(), []
        for bar in item["bars"]:
            if not isinstance(bar, dict) or set(bar) != {"open_utc", "close_utc", "close_price"}:
                raise _invalid()
            try:
                op, cl = _instant(bar["open_utc"]), _instant(bar["close_utc"])
            except Refusal as exc:
                raise _invalid() from exc
            if op in opens:
                raise Refusal("duplicate bar")
            opens.add(op)
            if cl <= op:
                raise _invalid()
            if cl > end:
                raise Refusal("bar after corpus end")
            regular = _micros(op) % (delta_s * 1_000_000) == 0 and cl == op + delta
            price = None
            if regular:
                value = bar["close_price"]
                if not isinstance(value, str) or not PRICE_RE.fullmatch(value):
                    raise _invalid()
                price = Fraction(value)
                if price <= 0:
                    raise _invalid()
            parsed.append((op, cl, regular, price))
            outbars.append({"open_utc": bar["open_utc"], "close_utc": bar["close_utc"]})
        series[key] = parsed
        output_series.append({"symbol": key[0], "lineage": key[1], "bars": outbars})
    if any(m not in series for m in member_set):
        raise Refusal("member has no series")
    forecasts = {}
    for item in forecasts_raw:
        if (
            not isinstance(item, dict)
            or set(item) != {"symbol", "lineage", "reference_close_utc", "candidate", "baseline"}
            or not all(
                isinstance(item.get(k), str) and NAME_RE.fullmatch(item[k])
                for k in ("symbol", "lineage")
            )
        ):
            raise _invalid()
        try:
            t0 = _instant(item["reference_close_utc"])
        except Refusal as exc:
            raise _invalid() from exc
        key = (item["symbol"], item["lineage"], t0)
        if key in forecasts:
            raise Refusal("duplicate forecast")
        probs = {arm: item[arm] for arm in ("candidate", "baseline")}
        for arm in probs:
            _probabilities(probs[arm])
        forecasts[key] = probs
    schedule = []
    step = params["cadence_bars"] * delta
    t0 = asof
    while t0 < quarter:
        for symbol, lineage in members:
            key = (symbol, lineage, t0)
            if key not in forecasts:
                raise Refusal("missing forecast")
            schedule.append((symbol, lineage, t0, forecasts.pop(key)))
        t0 += step
    if forecasts:
        raise Refusal("forecast not on a scheduled instant")
    rows, labels = [], {k: 0 for k in ("UP", "DOWN", "TIMEOUT")}
    for symbol, lineage, t0, probs in sorted(schedule, key=lambda r: (r[0], r[1], r[2])):
        h = t0 + params["horizon_bars"] * delta
        bars = series[(symbol, lineage)]
        ref = next((p for _, cl, regular, p in bars if regular and cl == t0), None)
        term = next((p for _, cl, regular, p in bars if regular and cl == h), None)
        label = None
        if h <= quarter and ref is not None and term is not None:
            label = _label(ref, term, band)
            labels[label] += 1
        rows.append(
            {
                "symbol": symbol,
                "lineage": lineage,
                "reference_close_utc": _utc_text(t0),
                "label": label,
                **probs,
            }
        )
    scheduled, labelled = len(rows), sum(labels.values())
    unlabelled = sum(row["label"] is None for row in rows)
    if scheduled != labelled + unlabelled or labelled != sum(labels.values()):
        raise Refusal("accounting identity failed")
    censor_input = {
        "input_id": INPUT_ID,
        "source": "synthetic",
        "quarter_as_of_utc": data["quarter_as_of_utc"],
        "corpus_end_utc": data["corpus_end_utc"],
        "timeframe": tf,
        "members": [{"symbol": symbol, "lineage": lineage} for symbol, lineage in members],
        "series": output_series,
        "rows": rows,
    }
    cin_bytes = _output_bytes(censor_input)
    cin_digest = hashlib.sha256(cin_bytes).hexdigest()
    record = {
        "record_id": RECORD_ID,
        "status": "SYNTHETIC",
        "ruling": {
            "C10": "A+ owner-ruled 2026-10-29; rows classified and bounded only by quant_ng_censor",
            "parameters": {
                k: params[k] for k in ("horizon_bars", "cadence_bars", "band_frac", "ruling")
            },
            "target": "TERMINAL_CLOSE_VS_BAND_3STATE / EXACT_TERMINAL_BAR_SAME_VENUE",
        },
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "censor_input_sha256": cin_digest,
        "timeframe": tf,
        "quarter_as_of_utc": _utc_text(asof),
        "quarter_end_utc": _utc_text(quarter),
        "corpus_end_utc": _utc_text(end),
        "counts": {
            "scheduled": scheduled,
            "labelled": labelled,
            "unlabelled": unlabelled,
            "labels": labels,
        },
        "not_implemented": [
            "real-data inputs (unruled)",
            "ruled horizon, cadence and band (unruled)",
        ],
    }
    record_bytes = _output_bytes(record)
    OUTPUT_HOLDER[0] = output
    created = _make_output(output)
    try:
        create_readonly(output / "CENSOR_INPUT.json", cin_bytes)
        create_readonly(output / "EVALROWS_RECORD.json", record_bytes)
        return {
            "status": "PASS",
            "censor_input_sha256": cin_digest,
            "record_sha256": hashlib.sha256(record_bytes).hexdigest(),
        }
    except BaseException:
        for name in ("CENSOR_INPUT.json", "EVALROWS_RECORD.json"):
            try:
                (output / name).unlink(missing_ok=True)
            except OSError:
                pass
        _unwind(created)
        raise


def main(argv: list[str] | None = None) -> int:
    install_guard(OUTPUT_HOLDER)
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
