"""Dormant MOCK-only validator for the PROPOSED capture-time contract d2.

It validates a capture log as a Python mapping. It does no I/O and no network, is wired into
nothing, and refuses every ARCHIVE log.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

_FETCH_SPEC = importlib.util.spec_from_file_location(
    "quant_ng_fetch", Path(__file__).with_name("quant_ng_fetch.py")
)
if _FETCH_SPEC is None or _FETCH_SPEC.loader is None:
    raise RuntimeError("cannot load fetch helper")
_FETCH = importlib.util.module_from_spec(_FETCH_SPEC)
sys.modules["quant_ng_fetch"] = _FETCH
_PREVIOUS_BYTECODE = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    _FETCH_SPEC.loader.exec_module(_FETCH)
finally:
    sys.dont_write_bytecode = _PREVIOUS_BYTECODE

Refusal = _FETCH.Refusal
LAYOUT = _FETCH.LAYOUT

CAPTURE_LOG_ID = "ucpe.quant_ng.capture_log.v1"
RUN_KEYS = frozenset(
    {
        "capture_log_id",
        "status",
        "step",
        "plan_sha256",
        "tool_sha256",
        "transport",
        "host_allowlist",
        "authorization",
        "clock",
        "date_tolerance_seconds",
        "previous_capture_log_sha256",
        "run_start_utc",
        "run_end_utc",
        "run_status",
        "refusal",
        "records",
        "records_sha256",
        "licence_notice",
    }
)
RECORD_KEYS = frozenset(
    {
        "seq",
        "role",
        "path",
        "host",
        "requested_at_utc",
        "last_byte_at_utc",
        "http_status",
        "outcome",
        "body_sha256",
        "body_size",
        "headers_sha256",
        "date_header",
        "date_check",
        "last_modified_header",
    }
)
REFUSAL_REASONS = frozenset(
    {
        "capture not authorized",
        "capture log malformed",
        "capture instant decreased",
        "host not allowlisted",
        "redirect refused",
        "not https",
        "capture run not complete",
        "capture log missing",
        "capture log not bound",
        "recapture not linked",
        "recapture interval too short",
        "changelog read does not bracket the file reads",
        "changelog contradicts capture time",
        "as-of not before capture",
        "scope sentence incomplete",
        "only the mock transport exists",
        "object is not a mock object",
        "output folder is not empty",
        "request cap exceeded",
        "unverified share above the cap",
    }
)
_INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$")
_HEX = re.compile(r"^[0-9a-f]{64}$")
_IMF = re.compile(
    r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
    r"\d{4} \d{2}:\d{2}:\d{2} GMT$"
)


def _refuse(reason: str = "capture log malformed") -> None:
    raise Refusal(reason)


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _instant(value: Any) -> datetime | None:
    if not isinstance(value, str) or not _INSTANT.fullmatch(value):
        return None
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None


def _hex(value: Any) -> bool:
    return isinstance(value, str) and _HEX.fullmatch(value) is not None


def date_check(
    date_header: str | None,
    requested_at_utc: str,
    last_byte_at_utc: str,
    *,
    tolerance_seconds: int,
) -> str:
    if not _integer(tolerance_seconds) or tolerance_seconds < 0:
        _refuse()
    if date_header is None:
        return "ABSENT"
    if not isinstance(date_header, str) or not _IMF.fullmatch(date_header):
        return "UNPARSEABLE"
    try:
        parsed = parsedate_to_datetime(date_header)
    except (TypeError, ValueError, OverflowError):
        return "UNPARSEABLE"
    if parsed.strftime("%a") != date_header[:3]:
        return "UNPARSEABLE"
    requested, last_byte = _instant(requested_at_utc), _instant(last_byte_at_utc)
    if requested is None or last_byte is None:
        _refuse()
    date_value = parsed.replace(tzinfo=UTC)
    lower = requested.replace(microsecond=0) - timedelta(seconds=tolerance_seconds)
    upper = last_byte.replace(microsecond=0) + timedelta(seconds=tolerance_seconds)
    return "WITHIN_TOLERANCE" if lower <= date_value <= upper else "BEYOND_TOLERANCE"


def _allowed_role(step: str, role: str) -> bool:
    return (
        role
        in {
            "listing": {"listing_page"},
            "acquisition": {"zip", "checksum"},
            "recapture": {"zip", "checksum"},
            "changelog": {"changelog"},
        }[step]
    )


def validate_capture_log(log: Any, *, date_tolerance_seconds: int | None = None) -> None:
    def malformed() -> None:
        _refuse("capture log malformed")

    if not isinstance(log, Mapping) or set(log) != RUN_KEYS:
        malformed()
    if log["status"] == "ARCHIVE":
        _refuse("capture not authorized")
    if log["status"] != "MOCK":
        malformed()
    if date_tolerance_seconds is not None and (
        not _integer(date_tolerance_seconds) or date_tolerance_seconds < 0
    ):
        malformed()
    if (
        log["capture_log_id"] != CAPTURE_LOG_ID
        or log["transport"] != "mock"
        or log["step"] not in {"listing", "acquisition", "recapture", "changelog"}
        or not _hex(log["plan_sha256"])
        or not _hex(log["tool_sha256"])
        or log["host_allowlist"] != []
        or not isinstance(log["authorization"], Mapping)
        or set(log["authorization"])
        != {"run_authorization_sha256", "licence_ruling_sha256", "terms_version"}
        or any(value is not None for value in log["authorization"].values())
        or log["clock"] != {"source": "local_system_clock", "zone": "UTC", "verified": False}
        or type(log["clock"].get("verified")) is not bool
        or log["date_tolerance_seconds"] is not None
        and (not _integer(log["date_tolerance_seconds"]) or log["date_tolerance_seconds"] < 0)
    ):
        malformed()
    previous = log["previous_capture_log_sha256"]
    if log["step"] in {"listing", "acquisition"} and previous is not None:
        malformed()
    if log["step"] == "recapture" and not _hex(previous):
        malformed()
    if log["step"] == "changelog" and previous is not None and not _hex(previous):
        malformed()
    if _instant(log["run_start_utc"]) is None:
        malformed()
    if log["run_status"] == "COMPLETE":
        if _instant(log["run_end_utc"]) is None or log["refusal"] is not None:
            malformed()
    elif log["run_status"] == "REFUSED":
        if log["run_end_utc"] is not None or log["refusal"] not in REFUSAL_REASONS:
            malformed()
    else:
        malformed()
    records, digests = log["records"], log["records_sha256"]
    if (
        not isinstance(records, list)
        or not isinstance(digests, list)
        or len(records) != len(digests)
    ):
        malformed()
    if any(not _hex(digest) for digest in digests) or log["licence_notice"] is not None:
        malformed()
    paths: dict[str, list[Mapping[str, Any]]] = {"zip": [], "checksum": []}
    for index, record in enumerate(records, 1):
        if not isinstance(record, Mapping) or set(record) != RECORD_KEYS:
            malformed()
        role, path = record["role"], record["path"]
        if (
            not _integer(record["seq"])
            or record["seq"] != index
            or role not in {"listing_page", "zip", "checksum", "changelog"}
            or not _allowed_role(log["step"], role)
            or record["host"] != "mock"
            or _instant(record["requested_at_utc"]) is None
            or _instant(record["last_byte_at_utc"]) is None
            or not _integer(record["http_status"])
            or (record["http_status"], record["outcome"])
            not in {(200, "BODY_2XX"), (404, "FINAL_NON_2XX")}
            or not _hex(record["body_sha256"])
            or not _integer(record["body_size"])
            or record["body_size"] < 0
            or not _hex(record["headers_sha256"])
            or (record["date_header"] is not None and not isinstance(record["date_header"], str))
            or record["date_check"] != "NOT_APPLICABLE"
            or (
                record["last_modified_header"] is not None
                and not isinstance(record["last_modified_header"], str)
            )
        ):
            malformed()
        if role == "zip":
            if not isinstance(path, str) or LAYOUT.fullmatch(path) is None:
                malformed()
            paths["zip"].append(record)
        elif role == "checksum":
            if (
                not isinstance(path, str)
                or not path.endswith(".CHECKSUM")
                or LAYOUT.fullmatch(path[:-9]) is None
            ):
                malformed()
            paths["checksum"].append(record)
        elif role in {"listing_page", "changelog"} and (not isinstance(path, str) or not path):
            malformed()
    if log["step"] in {"acquisition", "recapture"}:
        zips = [r["path"] for r in paths["zip"]]
        checksums = [r["path"] for r in paths["checksum"]]
        if (
            len(zips) != len(set(zips))
            or len(checksums) != len(set(checksums))
            or set(p + ".CHECKSUM" for p in zips) != set(checksums)
        ):
            malformed()
    previous_time = _instant(log["run_start_utc"])
    for record in records:
        requested = _instant(record["requested_at_utc"])
        last_byte = _instant(record["last_byte_at_utc"])
        if requested < previous_time or last_byte < requested:
            _refuse("capture instant decreased")
        previous_time = last_byte
    if log["run_status"] == "COMPLETE" and previous_time > _instant(log["run_end_utc"]):
        _refuse("capture instant decreased")


def check_manifest_binding(log: Any, manifest: Any) -> None:
    validate_capture_log(log)
    if log["step"] not in {"acquisition", "recapture"}:
        _refuse("capture log not bound")
    if not isinstance(manifest, Mapping) or not isinstance(manifest.get("files"), list):
        _refuse("capture log not bound")
    zips = {r["path"]: r for r in log["records"] if r["role"] == "zip"}
    checksums = {r["path"]: r for r in log["records"] if r["role"] == "checksum"}
    rows: dict[str, Mapping[str, Any]] = {}
    for row in manifest["files"]:
        if (
            not isinstance(row, Mapping)
            or not isinstance(row.get("path"), str)
            or row["path"] in rows
        ):
            _refuse("capture log not bound")
        rows[row["path"]] = row
        path = row["path"]
        zip_record, checksum_record = zips.get(path), checksums.get(path + ".CHECKSUM")
        if zip_record is None or checksum_record is None:
            _refuse("capture log not bound")
        for record, digest_key in (
            (zip_record, "sha256"),
            (checksum_record, "checksum_file_sha256"),
        ):
            digest = row.get(digest_key)
            missing = record["outcome"] == "FINAL_NON_2XX"
            if (digest is None) != missing or (digest is None and row.get("class") != "missing"):
                _refuse("capture log not bound")
            if digest is not None and digest != record["body_sha256"]:
                _refuse("capture log not bound")
    if set(zips) != set(rows) or set(checksums) != {path + ".CHECKSUM" for path in rows}:
        _refuse("capture log not bound")
