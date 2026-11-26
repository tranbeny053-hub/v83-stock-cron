import ast
import copy
from pathlib import Path

import pytest

from scripts import quant_ng_capture_log as capture

H = "a" * 64
# Non-F3 bases only: BTCUSDT and ETHUSDT are never requested (OP-2, ruled).
ZIP_OK = "data/spot/daily/klines/SOLUSDT/1h/SOLUSDT-1h-2024-01-01.zip"
ZIP_MISSING = "data/spot/daily/klines/ADAUSDT/1h/ADAUSDT-1h-2024-01-01.zip"


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
        "unhashable_step",
        "unhashable_role",
        "unhashable_outcome",
        "unhashable_refusal",
        "records_length",
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
        "unhashable-step",
        "unhashable-role",
        "unhashable-outcome",
        "unhashable-refusal",
        "records-length",
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
    elif mutation == "unhashable_step":
        log["step"] = ["acquisition"]
    elif mutation == "unhashable_role":
        log["records"][0]["role"] = ["zip"]
    elif mutation == "unhashable_outcome":
        log["records"][0]["outcome"] = ["BODY_2XX"]
    elif mutation == "unhashable_refusal":
        log["run_status"], log["run_end_utc"] = "REFUSED", None
        log["refusal"] = ["capture log malformed"]
    elif mutation == "records_length":
        log["records_sha256"].pop()
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
    ids=["minus-bound", "plus-bound", "minus-over", "plus-over", "wrong-weekday", "absent"],
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


@pytest.mark.parametrize(
    "where",
    ["between", "within", "run_end"],
    ids=["between-records", "within-record", "run-end-before-last-byte"],
)
def test_kat_decreasing_instants(where):
    log, _ = fixture()
    if where == "between":
        log["records"][1]["requested_at_utc"] = "2024-01-01T00:00:00Z"
    elif where == "within":
        log["records"][0]["last_byte_at_utc"] = "2023-12-31T23:59:59Z"
    else:
        log["run_end_utc"] = "2024-01-01T00:00:03Z"
    raises(log, "capture instant decreased")


@pytest.mark.parametrize(
    "case",
    ["digest", "extra", "row_without_records", "none_ok"],
    ids=["digest-mismatch", "extra-record", "row-without-records", "none-with-ok-class"],
)
def test_kat_manifest_binding_refuses(case):
    log, manifest = fixture()
    if case == "digest":
        manifest["files"][0]["sha256"] = "d" * 64
    elif case == "extra":
        extra_zip = "data/spot/daily/klines/XRPUSDT/1h/XRPUSDT-1h-2024-01-01.zip"
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
    elif case == "row_without_records":
        # A missing checksum RECORD is a pairing failure, refused by validation first (malformed);
        # binding's own failure is a MANIFEST row the log has no records for.
        manifest["files"].append(
            {
                "path": "data/spot/daily/klines/XRPUSDT/1h/XRPUSDT-1h-2024-01-01.zip",
                "class": "missing",
                "sha256": None,
                "checksum_file_sha256": None,
            }
        )
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


@pytest.mark.parametrize(
    "base,role",
    [("BTCUSDT", "zip"), ("ETHUSDT", "zip"), ("BTCUSDT", "checksum")],
    ids=["btc-zip", "eth-zip", "btc-checksum"],
)
def test_kat_btc_eth_never_requested(base, role):
    log, _ = fixture()
    path = f"data/spot/daily/klines/{base}/1h/{base}-1h-2024-01-01.zip"
    index = 0 if role == "zip" else 1
    log["records"][index]["path"] = path + (".CHECKSUM" if role == "checksum" else "")
    raises(log, "BTCUSDT and ETHUSDT are never requested")


def test_kat_missing_checksum_record_is_a_pairing_failure():
    log, manifest = fixture()
    log["records"].pop(1)
    log["records_sha256"].pop(1)
    for seq, record in enumerate(log["records"], 1):
        record["seq"] = seq
    raises(log)
    with pytest.raises(capture.Refusal, match="^capture log malformed$"):
        capture.check_manifest_binding(log, manifest)


def test_kat_weekday_check_needs_no_locale():
    source = Path(capture.__file__).read_text()
    assert "strftime" not in source and "locale" not in source


@pytest.mark.parametrize(
    "mutation",
    ["seq_gap", "unknown_refusal", "recapture_without_previous", "licence_notice"],
    ids=["seq-gap", "unknown-refusal", "recapture-without-previous", "licence-notice"],
)
def test_kat_malformed_probe_gaps(mutation):
    log, _ = fixture()
    if mutation == "seq_gap":
        log["records"][1]["seq"] = 3
    elif mutation == "unknown_refusal":
        log["run_status"], log["run_end_utc"] = "REFUSED", None
        log["refusal"] = "not a reason of the contract"
    elif mutation == "recapture_without_previous":
        log["step"] = "recapture"
    else:
        log["licence_notice"] = {"credit": "x"}
    raises(log)


def test_kat_recapture_with_previous_digest_passes():
    log, manifest = fixture()
    log["step"], log["previous_capture_log_sha256"] = "recapture", "e" * 64
    capture.validate_capture_log(log)
    capture.check_manifest_binding(log, manifest)


def test_kat_binding_refuses_a_none_digest_whose_class_is_not_missing():
    log, manifest = fixture()
    manifest["files"][1]["class"] = "ok"
    with pytest.raises(capture.Refusal, match="^capture log not bound$"):
        capture.check_manifest_binding(log, manifest)


def test_kat_date_check_refuses_a_negative_tolerance():
    with pytest.raises(capture.Refusal, match="^capture log malformed$"):
        capture.date_check(
            None, "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z", tolerance_seconds=-1
        )


# ---- LANE2-P1 fold: the contract's literal reasons, the other steps, and date_check's edges ----

CONTRACT_REASONS = {
    # CTC d2 §10.2, one string per name
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
    # CTC d2 §10.1, the five fetch.py refusals
    "only the mock transport exists",
    "object is not a mock object",
    "output folder is not empty",
    "request cap exceeded",
    "unverified share above the cap",
}


def test_kat_refusal_reasons_are_exactly_the_contracts():
    assert len(CONTRACT_REASONS) == 20 and capture.REFUSAL_REASONS == CONTRACT_REASONS


def single_record_log(step, role, path):
    log, _ = fixture()
    record = log["records"][0] | {"role": role, "path": path, "seq": 1}
    log.update(step=step, records=[record], records_sha256=[H])
    return log


LISTING_PATH = "data/spot/daily/klines/SOLUSDT/1h/"
CHANGELOG_PATH = "CHANGELOG.md"


def test_kat_listing_and_changelog_logs_pass():
    capture.validate_capture_log(single_record_log("listing", "listing_page", LISTING_PATH))
    changelog = single_record_log("changelog", "changelog", CHANGELOG_PATH)
    capture.validate_capture_log(changelog)
    changelog["previous_capture_log_sha256"] = "e" * 64
    capture.validate_capture_log(changelog)


@pytest.mark.parametrize(
    "step,role,path,previous",
    [
        ("listing", "zip", ZIP_OK, None),
        ("listing", "listing_page", "", None),
        ("listing", "listing_page", LISTING_PATH, "e" * 64),
        ("changelog", "listing_page", CHANGELOG_PATH, None),
        ("changelog", "changelog", "", None),
        ("changelog", "changelog", CHANGELOG_PATH, "not-hex"),
    ],
    ids=[
        "listing-with-zip-role",
        "listing-empty-path",
        "listing-with-previous",
        "changelog-with-listing-role",
        "changelog-empty-path",
        "changelog-bad-previous",
    ],
)
def test_kat_listing_and_changelog_mutations(step, role, path, previous):
    log = single_record_log(step, role, path)
    log["previous_capture_log_sha256"] = previous
    raises(log)


@pytest.mark.parametrize("step", ["listing", "changelog"], ids=["listing", "changelog"])
def test_kat_binding_refuses_a_step_without_files(step):
    role, path = (
        ("listing_page", LISTING_PATH) if step == "listing" else ("changelog", CHANGELOG_PATH)
    )
    _, manifest = fixture()
    with pytest.raises(capture.Refusal, match="^capture log not bound$"):
        capture.check_manifest_binding(single_record_log(step, role, path), manifest)


def test_kat_binding_refuses_a_refused_run():
    log, manifest = fixture()
    log["run_status"], log["run_end_utc"] = "REFUSED", None
    log["refusal"] = "request cap exceeded"
    capture.validate_capture_log(log)
    with pytest.raises(capture.Refusal, match="^capture run not complete$"):
        capture.check_manifest_binding(log, manifest)


def test_kat_binding_refuses_class_missing_with_both_payloads():
    log, manifest = fixture()
    manifest["files"][0]["class"] = "missing"
    with pytest.raises(capture.Refusal, match="^capture log not bound$"):
        capture.check_manifest_binding(log, manifest)


@pytest.mark.parametrize(
    "header,expected",
    [
        ("Mon, 01 Jan 2024 00:00:10 UTC", "UNPARSEABLE"),
        ("Mon, 01 Jan 2024 00:00:10 EST", "UNPARSEABLE"),
        ("Mon, ０１ Jan 2024 00:00:10 GMT", "UNPARSEABLE"),
        ("Mon, 31 Feb 2024 00:00:10 GMT", "UNPARSEABLE"),
        ("Mon, 01 Jan 0024 00:00:10 GMT", "BEYOND_TOLERANCE"),
        ("Monday, 01-Jan-24 00:00:10 GMT", "UNPARSEABLE"),
    ],
    ids=["utc-zone", "est-zone", "fullwidth-digits", "invalid-day", "year-0024", "rfc850-form"],
)
def test_kat_date_check_edges(header, expected):
    assert (
        capture.date_check(
            header, "2024-01-01T00:00:10Z", "2024-01-01T00:00:10Z", tolerance_seconds=2
        )
        == expected
    )


@pytest.mark.parametrize(
    "requested,tolerance",
    [("2024-01-01T00:00:10Z", 10**14), ("0001-01-01T00:00:00Z", 10)],
    ids=["huge-tolerance", "year-one-instant"],
)
def test_kat_date_check_overflow_is_a_refusal(requested, tolerance):
    with pytest.raises(capture.Refusal, match="^capture log malformed$"):
        capture.date_check(
            "Mon, 01 Jan 2024 00:00:10 GMT", requested, requested, tolerance_seconds=tolerance
        )


@pytest.mark.parametrize(
    "path,reason",
    [
        (
            "data/spot/daily/klines/F3USDT/1h/F3USDT-1h-2024-01-01.zip",
            "protected path",
        ),
        (
            "data/spot/daily/klines/SOLUSDT/1h/ADAUSDT-4h-2024-01-01.zip",
            "capture log malformed",
        ),
        (
            "data/spot/daily/klines/SOLUSDT/1h/SOLUSDT-1h-2024-13-45.zip",
            "capture log malformed",
        ),
    ],
    ids=["protected-component", "filename-mismatch", "invalid-period"],
)
def test_kat_zip_paths_use_the_fetch_check(path, reason):
    log, _ = fixture()
    log["records"][0]["path"] = path
    raises(log, reason)


def test_kat_unicode_digit_instant_is_malformed():
    log, _ = fixture()
    log["run_start_utc"] = "２024-01-01T00:00:00Z"
    raises(log)
