import ast
import copy
from pathlib import Path

import pytest

from scripts import quant_ng_capture_log as capture

H = "a" * 64
ZIP_OK = "data/spot/daily/klines/BTCUSDT/1h/BTCUSDT-1h-2024-01-01.zip"
ZIP_MISSING = "data/spot/daily/klines/ETHUSDT/1h/ETHUSDT-1h-2024-01-01.zip"


def fixture():
    rows = [
        {"path": ZIP_OK, "class": "ok", "sha256": "b" * 64, "checksum_file_sha256": "c" * 64},
        {"path": ZIP_MISSING, "class": "missing", "sha256": None, "checksum_file_sha256": None},
    ]
    records = []
    for index, (path, role, status, outcome, digest) in enumerate(
        [
            (ZIP_OK, "zip", 200, "BODY_2XX", "b" * 64),
            (ZIP_OK + ".CHECKSUM", "checksum", 200, "BODY_2XX", "c" * 64),
            (ZIP_MISSING, "zip", 404, "FINAL_NON_2XX", H),
            (ZIP_MISSING + ".CHECKSUM", "checksum", 404, "FINAL_NON_2XX", H),
        ],
        1,
    ):
        records.append(
            {
                "seq": index,
                "role": role,
                "path": path,
                "host": "mock",
                "requested_at_utc": f"2024-01-01T00:00:0{index}Z",
                "last_byte_at_utc": f"2024-01-01T00:00:0{index}Z",
                "http_status": status,
                "outcome": outcome,
                "body_sha256": digest,
                "body_size": 0,
                "headers_sha256": H,
                "date_header": None,
                "date_check": "NOT_APPLICABLE",
                "last_modified_header": None,
            }
        )
    log = {
        "capture_log_id": capture.CAPTURE_LOG_ID,
        "status": "MOCK",
        "step": "acquisition",
        "plan_sha256": H,
        "tool_sha256": H,
        "transport": "mock",
        "host_allowlist": [],
        "authorization": {
            "run_authorization_sha256": None,
            "licence_ruling_sha256": None,
            "terms_version": None,
        },
        "clock": {"source": "local_system_clock", "zone": "UTC", "verified": False},
        "date_tolerance_seconds": None,
        "previous_capture_log_sha256": None,
        "run_start_utc": "2024-01-01T00:00:00Z",
        "run_end_utc": "2024-01-01T00:00:05Z",
        "run_status": "COMPLETE",
        "refusal": None,
        "records": records,
        "records_sha256": [H] * len(records),
        "licence_notice": None,
    }
    return log, {"manifest_id": "ucpe.quant_ng.fetch_manifest.v1", "status": "MOCK", "files": rows}


def raises(log, reason="capture log malformed", **kwargs):
    with pytest.raises(capture.Refusal, match="^" + reason.replace(".", r"\.") + "$"):
        capture.validate_capture_log(log, **kwargs)


def test_kat_base_log_passes():
    log, manifest = fixture()
    capture.validate_capture_log(log)
    capture.check_manifest_binding(log, manifest)


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_field",
        "wrong_id",
        "bad_step",
        "bad_digest",
        "host",
        "authorization",
        "clock",
        "log_tol",
        "previous",
        "bad_instant",
        "run_pair",
        "record_key",
        "record_role",
        "record_path",
        "bad_outcome",
        "body_hash",
        "negative_size",
        "date_check",
        "pairing",
        "bad_date_tolerance",
    ],
    ids=[
        "unknown-field",
        "wrong-id",
        "bad-step",
        "bad-digest",
        "host",
        "authorization",
        "clock",
        "log-tolerance",
        "previous",
        "bad-instant",
        "run-pair",
        "record-key",
        "record-role",
        "record-path",
        "bad-outcome",
        "body-hash",
        "negative-size",
        "date-check",
        "pairing",
        "bad-date-tolerance",
    ],
)
def test_kat_malformed(mutation):
    log, _ = fixture()
    if mutation == "unknown_field":
        log["extra"] = 1
    elif mutation == "wrong_id":
        log["capture_log_id"] = "x"
    elif mutation == "bad_step":
        log["step"] = "nope"
    elif mutation == "bad_digest":
        log["plan_sha256"] = "A" * 64
    elif mutation == "host":
        log["host_allowlist"] = ["mock"]
    elif mutation == "authorization":
        log["authorization"]["terms_version"] = "x"
    elif mutation == "clock":
        log["clock"]["verified"] = 0
    elif mutation == "log_tol":
        log["date_tolerance_seconds"] = -1
    elif mutation == "previous":
        log["previous_capture_log_sha256"] = H
    elif mutation == "bad_instant":
        log["run_start_utc"] = "2024-02-30T00:00:00Z"
    elif mutation == "run_pair":
        log["refusal"] = "capture log malformed"
    elif mutation == "record_key":
        log["records"][0]["extra"] = 1
    elif mutation == "record_role":
        log["records"][0]["role"] = "changelog"
    elif mutation == "record_path":
        log["records"][0]["path"] = "x"
    elif mutation == "bad_outcome":
        log["records"][0]["outcome"] = "FINAL_NON_2XX"
    elif mutation == "body_hash":
        log["records"][0]["body_sha256"] = "A" * 64
    elif mutation == "negative_size":
        log["records"][0]["body_size"] = -1
    elif mutation == "date_check":
        log["records"][0]["date_check"] = "ABSENT"
    elif mutation == "pairing":
        log["records"].pop()
    elif mutation == "bad_date_tolerance":
        raises(log, date_tolerance_seconds=True)
        return
    raises(log)


def test_kat_archive_always_refused():
    log, _ = fixture()
    log["status"] = "ARCHIVE"
    log["transport"] = "https"
    log["host_allowlist"] = ["data.binance.vision"]
    log["authorization"] = {
        "run_authorization_sha256": H,
        "licence_ruling_sha256": H,
        "terms_version": "terms",
    }
    raises(log, "capture not authorized")


@pytest.mark.parametrize(
    "field", ["seq", "http_status", "body_size"], ids=["seq", "http-status", "body-size"]
)
def test_kat_bool_not_integer(field):
    log, _ = fixture()
    log["records"][0][field] = True
    raises(log)


@pytest.mark.parametrize(
    "header,expected,label",
    [
        ("Mon, 01 Jan 2024 00:00:08 GMT", "WITHIN_TOLERANCE", "minus-bound"),
        ("Mon, 01 Jan 2024 00:00:12 GMT", "WITHIN_TOLERANCE", "plus-bound"),
        ("Mon, 01 Jan 2024 00:00:07 GMT", "BEYOND_TOLERANCE", "minus-over"),
        ("Mon, 01 Jan 2024 00:00:13 GMT", "BEYOND_TOLERANCE", "plus-over"),
        ("Tue, 01 Jan 2024 00:00:00 GMT", "UNPARSEABLE", "wrong-weekday"),
        (None, "ABSENT", "absent"),
    ],
    ids=lambda value: value if isinstance(value, str) and len(value) < 24 else None,
)
def test_kat_date_check(header, expected, label):
    assert (
        capture.date_check(
            header, "2024-01-01T00:00:10.9Z", "2024-01-01T00:00:10Z", tolerance_seconds=2
        )
        == expected
    )


def test_kat_date_check_truncates_fraction():
    assert (
        capture.date_check(
            "Mon, 01 Jan 2024 00:00:08 GMT",
            "2024-01-01T00:00:10.9Z",
            "2024-01-01T00:00:10Z",
            tolerance_seconds=2,
        )
        == "WITHIN_TOLERANCE"
    )


def test_kat_date_tolerance_bool_refused():
    with pytest.raises(capture.Refusal, match="capture log malformed"):
        capture.date_check(
            None, "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z", tolerance_seconds=True
        )


def test_kat_equal_instants_pass():
    log, _ = fixture()
    for record in log["records"]:
        record["requested_at_utc"] = record["last_byte_at_utc"] = "2024-01-01T00:00:00Z"
    capture.validate_capture_log(log)


@pytest.mark.parametrize("where", ["between", "within"], ids=["between-records", "within-record"])
def test_kat_decreasing_instants(where):
    log, _ = fixture()
    if where == "between":
        log["records"][1]["requested_at_utc"] = "2024-01-01T00:00:00Z"
    else:
        log["records"][0]["last_byte_at_utc"] = "2023-12-31T23:59:59Z"
    raises(log, "capture instant decreased")


@pytest.mark.parametrize(
    "case",
    ["digest", "extra", "missing_checksum", "none_ok"],
    ids=["digest-mismatch", "extra-record", "missing-checksum", "none-with-ok-class"],
)
def test_kat_manifest_binding_refuses(case):
    log, manifest = fixture()
    if case == "digest":
        manifest["files"][0]["sha256"] = "d" * 64
    elif case == "extra":
        extra_zip = "data/spot/daily/klines/ADAUSDT/1h/ADAUSDT-1h-2024-01-01.zip"
        for offset, role in enumerate(("zip", "checksum"), 5):
            log["records"].append(
                copy.deepcopy(log["records"][0])
                | {
                    "seq": offset,
                    "role": role,
                    "path": extra_zip + (".CHECKSUM" if role == "checksum" else ""),
                    "requested_at_utc": f"2024-01-01T00:00:0{offset}Z",
                    "last_byte_at_utc": f"2024-01-01T00:00:0{offset}Z",
                }
            )
            log["records_sha256"].append("a" * 64)
        log["run_end_utc"] = "2024-01-01T00:00:07Z"
    elif case == "missing_checksum":
        log["records"].pop(1)
    else:
        manifest["files"][0]["sha256"] = None
    with pytest.raises(capture.Refusal, match="capture log not bound"):
        capture.check_manifest_binding(log, manifest)


@pytest.mark.parametrize(
    "reason",
    sorted(capture.REFUSAL_REASONS),
    ids=["reason-" + str(i) for i in range(len(capture.REFUSAL_REASONS))],
)
def test_kat_each_refusal_reason_available(reason):
    log, _ = fixture()
    log["run_status"] = "REFUSED"
    log["run_end_utc"] = None
    log["refusal"] = reason
    capture.validate_capture_log(log)


def test_kat_ast_is_pure():
    tree = ast.parse(Path(capture.__file__).read_text())
    forbidden = {"socket", "http", "urllib", "requests", "httpx", "subprocess"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] not in forbidden for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in forbidden
        if isinstance(node, ast.Call):
            assert not (isinstance(node.func, ast.Name) and node.func.id == "open")
