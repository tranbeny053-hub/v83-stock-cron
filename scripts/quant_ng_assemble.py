#!/usr/bin/env python3
"""Bind re-derived MOCK parser output into provisional universe evidence.

Every refusal is printed as JSON with exit 2 and leaves no output behind.
Refusals include invalid plans or input digests, non-MOCK manifests, parse bytes
not derived from the manifest, invalid policy or non-market evidence, and a
nonempty output folder. MOCK only; not admissible to the builder until change
4b; no policy interpreted. MOCK has no lineage source, so candidate lineage is
always null, meaning unknown and never "no ticker reuse". An unusable series is
null, never zero. Per-file provenance carries identities only; policy-derived
fields are explicitly pending change 3.

Usage: ``python -I -B scripts/quant_ng_assemble.py <plan.json>``.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

PLAN_KEYS = {
    "plan_id",
    "fetch_output_dir",
    "cutoff_utc",
    "parse",
    "policy",
    "non_market_evidence",
    "output_dir",
}
PIN_KEYS = {"path", "sha256"}
HEX_RE = re.compile(r"^[0-9a-f]{64}$")
NON_MARKET_KEYS = {
    "evidence_id",
    "source",
    "exclusion_verification",
    "not_leveraged_verification",
    "freshness",
}
_OUTPUT_HOLDER: list[Path | None] = [None]


def _load_parser():
    spec = importlib.util.spec_from_file_location(
        "quant_ng_extract_assemble", Path(__file__).with_name("quant_ng_extract.py")
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load parser")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


_EXTRACT = _load_parser()
Refusal = _EXTRACT._FIT.Refusal
_path = _EXTRACT._FIT._path
_json_bytes = _EXTRACT._FIT._json_bytes
_instant = _EXTRACT._FIT._instant
create_readonly = _EXTRACT._FIT.create_readonly
install_guard = _EXTRACT._FIT.install_guard
_make_output = _EXTRACT._FIT._make_output
_unwind = _EXTRACT._FIT._unwind


def _load_policy():
    spec = importlib.util.spec_from_file_location(
        "quant_ng_policy_assemble", Path(__file__).with_name("quant_ng_policy.py")
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load policy")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


_POLICY = _load_policy()


def _pin(value: Any) -> tuple[Path, bytes, str]:
    if not isinstance(value, dict) or set(value) != PIN_KEYS:
        raise Refusal("invalid plan")
    if not isinstance(value["path"], str) or not isinstance(value["sha256"], str):
        raise Refusal("invalid plan")
    if not HEX_RE.fullmatch(value["sha256"]):
        raise Refusal("invalid plan")
    path = _path(value["path"])
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise Refusal("input digest mismatch") from exc
    if hashlib.sha256(raw).hexdigest() != value["sha256"]:
        raise Refusal("input digest mismatch")
    return path, raw, value["sha256"]


def _json(raw: bytes) -> Any:
    return json.loads(raw, object_pairs_hook=_EXTRACT._FIT._no_duplicate_keys)


def check_non_market(obj: Any) -> None:
    if (
        not isinstance(obj, dict)
        or set(obj) != NON_MARKET_KEYS
        or obj.get("evidence_id") != "ucpe.quant_ng.non_market_evidence.v1"
        or obj.get("source") != "mock"
        or any(
            not isinstance(obj.get(key), list)
            for key in ("exclusion_verification", "not_leveraged_verification", "freshness")
        )
    ):
        raise Refusal("invalid non-market evidence")


def _provenance(series: dict[str, Any], policy_sha256: str) -> dict[str, Any]:
    return {
        "files": [
            {key: item[key] for key in ("path", "sha256", "official_checksum", "class")}
            for item in series["objects"]
        ],
        "series_usable": series["usable"],
        "series_reason": series["reason"],
        "policy_fields": {"policy_sha256": policy_sha256},
    }


def evidence(
    parse: dict[str, Any],
    *,
    fetch_dir: Path,
    parse_sha256: str,
    policy_path: Path,
    policy_sha256: str,
    non_market_path: Path,
    non_market_sha256: str,
    non_market: dict[str, Any],
) -> dict[str, Any]:
    candidates = []
    for symbol_data in parse["symbols"]:
        symbol = symbol_data["symbol"]
        if not isinstance(symbol, str) or not symbol.endswith("USDT"):
            raise Refusal("invalid parse symbol")
        daily = symbol_data["daily"]
        daily_provenance = _provenance(daily, policy_sha256)
        coverage = {}
        for name in ("15m", "1H", "4H"):
            series = symbol_data["coverage"][name]
            coverage[name] = {
                "present_in_window": (
                    series["present_in_window"] if series["usable"] else None
                ),
                "provenance": _provenance(series, policy_sha256),
            }
        candidates.append(
            {
                "symbol": symbol,
                "base": symbol[:-4],
                "quote": "USDT",
                "lineage": None,
                "listing": {
                    "first_daily_bar_open_utc": daily["first_open_utc"],
                    "provenance": daily_provenance,
                },
                "daily_quote_volume": {
                    "bars": daily["bars"] if daily["usable"] else None,
                    "provenance": daily_provenance,
                },
                "coverage": coverage,
            }
        )
    return {
        "evidence_id": "ucpe.quant_ng.universe_evidence.v1",
        "source": "mock",
        "candidates": candidates,
        "exclusion_verification": non_market["exclusion_verification"],
        "not_leveraged_verification": non_market["not_leveraged_verification"],
        "freshness": non_market["freshness"],
        "binding": {
            "fetch_output_dir": str(fetch_dir),
            "cutoff_utc": parse["cutoff_utc"],
            "parse_sha256": parse_sha256,
            "manifest_sha256": parse["manifest_sha256"],
            "policy_sha256": policy_sha256,
            "policy_path": str(policy_path),
            "non_market_sha256": non_market_sha256,
            "non_market_path": str(non_market_path),
            "assemble_tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
    }


def _output_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def run(plan_arg: str) -> dict[str, Any]:
    plan_path = _path(plan_arg)
    try:
        _, plan = _json_bytes(plan_path, "plan unreadable")
    except Refusal as exc:
        if str(exc) == "plan unreadable":
            try:
                json.loads(
                    plan_path.read_bytes(),
                    object_pairs_hook=_EXTRACT._FIT._no_duplicate_keys,
                )
            except ValueError as parse_exc:
                if "duplicate key" in str(parse_exc):
                    raise Refusal("invalid plan") from parse_exc
            except OSError:
                pass
        raise
    if (
        not isinstance(plan, dict)
        or set(plan) != PLAN_KEYS
        or plan.get("plan_id") != "ucpe.quant_ng.assemble.v1"
        or not all(
            isinstance(plan.get(key), str)
            for key in ("fetch_output_dir", "cutoff_utc", "output_dir")
        )
    ):
        raise Refusal("invalid plan")

    # Pin every supplied input before interpreting any of them.
    parse_path, parse_raw, parse_sha = _pin(plan["parse"])
    policy_path, policy_raw, policy_sha = _pin(plan["policy"])
    non_market_path, non_market_raw, non_market_sha = _pin(plan["non_market_evidence"])

    fetch_dir = _path(plan["fetch_output_dir"])
    cutoff = _instant(plan["cutoff_utc"])
    if cutoff.hour or cutoff.minute or cutoff.second or cutoff.microsecond:
        raise Refusal("cutoff is not UTC midnight")
    derived = _EXTRACT.derive(fetch_dir, cutoff)
    if derived != parse_raw:
        raise Refusal("parse not derived from manifest")
    try:
        parse = _json(parse_raw)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise Refusal("parse not derived from manifest") from exc
    if not isinstance(parse, dict):
        raise Refusal("parse not derived from manifest")
    try:
        policy = _POLICY.load(policy_path, policy_sha)
    except _POLICY.Refusal as exc:
        raise Refusal(str(exc)) from exc
    try:
        non_market = _json(non_market_raw)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise Refusal("invalid non-market evidence") from exc
    check_non_market(non_market)
    if policy["parameters"]["D3_evidence"]["non_market_sha256"] != non_market_sha:
        raise Refusal("invalid policy")

    output = _path(plan["output_dir"])
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise Refusal("output folder is not empty")
    payload = _output_bytes(
        evidence(
            parse,
            fetch_dir=fetch_dir,
            parse_sha256=parse_sha,
            policy_path=policy_path,
            policy_sha256=policy_sha,
            non_market_path=non_market_path,
            non_market_sha256=non_market_sha,
            non_market=non_market,
        )
    )
    _OUTPUT_HOLDER[0] = output
    created = _make_output(output)
    try:
        create_readonly(output / "EVIDENCE.json", payload)
        return {"status": "PASS", "evidence_sha256": hashlib.sha256(payload).hexdigest()}
    except BaseException:
        if output.exists():
            try:
                (output / "EVIDENCE.json").unlink(missing_ok=True)
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
        print(json.dumps({"status": "REFUSAL", "reason": f"run failed: {type(exc).__name__}"}))
        return 2
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
