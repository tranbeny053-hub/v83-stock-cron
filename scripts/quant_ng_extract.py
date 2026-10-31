#!/usr/bin/env python3
"""Parse verified local MOCK kline archive objects for OD-NG-5(b), step (b1).

This offline tool reads only a fetch manifest and its verified zip objects. It
produces parsed bars and window counts, not builder evidence, and writes
per-file identities, not provenance records. Every refusal is printed as JSON
with exit 2 and leaves no output behind. Refusals include: unreadable or
invalid plan, cutoff not UTC midnight, invalid path, nonempty output,
unreadable or invalid manifest, a non-MOCK manifest, reserved BTCUSDT or ETHUSDT,
symlinks below the fetch output,
object does not match the manifest, object is not a mock object, object changed
after verification, no files, file not verified, malformed archive file,
malformed row, invalid timestamp, malformed volume, bar outside its file period,
and duplicate bar. Guard refusals include filesystem change outside the output
folder: <event>. Unexpected errors are reported as run failed: <Type>.

Usage: ``python -I -B scripts/quant_ng_extract.py <plan.json>``.

``derive`` returns the exact PARSE.json bytes and writes nothing; ``run`` writes them.
PARSE v4 is unpublished; ``daily.first_unflagged_open_utc`` is additive within v4.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import re
import sys
import zipfile
from datetime import UTC, date, datetime, time, timedelta
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


class NotMockObject(Refusal):
    def __init__(self) -> None:
        super().__init__("object is not a mock object")


_path = _FIT._path
_json_bytes = _FIT._json_bytes
create_readonly = _FIT.create_readonly
install_guard = _FIT.install_guard
_make_output = _FIT._make_output
_unwind = _FIT._unwind
_instant = _FIT._instant
_OUTPUT_HOLDER: list[Path | None] = [None]

PLAN_KEYS = {"plan_id", "fetch_output_dir", "cutoff_utc", "output_dir"}
HEX_RE = re.compile(r"^[0-9a-f]{64}$")
VOLUME_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")
LAYOUT_RE = re.compile(
    r"^data/spot/(monthly|daily)/klines/([A-Z0-9]+USDT)/(15m|1h|4h|1d)/([A-Z0-9]+)-([0-9A-Za-z]+)-(.+)\.zip$"
)
INTERVALS = {
    "15m": 15 * 60_000_000,
    "1h": 60 * 60_000_000,
    "4h": 4 * 60 * 60_000_000,
    "1d": 24 * 60 * 60_000_000,
}
OUTPUT_INTERVALS = {"15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D"}
HISTORY_BARS = {"15m": 678, "1H": 678, "4H": 174}
DAILY_DAYS = 90
MAX_MEMBER_SIZE = 64 * 1024 * 1024
HASH_CHUNK_SIZE = 1024 * 1024
MOCK_MARKER = b"UCPE-MOCK-v1"
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _has_mock_marker(tail: bytes) -> bool:
    return (
        len(tail) == 34
        and tail[:4] == b"PK\x05\x06"
        and tail[-14:-12] == b"\x0c\x00"
        and tail[-12:] == MOCK_MARKER
    )


def _output_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def _utc_text(value: datetime) -> str:
    value = value.astimezone(UTC)
    base = value.strftime("%Y-%m-%dT%H:%M:%S")
    return f"{base}.{value.microsecond:06d}Z" if value.microsecond else f"{base}Z"


def _timestamp(value: str) -> tuple[int, int]:
    if not value.isascii() or not value.isdigit() or len(value) not in (13, 16):
        raise Refusal("invalid timestamp")
    width = len(value)
    number = int(value)
    micros = number * (1000 if width == 13 else 1)
    return micros, width


def _dt(micros: int) -> datetime:
    return EPOCH + timedelta(microseconds=micros)


def _period_start(row: dict[str, Any]) -> datetime:
    try:
        if row["granularity"] == "monthly":
            period = row["period"]
            if not isinstance(period, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}", period):
                raise ValueError("noncanonical monthly period")
            year, month = (int(part) for part in period.split("-"))
            return datetime(year, month, 1, tzinfo=UTC)
        period = row["period"]
        if not isinstance(period, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", period):
            raise ValueError("noncanonical daily period")
        return datetime.combine(date.fromisoformat(period), time(), UTC)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise Refusal("invalid manifest") from exc


def _row_period_end(start: datetime, row: dict[str, Any]) -> datetime:
    if row["granularity"] == "monthly":
        return datetime(start.year + (start.month == 12), start.month % 12 + 1, 1, tzinfo=UTC)
    return start + timedelta(days=1)


def _object_identities(
    rows: list[dict[str, Any]], last_bar_closes: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    fields = ("path", "granularity", "period", "sha256", "official_checksum", "class")
    result = []
    for row in sorted(rows, key=lambda item: item["path"]):
        item = {field: row[field] for field in fields}
        item["last_bar_close_utc"] = (last_bar_closes or {}).get(row["path"])
        result.append(item)
    return result


def _verifiable(row: dict[str, Any], cutoff: datetime) -> bool:
    # Both verification and parse selection must use the same filter.
    return row["class"] == "ok" and _period_start(row) < cutoff


def _micros(value: datetime) -> int:
    delta = value - EPOCH
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def _check_symlinks(root: Path) -> None:
    if root.is_symlink():
        raise Refusal("symlink path")
    try:
        for item in root.rglob("*"):
            if item.is_symlink():
                raise Refusal("symlink path")
    except OSError as exc:
        raise Refusal("manifest unreadable") from exc


def _read_archive(
    blob: bytes,
    row: dict[str, Any],
    cutoff_us: int,
    interval_us: int,
    start: datetime,
    end: datetime,
) -> tuple[list[tuple[int, str, bool]], int, int, int, int]:
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            if archive.comment != MOCK_MARKER:
                raise NotMockObject()
            members = archive.infolist()
            expected = Path(row["path"]).name[:-4] + ".csv"
            if (
                len(members) != 1
                or members[0].filename != expected
                or members[0].flag_bits & 1
                or members[0].file_size > MAX_MEMBER_SIZE
            ):
                raise Refusal("malformed archive file")
            content = archive.read(members[0])
    except Refusal:
        raise
    except Exception as exc:
        raise Refusal("malformed archive file") from exc
    lines = content.split(b"\n")
    if content.endswith(b"\n"):
        lines.pop()
    bars: list[tuple[int, str, bool]] = []
    widths: set[int] = set()
    off_grid = zero_volume = close_anomalies = close_anomalies_all = 0
    history = HISTORY_BARS.get(OUTPUT_INTERVALS.get(row["interval"], ""))
    window_start = cutoff_us - (
        DAILY_DAYS * 86400_000_000 if row["interval"] == "1d" else (history or 0) * interval_us
    )
    for raw_line in lines:
        if raw_line.endswith(b"\r"):
            raw_line = raw_line[:-1]
        field0 = raw_line.split(b",", 1)[0]
        if field0.isdigit() and len(field0) in (13, 16):
            open_us = int(field0) * (1000 if len(field0) == 13 else 1)
            if open_us >= cutoff_us:
                continue
        elif field0.isdigit():
            raise Refusal("invalid timestamp")
        else:
            raise Refusal("malformed row")
        try:
            line = raw_line.decode("ascii")
        except UnicodeDecodeError as exc:
            raise Refusal("malformed row") from exc
        fields = line.split(",")
        try:
            open_us, open_width = _timestamp(fields[0])
        except Refusal as exc:
            if len(fields) != 12 or fields[0].strip().lower() in {"open_time", "open time", "open"}:
                raise Refusal("malformed row") from exc
            raise
        # A row dated at or after T is discarded before any other check, so nothing dated after T
        # can make its series unusable.
        if open_us >= cutoff_us:
            continue
        if len(fields) != 12:
            raise Refusal("malformed row")
        widths.add(open_width)
        if len(widths) != 1:
            raise Refusal("invalid timestamp")
        close_us, close_width = _timestamp(fields[6])
        widths.add(close_width)
        if len(widths) != 1:
            raise Refusal("invalid timestamp")
        if not VOLUME_RE.fullmatch(fields[7]):
            raise Refusal("malformed volume")
        if not _micros(start) <= open_us < _micros(end):
            raise Refusal("bar outside its file period")
        if open_us % interval_us:
            if open_us >= window_start:
                off_grid += 1
            continue
        close_time_anomaly = close_us != open_us + interval_us - (
            1000 if open_width == 13 else 1
        )
        if close_time_anomaly:
            close_anomalies_all += 1
            if open_us >= window_start:
                close_anomalies += 1
        if open_us >= window_start and not fields[7].replace(".", "").strip("0"):
            zero_volume += 1
        bars.append((open_us, fields[7], close_time_anomaly))
    return bars, off_grid, zero_volume, close_anomalies, close_anomalies_all


def derive(fetch_dir: Path, cutoff: datetime) -> bytes:
    manifest_file = fetch_dir / "MANIFEST.json"
    manifest_bytes, manifest = _json_bytes(manifest_file, "manifest unreadable")
    if (
        not isinstance(manifest, dict)
        or manifest.get("manifest_id") != "ucpe.quant_ng.fetch_manifest.v1"
    ):
        raise Refusal("invalid manifest")
    if manifest.get("status") != "MOCK":
        raise Refusal("only a mock manifest is accepted")
    rows = manifest.get("files")
    row_keys = {
        "path",
        "symbol",
        "base",
        "interval",
        "granularity",
        "period",
        "class",
        "sha256",
        "size",
        "official_checksum",
        "checksum_file_sha256",
    }
    if not isinstance(rows, list) or any(
        not isinstance(row, dict) or set(row) != row_keys for row in rows
    ):
        raise Refusal("invalid manifest")
    if any(isinstance(row, dict) and row.get("symbol") in {"BTCUSDT", "ETHUSDT"} for row in rows):
        raise Refusal("BTCUSDT and ETHUSDT are never parsed")
    for row in rows:
        match = LAYOUT_RE.fullmatch(row["path"])
        if not match:
            raise Refusal("invalid manifest")
        granularity, symbol, interval, file_symbol, file_interval, period = match.groups()
        if (
            symbol != file_symbol
            or interval != file_interval
            or (granularity, symbol, interval, period)
            != (row["granularity"], row["symbol"], row["interval"], row["period"])
            or row["base"] != symbol[:-4]
        ):
            raise Refusal("invalid manifest")
    for row in rows:
        if (
            any(
                not isinstance(row[key], str)
                for key in ("path", "symbol", "base", "interval", "granularity", "period", "class")
            )
            or row["class"] not in {"missing", "checksum_malformed", "mismatch", "ok"}
            or row["granularity"] not in {"daily", "monthly"}
            or (row["sha256"] is not None and not isinstance(row["sha256"], str))
            or (
                row["official_checksum"] is not None
                and not isinstance(row["official_checksum"], str)
            )
            or (
                row["checksum_file_sha256"] is not None
                and not isinstance(row["checksum_file_sha256"], str)
            )
            or (
                row["size"] is not None
                and (isinstance(row["size"], bool) or not isinstance(row["size"], int))
            )
        ):
            raise Refusal("invalid manifest")
    _check_symlinks(fetch_dir)
    cutoff_us = _micros(cutoff)
    # Verify every pre-cutoff object before parsing any series.
    for row in rows:
        if _verifiable(row, cutoff):
            digest, official = row["sha256"], row["official_checksum"]
            if (
                not isinstance(digest, str)
                or not HEX_RE.fullmatch(digest)
                or not isinstance(official, str)
                or not HEX_RE.fullmatch(official)
            ):
                raise Refusal("object does not match the manifest")
            try:
                hasher = hashlib.sha256()
                tail = b""
                with (fetch_dir / "objects" / digest).open("rb") as stream:
                    while chunk := stream.read(HASH_CHUNK_SIZE):
                        hasher.update(chunk)
                        tail = (tail + chunk)[-34:]
                actual = hasher.hexdigest()
            except OSError as exc:
                raise Refusal("object does not match the manifest") from exc
            if actual != digest or actual != official:
                raise Refusal("object does not match the manifest")
            if not _has_mock_marker(tail):
                raise NotMockObject()
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    symbols: set[str] = set()
    after = 0
    for row in rows:
        symbol, interval = row["symbol"], row["interval"]
        if (
            not isinstance(symbol, str)
            or not isinstance(interval, str)
            or interval not in INTERVALS
        ):
            raise Refusal("invalid manifest")
        if symbol in {"BTCUSDT", "ETHUSDT"}:
            raise Refusal("BTCUSDT and ETHUSDT are never parsed")
        start = _period_start(row)
        if start >= cutoff:
            after += 1
            continue
        symbols.add(symbol)
        groups.setdefault((symbol, interval), []).append(row)
    parsed: dict[tuple[str, str], dict[str, Any]] = {}
    for key in sorted(set((symbol, interval) for symbol in symbols for interval in INTERVALS)):
        series_rows = groups.get(key, [])
        if not series_rows:
            parsed[key] = {"usable": False, "reason": "no files"}
            continue
        if any(not _verifiable(row, cutoff) for row in series_rows):
            parsed[key] = {"usable": False, "reason": "file not verified"}
            continue
        all_bars: list[tuple[int, str, bool]] = []
        object_last_opens: dict[str, int] = {}
        counters = [0, 0, 0, 0]
        reason = None
        for row in series_rows:
            digest = row["sha256"]
            try:
                blob = (fetch_dir / "objects" / digest).read_bytes()
            except OSError as exc:
                raise Refusal("object changed after verification") from exc
            if hashlib.sha256(blob).hexdigest() != digest:
                raise Refusal("object changed after verification")
            start = _period_start(row)
            end = _row_period_end(start, row)
            try:
                bars, *counts = _read_archive(
                    blob, row, cutoff_us, INTERVALS[key[1]], start, end
                )
            except NotMockObject:
                raise
            except Refusal as exc:
                reason = str(exc)
                break
            finally:
                del blob
            all_bars.extend(bars)
            if bars:
                object_last_opens[row["path"]] = max(open_us for open_us, _, _ in bars)
            counters = [a + b for a, b in zip(counters, counts, strict=True)]
        if reason:
            parsed[key] = {"usable": False, "reason": reason}
            continue
        opens = [bar[0] for bar in all_bars]
        if len(opens) != len(set(opens)):
            parsed[key] = {"usable": False, "reason": "duplicate bar"}
            continue
        if key[1] == "1d":
            parsed[key] = {
                "usable": True,
                "reason": None,
                "bars": all_bars,
                "counts": counters,
                "last_bar_closes": {
                    path: _utc_text(_dt(open_us + INTERVALS[key[1]]))
                    for path, open_us in object_last_opens.items()
                },
            }
        else:
            window_start = cutoff_us - (
                HISTORY_BARS[OUTPUT_INTERVALS[key[1]]] * INTERVALS[key[1]]
            )
            parsed[key] = {
                "usable": True,
                "reason": None,
                "present": sum(window_start <= t < cutoff_us for t, _, _ in all_bars),
                "counts": counters,
                "last_bar_closes": {
                    path: _utc_text(_dt(open_us + INTERVALS[key[1]]))
                    for path, open_us in object_last_opens.items()
                },
            }
            del all_bars, opens
    daily_start_us = cutoff_us - DAILY_DAYS * 24 * 60 * 60 * 1_000_000
    output_symbols = []
    for symbol in sorted(symbols):
        daily = parsed[(symbol, "1d")]
        if daily["usable"]:
            bars = daily["bars"]
            window = [(t, v, anomaly) for t, v, anomaly in bars if daily_start_us <= t < cutoff_us]
            first = min((t for t, _, _ in bars), default=None)
            first_unflagged = min(
                (t for t, _, anomaly in bars if not anomaly), default=None
            )
            daily_out = {
                "usable": True,
                "reason": None,
                "objects": _object_identities(
                    groups.get((symbol, "1d"), []), daily["last_bar_closes"]
                ),
                "bars": [
                    {
                        "open_utc": _utc_text(_dt(t)),
                        "quote_volume": v,
                        "close_time_anomaly": anomaly,
                    }
                    for t, v, anomaly in sorted(window)
                ],
                "first_open_utc": _utc_text(_dt(first)) if first is not None else None,
                "first_unflagged_open_utc": (
                    _utc_text(_dt(first_unflagged)) if first_unflagged is not None else None
                ),
                "off_grid": daily["counts"][0],
                "zero_volume": daily["counts"][1],
                "close_time_anomalies": daily["counts"][2],
                "close_time_anomalies_all": daily["counts"][3],
            }
        else:
            daily_out = {
                "usable": False,
                "reason": daily["reason"],
                "objects": _object_identities(groups.get((symbol, "1d"), [])),
                "bars": None,
                "first_open_utc": None,
                "first_unflagged_open_utc": None,
                "off_grid": None,
                "zero_volume": None,
                "close_time_anomalies": None,
                "close_time_anomalies_all": None,
            }
        coverage = {}
        for interval in ("15m", "1h", "4h"):
            series = parsed[(symbol, interval)]
            out_name = OUTPUT_INTERVALS[interval]
            if series["usable"]:
                counts = series["counts"]
                coverage[out_name] = {
                    "usable": True,
                    "reason": None,
                    "present_in_window": series["present"],
                    "objects": _object_identities(
                        groups.get((symbol, interval), []), series["last_bar_closes"]
                    ),
                    "off_grid": counts[0],
                    "zero_volume": counts[1],
                    "close_time_anomalies": counts[2],
                    "close_time_anomalies_all": counts[3],
                }
            else:
                coverage[out_name] = {
                    "usable": False,
                    "reason": series["reason"],
                    "present_in_window": None,
                    "objects": _object_identities(groups.get((symbol, interval), [])),
                    "off_grid": None,
                    "zero_volume": None,
                    "close_time_anomalies": None,
                    "close_time_anomalies_all": None,
                }
        output_symbols.append({"symbol": symbol, "daily": daily_out, "coverage": coverage})
    result = {
        "parse_id": "ucpe.quant_ng.extract_parse.v4",
        "status": "MOCK",
        "note": (
            "parsed bars with per-file identities, not builder evidence: "
            "availability, revision and provenance policy are unruled"
        ),
        "cutoff_utc": _utc_text(cutoff),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "windows": {"daily_days": DAILY_DAYS, "history_bars": HISTORY_BARS},
        "files_after_cutoff": after,
        "symbols": output_symbols,
    }
    return _output_bytes(result)


def run(plan_arg: str) -> dict[str, Any]:
    plan_path = _path(plan_arg)
    try:
        _, plan = _json_bytes(plan_path, "plan unreadable")
    except Refusal as exc:
        if str(exc) == "plan unreadable":
            try:
                json.loads(plan_path.read_bytes(), object_pairs_hook=_FIT._no_duplicate_keys)
            except ValueError as parse_exc:
                if "duplicate key" in str(parse_exc):
                    raise Refusal("invalid plan") from parse_exc
            except OSError:
                pass
        raise
    if (
        not isinstance(plan, dict)
        or set(plan) != PLAN_KEYS
        or plan.get("plan_id") != "ucpe.quant_ng.extract.v1"
        or not all(isinstance(plan.get(key), str) for key in PLAN_KEYS - {"plan_id"})
    ):
        raise Refusal("invalid plan")
    cutoff = _instant(plan["cutoff_utc"])
    if cutoff.hour or cutoff.minute or cutoff.second or cutoff.microsecond:
        raise Refusal("cutoff is not UTC midnight")
    fetch_dir = _path(plan["fetch_output_dir"])
    output = _path(plan["output_dir"])
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise Refusal("output folder is not empty")
    payload = derive(fetch_dir, cutoff)
    _OUTPUT_HOLDER[0] = output
    created = _make_output(output)
    try:
        create_readonly(output / "PARSE.json", payload)
        return {"status": "PASS", "parse_sha256": hashlib.sha256(payload).hexdigest()}
    except BaseException:
        if output.exists():
            try:
                (output / "PARSE.json").unlink(missing_ok=True)
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
