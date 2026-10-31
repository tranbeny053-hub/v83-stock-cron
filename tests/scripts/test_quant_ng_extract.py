from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/quant_ng_extract.py"
FETCH = ROOT / "scripts/quant_ng_fetch.py"
FORBIDDEN = {
    "socket",
    "ssl",
    "urllib",
    "http",
    "requests",
    "httpx",
    "ftplib",
    "asyncio",
    "subprocess",
}
T = "2025-04-01T00:00:00Z"
TMS = 1743465600000


def zip_blob(
    name: str,
    rows: list[str],
    extra: list[tuple[str, bytes]] | None = None,
    comment: bytes = b"UCPE-MOCK-v1",
) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.comment = comment
        archive.writestr(name[:-4] + ".csv", "\n".join(rows) + "\n")
        for member, data in extra or []:
            archive.writestr(member, data)
    return stream.getvalue()


def row(
    open_ms: int, close_ms: int | str | None = None, volume: str = "2.50", fill: str = "v"
) -> str:
    close = open_ms + 899999 if close_ms is None else close_ms
    return ",".join([str(open_ms), *([fill] * 5), str(close), volume, *([fill] * 4)])


def archive(
    root: Path,
    interval: str,
    period: str,
    blob: bytes,
    symbol: str = "AAAUSDT",
    granularity: str = "daily",
    check: str | None = None,
) -> str:
    filename = f"{symbol}-{interval}-{period}.zip"
    rel = f"data/spot/{granularity}/klines/{symbol}/{interval}/{filename}"
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(blob)
    checksum = hashlib.sha256(blob).hexdigest() if check is None else check
    (target.parent / (filename + ".CHECKSUM")).write_bytes(f"{checksum}  {filename}\n".encode())
    return rel


def fetch(tmp_path: Path, paths: list[str], outname: str = "fetched") -> Path:
    root, output = tmp_path / "archive", tmp_path / outname
    plan = {
        "plan_id": "ucpe.quant_ng.fetch.v1",
        "transport": "mock",
        "mock_archive_root": str(root),
        "files": [{"path": p} for p in paths],
        "refused_bases": [],
        "max_requests": 2 * len(paths),
        "unverified_share_max": 1,
        "output_dir": str(output),
    }
    planfile = tmp_path / "fetchplan.json"
    planfile.write_text(json.dumps(plan, separators=(",", ":")))
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(FETCH), str(planfile)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return output


def invoke(
    tmp_path: Path,
    fetched: Path,
    outname: str = "parsed",
    *,
    cutoff: str = T,
    plan_changes: dict | None = None,
    raw: bytes | None = None,
):
    output = tmp_path / outname
    plan = {
        "plan_id": "ucpe.quant_ng.extract.v1",
        "fetch_output_dir": str(fetched),
        "cutoff_utc": cutoff,
        "output_dir": str(output),
    }
    plan.update(plan_changes or {})
    p = tmp_path / (outname + "plan.json")
    p.write_bytes(raw if raw is not None else json.dumps(plan, separators=(",", ":")).encode())
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(SCRIPT), str(p)], cwd=ROOT, capture_output=True, text=True
    )
    return result, output


def symbols_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    marker = b'"symbols":'
    start = raw.index(marker) + len(marker)
    decoder = json.JSONDecoder()
    value, end = decoder.raw_decode(raw[start:].decode())
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()[:end]


def _identity_rows(fetched: Path, symbol: str, interval: str) -> list[dict]:
    manifest = json.loads((fetched / "MANIFEST.json").read_bytes())
    fields = ("path", "granularity", "period", "sha256", "official_checksum", "class")
    rows = [
        row
        for row in manifest["files"]
        if row["symbol"] == symbol and row["interval"] == interval
        and row["period"] < "2025-04"
    ]
    ordered = sorted(rows, key=lambda row: row["path"])
    return [{field: row[field] for field in fields} for row in ordered]


def _write_manifest(fetched: Path, manifest: dict) -> None:
    path = fetched / "MANIFEST.json"
    path.chmod(0o600)
    path.write_text(json.dumps(manifest))
    path.chmod(0o444)


def make_series(
    tmp_path: Path,
    interval: str = "15m",
    period: str = "2025-03-31",
    rows: list[str] | None = None,
    symbol: str = "AAAUSDT",
    *,
    granularity: str = "daily",
    check: str | None = None,
    extra=None,
):
    base = f"{symbol}-{interval}-{period}.zip"
    path = archive(
        tmp_path / "archive",
        interval,
        period,
        zip_blob(base, rows or [row(TMS - 900000)], extra),
        symbol,
        granularity,
        check,
    )
    return fetch(tmp_path, [path])


def test_pass_fields_and_stable_bytes(tmp_path: Path) -> None:
    paths = []
    root = tmp_path / "archive"
    for interval, period, granularity, open_ms in [
        ("15m", "2025-03-31", "daily", TMS - 900000),
        ("1h", "2025-03", "monthly", TMS - 3600000),
        ("4h", "2025-03", "monthly", TMS - 14400000),
        ("1d", "2025-03", "monthly", TMS - 86400000),
    ]:
        name = f"AAAUSDT-{interval}-{period}.zip"
        paths.append(
            archive(root, interval, period, zip_blob(name, [row(open_ms)]), granularity=granularity)
        )
    paths.append(
        archive(
            root,
            "1d",
            "2025-03-31",
            zip_blob("BBBUSDT-1d-2025-03-31.zip", [row(TMS - 86400000, volume="0")]),
            symbol="BBBUSDT",
        )
    )
    fetched = fetch(tmp_path, paths)
    result, output = invoke(tmp_path, fetched)
    assert result.returncode == 0
    raw = (output / "PARSE.json").read_bytes()
    body = json.loads(raw)
    assert result.stdout.strip() == json.dumps(
        {"status": "PASS", "parse_sha256": hashlib.sha256(raw).hexdigest()}, separators=(",", ":")
    )
    assert (output / "PARSE.json").stat().st_mode & 0o777 == 0o444
    assert body["parse_id"] == "ucpe.quant_ng.extract_parse.v2" and body["status"] == "MOCK"
    assert body["note"] == (
        "parsed bars with per-file identities, not builder evidence: availability, revision "
        "and provenance policy are unruled"
    )
    assert body["cutoff_utc"] == T and body["files_after_cutoff"] == 0
    assert body["windows"] == {"daily_days": 90, "history_bars": {"15m": 678, "1H": 678, "4H": 174}}
    assert (
        body["manifest_sha256"]
        == hashlib.sha256((fetched / "MANIFEST.json").read_bytes()).hexdigest()
    )
    assert body["tool_sha256"] == hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    canonical = (
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()
    assert raw == canonical
    assert [entry["symbol"] for entry in body["symbols"]] == ["AAAUSDT", "BBBUSDT"]
    symbol = body["symbols"][0]
    assert symbol["symbol"] == "AAAUSDT"
    assert symbol["daily"]["bars"] == [{"open_utc": "2025-03-31T00:00:00Z", "quote_volume": "2.50"}]
    assert symbol["daily"]["first_open_utc"] == "2025-03-31T00:00:00Z"
    assert symbol["coverage"]["15m"]["present_in_window"] == 1
    assert symbol["coverage"]["1H"]["present_in_window"] == 1
    assert symbol["coverage"]["4H"]["present_in_window"] == 1
    assert symbol["daily"]["usable"] is True
    assert symbol["daily"] == {
        "usable": True,
        "reason": None,
        "objects": _identity_rows(fetched, "AAAUSDT", "1d"),
        "bars": [{"open_utc": "2025-03-31T00:00:00Z", "quote_volume": "2.50"}],
        "first_open_utc": "2025-03-31T00:00:00Z",
        "off_grid": 0,
        "zero_volume": 0,
        "close_time_anomalies": 1,
    }
    assert symbol["coverage"] == {
        "15m": {
            "usable": True,
            "reason": None,
            "objects": _identity_rows(fetched, "AAAUSDT", "15m"),
            "present_in_window": 1,
            "off_grid": 0,
            "zero_volume": 0,
            "close_time_anomalies": 0,
        },
        "1H": {
            "usable": True,
            "reason": None,
            "objects": _identity_rows(fetched, "AAAUSDT", "1h"),
            "present_in_window": 1,
            "off_grid": 0,
            "zero_volume": 0,
            "close_time_anomalies": 1,
        },
        "4H": {
            "usable": True,
            "reason": None,
            "objects": _identity_rows(fetched, "AAAUSDT", "4h"),
            "present_in_window": 1,
            "off_grid": 0,
            "zero_volume": 0,
            "close_time_anomalies": 1,
        },
    }
    assert body["symbols"][1]["symbol"] == "BBBUSDT"
    assert body["symbols"][1]["daily"]["zero_volume"] == 1
    _, output2 = invoke(tmp_path, fetched, "parsedagain")
    assert (output2 / "PARSE.json").read_bytes() == raw


def test_allowlist_and_after_cutoff_rows(tmp_path: Path) -> None:
    regular = row(TMS - 900000)
    future_fields = row(TMS * 1000, "bad", "bad").split(",")
    future_fields[1:6] = ["x"] * 5
    future_fields[8:] = ["x"] * 4
    future = ",".join(future_fields)
    fetched = make_series(tmp_path, rows=[regular, future])
    result, out = invoke(tmp_path, fetched)
    assert result.returncode == 0
    manifest = json.loads((fetched / "MANIFEST.json").read_bytes())
    digest = manifest["files"][0]["sha256"]
    csvpath = fetched / "objects" / digest
    with zipfile.ZipFile(io.BytesIO(csvpath.read_bytes())) as zf:
        member = zf.namelist()[0]
        lines = zf.read(member).decode().splitlines()
    replaced = []
    for line in lines:
        fields = line.split(",")
        for idx in [1, 2, 3, 4, 5, 8, 9, 10, 11]:
            fields[idx] = "x"
        replaced.append(",".join(fields))
    root = tmp_path / "other" / "archive"
    path = archive(root, "15m", "2025-03-31", zip_blob("AAAUSDT-15m-2025-03-31.zip", replaced))
    fetched2 = fetch(tmp_path / "other", [path])
    result2, out2 = invoke(tmp_path / "other", fetched2)
    assert result2.returncode == 0
    # The parsed values match; per-file identities reflect each distinct manifest.
    symbols_one = json.loads(symbols_bytes(out / "PARSE.json"))
    symbols_two = json.loads(symbols_bytes(out2 / "PARSE.json"))
    for symbols in (symbols_one, symbols_two):
        for item in symbols:
            item["daily"].pop("objects")
            for series in item["coverage"].values():
                series.pop("objects")
    assert symbols_one == symbols_two


def test_a_short_row_dated_after_cutoff_is_discarded(tmp_path: Path) -> None:
    """A row dated at or after T is discarded before its shape is checked."""
    short = ",".join(row(TMS * 1000).split(",")[:11])
    fetched = make_series(tmp_path, rows=[row(TMS - 900000), short])
    result, out = invoke(tmp_path, fetched)
    assert result.returncode == 0
    coverage = json.loads((out / "PARSE.json").read_bytes())["symbols"][0]["coverage"]["15m"]
    assert coverage["usable"] is True
    assert coverage["present_in_window"] == 1


def test_first_open_reaches_before_the_daily_window(tmp_path: Path) -> None:
    """The first daily bar is reported even before the 90-day window; bars hold the window only."""
    day = 86400000
    early, late = TMS - 100 * day, TMS - day
    root = tmp_path / "archive"
    paths = [
        archive(
            root,
            "1d",
            "2024-12",
            zip_blob("AAAUSDT-1d-2024-12.zip", [row(early, early + day - 1)]),
            granularity="monthly",
        ),
        archive(
            root,
            "1d",
            "2025-03",
            zip_blob("AAAUSDT-1d-2025-03.zip", [row(late, late + day - 1)]),
            granularity="monthly",
        ),
    ]
    result, out = invoke(tmp_path, fetch(tmp_path, paths))
    assert result.returncode == 0
    daily = json.loads((out / "PARSE.json").read_bytes())["symbols"][0]["daily"]
    assert daily["first_open_utc"] == "2024-12-22T00:00:00Z"
    assert [bar["open_utc"] for bar in daily["bars"]] == ["2025-03-31T00:00:00Z"]


def test_a_cutoff_off_midnight_by_an_hour_is_refused(tmp_path: Path) -> None:
    """T must be a UTC midnight; an hour past midnight is refused and leaves no output."""
    result, output = invoke(tmp_path, make_series(tmp_path), cutoff="2025-04-01T01:00:00Z")
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "cutoff is not UTC midnight"
    assert not output.exists()


@pytest.mark.parametrize(
    "interval,delta,period,granularity",
    [
        ("15m", 900000, "2025-03-31", "daily"),
        ("1h", 3600000, "2025-03", "monthly"),
        ("4h", 14400000, "2025-03", "monthly"),
        ("1d", 86400000, "2025-03", "monthly"),
    ],
    ids=["quarter-hour", "hour", "four-hour", "day"],
)
def test_cutoff_edge_is_closed(
    tmp_path: Path, interval: str, delta: int, period: str, granularity: str
) -> None:
    fetched = make_series(
        tmp_path,
        interval,
        period,
        [row(TMS - delta), row(TMS, "bad", "bad")],
        granularity=granularity,
    )
    result, out = invoke(tmp_path, fetched)
    assert result.returncode == 0
    body = json.loads((out / "PARSE.json").read_bytes())
    target = (
        body["symbols"][0]["daily"]
        if interval == "1d"
        else body["symbols"][0]["coverage"][{"15m": "15m", "1h": "1H", "4h": "4H"}[interval]]
    )
    if interval == "1d":
        assert len(target["bars"]) == 1
    else:
        assert target["present_in_window"] == 1


@pytest.mark.parametrize(
    "interval,delta,period,granularity",
    [
        ("15m", 678 * 900000, "2025-03-24", "daily"),
        ("1h", 678 * 3600000, "2025-03", "monthly"),
        ("4h", 174 * 14400000, "2025-03", "monthly"),
        ("1d", 90 * 86400000, "2025-01", "monthly"),
    ],
    ids=["quarter-edge", "hour-edge", "four-edge", "daily-edge"],
)
def test_window_start_is_included(
    tmp_path: Path, interval: str, delta: int, period: str, granularity: str
) -> None:
    fetched = make_series(
        tmp_path,
        interval,
        period,
        [row(TMS - delta)],
        granularity=granularity,
    )
    result, out = invoke(tmp_path, fetched)
    assert result.returncode == 0
    body = json.loads((out / "PARSE.json").read_bytes())
    target = (
        body["symbols"][0]["daily"]
        if interval == "1d"
        else body["symbols"][0]["coverage"][{"15m": "15m", "1h": "1H", "4h": "4H"}[interval]]
    )
    if interval == "1d":
        assert len(target["bars"]) == 1
    else:
        assert target["present_in_window"] == 1


@pytest.mark.parametrize(
    "row_value,reason",
    [
        ("short", "malformed row"),
        ("header", "malformed row"),
        ("volume", "malformed volume"),
        ("outside", "bar outside its file period"),
        ("mixed", "invalid timestamp"),
    ],
    ids=["short-row", "header-row", "bad-volume", "outside-period", "mixed-width"],
)
def test_series_reasons(tmp_path: Path, row_value: str, reason: str) -> None:
    valid = row(TMS - 900000)
    if row_value == "short":
        rows = [",".join(valid.split(",")[:-1])]
    elif row_value == "header":
        rows = ["open_time,open,high,low,close,volume,close_time,quote_volume,x,x,x,x"]
    elif row_value == "volume":
        fields = valid.split(",")
        fields[7] = "1e3"
        rows = [",".join(fields)]
    elif row_value == "outside":
        rows = [row(TMS - 3 * 86400000)]
    else:
        rows = [valid, row(TMS - 1800000).replace(str(TMS - 1800000), str((TMS - 1800000) * 1000))]
    fetched = make_series(tmp_path, rows=rows)
    result, out = invoke(tmp_path, fetched)
    assert result.returncode == 0
    assert (
        json.loads((out / "PARSE.json").read_bytes())["symbols"][0]["coverage"]["15m"]["reason"]
        == reason
    )


def test_off_grid_zero_and_close_anomaly(tmp_path: Path) -> None:
    rows = [row(TMS - 900000, volume="0"), row(TMS - 450000), row(TMS - 1800000, TMS - 1)]
    fetched = make_series(tmp_path, rows=rows)
    result, out = invoke(tmp_path, fetched)
    assert result.returncode == 0
    series = json.loads((out / "PARSE.json").read_bytes())["symbols"][0]["coverage"]["15m"]
    assert (
        series["present_in_window"],
        series["off_grid"],
        series["zero_volume"],
        series["close_time_anomalies"],
    ) == (2, 1, 1, 1)


@pytest.mark.parametrize(
    "case,reason",
    [
        ("two-members", "malformed archive file"),
        ("wrong-member", "malformed archive file"),
        ("inner-empty", "malformed row"),
        ("duplicate", "duplicate bar"),
    ],
    ids=["two-members", "wrong-name", "inner-empty", "repeated-bar"],
)
def test_archive_and_row_failures(tmp_path: Path, case: str, reason: str) -> None:
    name = "AAAUSDT-15m-2025-03-31.zip"
    if case == "two-members":
        blob = zip_blob(name, [row(TMS - 900000)], [("extra.csv", b"x")])
    elif case == "wrong-member":
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as zf:
            zf.comment = b"UCPE-MOCK-v1"
            zf.writestr("wrong.csv", row(TMS - 900000))
        blob = stream.getvalue()
    elif case == "inner-empty":
        blob = zip_blob(name, [row(TMS - 900000), "", row(TMS - 1800000)])
    else:
        blob = zip_blob(name, [row(TMS - 900000), row(TMS - 900000)])
    path = archive(tmp_path / "archive", "15m", "2025-03-31", blob)
    fetched = fetch(tmp_path, [path])
    result, out = invoke(tmp_path, fetched)
    assert result.returncode == 0
    assert (
        json.loads((out / "PARSE.json").read_bytes())["symbols"][0]["coverage"]["15m"]["reason"]
        == reason
    )


def test_duplicate_bar_across_files_makes_series_unusable(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    open_ms = TMS - 900000
    monthly = archive(
        root,
        "15m",
        "2025-03",
        zip_blob("AAAUSDT-15m-2025-03.zip", [row(open_ms)]),
        granularity="monthly",
    )
    daily = archive(
        root,
        "15m",
        "2025-03-31",
        zip_blob("AAAUSDT-15m-2025-03-31.zip", [row(open_ms)]),
    )
    fetched = fetch(tmp_path, [monthly, daily])
    result, out = invoke(tmp_path, fetched)
    assert result.returncode == 0
    assert (
        json.loads((out / "PARSE.json").read_bytes())["symbols"][0]["coverage"]["15m"]["reason"]
        == "duplicate bar"
    )


def test_microseconds_and_window_counters(tmp_path: Path) -> None:
    opens = (TMS - 900000) * 1000
    name = "AAAUSDT-15m-2025-03-31.zip"
    fields = row(TMS - 900000).split(",")
    fields[0], fields[6] = str(opens), str(opens + 900_000_000 - 1)
    path = archive(tmp_path / "archive", "15m", "2025-03-31", zip_blob(name, [",".join(fields)]))
    fetched = fetch(tmp_path, [path])
    result, out = invoke(tmp_path, fetched)
    assert result.returncode == 0
    series = json.loads((out / "PARSE.json").read_bytes())["symbols"][0]["coverage"]["15m"]
    assert series["present_in_window"] == 1


@pytest.mark.parametrize(
    "period,granularity,cls",
    [
        ("2025-04-01", "daily", "mismatch"),
        ("2025-04-01", "daily", "missing"),
        ("2025-04", "monthly", "mismatch"),
        ("2025-04", "monthly", "missing"),
    ],
    ids=["day-mismatch", "day-missing", "month-mismatch", "month-missing"],
)
def test_period_after_cutoff_skips_unverified_file(
    tmp_path: Path, period: str, granularity: str, cls: str
) -> None:
    root = tmp_path / "archive"
    filename = f"AAAUSDT-15m-{period}.zip"
    rel = f"data/spot/{granularity}/klines/AAAUSDT/15m/{filename}"
    if cls == "mismatch":
        archive(
            root,
            "15m",
            period,
            zip_blob(filename, [row(TMS)]),
            granularity=granularity,
            check="0" * 64,
        )
    fetched = fetch(tmp_path, [rel])
    result, out = invoke(tmp_path, fetched)
    assert result.returncode == 0
    body = json.loads((out / "PARSE.json").read_bytes())
    assert body["files_after_cutoff"] == 1
    assert body["symbols"] == []


def test_series_unverified_and_missing_files(tmp_path: Path) -> None:
    path = archive(
        tmp_path / "archive",
        "15m",
        "2025-03-31",
        zip_blob("AAAUSDT-15m-2025-03-31.zip", [row(TMS - 900000)]),
        check="0" * 64,
    )
    fetched = fetch(tmp_path, [path])
    result, out = invoke(tmp_path, fetched)
    assert result.returncode == 0
    symbol = json.loads((out / "PARSE.json").read_bytes())["symbols"][0]
    assert symbol["coverage"]["15m"]["reason"] == "file not verified"
    assert symbol["coverage"]["1H"]["reason"] == "no files"


def test_oversize_member_refused_by_series(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = importlib.util.spec_from_file_location("extract_for_limit", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "MAX_MEMBER_SIZE", 1)
    blob = zip_blob("AAAUSDT-15m-2025-03-31.zip", [row(TMS - 900000)])
    path = archive(tmp_path / "archive", "15m", "2025-03-31", blob)
    fetched = fetch(tmp_path, [path])
    plan = {
        "plan_id": "ucpe.quant_ng.extract.v1",
        "fetch_output_dir": str(fetched),
        "cutoff_utc": T,
        "output_dir": str(tmp_path / "parsed"),
    }
    plan_path = tmp_path / "localplan.json"
    plan_path.write_text(json.dumps(plan))
    module.run(str(plan_path))
    assert (
        json.loads((tmp_path / "parsed" / "PARSE.json").read_bytes())["symbols"][0]["coverage"][
            "15m"
        ]["reason"]
        == "malformed archive file"
    )


def test_source_and_guard_shape() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not imports.intersection(FORBIDDEN)
    assert source.count("install_guard(_OUTPUT_HOLDER)") == 1
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    assert (
        sum(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "install_guard"
            for n in ast.walk(main)
        )
        == 1
    )


def test_invalid_plan_duplicate_key_and_cutoff(tmp_path: Path) -> None:
    fetched = make_series(tmp_path)
    raw = b'{"plan_id":"ucpe.quant_ng.extract.v1","plan_id":"ucpe.quant_ng.extract.v1"}'
    result, output = invoke(tmp_path, fetched, raw=raw)
    assert result.returncode == 2 and json.loads(result.stdout)["reason"] == "invalid plan"
    result, output = invoke(tmp_path, fetched, "badcut", cutoff="2025-04-01T00:00:01Z")
    assert (
        result.returncode == 2
        and json.loads(result.stdout)["reason"] == "cutoff is not UTC midnight"
    )
    assert not output.exists()


@pytest.mark.parametrize(
    "raw",
    [
        b'{"plan_id":"ucpe.quant_ng.extract.v1","fetch_output_dir":"x","cutoff_utc":"2025-04-01T00:00:00Z","output_dir":"y","extra":"x"}',
        b'{"plan_id":"ucpe.quant_ng.extract.v1","fetch_output_dir":4,"cutoff_utc":"2025-04-01T00:00:00Z","output_dir":"y"}',
        b'{"plan_id":"ucpe.quant_ng.extract.v1","fetch_output_dir":"x","cutoff_utc":"2025-04-01T00:00:00Z","output_dir":false}',
        b'{"plan_id":"ucpe.quant_ng.extract.v1","cutoff_utc":"2025-04-01T00:00:00Z","output_dir":"y"}',
    ],
    ids=["extra-key", "wrong-fetch-type", "wrong-output-type", "missing-fetch-dir"],
)
def test_plan_schema_refuses_invalid_shapes(tmp_path: Path, raw: bytes) -> None:
    fetched = make_series(tmp_path)
    result, output = invoke(tmp_path, fetched, raw=raw)
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "invalid plan"
    assert not output.exists()


@pytest.mark.parametrize(
    "case,reason",
    [
        ("status", "only a mock manifest is accepted"),
        ("identity", "invalid manifest"),
        ("reserved-btc", "BTCUSDT and ETHUSDT are never parsed"),
        ("reserved-eth", "BTCUSDT and ETHUSDT are never parsed"),
        ("missing-object", "object does not match the manifest"),
        ("changed-object", "object does not match the manifest"),
        ("object-link", "symlink path"),
    ],
    ids=[
        "non-mock",
        "bad-identity",
        "btc-symbol",
        "eth-symbol",
        "missing-object",
        "changed-object",
        "object-link",
    ],
)
def test_manifest_and_object_refusals_leave_no_output(
    tmp_path: Path, case: str, reason: str
) -> None:
    fetched = make_series(tmp_path)
    manifest_path = fetched / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_bytes())
    entry = manifest["files"][0]
    if case == "status":
        manifest["status"] = "REAL"
    elif case == "identity":
        manifest["manifest_id"] = "wrong"
    elif case == "reserved-btc":
        entry["symbol"] = "BTCUSDT"
    elif case == "reserved-eth":
        entry["symbol"] = "ETHUSDT"
    elif case == "missing-object":
        (fetched / "objects" / entry["sha256"]).unlink()
    elif case == "changed-object":
        target = fetched / "objects" / entry["sha256"]
        target.chmod(0o600)
        target.write_bytes(b"changed")
        target.chmod(0o444)
    else:
        target = fetched / "objects" / entry["sha256"]
        target.unlink()
        target.symlink_to(tmp_path / "elsewhere")
    if case in {"status", "identity", "reserved-btc", "reserved-eth"}:
        manifest_path.chmod(0o600)
        manifest_path.write_text(json.dumps(manifest))
        manifest_path.chmod(0o444)
    result, output = invoke(tmp_path, fetched)
    assert result.returncode == 2 and json.loads(result.stdout)["reason"] == reason
    assert not output.exists()


def test_nonempty_output_refused(tmp_path: Path) -> None:
    fetched = make_series(tmp_path)
    output = tmp_path / "occupied"
    output.mkdir()
    (output / "keep").write_text("x")
    result, _ = invoke(tmp_path, fetched, "occupied")
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "output folder is not empty"
    assert (output / "keep").read_text() == "x"


def test_midmonth_discards_undecodable_rows_and_allows_no_final_newline(tmp_path: Path) -> None:
    cutoff = datetime(2025, 4, 15, tzinfo=UTC)
    cutoff_ms = int(cutoff.timestamp() * 1000)
    before = row(cutoff_ms - 900000)
    after = row(cutoff_ms, "bad", "bad").split(",")
    after_bytes = [field.encode() for field in after]
    after_bytes[1] = b"\xff"
    after = b",".join(after_bytes)
    short = ",".join(row(cutoff_ms + 900000).split(",")[:11]).encode()
    payload = before.encode() + b"\n" + after + b"\n" + short
    filename = "AAAUSDT-15m-2025-04.zip"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.comment = b"UCPE-MOCK-v1"
        zf.writestr(filename[:-4] + ".csv", payload)
    path = archive(tmp_path / "archive", "15m", "2025-04", stream.getvalue(), granularity="monthly")
    result, output = invoke(tmp_path, fetch(tmp_path, [path]), cutoff="2025-04-15T00:00:00Z")
    assert result.returncode == 0
    body = json.loads((output / "PARSE.json").read_bytes())
    assert body["symbols"][0]["coverage"]["15m"]["present_in_window"] == 1


@pytest.mark.parametrize(
    "interval,delta,period,granularity",
    [
        ("15m", 679 * 900000, "2025-03-24", "daily"),
        ("1h", 679 * 3600000, "2025-03", "monthly"),
        ("4h", 175 * 14400000, "2025-03", "monthly"),
    ],
    ids=["quarter-before", "hour-before", "four-before"],
)
def test_bar_before_window_start_is_excluded(
    tmp_path: Path, interval: str, delta: int, period: str, granularity: str
) -> None:
    fetched = make_series(tmp_path, interval, period, [row(TMS - delta)], granularity=granularity)
    result, output = invoke(tmp_path, fetched)
    assert result.returncode == 0
    coverage = json.loads((output / "PARSE.json").read_bytes())["symbols"][0]["coverage"]
    name = {"15m": "15m", "1h": "1H", "4h": "4H"}[interval]
    assert coverage[name]["present_in_window"] == 0


def test_daily_bar_before_window_start_is_excluded(tmp_path: Path) -> None:
    open_ms = TMS - 91 * 86400000
    fetched = make_series(
        tmp_path, "1d", "2024-12", [row(open_ms, open_ms + 86400000 - 1)], granularity="monthly"
    )
    result, output = invoke(tmp_path, fetched)
    assert result.returncode == 0
    daily = json.loads((output / "PARSE.json").read_bytes())["symbols"][0]["daily"]
    assert daily["bars"] == []


def test_off_grid_daily_bar_is_counted_outside_slots(tmp_path: Path) -> None:
    open_ms = TMS - 86400000 + 1000
    fetched = make_series(tmp_path, "1d", "2025-03", [row(open_ms)], granularity="monthly")
    result, output = invoke(tmp_path, fetched)
    assert result.returncode == 0
    daily = json.loads((output / "PARSE.json").read_bytes())["symbols"][0]["daily"]
    assert daily["bars"] == [] and daily["off_grid"] == 1


def test_corrupt_deflate_stream_fails_only_its_series(tmp_path: Path) -> None:
    original = zip_blob("AAAUSDT-15m-2025-03-31.zip", [row(TMS - 900000)])
    damaged = bytearray(original)
    name_len = int.from_bytes(damaged[26:28], "little")
    extra_len = int.from_bytes(damaged[28:30], "little")
    payload_start = 30 + name_len + extra_len
    damaged[payload_start] ^= 0xFF
    path = archive(tmp_path / "archive", "15m", "2025-03-31", bytes(damaged))
    result, output = invoke(tmp_path, fetch(tmp_path, [path]))
    assert result.returncode == 0
    coverage = json.loads((output / "PARSE.json").read_bytes())["symbols"][0]["coverage"]
    assert coverage["15m"]["reason"] == "malformed archive file"


def test_all_pre_cutoff_objects_are_checked_before_series_status(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    good = archive(
        root, "15m", "2025-03-31", zip_blob("AAAUSDT-15m-2025-03-31.zip", [row(TMS - 900000)])
    )
    bad = archive(
        root,
        "15m",
        "2025-03",
        zip_blob("AAAUSDT-15m-2025-03.zip", [row(TMS - 900000)]),
        granularity="monthly",
        check="0" * 64,
    )
    fetched = fetch(tmp_path, [good, bad])
    manifest = json.loads((fetched / "MANIFEST.json").read_bytes())
    (fetched / "objects" / manifest["files"][0]["sha256"]).unlink()
    result, output = invoke(tmp_path, fetched)
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "object does not match the manifest"
    assert not output.exists()


def test_symbol_with_only_after_cutoff_rows_is_omitted(tmp_path: Path) -> None:
    path = archive(
        tmp_path / "archive",
        "15m",
        "2025-04-01",
        zip_blob("ZZZUSDT-15m-2025-04-01.zip", [row(TMS)]),
        symbol="ZZZUSDT",
    )
    result, output = invoke(tmp_path, fetch(tmp_path, [path]))
    assert result.returncode == 0
    body = json.loads((output / "PARSE.json").read_bytes())
    assert body["files_after_cutoff"] == 1 and body["symbols"] == []


def test_objects_list_pre_cutoff_rows_in_path_order(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    paths = [
        archive(
            root,
            "15m",
            "2025-03",
            zip_blob("AAAUSDT-15m-2025-03.zip", [row(TMS - 3 * 86400000)]),
            granularity="monthly",
        ),
        archive(
            root,
            "15m",
            "2025-03-30",
            zip_blob("AAAUSDT-15m-2025-03-30.zip", [row(TMS - 2 * 86400000)]),
        ),
        archive(
            root,
            "15m",
            "2025-03-31",
            zip_blob("AAAUSDT-15m-2025-03-31.zip", [row(TMS - 900000)]),
        ),
        archive(
            root,
            "15m",
            "2025-04-01",
            zip_blob("AAAUSDT-15m-2025-04-01.zip", [row(TMS)]),
        ),
    ]
    fetched = fetch(tmp_path, paths)
    result, output = invoke(tmp_path, fetched)
    assert result.returncode == 0
    body = json.loads((output / "PARSE.json").read_bytes())
    coverage = body["symbols"][0]["coverage"]["15m"]
    assert coverage["objects"] == _identity_rows(fetched, "AAAUSDT", "15m")
    assert len(coverage["objects"]) == 3
    assert body["files_after_cutoff"] == 1
    assert all(entry["period"] != "2025-04-01" for entry in coverage["objects"])


@pytest.mark.parametrize(
    "object_class",
    ["missing", "mismatch"],
    ids=["missing-file", "mismatched-file"],
)
def test_unusable_series_still_lists_object_identities(
    tmp_path: Path, object_class: str
) -> None:
    root = tmp_path / "archive"
    good = archive(
        root,
        "15m",
        "2025-03-31",
        zip_blob("AAAUSDT-15m-2025-03-31.zip", [row(TMS - 900000)]),
    )
    bad = archive(
        root,
        "15m",
        "2025-03-30",
        zip_blob("AAAUSDT-15m-2025-03-30.zip", [row(TMS - 2 * 86400000)]),
        check="0" * 64 if object_class == "mismatch" else None,
    )
    fetched = fetch(tmp_path, [good, bad])
    manifest = json.loads((fetched / "MANIFEST.json").read_bytes())
    manifest_bad = next(item for item in manifest["files"] if item["path"] == bad)
    if object_class == "missing":
        manifest_bad["class"] = "missing"
        manifest_bad["sha256"] = None
        manifest_bad["official_checksum"] = None
        manifest_bad["size"] = None
    _write_manifest(fetched, manifest)
    result, output = invoke(tmp_path, fetched)
    assert result.returncode == 0
    coverage = json.loads((output / "PARSE.json").read_bytes())["symbols"][0]["coverage"]["15m"]
    assert coverage["usable"] is False
    assert object_class in [entry["class"] for entry in coverage["objects"]]
    assert coverage["objects"] == _identity_rows(fetched, "AAAUSDT", "15m")


def test_manifest_path_must_match_its_row_fields(tmp_path: Path) -> None:
    fetched = make_series(tmp_path)
    manifest_path = fetched / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["files"][0]["interval"] = "1h"
    manifest_path.chmod(0o600)
    manifest_path.write_text(json.dumps(manifest))
    manifest_path.chmod(0o444)
    result, output = invoke(tmp_path, fetched)
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "invalid manifest"
    assert not output.exists()


def test_an_object_changed_after_verification_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetched = make_series(
        tmp_path,
        "1d",
        "2025-03",
        [row(TMS - 86400000, TMS - 1, volume="2.50")],
        granularity="monthly",
    )
    manifest = json.loads((fetched / "MANIFEST.json").read_bytes())
    object_path = fetched / "objects" / manifest["files"][0]["sha256"]
    original_read = Path.read_bytes
    changed = False

    def read_and_replace(path: Path) -> bytes:
        nonlocal changed
        if path == object_path:
            changed = True
            object_path.chmod(0o600)
            object_path.write_bytes(
                zip_blob(
                    "AAAUSDT-1d-2025-03.zip",
                    [row(TMS - 86400000, TMS - 1, volume="9.00")],
                )
            )
            object_path.chmod(0o444)
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", read_and_replace)
    spec = importlib.util.spec_from_file_location("extract_verified_bytes", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plan = {
        "plan_id": "ucpe.quant_ng.extract.v1",
        "fetch_output_dir": str(fetched),
        "cutoff_utc": T,
        "output_dir": str(tmp_path / "parsed"),
    }
    plan_path = tmp_path / "localplan.json"
    plan_path.write_text(json.dumps(plan))

    with pytest.raises(module.Refusal, match="object changed after verification"):
        module.run(str(plan_path))
    assert changed
    assert not (tmp_path / "parsed" / "PARSE.json").exists()
    assert not (tmp_path / "parsed").exists()


def test_verified_object_parses_its_original_value(tmp_path: Path) -> None:
    fetched = make_series(
        tmp_path,
        "1d",
        "2025-03",
        [row(TMS - 86400000, TMS - 1, volume="2.50")],
        granularity="monthly",
    )
    result, output = invoke(tmp_path, fetched)
    assert result.returncode == 0
    parsed = json.loads((output / "PARSE.json").read_bytes())
    assert parsed["symbols"][0]["daily"]["bars"][0]["quote_volume"] == "2.50"


def test_upfront_hash_streams_and_parse_reads_each_object_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetched = make_series(tmp_path)
    manifest = json.loads((fetched / "MANIFEST.json").read_bytes())
    object_path = fetched / "objects" / manifest["files"][0]["sha256"]
    original_read_bytes = Path.read_bytes
    original_open = Path.open
    events: list[tuple[str, Path]] = []

    def watched_read_bytes(path: Path) -> bytes:
        if path == object_path:
            events.append(("read", path))
        return original_read_bytes(path)

    def watched_open(path: Path, *args, **kwargs):
        if path == object_path:
            events.append(("stream", path))
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", watched_read_bytes)
    monkeypatch.setattr(Path, "open", watched_open)
    spec = importlib.util.spec_from_file_location("extract_streamed_hash", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plan_path = tmp_path / "stream-plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "plan_id": "ucpe.quant_ng.extract.v1",
                "fetch_output_dir": str(fetched),
                "cutoff_utc": T,
                "output_dir": str(tmp_path / "streamed"),
            }
        )
    )
    assert module.run(str(plan_path))["status"] == "PASS"
    first_read = next(i for i, (event, _) in enumerate(events) if event == "read")
    assert all(event == "stream" for event, _ in events[:first_read])
    assert [event for event, _ in events].count("stream") == 2
    assert [event for event, _ in events].count("read") == 1


def _replace_fetched_object(fetched: Path, blob: bytes) -> None:
    manifest_path = fetched / "MANIFEST.json"
    manifest_path.chmod(0o600)
    manifest = json.loads(manifest_path.read_bytes())
    row = manifest["files"][0]
    old_path = fetched / "objects" / row["sha256"]
    old_path.chmod(0o600)
    old_path.unlink()
    digest = hashlib.sha256(blob).hexdigest()
    (fetched / "objects" / digest).write_bytes(blob)
    (fetched / "objects" / digest).chmod(0o444)
    row["sha256"] = digest
    row["official_checksum"] = digest
    row["size"] = len(blob)
    manifest_path.write_text(json.dumps(manifest, separators=(",", ":")) + "\n")
    manifest_path.chmod(0o444)


@pytest.mark.parametrize(
    "comment",
    [b"", b"NOT-MOCK-v1!", b"UCPE-MOCK-v1!"],
    ids=["no-marker", "different-comment", "long-comment"],
)
def test_unmarked_object_refuses_the_parse_run(
    tmp_path: Path, comment: bytes
) -> None:
    fetched = make_series(tmp_path)
    _replace_fetched_object(
        fetched,
        zip_blob("AAAUSDT-15m-2025-03-31.zip", [row(TMS - 900000)], comment=comment),
    )
    plan_path = tmp_path / "marker-plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "plan_id": "ucpe.quant_ng.extract.v1",
                "fetch_output_dir": str(fetched),
                "cutoff_utc": T,
                "output_dir": str(tmp_path / "marker-output"),
            }
        )
    )
    spec = importlib.util.spec_from_file_location("extract_marker_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(module.Refusal, match="object is not a mock object"):
        module.run(str(plan_path))
    assert not (tmp_path / "marker-output").exists()


def test_parse_time_comment_mismatch_refuses_the_parse_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetched = make_series(tmp_path)
    spec = importlib.util.spec_from_file_location("extract_parse_marker_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original_zipfile = module.zipfile.ZipFile

    class WrongCommentArchive:
        def __init__(self, *args, **kwargs):
            self.archive = original_zipfile(*args, **kwargs)
            self.comment = b"NOT-MOCK-v1!"

        def __enter__(self):
            self.archive.__enter__()
            return self

        def __exit__(self, *args):
            return self.archive.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.archive, name)

    monkeypatch.setattr(module.zipfile, "ZipFile", WrongCommentArchive)
    plan_path = tmp_path / "parse-marker-plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "plan_id": "ucpe.quant_ng.extract.v1",
                "fetch_output_dir": str(fetched),
                "cutoff_utc": T,
                "output_dir": str(tmp_path / "parse-marker-output"),
            }
        )
    )
    with pytest.raises(module.Refusal, match="object is not a mock object"):
        module.run(str(plan_path))
    assert not (tmp_path / "parse-marker-output").exists()


@pytest.mark.parametrize("bad_tail", ["missing marker", "wrong length"], ids=["missing", "length"])
def test_upfront_marker_refusal_precedes_parse_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bad_tail: str,
) -> None:
    fetched = make_series(tmp_path)
    manifest = json.loads((fetched / "MANIFEST.json").read_bytes())
    object_path = fetched / "objects" / manifest["files"][0]["sha256"]
    blob = object_path.read_bytes()
    if bad_tail == "missing marker":
        blob = zip_blob(
            "AAAUSDT-15m-2025-03-31.zip",
            [row(TMS - 900000)],
            comment=b"NOT-MOCK-v1!",
        )
    else:
        damaged = bytearray(blob)
        damaged[-14:-12] = b"\x0d\x00"
        blob = bytes(damaged)
    _replace_fetched_object(fetched, blob)
    spec = importlib.util.spec_from_file_location("extract_upfront_marker", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def parse_must_not_run(*args, **kwargs):
        pytest.fail("parse pass ran before upfront marker refusal")

    monkeypatch.setattr(module, "_read_archive", parse_must_not_run)
    plan_path = tmp_path / "upfront-marker-plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "plan_id": "ucpe.quant_ng.extract.v1",
                "fetch_output_dir": str(fetched),
                "cutoff_utc": T,
                "output_dir": str(tmp_path / "upfront-marker-output"),
            }
        )
    )
    with pytest.raises(module.Refusal, match="object is not a mock object"):
        module.run(str(plan_path))
    assert not (tmp_path / "upfront-marker-output").exists()


def test_large_object_stream_hash_checks_its_tail(tmp_path: Path) -> None:
    import random

    rng = random.Random(42)
    fields = ["".join(rng.choices("abcdef0123456789", k=150000)) for _ in range(9)]
    csv_row = ",".join(
        [str(TMS - 900000), *fields[:5], str(TMS - 1), "2.50", *fields[5:]]
    )
    member = "AAAUSDT-15m-2025-03-31.csv"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.comment = b"UCPE-MOCK-v1"
        zf.writestr(member, csv_row + "\n")
    blob = stream.getvalue()
    assert len(blob) > 1024 * 1024
    path = archive(tmp_path / "archive", "15m", "2025-03-31", blob)
    fetched = fetch(tmp_path, [path])
    result, output = invoke(tmp_path, fetched, "large-good")
    assert result.returncode == 0
    manifest = json.loads((fetched / "MANIFEST.json").read_bytes())
    object_path = fetched / "objects" / manifest["files"][0]["sha256"]
    object_path.chmod(0o600)
    changed = bytearray(object_path.read_bytes())
    changed[-1] ^= 1
    object_path.write_bytes(changed)
    object_path.chmod(0o444)
    refused, bad_output = invoke(tmp_path, fetched, "large-tail-change")
    assert refused.returncode == 2
    assert json.loads(refused.stdout)["reason"] == "object does not match the manifest"
    assert not bad_output.exists()


@pytest.mark.parametrize(
    "granularity,period",
    [
        ("monthly", "2025-3"),
        ("monthly", "2025-+3"),
        ("monthly", " 2025-03"),
        ("monthly", "2025-０3"),
        ("monthly", "2025-13"),
        ("daily", "2025-02-30"),
        ("daily", "20250331"),
    ],
    ids=[
        "short-month",
        "signed-month",
        "spaced-month",
        "unicode-month",
        "bad-month",
        "bad-day",
        "basic-format-day",
    ],
)
def test_noncanonical_manifest_period_is_refused(
    tmp_path: Path, granularity: str, period: str
) -> None:
    if granularity == "monthly":
        fetched = make_series(tmp_path, "15m", "2025-03", granularity="monthly")
    else:
        fetched = make_series(tmp_path, "15m", "2025-03-31", granularity="daily")
    manifest_path = fetched / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_bytes())
    entry = manifest["files"][0]
    filename = f'{entry["symbol"]}-{entry["interval"]}-{period}.zip'
    entry["period"] = period
    entry["path"] = entry["path"].rsplit("/", 1)[0] + "/" + filename
    manifest_path.chmod(0o600)
    manifest_path.write_text(json.dumps(manifest))
    manifest_path.chmod(0o444)

    result, output = invoke(tmp_path, fetched)
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "invalid manifest"
    assert not output.exists()
