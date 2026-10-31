#!/usr/bin/env python3
"""Bind re-derived MOCK parser output into provisional universe evidence.

Every refusal is printed as JSON with exit 2 and leaves no output behind.
Refusals include invalid plans or input digests, non-MOCK manifests, parse bytes
not derived from the manifest, invalid policy or non-market evidence, and a
nonempty output folder. MOCK only; not admissible to the builder until change
4b. D8 CT-2 and CT-3 interpretations are INFERRED from the bound policy text.
MOCK has no lineage source, so candidate lineage is
always null, meaning unknown and never "no ticker reuse". An unusable series is
null, never zero. Per-file provenance carries identities only; policy-derived
fields are explicitly pending change 3.

The MOCK changelog limitation is documented below: paths must be unique, so a
file updated twice cannot be represented. This format is an assumption until
the owner authorizes reading the venue's real files. Proxy timeframe 1D names
the parser's daily block.

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
    "changelog",
    "proxy_windows",
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
CHANGELOG_ASSUMPTION = (
    "This format is an assumption until the owner authorizes reading the venue's real files."
)
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


def check_changelog(obj: Any) -> None:
    if (
        not isinstance(obj, dict)
        or set(obj) != {"changelog_id", "source", "assumption", "entries"}
        or obj.get("changelog_id") != "ucpe.quant_ng.mock_changelog.v1"
        or obj.get("source") != "mock"
        or obj.get("assumption") != CHANGELOG_ASSUMPTION
        or not isinstance(obj.get("entries"), list)
    ):
        raise Refusal("invalid changelog")
    paths = set()
    for entry in obj["entries"]:
        if not isinstance(entry, dict) or set(entry) != {
            "path", "replaced_sha256", "replacement_sha256", "updated_utc"
        }:
            raise Refusal("invalid changelog")
        path = entry.get("path")
        if not isinstance(path, str) or not path or path in paths:
            raise Refusal("invalid changelog")
        paths.add(path)
        if any(
            not isinstance(entry.get(key), str) or not HEX_RE.fullmatch(entry[key])
            for key in ("replaced_sha256", "replacement_sha256")
        ):
            raise Refusal("invalid changelog")
        if entry["replaced_sha256"] == entry["replacement_sha256"]:
            raise Refusal("invalid changelog")
        try:
            _instant(entry.get("updated_utc"))
        except Refusal as exc:
            raise Refusal("invalid changelog") from exc


def check_proxy_windows(obj: Any) -> None:
    if (
        not isinstance(obj, dict)
        or set(obj) != {"windows_id", "source", "bases"}
        or obj.get("windows_id") != "ucpe.quant_ng.mock_proxy_windows.v1"
        or obj.get("source") != "mock"
        or not isinstance(obj.get("bases"), list)
    ):
        raise Refusal("invalid proxy windows")
    bases = set()
    for item in obj["bases"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"base", "refused_from_utc", "seams"}
            or not isinstance(item.get("base"), str)
            or not re.fullmatch(r"^[A-Z0-9]+$", item["base"])
            or item["base"] in bases
            or not isinstance(item.get("seams"), list)
        ):
            raise Refusal("invalid proxy windows")
        bases.add(item["base"])
        try:
            _instant(item.get("refused_from_utc"))
            for seam in item["seams"]:
                if (
                    not isinstance(seam, dict)
                    or set(seam) != {"from_utc", "to_utc", "timeframe"}
                    or seam.get("timeframe") not in {"15m", "1H", "4H", "1D"}
                    or _instant(seam.get("from_utc")) >= _instant(seam.get("to_utc"))
                ):
                    raise Refusal("invalid proxy windows")
        except Refusal as exc:
            raise Refusal("invalid proxy windows") from exc


def _file_provenance(item, availability, revision, changelog_entry):
    digest = item["sha256"]
    available = item["last_bar_close_utc"] if availability == "P-2" else None
    revisions = []
    complete = False
    if revision == "RP-0" and availability == "P-2":
        revisions = [{"sha256": digest, "available_from_utc": available}]
    elif revision == "RP-3":
        if changelog_entry is None:
            revisions = [{"sha256": digest, "available_from_utc": available}]
            complete = True
        else:
            old = changelog_entry["replaced_sha256"]
            new = changelog_entry["replacement_sha256"]
            updated = changelog_entry["updated_utc"]
            if digest == new:
                if (
                    availability == "P-2"
                    and available is not None
                    and _instant(available) >= _instant(updated)
                ):
                    raise Refusal("invalid changelog")
                complete = True
                revisions = [
                    {"sha256": old, "available_before_utc": updated},
                    {"sha256": new, "available_from_utc": updated},
                ]
                available = updated if available is not None else None
            elif digest == old:
                if availability == "P-2" and (
                    available is None or _instant(available) >= _instant(updated)
                ):
                    raise Refusal("invalid changelog")
                complete = True
                revisions = [
                    {"sha256": old, "available_from_utc": available},
                    {"sha256": new, "available_from_utc": updated},
                ]
            else:
                raise Refusal("STOP S5: unlisted revision")
    if availability == "P-1":
        available, revisions, complete = None, [], False
    return {
        "source": "mock",
        "sha256": digest,
        "official_checksum": item["official_checksum"],
        "available_from_utc": available,
        "revisions": revisions,
        "revision_history_complete": complete,
    }


def _provenance(series: dict[str, Any], policy_sha256: str, availability: str,
                revision: str, changelog: dict[str, Any] | None) -> dict[str, Any]:
    entries = {entry["path"]: entry for entry in (changelog or {}).get("entries", [])}
    return {
        "files": [
            {
                key: item[key]
                for key in (
                    "path",
                    "sha256",
                    "official_checksum",
                    "class",
                    "last_bar_close_utc",
                )
            } | _file_provenance(item, availability, revision, entries.get(item["path"]))
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
    policy: dict[str, Any],
    changelog: dict[str, Any] | None = None,
    proxy_windows: dict[str, Any] | None = None,
) -> dict[str, Any]:
    availability = policy["parameters"]["D4_availability"]["value"]
    revision = policy["parameters"]["D5_revision"]["value"]
    if revision in {"RP-1", "RP-2", "RP-3+RP-1"}:
        raise Refusal("policy detail unruled: capture time")
    close_time_option = policy["parameters"]["D8_close_time"]["value"]
    evidence_option = policy["parameters"]["D3_evidence"]["value"]
    if evidence_option == "E-1":
        raise Refusal("policy option not built: E-1")
    if evidence_option == "E-2":
        raise Refusal("policy option not built: E-2")
    if evidence_option == "E-3" and (
        non_market["exclusion_verification"]
        or non_market["not_leveraged_verification"]
    ):
        raise Refusal("invalid non-market evidence: E-3 holds no exclusion documents")
    candidates = []
    for symbol_data in parse["symbols"]:
        symbol = symbol_data["symbol"]
        if not isinstance(symbol, str) or not symbol.endswith("USDT"):
            raise Refusal("invalid parse symbol")
        daily = symbol_data["daily"]
        daily_unusable = (
            close_time_option == "CT-3"
            and daily["usable"]
            and daily["close_time_anomalies_all"] > 0
        )
        daily_usable = daily["usable"] and not daily_unusable
        daily_series = (
            {**daily, "usable": False, "reason": "close-time anomaly"}
            if daily_unusable
            else daily
        )
        daily_provenance = _provenance(
            daily_series, policy_sha256, availability, revision, changelog
        )
        coverage = {}
        for name in ("15m", "1H", "4H"):
            series = symbol_data["coverage"][name]
            series_unusable = (
                close_time_option == "CT-3"
                and series["usable"]
                and series["close_time_anomalies_all"] > 0
            )
            series_usable = series["usable"] and not series_unusable
            effective_series = (
                {**series, "usable": False, "reason": "close-time anomaly"}
                if series_unusable
                else series
            )
            coverage[name] = {
                "present_in_window": (
                    series["present_in_window"] - series["close_time_anomalies"]
                    if series_usable and close_time_option == "CT-2"
                    else series["present_in_window"] if series_usable else None
                ),
                "provenance": _provenance(
                    effective_series, policy_sha256, availability, revision, changelog
                ),
            }
        candidates.append(
            {
                "symbol": symbol,
                "base": symbol[:-4],
                "quote": "USDT",
                "lineage": None,
                "listing": {
                    "first_daily_bar_open_utc": (
                        daily["first_unflagged_open_utc"]
                        if close_time_option == "CT-2" and daily_usable
                        else daily["first_open_utc"] if daily_usable else None
                    ),
                    "provenance": daily_provenance,
                },
                "daily_quote_volume": {
                    "bars": [
                        {key: value for key, value in bar.items() if key != "close_time_anomaly"}
                        for bar in daily["bars"]
                        if close_time_option != "CT-2" or not bar["close_time_anomaly"]
                    ]
                    if daily_usable
                    else None,
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
            "changelog_path": None if changelog is None else changelog["path"],
            "changelog_sha256": None if changelog is None else changelog["sha256"],
            "proxy_windows_path": None if proxy_windows is None else proxy_windows["path"],
            "proxy_windows_sha256": None if proxy_windows is None else proxy_windows["sha256"],
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
    try:
        policy = _POLICY.load(policy_path, policy_sha)
    except _POLICY.Refusal as exc:
        raise Refusal(str(exc)) from exc
    named_changelog = policy["parameters"]["D5_revision"]["changelog_sha256"]
    named_windows = policy["parameters"]["D6_proxy"]["windows_sha256"]
    changelog_input = plan["changelog"]
    windows_input = plan["proxy_windows"]
    if named_changelog is None and changelog_input is not None:
        raise Refusal("invalid policy")
    if named_windows is None and windows_input is not None:
        raise Refusal("invalid policy")
    changelog_meta = windows_meta = None
    changelog = windows = None
    for input_value, named, label in (
        (changelog_input, named_changelog, "changelog"),
        (windows_input, named_windows, "proxy windows"),
    ):
        if named is not None and input_value is None:
            raise Refusal(f"policy detail unruled: {label}")
    if changelog_input is not None:
        changelog_path, changelog_raw, changelog_sha = _pin(changelog_input)
        if changelog_sha != named_changelog:
            raise Refusal("invalid policy")
        try:
            changelog = _json(changelog_raw)
        except (UnicodeError, ValueError, TypeError) as exc:
            raise Refusal("invalid changelog") from exc
        check_changelog(changelog)
        changelog_meta = {"path": str(changelog_path), "sha256": changelog_sha, **changelog}
    if windows_input is not None:
        windows_path, windows_raw, windows_sha = _pin(windows_input)
        if windows_sha != named_windows:
            raise Refusal("invalid policy")
        try:
            windows = _json(windows_raw)
        except (UnicodeError, ValueError, TypeError) as exc:
            raise Refusal("invalid proxy windows") from exc
        check_proxy_windows(windows)
        windows_meta = {"path": str(windows_path), "sha256": windows_sha, **windows}

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
            policy=policy,
            changelog=changelog_meta,
            proxy_windows=windows_meta,
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
