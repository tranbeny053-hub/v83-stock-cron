from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/quant_ng_fetch.py"
MOCK_MARKER = b"UCPE-MOCK-v1"
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


def zip_blob(content: bytes = b"") -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as mock:
        mock.comment = MOCK_MARKER
        info = zipfile.ZipInfo("payload", date_time=(1980, 1, 1, 0, 0, 0))
        mock.writestr(info, content)
    return stream.getvalue()


def test_zip_blob_is_deterministic_across_dos_timestamp_boundaries() -> None:
    first = zip_blob(b"x")
    time.sleep(2.1)
    assert zip_blob(b"x") == first


def archive(
    root: Path, path: str, content: bytes | None = None, checksum: bytes | None = None
) -> None:
    content = zip_blob() if content is None else content
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    check = (
        hashlib.sha256(content).hexdigest().encode() + b"  " + target.name.encode() + b"\n"
        if checksum is None
        else checksum
    )
    target.with_name(target.name + ".CHECKSUM").write_bytes(check)


def plan_for(root: Path, output: Path, paths: list[str], **changes) -> dict:
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
    plan.update(changes)
    return plan


def invoke(tmp_path: Path, plan: dict, raw: bytes | None = None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / "plan.json"
    p.write_bytes(raw if raw is not None else json.dumps(plan, separators=(",", ":")).encode())
    return subprocess.run(
        [sys.executable, "-I", "-B", str(SCRIPT), str(p)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    ), Path(plan["output_dir"])


def test_pass_manifest_and_deterministic_objects(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    paths = [
        "data/spot/monthly/klines/AAAUSDT/1h/AAAUSDT-1h-2025-01.zip",
        "data/spot/daily/klines/BBBUSDT/15m/BBBUSDT-15m-2025-01-02.zip",
        "data/spot/daily/klines/CCCUSDT/4h/CCCUSDT-4h-2025-01-03.zip",
        "data/spot/monthly/klines/DDDUSDT/1d/DDDUSDT-1d-2025-02.zip",
    ]
    archive(root, paths[0], zip_blob(b"shared"))
    archive(root, paths[1], zip_blob(b"shared"))
    archive(root, paths[2], zip_blob(b"wrong"), b"0" * 64 + b"  CCCUSDT-4h-2025-01-03.zip\n")
    archive(root, paths[3], zip_blob(b"malformed"), b"nope\n")
    paths.append("data/spot/daily/klines/EEEUSDT/1h/EEEUSDT-1h-2025-01-04.zip")
    plan = plan_for(root, tmp_path / "out1", paths)
    # Missing case is the final path; all four archive content classes are represented.
    plan["max_requests"] = 10
    pbytes = json.dumps(plan, separators=(",", ":")).encode()
    result, output = invoke(tmp_path, plan, pbytes)
    assert result.returncode == 0, result.stdout + result.stderr
    body = json.loads((output / "MANIFEST.json").read_bytes())
    assert body == {
        "manifest_id": "ucpe.quant_ng.fetch_manifest.v1",
        "status": "MOCK",
        "plan_sha256": hashlib.sha256(pbytes).hexdigest(),
        "tool_sha256": hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
        "transport": "mock",
        "requests": 10,
        "counts": {"missing": 1, "checksum_malformed": 1, "mismatch": 1, "ok": 2},
        "files": [
            {
                "path": paths[0],
                "symbol": "AAAUSDT",
                "base": "AAA",
                "interval": "1h",
                "granularity": "monthly",
                "period": "2025-01",
                "class": "ok",
                "sha256": hashlib.sha256(zip_blob(b"shared")).hexdigest(),
                "size": len(zip_blob(b"shared")),
                "official_checksum": hashlib.sha256(zip_blob(b"shared")).hexdigest(),
                "checksum_file_sha256": hashlib.sha256(
                    hashlib.sha256(zip_blob(b"shared")).hexdigest().encode()
                    + b"  AAAUSDT-1h-2025-01.zip\n"
                ).hexdigest(),
            },
            {
                "path": paths[1],
                "symbol": "BBBUSDT",
                "base": "BBB",
                "interval": "15m",
                "granularity": "daily",
                "period": "2025-01-02",
                "class": "ok",
                "sha256": hashlib.sha256(zip_blob(b"shared")).hexdigest(),
                "size": len(zip_blob(b"shared")),
                "official_checksum": hashlib.sha256(zip_blob(b"shared")).hexdigest(),
                "checksum_file_sha256": hashlib.sha256(
                    hashlib.sha256(zip_blob(b"shared")).hexdigest().encode()
                    + b"  BBBUSDT-15m-2025-01-02.zip\n"
                ).hexdigest(),
            },
            {
                "path": paths[2],
                "symbol": "CCCUSDT",
                "base": "CCC",
                "interval": "4h",
                "granularity": "daily",
                "period": "2025-01-03",
                "class": "mismatch",
                "sha256": hashlib.sha256(zip_blob(b"wrong")).hexdigest(),
                "size": len(zip_blob(b"wrong")),
                "official_checksum": "0" * 64,
                "checksum_file_sha256": hashlib.sha256(
                    b"0" * 64 + b"  CCCUSDT-4h-2025-01-03.zip\n"
                ).hexdigest(),
            },
            {
                "path": paths[3],
                "symbol": "DDDUSDT",
                "base": "DDD",
                "interval": "1d",
                "granularity": "monthly",
                "period": "2025-02",
                "class": "checksum_malformed",
                "sha256": hashlib.sha256(zip_blob(b"malformed")).hexdigest(),
                "size": len(zip_blob(b"malformed")),
                "official_checksum": None,
                "checksum_file_sha256": hashlib.sha256(b"nope\n").hexdigest(),
            },
            {
                "path": paths[4],
                "symbol": "EEEUSDT",
                "base": "EEE",
                "interval": "1h",
                "granularity": "daily",
                "period": "2025-01-04",
                "class": "missing",
                "sha256": None,
                "size": None,
                "official_checksum": None,
                "checksum_file_sha256": None,
            },
        ],
    }
    raw_manifest = (output / "MANIFEST.json").read_bytes()
    assert (
        raw_manifest
        == (
            json.dumps(
                json.loads(raw_manifest), sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
            + "\n"
        ).encode()
    )
    objects = list((output / "objects").iterdir())
    expected_blobs = [
        zip_blob(b"shared"),
        (hashlib.sha256(zip_blob(b"shared")).hexdigest().encode() + b"  AAAUSDT-1h-2025-01.zip\n"),
        (
            hashlib.sha256(zip_blob(b"shared")).hexdigest().encode()
            + b"  BBBUSDT-15m-2025-01-02.zip\n"
        ),
        zip_blob(b"wrong"),
        b"0" * 64 + b"  CCCUSDT-4h-2025-01-03.zip\n",
        zip_blob(b"malformed"),
        b"nope\n",
    ]
    assert {p.name for p in objects} == {hashlib.sha256(x).hexdigest() for x in expected_blobs}
    assert all(p.stat().st_mode & 0o777 == 0o444 for p in objects)
    assert (output / "MANIFEST.json").stat().st_mode & 0o777 == 0o444
    shared_digest = hashlib.sha256(zip_blob(b"shared")).hexdigest()
    assert len([p for p in objects if p.name == shared_digest]) == 1
    assert str(tmp_path) not in (output / "MANIFEST.json").read_text()
    # Recreate a fresh destination with identical plan bytes and compare exact bytes.
    saved = tmp_path / "saved-output"
    output.rename(saved)
    result2, output2 = invoke(tmp_path / "run2", plan, pbytes)
    assert result2.returncode == 0
    assert (output2 / "MANIFEST.json").read_bytes() == (saved / "MANIFEST.json").read_bytes()


def test_markerless_zip_payload_refuses_without_writing(tmp_path: Path) -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as mock:
        info = zipfile.ZipInfo("payload", date_time=(1980, 1, 1, 0, 0, 0))
        mock.writestr(info, b"data")
    path = "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-1h-2025-01-01.zip"
    root, output = tmp_path / "archive", tmp_path / "out"
    archive(root, path, stream.getvalue())
    result, actual_output = invoke(tmp_path, plan_for(root, output, [path]))
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "object is not a mock object"
    assert actual_output == output
    assert not output.exists()


def test_non_zip_marker_tail_refuses_without_writing(tmp_path: Path) -> None:
    payload = b"arbitrary bytes here!!" + b"\x0c\x00UCPE-MOCK-v1"
    assert len(payload) == 36
    path = "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-1h-2025-01-01.zip"
    root, output = tmp_path / "archive", tmp_path / "out"
    archive(root, path, payload)
    result, actual_output = invoke(tmp_path, plan_for(root, output, [path]))
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "object is not a mock object"
    assert actual_output == output
    assert not output.exists()


@pytest.mark.parametrize(
    "path,reason",
    [
        (
            "data/spot/daily/klines/BTCUSDT/1h/BTCUSDT-1h-2025-01-01.zip",
            "BTCUSDT and ETHUSDT are never requested",
        ),
        (
            "data/spot/daily/klines/ETHUSDT/1h/ETHUSDT-1h-2025-01-01.zip",
            "BTCUSDT and ETHUSDT are never requested",
        ),
        (
            "data/spot/daily/klines/btcusdt/1h/btcusdt-1h-2025-01-01.zip",
            "not an archive kline path",
        ),
        ("data/spot/daily/klines/AAAUSDT/1h/BBB-1h-2025-01-01.zip", "not an archive kline path"),
        (
            "data/spot/daily/klines/AAAUSDT/2h/AAAUSDT-2h-2025-01-01.zip",
            "not an archive kline path",
        ),
        ("data/spot/monthly/klines/AAAUSDT/1h/AAAUSDT-1h-2025-13.zip", "not an archive kline path"),
        (
            "data/spot/monthly/klines/AAAUSDT/1h/AAAUSDT-1h-٢٠٢٥-01.zip",
            "not an archive kline path",
        ),
        (
            "data/spot/monthly/klines/AAAUSDT/1h/AAAUSDT-1h-２０２５-01.zip",
            "not an archive kline path",
        ),
        (
            "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-1h-٢٠٢٥-01-02.zip",
            "not an archive kline path",
        ),
        (
            "data/spot/monthly/klines/AAAUSDT/1h/AAAUSDT-1h-0000-01.zip",
            "not an archive kline path",
        ),
        (
            "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-1h-2025-02-30.zip",
            "not an archive kline path",
        ),
        (
            "data/spot/daily/klines/AAAUSDT/1h/../AAAUSDT-1h-2025-01-01.zip",
            "not an archive kline path",
        ),
        (
            "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-4h-2025-01-01.zip",
            "not an archive kline path",
        ),
        (
            "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-1h-2025-1-01.zip",
            "not an archive kline path",
        ),
        ("data/spot/daily/klines/5AUSDT/1h/5AUSDT-1h-2025-01-01.zip", "protected path"),
    ],
)
def test_path_refusals(tmp_path: Path, path: str, reason: str) -> None:
    plan = plan_for(tmp_path / "archive", tmp_path / "out", [path])
    result, output = invoke(tmp_path, plan)
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"status": "REFUSAL", "reason": reason}
    assert not output.exists()


@pytest.mark.parametrize(
    "update,reason",
    [
        ({"transport": "https"}, "only the mock transport exists"),
        ({"refused_bases": ["AAA"]}, "refused base"),
        ({"refused_bases": ["bad-base"]}, "invalid plan"),
        ({"max_requests": 1}, "request cap exceeded"),
        ({"unverified_share_max": -0.1}, "invalid plan"),
    ],
)
def test_plan_refusals_leave_nothing(tmp_path: Path, update: dict, reason: str) -> None:
    path = "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-1h-2025-01-01.zip"
    plan = plan_for(tmp_path / "archive", tmp_path / "out", [path], **update)
    result, output = invoke(tmp_path, plan)
    assert result.returncode == 2 and json.loads(result.stdout)["reason"] == reason
    assert not output.exists()


@pytest.mark.parametrize(
    "change",
    [
        {"files": []},
        {
            "files": [
                {
                    "path": "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-1h-2025-01-01.zip",
                    "extra": True,
                }
            ]
        },
        {
            "files": [
                {"path": "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-1h-2025-01-01.zip"},
                {"path": "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-1h-2025-01-01.zip"},
            ]
        },
        {"max_requests": 0},
        {"max_requests": True},
    ],
)
def test_malformed_file_rows_and_request_caps_refuse_cleanly(tmp_path: Path, change: dict) -> None:
    valid_path = "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-1h-2025-01-01.zip"
    plan = plan_for(tmp_path / "archive", tmp_path / "out", [valid_path], **change)
    result, output = invoke(tmp_path, plan)
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "invalid plan"
    assert not output.exists()


def test_nonempty_output_refusal_preserves_existing_content(tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_bytes(b"untouched")
    path = "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-1h-2025-01-01.zip"
    plan = plan_for(tmp_path / "archive", output, [path])
    result, _ = invoke(tmp_path / "run", plan)
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "output folder is not empty"
    assert sentinel.read_bytes() == b"untouched"


def test_checksum_line_for_another_file_is_malformed(tmp_path: Path) -> None:
    path = "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-1h-2025-01-01.zip"
    root = tmp_path / "archive"
    checksum = hashlib.sha256(zip_blob(b"payload")).hexdigest().encode() + b"  other.zip\n"
    archive(root, path, zip_blob(b"payload"), checksum)
    plan = plan_for(root, tmp_path / "out", [path])
    result, output = invoke(tmp_path, plan)
    assert result.returncode == 0
    assert (
        json.loads((output / "MANIFEST.json").read_bytes())["files"][0]["class"]
        == "checksum_malformed"
    )


@pytest.mark.parametrize(
    "ending",
    [
        lambda digest, name: digest.upper().encode() + b"  " + name + b"\n",
        lambda digest, name: digest.encode() + b" " + name + b"\n",
        lambda digest, name: digest.encode() + b"  " + name + b"\r\n",
        lambda digest, name: digest.encode() + b"  " + name + b"\n\n",
    ],
    ids=["uppercase", "space", "crlf", "blankline"],
)
def test_checksum_malformed_line_formats(tmp_path_factory, ending) -> None:
    tmp_path = tmp_path_factory.mktemp("checksum-cases")
    path = "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-1h-2025-01-01.zip"
    root = tmp_path / "archive"
    checksum = ending(hashlib.sha256(zip_blob(b"payload")).hexdigest(), Path(path).name.encode())
    archive(root, path, zip_blob(b"payload"), checksum)
    plan = plan_for(root, tmp_path / "out", [path])
    result, output = invoke(tmp_path, plan)
    assert result.returncode == 0
    assert (
        json.loads((output / "MANIFEST.json").read_bytes())["files"][0]["class"]
        == "checksum_malformed"
    )


def test_validates_every_path_before_reading_archive_bytes(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    first = "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-1h-2025-01-01.zip"
    forbidden = "data/spot/daily/klines/BTCUSDT/1h/BTCUSDT-1h-2025-01-01.zip"
    archive(root, first)
    unreadable = root / first
    original_mode = unreadable.stat().st_mode & 0o777
    output = tmp_path / "out"
    try:
        unreadable.chmod(0)
        plan = plan_for(root, output, [first, forbidden])
        result, _ = invoke(tmp_path, plan)
        assert result.returncode == 2
        assert json.loads(result.stdout) == {
            "status": "REFUSAL",
            "reason": "BTCUSDT and ETHUSDT are never requested",
        }
        assert not output.exists()
    finally:
        unreadable.chmod(original_mode)


@pytest.mark.parametrize("root_is_file", [True, False], ids=["root-file", "archive-folder"])
def test_unreadable_archive_paths_refuse_without_output(tmp_path: Path, root_is_file: bool) -> None:
    root = tmp_path / "archive"
    path = "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-1h-2025-01-01.zip"
    if root_is_file:
        root.write_bytes(b"not a directory")
    else:
        folder = root / path
        folder.mkdir(parents=True)
    output = tmp_path / "out"
    plan = plan_for(root, output, [path])
    result, _ = invoke(tmp_path, plan)
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"status": "REFUSAL", "reason": "archive unreadable"}
    assert not output.exists()


def test_missing_only_file_exceeds_unverified_share_cap(tmp_path: Path) -> None:
    path = "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-1h-2025-01-01.zip"
    plan = plan_for(tmp_path / "archive", tmp_path / "out", [path], unverified_share_max=0.99)
    result, output = invoke(tmp_path, plan)
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "unverified share above the cap"
    assert not output.exists()


def test_a_refusal_keeps_a_preexisting_empty_output_folder(tmp_path: Path) -> None:
    """The run did not create the folder, so a refusal empties it but never removes it."""
    output = tmp_path / "a" / "b" / "out"
    output.mkdir(parents=True)
    path = "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-1h-2025-01-01.zip"
    plan = plan_for(tmp_path / "archive", output, [path], unverified_share_max=0.99)
    result, _ = invoke(tmp_path / "run", plan)
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "unverified share above the cap"
    assert output.is_dir()
    assert list(output.iterdir()) == []


def test_a_new_parent_folder_is_refused_before_anything_is_made(tmp_path: Path) -> None:
    """The guard confines writes to the output folder itself, so new parents are never created."""
    output = tmp_path / "a" / "b" / "out"
    path = "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-1h-2025-01-01.zip"
    plan = plan_for(tmp_path / "archive", output, [path], unverified_share_max=0.99)
    result, _ = invoke(tmp_path / "run", plan)
    assert result.returncode == 2
    assert result.stderr == ""
    assert json.loads(result.stdout)["reason"] == (
        "filesystem change outside the output folder: os.mkdir"
    )
    assert not (tmp_path / "a").exists()


def test_unverified_share_boundary_and_archive_symlink(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    path = "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-1h-2025-01-01.zip"
    archive(root, path, zip_blob(b"x"), b"bad")
    plan = plan_for(root, tmp_path / "equal", [path], unverified_share_max=1)
    result, output = invoke(tmp_path / "equalcase", plan)
    assert result.returncode == 0 and output.exists()
    plan = plan_for(root, tmp_path / "above", [path], unverified_share_max=0.99)
    result, output = invoke(tmp_path / "abovecase", plan)
    assert (
        result.returncode == 2
        and json.loads(result.stdout)["reason"] == "unverified share above the cap"
    )
    assert not output.exists()
    (root / path).unlink()
    (root / path).symlink_to(tmp_path / "outside")
    plan = plan_for(root, tmp_path / "symlinkout", [path])
    result, output = invoke(tmp_path / "symlinkcase", plan)
    assert (
        result.returncode == 2
        and json.loads(result.stdout)["reason"] == "archive path escapes the root"
    )
    assert not output.exists()


def test_unknown_and_duplicate_keys(tmp_path: Path) -> None:
    path = "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-1h-2025-01-01.zip"
    plan = plan_for(tmp_path / "archive", tmp_path / "unknown", [path], extra="bad")
    result, output = invoke(tmp_path / "unknowncase", plan)
    assert (
        result.returncode == 2
        and json.loads(result.stdout)["reason"] == "invalid plan"
        and not output.exists()
    )
    raw = b'{"plan_id":"ucpe.quant_ng.fetch.v1","plan_id":"ucpe.quant_ng.fetch.v1"}'
    plan = plan_for(tmp_path / "archive", tmp_path / "duplicate", [path])
    result, output = invoke(tmp_path / "duplicatecase", plan, raw)
    assert (
        result.returncode == 2
        and json.loads(result.stdout)["reason"] == "plan unreadable"
        and not output.exists()
    )


def test_source_has_no_network_or_process_imports() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports |= {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not (imports & FORBIDDEN)


def test_guard_is_installed_once_inside_main() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.count("install_guard(_OUTPUT_HOLDER)") == 1
    tree = ast.parse(source)
    main = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "install_guard"
        for node in ast.walk(main)
    )


def test_unexpected_run_error_reports_its_type(tmp_path: Path, monkeypatch, capsys) -> None:
    spec = importlib.util.spec_from_file_location("quant_ng_fetch_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    monkeypatch.setattr(module, "install_guard", lambda _holder: None)

    def fail(_output):
        raise KeyError("injected internal error")

    monkeypatch.setattr(module, "_make_output", fail)
    path = "data/spot/daily/klines/AAAUSDT/1h/AAAUSDT-1h-2025-01-01.zip"
    plan = plan_for(tmp_path / "archive", tmp_path / "out", [path])
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    assert module.main([str(plan_file)]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "status": "REFUSAL",
        "reason": "run failed: KeyError",
    }
