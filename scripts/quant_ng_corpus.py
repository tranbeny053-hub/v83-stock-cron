#!/usr/bin/env python3
"""Build synthetic, dormant as-of universe snapshots for OD-NG-5(a).

This tool builds membership snapshots and their input manifest. It does not fetch
or use real data (OD-NG-5(b)), define a completeness constant (OD-NG-7 item 7.1),
or produce evaluation rows or outcome accounting. Ruled values live in
UNIVERSE_RULE_v1.json, pinned by its SHA-256 digest. Plans and evidence follow
the schemas validated below. Exit codes are 0 for PASS and 2 for REFUSAL. The
F-C firewall ships an admissibility check requiring a clean methodology and no
F3-calendar overlap; it does not make F3 judgments.

Plan schema (all keys required; unknown keys are refused)::

    {"plan_id": "ucpe.quant_ng.universe.v1", "as_of_utc": "<ISO-8601 Z, a UTC midnight>",
     "evidence": {"path": "<file>", "sha256": "<64 lowercase hex>"},
     "operating_period_start": {"utc": "<ISO-8601 Z or null>", "provenance": "<text or null>"},
     "completeness": {"threshold": "<synthetic test number>", "ruling": "SYNTHETIC_TEST_ONLY"},
     "output_dir": "<new or empty folder>"}

Evidence schema::

    {"evidence_id": "ucpe.quant_ng.universe_evidence.v1", "source": "synthetic",
     "candidates": [{"symbol", "base", "quote", "lineage", "listing",
                     "daily_quote_volume", "coverage"}],
     "exclusion_verification": [{"base", "class", "valid_from_utc", "valid_to_utc", "provenance"}],
     "not_leveraged_verification": [{"base", "valid_from_utc", "valid_to_utc", "provenance"}],
     "freshness": [{"symbol", "timeframe", "span_start_utc", "span_end_utc",
                    "state", "provenance"}]}

Each provenance value has source, sha256, official_checksum, available_from_utc,
revisions, and revision_history_complete. Candidate listing and volume values
pair their fields with provenance; coverage maps each timeframe to a present bar
count and provenance. Per-file provenance uses ``{"files": [...], ...}`` and
requires ``policy_fields`` to contain exactly ``policy_sha256`` with a lowercase
SHA-256 value. A bound revision records the old digest with
``available_before_utc`` and the held digest with its exact
``available_from_utc`` replacement instant.

Rules implemented from OD_NG_5_PART_A_RULED.md §2:
B1 — verified as-of exclusions and leveraged-token trigger verification.
B2 — known freshness states and freshness evidence precedence.
B3 — operating-period protection and unknown when its start is absent.
B4 — calendar-overlap and methodology firewall stamping.
B5 — historical availability and revision provenance checks.
B6 — synthetic-only completeness threshold requirement.
B7 — top-30 undecidability and the contenders that actually block it.
B8 — refusal of membership bars and listing dates at or after T.
G-1 (a′) — trading at T, synthetic-only.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import sys
from datetime import datetime, timedelta
from decimal import Context, Decimal, Inexact, InvalidOperation, Rounded, localcontext
from pathlib import Path
from typing import Any

UNIVERSE_RULE_V1_SHA256 = "1f81113bb00983a17fa5924569c30a9982efac83676f9495c106cd5bf3cfbb39"
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
_no_duplicate_keys = _FIT._no_duplicate_keys
_json_bytes = _FIT._json_bytes
create_readonly = _FIT.create_readonly
install_guard = _FIT.install_guard
_make_output = _FIT._make_output
_unwind = _FIT._unwind
PROTECTED = _FIT.PROTECTED
FORBIDDEN_TREES = _FIT.FORBIDDEN_TREES
_OUTPUT_HOLDER: list[Path | None] = [None]

PLAN_KEYS = {
    "plan_id",
    "as_of_utc",
    "evidence",
    "operating_period_start",
    "completeness",
    "output_dir",
}
PROV_KEYS = {
    "source",
    "sha256",
    "official_checksum",
    "available_from_utc",
    "revisions",
    "revision_history_complete",
}
ASSEMBLE_BINDING_KEYS = {
    "fetch_output_dir",
    "cutoff_utc",
    "parse_sha256",
    "manifest_sha256",
    "policy_sha256",
    "policy_path",
    "non_market_sha256",
    "non_market_path",
    "changelog_path",
    "changelog_sha256",
    "proxy_windows_path",
    "proxy_windows_sha256",
    "assemble_tool_sha256",
}
HEX_RE = re.compile(r"^[0-9a-f]{64}$")
# A base asset is upper-case letters and digits only, and a symbol is exactly its base followed by
# the ruled quote. Anything else — lower case, padding, a declared base that is not the symbol's —
# is refused, because every rule below (the reserved symbols, the exclusion lists, the known cells)
# matches on these strings exactly, and a non-canonical spelling would slip past all of them.
BASE_RE = re.compile(r"^[A-Z0-9]+$")
# A volume is a plain non-negative decimal string: no JSON number (a binary float), no sign, no
# exponent, no underscore or padding.
VOLUME_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")
# Medians and thresholds are computed exactly: any rounding raises, and is refused.
EXACT = Context(prec=1000, traps=[Inexact, Rounded, InvalidOperation])


def instant(value: Any) -> datetime:
    try:
        return _FIT._instant(value)
    except Refusal as exc:
        raise Refusal("malformed instant") from exc


def _load_assembler():
    spec = importlib.util.spec_from_file_location(
        "quant_ng_assemble_corpus", Path(__file__).with_name("quant_ng_assemble.py")
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load assembler")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    previous_fit = sys.modules.get("quant_ng_fit")
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
        if previous_fit is not None:
            sys.modules["quant_ng_fit"] = previous_fit
        else:
            sys.modules.pop("quant_ng_fit", None)
    return module


def _load_policy():
    spec = importlib.util.spec_from_file_location(
        "quant_ng_policy_corpus", Path(__file__).with_name("quant_ng_policy.py")
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


def __getattr__(name: str):
    if name == "_ASSEMBLE":
        return _load_assembler()
    raise AttributeError(name)


def load_rule(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise Refusal("rule unreadable") from exc
    if hashlib.sha256(raw).hexdigest() != UNIVERSE_RULE_V1_SHA256:
        raise Refusal("rule digest mismatch")
    try:
        parsed = json.loads(raw, object_pairs_hook=_no_duplicate_keys)
    except (ValueError, UnicodeError) as exc:
        raise Refusal("rule malformed") from exc
    if not isinstance(parsed, dict):
        raise Refusal("rule malformed")
    return parsed


def _prov(
    raw: Any, cutoff: datetime, expected_policy_sha256: str | None = None,
    allowed_source: str = "synthetic",
) -> tuple[bool, dict[str, Any]]:
    # The synthetic-only gate comes first, so a non-synthetic record is refused even when it is
    # also malformed, instead of being quietly treated as unknown.
    source_reason = f"source must be {allowed_source}"
    if isinstance(raw, dict) and "source" in raw and raw["source"] != allowed_source:
        raise Refusal(source_reason)
    if isinstance(raw, dict) and "files" in raw:
        if set(raw) != {"files", "series_usable", "series_reason", "policy_fields"}:
            return False, {}
        files = raw.get("files")
        if isinstance(files, list) and any(
            isinstance(item, dict)
            and "source" in item
            and item["source"] != allowed_source
            for item in files
        ):
            raise Refusal(source_reason)
        if (
            raw.get("series_usable") is not True
            or not isinstance(files, list)
            or not files
            or not isinstance(raw.get("policy_fields"), dict)
            or set(raw["policy_fields"]) != {"policy_sha256"}
            or not isinstance(raw["policy_fields"].get("policy_sha256"), str)
            or not HEX_RE.fullmatch(raw["policy_fields"]["policy_sha256"])
            or expected_policy_sha256 is None
            or raw["policy_fields"]["policy_sha256"] != expected_policy_sha256
        ):
            return False, {}
        # The assembler's pending policy fields keep its MOCK series fail-closed.
        metadata = []
        for item in files:
            if isinstance(item, dict) and "source" in item and item["source"] != allowed_source:
                raise Refusal(source_reason)
            if not isinstance(item, dict) or set(item) != PROV_KEYS | {"path", "class"}:
                return False, {}
            if item["class"] != "ok":
                return False, {}
            usable, stamp = _prov(
                {key: item[key] for key in PROV_KEYS}, cutoff,
                expected_policy_sha256=expected_policy_sha256,
                allowed_source=allowed_source,
            )
            if not usable:
                return False, {}
            metadata.append(stamp)
        return True, {"files": metadata}
    if not isinstance(raw, dict) or set(raw) != PROV_KEYS:
        return False, {}
    sha = raw.get("sha256")
    official = raw.get("official_checksum")
    if (
        not isinstance(sha, str)
        or not HEX_RE.fullmatch(sha)
        or not isinstance(official, str)
        or not HEX_RE.fullmatch(official)
    ):
        return False, {}
    try:
        available = instant(raw.get("available_from_utc"))
    except Refusal:
        return False, {}
    revisions = raw.get("revisions")
    if not isinstance(revisions, list) or raw.get("revision_history_complete") is not True:
        return False, {}
    checked = []
    for item in revisions:
        if not isinstance(item, dict) or set(item) not in (
            {"sha256", "available_from_utc"},
            {"sha256", "available_before_utc"},
        ):
            return False, {}
        digest = item.get("sha256")
        if not isinstance(digest, str) or not HEX_RE.fullmatch(digest):
            return False, {}
        if "available_before_utc" in item:
            try:
                instant(item.get("available_before_utc"))
            except Refusal:
                return False, {}
            continue
        try:
            date = instant(item.get("available_from_utc"))
        except Refusal:
            return False, {}
        checked.append((date, digest))
    if not any(digest == sha and date == available for date, digest in checked):
        return False, {}
    current = [entry for entry in checked if entry[0] <= cutoff]
    # The revision current at T is the latest one available at or before T. Two different digests
    # published at that same instant leave no single current revision, so the record is unknown.
    latest = max((date for date, _ in current), default=None)
    at_latest = {digest for date, digest in current if date == latest}
    usable = sha == official and at_latest == {sha} and available <= cutoff
    return usable, {"sha256": sha, "available_from_utc": raw["available_from_utc"]}


def verify_derived(bundle: dict) -> dict[str, Any]:
    """Verify assembler evidence against its bound source files and parser output."""
    assembler = None
    try:
        binding = bundle.get("binding") if isinstance(bundle, dict) else None
        if not isinstance(binding, dict) or set(binding) != ASSEMBLE_BINDING_KEYS:
            raise Refusal("evidence not bound")
        for key in ("fetch_output_dir", "cutoff_utc", "policy_path", "non_market_path"):
            if not isinstance(binding.get(key), str):
                raise Refusal("evidence not bound")
        for key in (
            "parse_sha256",
            "manifest_sha256",
            "policy_sha256",
            "non_market_sha256",
            "assemble_tool_sha256",
        ):
            if not isinstance(binding.get(key), str) or not HEX_RE.fullmatch(binding[key]):
                raise Refusal("evidence not bound")
        for path_key, digest_key in (
            ("changelog_path", "changelog_sha256"),
            ("proxy_windows_path", "proxy_windows_sha256"),
        ):
            path_value, digest_value = binding.get(path_key), binding.get(digest_key)
            if (path_value is None) != (digest_value is None):
                raise Refusal("evidence not bound")
            if path_value is not None and (
                not isinstance(path_value, str)
                or not isinstance(digest_value, str)
                or not HEX_RE.fullmatch(digest_value)
            ):
                raise Refusal("evidence not bound")
        try:
            fetch_dir = _path(binding["fetch_output_dir"])
            policy_path = _path(binding["policy_path"])
            non_market_path = _path(binding["non_market_path"])
        except Refusal as exc:
            raise Refusal("evidence not bound") from exc
        if any(
            str(path) != binding[key]
            for path, key in (
                (fetch_dir, "fetch_output_dir"),
                (policy_path, "policy_path"),
                (non_market_path, "non_market_path"),
            )
        ):
            raise Refusal("evidence not bound")
        assembler = _load_assembler()
        policy_module = _load_policy()
        try:
            policy_raw = policy_path.read_bytes()
            non_market_raw = non_market_path.read_bytes()
            manifest_raw = (fetch_dir / "MANIFEST.json").read_bytes()
        except OSError as exc:
            raise Refusal("evidence not bound") from exc
        if (
            hashlib.sha256(policy_raw).hexdigest() != binding["policy_sha256"]
            or hashlib.sha256(non_market_raw).hexdigest() != binding["non_market_sha256"]
            or hashlib.sha256(manifest_raw).hexdigest() != binding["manifest_sha256"]
        ):
            raise Refusal("evidence not bound")
        try:
            non_market = assembler._json(non_market_raw)
            assembler.check_non_market(non_market)
        except assembler.Refusal as exc:
            raise Refusal(str(exc)) from exc
        try:
            policy = policy_module.load(policy_path, binding["policy_sha256"])
        except policy_module.Refusal as exc:
            raise Refusal(str(exc)) from exc
        named_values = (
            (
                "changelog_path",
                "changelog_sha256",
                policy["parameters"]["D5_revision"]["changelog_sha256"],
                "changelog",
            ),
            (
                "proxy_windows_path",
                "proxy_windows_sha256",
                policy["parameters"]["D6_proxy"]["windows_sha256"],
                "proxy windows",
            ),
        )
        extra_inputs = {}
        for path_key, digest_key, named, label in named_values:
            path_value, digest_value = binding[path_key], binding[digest_key]
            if named is None:
                if path_value is not None or digest_value is not None:
                    raise Refusal("evidence not bound")
                extra_inputs[label] = None
                continue
            if path_value is None:
                raise Refusal(f"policy detail unruled: {label}")
            if digest_value != named:
                raise Refusal("evidence not bound")
            try:
                extra_path = _path(path_value)
                if str(extra_path) != path_value:
                    raise Refusal("evidence not bound")
                extra_raw = extra_path.read_bytes()
            except (OSError, Refusal) as exc:
                raise Refusal("evidence not bound") from exc
            if hashlib.sha256(extra_raw).hexdigest() != digest_value:
                raise Refusal("evidence not bound")
            try:
                extra_obj = assembler._json(extra_raw)
                checker = (
                    assembler.check_changelog
                    if label == "changelog"
                    else assembler.check_proxy_windows
                )
                checker(extra_obj)
            except assembler.Refusal as exc:
                raise Refusal(str(exc)) from exc
            extra_inputs[label] = {"path": path_value, "sha256": digest_value, **extra_obj}
        if (
            policy["parameters"]["D3_evidence"]["non_market_sha256"]
            != binding["non_market_sha256"]
        ):
            raise Refusal("evidence not bound")
        cutoff = instant(binding["cutoff_utc"])
        if cutoff.hour or cutoff.minute or cutoff.second or cutoff.microsecond:
            raise Refusal("evidence not bound")
        parse_raw = assembler._EXTRACT.derive(fetch_dir, cutoff)
        if hashlib.sha256(parse_raw).hexdigest() != binding["parse_sha256"]:
            raise Refusal("parse not derived from manifest")
        parse = assembler._json(parse_raw)
        if not isinstance(parse, dict) or parse.get("cutoff_utc") != binding["cutoff_utc"]:
            raise Refusal("evidence not bound")
        recomputed = assembler.evidence(
            parse,
            fetch_dir=fetch_dir,
            parse_sha256=binding["parse_sha256"],
            policy_path=policy_path,
            policy_sha256=binding["policy_sha256"],
            non_market_path=non_market_path,
            non_market_sha256=binding["non_market_sha256"],
            non_market=non_market,
            policy=policy,
            changelog=extra_inputs["changelog"],
            proxy_windows=extra_inputs["proxy windows"],
        )
        compare_bundle = dict(bundle)
        compare_bundle["binding"] = dict(binding)
        compare_bundle["binding"].pop("assemble_tool_sha256")
        recomputed["binding"].pop("assemble_tool_sha256")
        if assembler._output_bytes(compare_bundle) != assembler._output_bytes(recomputed):
            raise Refusal("evidence not derived from parse")
        return {
            "policy": policy,
            "changelog": extra_inputs["changelog"],
            "proxy_windows": extra_inputs["proxy windows"],
        }
    except Refusal:
        raise
    except Exception as exc:
        if assembler is not None and isinstance(exc, assembler.Refusal):
            raise Refusal(str(exc)) from exc
        if isinstance(exc, (OSError, ValueError, TypeError, KeyError, AttributeError)):
            raise Refusal("evidence not bound") from exc
        raise


def _canonical_symbol(symbol: Any, quote: str) -> bool:
    return (
        isinstance(symbol, str)
        and symbol.endswith(quote)
        and bool(BASE_RE.fullmatch(symbol[: -len(quote)]))
    )


def _volume_key(record: dict[str, Any]) -> tuple[Decimal, str]:
    """Rank by median volume descending, then symbol ascending. `copy_negate` is exact; a unary
    minus would round in the default 28-digit context and could reorder two large medians."""

    return Decimal(record["median_daily_quote_volume"]).copy_negate(), record["symbol"]


def _span_covers(start: datetime, end: datetime | None, at: datetime) -> bool:
    return start <= at and (end is None or at < end)


def _prov_entries(
    raw: Any, cutoff: datetime, expected: set[str], *,
    allowed_source: str = "synthetic", expected_policy_sha256: str | None = None,
) -> list[tuple[dict[str, Any], bool]]:
    if not isinstance(raw, list):
        raise Refusal("malformed verification list")
    out = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != expected:
            raise Refusal("malformed verification entry")
        usable, _ = _prov(item.get("provenance"), cutoff,
                          expected_policy_sha256=expected_policy_sha256,
                          allowed_source=allowed_source)
        start = instant(item.get("valid_from_utc"))
        end = None if item.get("valid_to_utc") is None else instant(item["valid_to_utc"])
        if end is not None and end <= start:
            raise Refusal("malformed verification span")
        out.append((item, usable and _span_covers(start, end, cutoff)))
    return out


def _candidate_rows(
    bundle: Any, rule: dict[str, Any], cutoff: datetime,
    verified: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(bundle, dict):
        raise Refusal("malformed evidence")
    source = bundle.get("source")
    if source == "mock" and verified is None:
        verified = verify_derived(bundle)
    allowed_source = "mock" if source == "mock" else "synthetic"
    expected_policy_sha256 = (
        bundle["binding"]["policy_sha256"] if allowed_source == "mock" else None
    )
    if not isinstance(bundle, dict) or set(bundle) != {
        "evidence_id",
        "source",
        "candidates",
        "exclusion_verification",
        "not_leveraged_verification",
        "freshness",
    }:
        raise Refusal("malformed evidence")
    if (
        bundle.get("evidence_id") != "ucpe.quant_ng.universe_evidence.v1"
        or source not in {"synthetic", "mock"}
    ):
        if source not in {"synthetic", "mock"}:
            raise Refusal("source must be synthetic")
        raise Refusal("malformed evidence")
    if source == "mock" and verified is None:
        raise Refusal("evidence not bound")
    if not all(
        isinstance(bundle.get(k), list)
        for k in ("candidates", "exclusion_verification", "not_leveraged_verification", "freshness")
    ):
        raise Refusal("malformed evidence")
    exclusions = _prov_entries(
        bundle["exclusion_verification"],
        cutoff,
        {"base", "class", "valid_from_utc", "valid_to_utc", "provenance"},
        allowed_source=allowed_source, expected_policy_sha256=expected_policy_sha256,
    )
    not_lev = _prov_entries(
        bundle["not_leveraged_verification"],
        cutoff,
        {"base", "valid_from_utc", "valid_to_utc", "provenance"},
        allowed_source=allowed_source, expected_policy_sha256=expected_policy_sha256,
    )
    for item, _ in exclusions:
        if (
            not isinstance(item["base"], str)
            or not BASE_RE.fullmatch(item["base"])
            or item["class"] not in {"pegged", "asset_backed", "wrapped", "leveraged"}
        ):
            raise Refusal("malformed exclusion verification")
    for item, _ in not_lev:
        if not isinstance(item["base"], str) or not BASE_RE.fullmatch(item["base"]):
            raise Refusal("malformed not-leveraged verification")
    tf_names = tuple(rule["history_window_bars"])
    rows = []
    seen = set()
    for c in bundle["candidates"]:
        if not isinstance(c, dict) or set(c) != {
            "symbol",
            "base",
            "quote",
            "lineage",
            "listing",
            "daily_quote_volume",
            "coverage",
        }:
            raise Refusal("malformed candidate")
        symbol, base = c["symbol"], c["base"]
        if not isinstance(base, str) or not BASE_RE.fullmatch(base):
            raise Refusal("non-canonical base")
        if c["quote"] != rule["quote"]:
            raise Refusal("quote mismatch")
        if base == rule["quote"] or symbol != base + rule["quote"]:
            raise Refusal("non-canonical symbol")
        if symbol in seen:
            raise Refusal("duplicate or malformed symbol")
        if c["lineage"] is not None and (
            not isinstance(c["lineage"], str) or not BASE_RE.fullmatch(c["lineage"])
        ):
            raise Refusal("malformed lineage")
        seen.add(symbol)
        if symbol in rule["not_candidates"]:
            raise Refusal("not a candidate")
        listing, volume = c["listing"], c["daily_quote_volume"]
        if (
            not isinstance(listing, dict)
            or set(listing) != {"first_daily_bar_open_utc", "provenance"}
            or not isinstance(volume, dict)
            or set(volume) != {"bars", "provenance"}
        ):
            raise Refusal("malformed listing or volume")
        first = instant(listing["first_daily_bar_open_utc"])
        if first.hour or first.minute or first.second or first.microsecond:
            raise Refusal("listing date is not UTC midnight")
        if first >= cutoff:
            raise Refusal("evidence date at or after T")
        lu, lp = _prov(listing["provenance"], cutoff, expected_policy_sha256, allowed_source)
        vu, vp = _prov(volume["provenance"], cutoff, expected_policy_sha256, allowed_source)
        bars = volume["bars"]
        if not isinstance(bars, list):
            raise Refusal("malformed daily bars")
        parsed_bars = []
        for bar in bars:
            if not isinstance(bar, dict) or set(bar) != {"open_utc", "quote_volume"}:
                raise Refusal("malformed daily bar")
            dt = instant(bar["open_utc"])
            if dt.hour or dt.minute or dt.second or dt.microsecond:
                raise Refusal("daily bar is not UTC midnight")
            if dt >= cutoff:
                raise Refusal("daily bar at or after T")
            raw_volume = bar["quote_volume"]
            if not isinstance(raw_volume, str) or not VOLUME_RE.fullmatch(raw_volume):
                raise Refusal("malformed volume")
            number = Decimal(raw_volume)
            parsed_bars.append((dt, number))
        if len({x[0] for x in parsed_bars}) != len(parsed_bars):
            raise Refusal("duplicate daily bar")
        coverage = c["coverage"]
        if not isinstance(coverage, dict) or set(coverage) != set(tf_names):
            raise Refusal("malformed coverage")
        cov = {}
        for tf in tf_names:
            cell = coverage[tf]
            if not isinstance(cell, dict) or set(cell) != {"present_in_window", "provenance"}:
                raise Refusal("malformed coverage")
            count = cell["present_in_window"]
            if (
                isinstance(count, bool)
                or not isinstance(count, int)
                or count < 0
                or count > rule["history_window_bars"][tf]
            ):
                raise Refusal("invalid coverage count")
            usable, prov = _prov(cell["provenance"], cutoff, expected_policy_sha256, allowed_source)
            cov[tf] = {"count": count, "usable": usable, "input": prov}
        rows.append(
            {
                "symbol": symbol,
                "base": base,
                "lineage": c["lineage"],
                "first": first,
                "listing_usable": lu,
                "volume_usable": vu,
                "bars": parsed_bars,
                "coverage": cov,
                "listing_input": lp,
                "volume_input": vp,
                "exclusions": exclusions,
                "not_lev": not_lev,
            }
        )
    return rows


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    vals = sorted(values)
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    try:
        with localcontext(EXACT):
            return (vals[mid - 1] + vals[mid]) / Decimal(2)
    except (Inexact, Rounded) as exc:
        raise Refusal("volume beyond exact precision") from exc


def _exact_product(a: Decimal, b: Decimal) -> Decimal:
    with localcontext(EXACT):
        return a * b


def _decimal_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _freshness(
    bundle: dict[str, Any],
    row: dict[str, Any],
    tf: str,
    start: datetime,
    end: datetime,
    operating: datetime | None,
    rule: dict[str, Any],
    cutoff: datetime,
    allowed_source: str = "synthetic",
    expected_policy_sha256: str | None = None,
) -> str:
    known = rule["freshness"]["known_not_fresh"]
    for entry in known:
        if row["symbol"] in entry["symbols"] and tf in entry["timeframes"]:
            return entry["state"]
    if operating is None:
        return "unknown"
    if start < end and end > operating:
        return "operating_period"
    overlapping = []
    for item in bundle["freshness"]:
        if not isinstance(item, dict) or set(item) != {
            "symbol",
            "timeframe",
            "span_start_utc",
            "span_end_utc",
            "state",
            "provenance",
        }:
            raise Refusal("malformed freshness entry")
        usable, _ = _prov(item["provenance"], cutoff, expected_policy_sha256, allowed_source)
        a, b = instant(item["span_start_utc"]), instant(item["span_end_utc"])
        if b <= a:
            raise Refusal("malformed freshness span")
        if (
            item["state"] not in {"fresh", "spent", "unspent_unproven"}
            or not _canonical_symbol(item["symbol"], rule["quote"])
            or item["timeframe"] not in rule["history_window_bars"]
        ):
            raise Refusal("malformed freshness state")
        overlaps = a < end and b > start
        if item["symbol"] == row["symbol"] and item["timeframe"] == tf and overlaps:
            overlapping.append((item, usable, a, b))
    for state in ("spent", "unspent_unproven"):
        if any(usable and item["state"] == state for item, usable, _, _ in overlapping):
            return state
    if any(not usable for _, usable, _, _ in overlapping):
        return "unknown"
    if any(item["state"] == "fresh" and a <= start and b >= end for item, _, a, b in overlapping):
        return "fresh"
    return "unknown"


def f3_judgment_admissible(snapshot: dict[str, Any]) -> bool:
    return (
        snapshot.get("f3_firewall") == "F-C"
        and snapshot.get("f3_calendar_overlap") is False
        and isinstance(snapshot.get("methodology"), dict)
        and snapshot["methodology"].get("f3_clean") is True
    )


def build(
    plan: dict[str, Any],
    evidence: dict[str, Any],
    rule: dict[str, Any],
    evidence_sha: str,
    tool_sha: str,
) -> dict[str, Any]:
    cutoff = instant(plan["as_of_utc"])
    verified = None
    mock = isinstance(evidence, dict) and evidence.get("source") == "mock"
    if mock:
        verified = verify_derived(evidence)
        binding = evidence["binding"]
        policy = verified["policy"]
        if plan["as_of_utc"] != binding["cutoff_utc"]:
            raise Refusal("evidence cutoff not bound")
        d7 = policy["parameters"]["D7_completeness"]["value"]
        if d7["shape"] != "ONE":
            raise Refusal("policy detail unruled: per-window completeness")
        if Decimal(str(plan["completeness"]["threshold"])) != Decimal(str(d7["values"]["all"])):
            raise Refusal("completeness threshold not bound")
        policy_op = policy["parameters"]["operating_period_start"]
        if (
            plan["operating_period_start"]["utc"] != policy_op["utc"]["value"]
            or plan["operating_period_start"]["provenance"]
            != policy_op["provenance"]["value"]
        ):
            raise Refusal("operating period not bound")
        proxy = policy["parameters"]["D6_proxy"]["value"]
        if proxy == "PX-1":
            raise Refusal("policy detail unruled: proxy names")
        # PX-2 support is intentionally deferred to change 4b-2.
        if proxy == "PX-2":
            raise Refusal("policy option not built: PX-2")
    allowed_source = "mock" if mock else "synthetic"
    expected_policy_sha256 = evidence["binding"]["policy_sha256"] if mock else None
    threshold = plan["completeness"]["threshold"]
    operating_raw = plan["operating_period_start"]["utc"]
    operating = None if operating_raw is None else instant(operating_raw)
    candidates = _candidate_rows(evidence, rule, cutoff, verified=verified)
    for item in evidence["freshness"]:
        if not isinstance(item, dict) or set(item) != {
            "symbol",
            "timeframe",
            "span_start_utc",
            "span_end_utc",
            "state",
            "provenance",
        }:
            raise Refusal("malformed freshness entry")
        span_start = instant(item["span_start_utc"])
        span_end = instant(item["span_end_utc"])
        _prov(item["provenance"], cutoff, expected_policy_sha256, allowed_source)
        if (
            not _canonical_symbol(item["symbol"], rule["quote"])
            or item["timeframe"] not in rule["history_window_bars"]
            or item["state"] not in {"fresh", "spent", "unspent_unproven"}
            or span_end <= span_start
        ):
            raise Refusal("malformed freshness entry")
        # Evidence may restate a known cell's state, but never contradict it: a known cell marked
        # with any other state is refused, not only one marked fresh.
        if any(
            item["symbol"] in known["symbols"]
            and item["timeframe"] in known["timeframes"]
            and item["state"] != known["state"]
            for known in rule["freshness"]["known_not_fresh"]
        ):
            raise Refusal("freshness contradicts known_not_fresh")
    inputs: dict[str, dict[str, str]] = {}
    new_listings, excluded, not_admitted = [], [], []
    records = []
    for index, item in enumerate(evidence["exclusion_verification"]):
        _, metadata = _prov(item.get("provenance"), cutoff, expected_policy_sha256, allowed_source)
        if metadata:
            inputs[f"exclusion:{index}"] = metadata
    for index, item in enumerate(evidence["not_leveraged_verification"]):
        _, metadata = _prov(item.get("provenance"), cutoff, expected_policy_sha256, allowed_source)
        if metadata:
            inputs[f"not_leveraged:{index}"] = metadata
    for index, item in enumerate(evidence["freshness"]):
        _, metadata = _prov(item.get("provenance"), cutoff, expected_policy_sha256, allowed_source)
        if metadata:
            inputs[f"freshness:{index}"] = metadata
    for row in candidates:
        symbol, base = row["symbol"], row["base"]
        for name in ("listing_input", "volume_input"):
            if row[name]:
                inputs[f"{symbol}:{name}"] = row[name]
        for tf, cell in row["coverage"].items():
            if cell["input"]:
                inputs[f"{symbol}:coverage:{tf}"] = cell["input"]
        labels = rule["exclusions"]
        class_found = next(
            (cl for cl in ("pegged", "asset_backed", "wrapped") if base in labels[cl]), None
        )
        covering = [(e, ok) for e, ok in row["exclusions"] if e["base"] == base and ok]
        lev_cover = any(
            e["base"] == base and e["class"] == "leveraged" and ok for e, ok in row["exclusions"]
        )
        nl_cover = any(e["base"] == base and ok for e, ok in row["not_lev"])
        terminal_reason = None
        if class_found:
            if any(e["class"] == class_found for e, _ in covering):
                excluded.append({"symbol": symbol, "class": class_found})
                terminal_reason = f"excluded:{class_found}"
                excluded_state = None
            else:
                excluded_state = "exclusion_unverified"
        elif lev_cover:
            excluded.append({"symbol": symbol, "class": "leveraged"})
            terminal_reason = "excluded:leveraged"
            excluded_state = None
        elif (
            any(base.endswith(suffix) for suffix in labels["leveraged"]["verification_triggers"])
            and not nl_cover
        ):
            excluded_state = "exclusion_unverified"
        else:
            excluded_state = None
        age_days = (cutoff - row["first"]).days
        if (
            terminal_reason is None
            and row["listing_usable"]
            and age_days < rule["new_listing_min_age_days"]
        ):
            new_listings.append({"symbol": symbol, "age_days": age_days})
            terminal_reason = "new_listing"
        bars = [
            v
            for dt, v in row["bars"]
            if cutoff - timedelta(days=rule["ranking"]["window_days"]) <= dt < cutoff
        ]
        trading_at_t = any(
            dt == cutoff - timedelta(days=1) and quote_volume > Decimal(0)
            for dt, quote_volume in row["bars"]
        )
        completeness_1d = Decimal(len(bars))
        window_days = Decimal(rule["ranking"]["window_days"])
        threshold_decimal = Decimal(str(threshold))
        median = _median(bars) if row["volume_usable"] else None
        statuses = {}
        for tf, cell in row["coverage"].items():
            reason = None
            if terminal_reason:
                reason = terminal_reason
            elif row["volume_usable"] and not trading_at_t:
                reason = "not_trading_at_t"
            elif row["volume_usable"] and completeness_1d < _exact_product(
                threshold_decimal, window_days
            ):
                reason = "incomplete_1d"
            elif cell["usable"] and Decimal(cell["count"]) < _exact_product(
                threshold_decimal, Decimal(rule["history_window_bars"][tf])
            ):
                reason = f"incomplete_{tf}"
            elif not row["listing_usable"] or not row["volume_usable"] or not cell["usable"]:
                reason = "provenance_unknown"
            elif excluded_state:
                reason = excluded_state
            statuses[tf] = {
                "status": "member" if reason is None else f"not_admitted: {reason}",
                "reason": reason,
            }
            if reason:
                not_admitted.append({"symbol": symbol, "reason": reason, "timeframe": tf})
        records.append(
            {
                "symbol": symbol,
                "listing": {
                    "first_daily_bar_open_utc": row["first"].strftime("%Y-%m-%dT%H:%M:%SZ")
                },
                "median_daily_quote_volume": _decimal_string(median),
                "rank_15m": None,
                "lineage": row["lineage"],
                "timeframes": statuses,
                "freshness": {},
            }
        )
    by_symbol = {r["symbol"]: r for r in records}
    cap = rule["caps"]["15m"]
    eligible = [r for r in records if r["timeframes"]["15m"]["reason"] is None]
    eligible.sort(key=_volume_key)
    for rank, rec in enumerate(eligible, 1):
        rec["rank_15m"] = rank
    unknown = [
        r
        for r in records
        if r["timeframes"]["15m"]["reason"] in {"provenance_unknown", "exclusion_unverified"}
    ]
    cutoff_key = (
        _volume_key(eligible[cap - 1])
        if len(eligible) >= cap
        else None
    )
    undecidable = any(
        r["median_daily_quote_volume"] is None
        or cutoff_key is None
        or _volume_key(r) < cutoff_key
        for r in unknown
    )
    blocking = [
        r["symbol"]
        for r in unknown
        if r["median_daily_quote_volume"] is None
        or cutoff_key is None
        or _volume_key(r) < cutoff_key
    ]
    m15 = [] if undecidable else [r["symbol"] for r in eligible[:cap]]
    if not undecidable:
        for rec in eligible[cap:]:
            rec["timeframes"]["15m"] = {"status": "not_admitted: cap", "reason": "cap"}
            not_admitted.append({"symbol": rec["symbol"], "reason": "cap", "timeframe": "15m"})
    else:
        for rec in eligible:
            rec["rank_15m"] = None
            rec["timeframes"]["15m"] = {"status": "undecidable", "reason": "top_n_undecidable"}
    members = {
        "15m": {
            "status": "UNDECIDABLE" if undecidable else "DECIDED",
            "symbols": sorted(m15),
            **({"blocking": sorted(blocking)} if undecidable else {}),
        },
        "1H": {
            "status": "DECIDED",
            "symbols": sorted(
                r["symbol"] for r in records if r["timeframes"]["1H"]["reason"] is None
            ),
        },
        "4H": {
            "status": "DECIDED",
            "symbols": sorted(
                r["symbol"] for r in records if r["timeframes"]["4H"]["reason"] is None
            ),
        },
    }
    span_end = cutoff + timedelta(days=rule["governed_span_days"])
    for tf, group in members.items():
        if tf == "15m" and group["status"] == "UNDECIDABLE":
            continue
        for sym in group["symbols"]:
            rec = by_symbol[sym]
            rec["freshness"][tf] = _freshness(
                evidence,
                next(c for c in candidates if c["symbol"] == sym),
                tf,
                cutoff,
                span_end,
                operating,
                rule,
                cutoff,
                allowed_source,
                expected_policy_sha256,
            )
    f3 = instant(rule["f3"]["calendar_start_utc"])

    overlap = (
        span_end > f3
        or any(
            dt >= f3 and cutoff - timedelta(days=rule["ranking"]["window_days"]) <= dt < cutoff
            for row in candidates
            for dt, _ in row["bars"]
        )
        or any(row["first"] >= f3 for row in candidates)
    )
    methodology = {
        "rule_sha256": UNIVERSE_RULE_V1_SHA256,
        "tool_sha256": tool_sha,
        "f3_clean": not mock,
        "basis": (
            "Source is MOCK evidence under a bound MOCK policy."
            if mock
            else "ruled 2026-10-25 by the owner from documents only; "
                 "this tool reads synthetic evidence only"
        ),
    }
    if mock:
        methodology["f3_clean_basis"] = "MOCK"
        methodology["policy_sha256"] = expected_policy_sha256
    return {
        "snapshot_id": "ucpe.universe.asof.v2",
        "status": "MOCK" if mock else "SYNTHETIC",
        "as_of_utc": plan["as_of_utc"],
        "rule_sha256": UNIVERSE_RULE_V1_SHA256,
        "evidence_sha256": evidence_sha,
        "tool_sha256": tool_sha,
        "ruling": {
            "R1": rule["ranking"]["window_days"],
            "R2": rule["caps"]["15m"],
            "R3": {tf: rule["caps"][tf] for tf in ("1H", "4H")},
            "R4": rule["exclusions"],
            "R5": rule["freshness"]["known_not_fresh"],
            "R6": rule["freshness"]["operating_period"],
            "R7": rule["f3"]["firewall"],
            "G1": (
                "a_prime: daily bar [T-1d, T) present with quote volume > 0; "
                "owner-ruled 2026-10-29; SYNTHETIC_ONLY"
            ),
        },
        "completeness": plan["completeness"],
        "operating_period_start": plan["operating_period_start"],
        "f3_firewall": rule["f3"]["firewall"],
        "f3_calendar_overlap": overlap,
        "methodology": methodology,
        "members": members,
        "symbols": records,
        "new_listings": new_listings,
        "excluded": excluded,
        "not_admitted": not_admitted,
        "inputs": inputs,
    }


def run(plan_arg: str) -> dict[str, Any]:
    plan_path = _path(plan_arg)
    raw, plan = _json_bytes(plan_path, "plan unreadable")
    if (
        not isinstance(plan, dict)
        or set(plan) != PLAN_KEYS
        or plan.get("plan_id") != "ucpe.quant_ng.universe.v1"
    ):
        raise Refusal("invalid plan")
    cutoff = instant(plan["as_of_utc"])
    if any((cutoff.hour, cutoff.minute, cutoff.second, cutoff.microsecond)):
        raise Refusal("as_of_utc must be UTC midnight")
    ev = plan["evidence"]
    if (
        not isinstance(ev, dict)
        or set(ev) != {"path", "sha256"}
        or not isinstance(ev["sha256"], str)
        or not HEX_RE.fullmatch(ev["sha256"])
    ):
        raise Refusal("malformed evidence pin")
    evidence_path = _path(ev["path"])
    evidence_bytes, evidence = _json_bytes(evidence_path, "evidence unreadable")
    evidence_sha = hashlib.sha256(evidence_bytes).hexdigest()
    if evidence_sha != ev["sha256"]:
        raise Refusal("evidence digest mismatch")
    op = plan["operating_period_start"]
    if not isinstance(op, dict) or set(op) != {"utc", "provenance"}:
        raise Refusal("malformed operating period")
    if op["utc"] is None:
        if op["provenance"] is not None:
            raise Refusal("malformed operating period")
    else:
        instant(op["utc"])
        if not isinstance(op["provenance"], str) or not op["provenance"].strip():
            raise Refusal("operating period provenance required")
    comp = plan["completeness"]
    if not isinstance(comp, dict) or set(comp) != {"threshold", "ruling"}:
        raise Refusal("malformed completeness")
    if comp["threshold"] is None:
        raise Refusal("completeness threshold unruled: OD-NG-7 item 7.1")
    if (
        isinstance(comp["threshold"], bool)
        or not isinstance(comp["threshold"], (int, float))
        or not math.isfinite(comp["threshold"])
        or not 0 < comp["threshold"] <= 1
    ):
        raise Refusal("invalid completeness threshold")
    if comp["ruling"] != "SYNTHETIC_TEST_ONLY":
        raise Refusal("completeness threshold requires SYNTHETIC_TEST_ONLY")
    output = _path(plan["output_dir"])
    _OUTPUT_HOLDER[0] = output
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise Refusal("output folder is not empty")
    root = Path(__file__).resolve().parents[1]
    rule = load_rule(root / "ops/quant_ng/UNIVERSE_RULE_v1.json")
    tool_sha = hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()
    snapshot = build(plan, evidence, rule, evidence_sha, tool_sha)
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    created = _make_output(output)
    try:
        create_readonly(output / "UNIVERSE_SNAPSHOT.json", payload.encode())
    except BaseException:
        _unwind(created)
        raise
    return {
        "status": "PASS",
        "artifact": str(output / "UNIVERSE_SNAPSHOT.json"),
        "artifact_sha256": hashlib.sha256(payload.encode()).hexdigest(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan")
    install_guard(_OUTPUT_HOLDER)
    try:
        result = run(parser.parse_args(argv).plan)
    except BaseException as exc:
        reason = str(exc) if isinstance(exc, Refusal) else f"run failed: {type(exc).__name__}"
        print(json.dumps({"status": "REFUSAL", "reason": reason}, separators=(",", ":")))
        return 2
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
