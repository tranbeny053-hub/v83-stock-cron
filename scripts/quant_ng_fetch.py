#!/usr/bin/env python3
"""Run the offline mock archive fetch executor for OD-NG-5(b), step (b1) only.

This is synthetic/offline tooling against a local mock archive folder: no network,
no kline parsing, and no evidence construction. Every refusal is printed as JSON
with exit 2 and leaves no output behind. Refusals include: malformed or duplicate
plan keys, unsupported transport, invalid archive paths/symbols/intervals/periods,
reserved BTCUSDT or ETHUSDT, refused bases, protected paths, request cap exceeded,
archive path escapes the root, archive unreadable, object is not a mock object,
unreadable plan, nonempty output,
and unverified share above the cap. Guard refusals include filesystem change outside
the output folder: <event>. Path refusals include path must be absolute, symlink path,
protected path, forbidden tree, and invalid path. Unexpected run errors are reported
as run failed: <Type>. A real transport, listing step, and any download require the
owner's later authorizations.

Usage: ``python -I -B scripts/quant_ng_fetch.py <plan.json>``.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from datetime import date
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
PROTECTED = _FIT.PROTECTED
_OUTPUT_HOLDER: list[Path | None] = [None]

KEYS = {
    "plan_id",
    "transport",
    "mock_archive_root",
    "files",
    "refused_bases",
    "max_requests",
    "unverified_share_max",
    "output_dir",
}
LAYOUT = re.compile(
    r"^data/spot/(monthly|daily)/klines/([A-Z0-9]+USDT)/(15m|1h|4h|1d)/([A-Z0-9]+)-([0-9A-Za-z]+)-(.+)\.zip$"
)
BASE = re.compile(r"^[A-Z0-9]+$")
CHECKSUM = re.compile(rb"^([0-9a-f]{64})  ([^\r\n]+)(?:\n)?$")
MOCK_MARKER = b"UCPE-MOCK-v1"


def _has_mock_marker(blob: bytes) -> bool:
    tail = blob[-34:]
    return (
        len(blob) >= 34
        and tail[:4] == b"PK\x05\x06"
        and tail[-14:-12] == b"\x0c\x00"
        and tail[-12:] == MOCK_MARKER
    )


def _manifest_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def _cleanup(output: Path) -> None:
    if output.exists():
        for item in sorted(output.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            try:
                if item.is_file() or item.is_symlink():
                    item.chmod(0o600) if not item.is_symlink() else None
                    item.unlink()
                elif item.is_dir():
                    item.rmdir()
            except OSError:
                pass


def _archive_fields(value: Any, refused_bases: list[str]) -> dict[str, str]:
    if not isinstance(value, str) or any(
        fragment in part.lower() for part in value.split("/") for fragment in PROTECTED
    ):
        raise Refusal("protected path")
    match = LAYOUT.fullmatch(value)
    if not match:
        raise Refusal("not an archive kline path")
    granularity, symbol, interval, filename_symbol, filename_interval, period = match.groups()
    if symbol != filename_symbol or interval != filename_interval or (symbol[:-4] == ""):
        raise Refusal("not an archive kline path")
    base = symbol[:-4]
    if symbol in {"BTCUSDT", "ETHUSDT"}:
        raise Refusal("BTCUSDT and ETHUSDT are never requested")
    if base in refused_bases:
        raise Refusal("refused base")
    if granularity == "monthly":
        valid_period = bool(re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", period))
        if valid_period:
            try:
                date.fromisoformat(period + "-01")
            except ValueError:
                valid_period = False
    else:
        valid_period = bool(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", period))
        if valid_period:
            try:
                date.fromisoformat(period)
            except ValueError:
                valid_period = False
    if not valid_period:
        raise Refusal("not an archive kline path")
    return {
        "symbol": symbol,
        "base": base,
        "interval": interval,
        "granularity": granularity,
        "period": period,
    }


def run(plan_arg: str) -> dict[str, Any]:
    plan_path = _path(plan_arg)
    plan_bytes, plan = _json_bytes(plan_path, "plan unreadable")
    if (
        not isinstance(plan, dict)
        or set(plan) != KEYS
        or plan.get("plan_id") != "ucpe.quant_ng.fetch.v1"
    ):
        raise Refusal("invalid plan")
    if plan["transport"] != "mock":
        raise Refusal("only the mock transport exists")
    if not isinstance(plan["refused_bases"], list) or any(
        not isinstance(b, str) or not BASE.fullmatch(b) for b in plan["refused_bases"]
    ):
        raise Refusal("invalid plan")
    files = plan["files"]
    if not isinstance(files, list) or not files:
        raise Refusal("invalid plan")
    if any(not isinstance(row, dict) or set(row) != {"path"} for row in files):
        raise Refusal("invalid plan")
    paths = [row["path"] for row in files]
    if any(not isinstance(path, str) for path in paths):
        raise Refusal("invalid plan")
    if len(set(paths)) != len(paths):
        raise Refusal("invalid plan")
    fields = [_archive_fields(path, plan["refused_bases"]) for path in paths]
    cap = plan["max_requests"]
    share = plan["unverified_share_max"]
    if (
        isinstance(cap, bool)
        or not isinstance(cap, int)
        or cap < 1
        or isinstance(share, bool)
        or not isinstance(share, (int, float))
        or not 0 <= share <= 1
    ):
        raise Refusal("invalid plan")
    if 2 * len(files) > cap:
        raise Refusal("request cap exceeded")
    root = _path(plan["mock_archive_root"])
    output = _path(plan["output_dir"])
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise Refusal("output folder is not empty")
    # The guard allows writes inside the output folder only, so a new parent folder is refused
    # before anything is made, as in the fit tool and the builder. A refusal later on unwinds
    # exactly what this run created.
    _OUTPUT_HOLDER[0] = output
    created = _make_output(output)
    try:
        tool_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        objects = output / "objects"
        objects.mkdir()
        counts = {name: 0 for name in ("missing", "checksum_malformed", "mismatch", "ok")}
        results = []
        for path, meta in zip(paths, fields, strict=True):
            payloads: list[bytes | None] = []
            for suffix in ("", ".CHECKSUM"):
                candidate = root / (path + suffix)
                walked = root
                for component in Path(path + suffix).parts:
                    walked = walked / component
                    if walked.is_symlink():
                        raise Refusal("archive path escapes the root")
                try:
                    resolved = candidate.resolve(strict=True)
                    resolved.relative_to(root)
                    payloads.append(resolved.read_bytes())
                except FileNotFoundError:
                    payloads.append(None)
                except ValueError:
                    raise Refusal("archive path escapes the root") from None
                except OSError:
                    raise Refusal("archive unreadable") from None
            zdata, cdata = payloads
            if zdata is not None and not _has_mock_marker(zdata):
                raise Refusal("object is not a mock object")
            for blob in payloads:
                if blob is not None:
                    digest = hashlib.sha256(blob).hexdigest()
                    target = objects / digest
                    if not target.exists():
                        create_readonly(target, blob)
            official = None
            if zdata is None or cdata is None:
                cls = "missing"
            else:
                parsed = CHECKSUM.fullmatch(cdata)
                if not parsed or parsed.group(2) != Path(path).name.encode():
                    cls = "checksum_malformed"
                else:
                    official = parsed.group(1).decode()
                    cls = "ok" if hashlib.sha256(zdata).hexdigest() == official else "mismatch"
            counts[cls] += 1
            results.append(
                {
                    **{"path": path},
                    **meta,
                    "class": cls,
                    "sha256": hashlib.sha256(zdata).hexdigest() if zdata is not None else None,
                    "size": len(zdata) if zdata is not None else None,
                    "official_checksum": official,
                    "checksum_file_sha256": hashlib.sha256(cdata).hexdigest()
                    if cdata is not None
                    else None,
                }
            )
        if (
            sum(counts[k] for k in ("missing", "checksum_malformed", "mismatch")) / len(files)
            > share
        ):
            raise Refusal("unverified share above the cap")
        manifest = {
            "manifest_id": "ucpe.quant_ng.fetch_manifest.v1",
            "status": "MOCK",
            "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
            "tool_sha256": tool_sha,
            "transport": "mock",
            "requests": 2 * len(files),
            "counts": counts,
            "files": results,
        }
        create_readonly(output / "MANIFEST.json", _manifest_bytes(manifest))
        return {
            "status": "PASS",
            "manifest_sha256": hashlib.sha256((output / "MANIFEST.json").read_bytes()).hexdigest(),
        }
    except BaseException:
        _cleanup(output)
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
