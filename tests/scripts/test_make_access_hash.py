from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_helper():
    spec = importlib.util.spec_from_file_location(
        "make_access_hash",
        ROOT / "scripts" / "make_access_hash.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_make_access_hash_requires_salt(monkeypatch, capsys) -> None:
    helper = load_helper()
    monkeypatch.delenv("UCPE_ACCESS_CODE_SALT", raising=False)
    monkeypatch.setenv("UCPE_ACCESS_CODE", "unit-test-code")

    result = helper.main([])

    captured = capsys.readouterr()
    assert result == 2
    assert "UCPE_ACCESS_CODE_SALT is required" in captured.err
    assert "unit-test-code" not in captured.out
    assert "unit-test-code" not in captured.err


@pytest.mark.parametrize(
    "name",
    (
        "APP_ACCESS_CODE_HASH",
        "DEV_MODE_CODE_HASH",
        "CONTROLLED_SMOKE_CODE_HASH",
    ),
)
def test_make_access_hash_outputs_named_hash_without_plaintext(
    monkeypatch, capsys, name
) -> None:
    helper = load_helper()
    monkeypatch.setenv("UCPE_ACCESS_CODE_SALT", "unit-test-salt")
    monkeypatch.setenv("UCPE_ACCESS_CODE", "unit-test-code")

    result = helper.main(["--name", name, "--iterations", "1000"])

    captured = capsys.readouterr()
    assert result == 0
    assert captured.out.startswith(f"{name}=")
    assert "unit-test-code" not in captured.out
    assert "unit-test-code" not in captured.err
    assert len(captured.out.strip().split("=", maxsplit=1)[1]) == 64


def test_make_access_hash_rejects_unsupported_name(monkeypatch, capsys) -> None:
    helper = load_helper()
    monkeypatch.setenv("UCPE_ACCESS_CODE_SALT", "unit-test-salt")
    monkeypatch.setenv("UCPE_ACCESS_CODE", "unit-test-code")

    with pytest.raises(SystemExit) as exc_info:
        helper.main(["--name", "UNSUPPORTED_CODE_HASH", "--iterations", "1000"])

    captured = capsys.readouterr()
    assert exc_info.value.code != 0
    assert "unit-test-code" not in captured.out
    assert "unit-test-code" not in captured.err


def test_make_access_hash_digest_is_identical_for_every_name(monkeypatch, capsys) -> None:
    helper = load_helper()
    monkeypatch.setenv("UCPE_ACCESS_CODE_SALT", "unit-test-salt")
    monkeypatch.setenv("UCPE_ACCESS_CODE", "unit-test-code")

    digests = []
    for name in helper.SUPPORTED_SECRET_NAMES:
        assert helper.main(["--name", name, "--iterations", "1000"]) == 0
        output = capsys.readouterr().out.strip()
        digests.append(output.split("=", maxsplit=1)[1])

    assert len(set(digests)) == 1


def test_make_access_hash_rejects_empty_code(monkeypatch, capsys) -> None:
    helper = load_helper()
    monkeypatch.setenv("UCPE_ACCESS_CODE_SALT", "unit-test-salt")
    monkeypatch.setenv("UCPE_ACCESS_CODE", "")

    result = helper.main([])

    captured = capsys.readouterr()
    assert result != 0
    assert "access code must not be empty" in captured.err


@pytest.mark.parametrize("iterations", ("0", "-1"))
def test_make_access_hash_rejects_non_positive_iterations(
    monkeypatch, capsys, iterations
) -> None:
    helper = load_helper()
    monkeypatch.setenv("UCPE_ACCESS_CODE_SALT", "unit-test-salt")
    monkeypatch.setenv("UCPE_ACCESS_CODE", "unit-test-code")

    result = helper.main(["--iterations", iterations])

    captured = capsys.readouterr()
    assert result != 0
    assert "iterations must be a positive integer" in captured.err
    assert "unit-test-code" not in captured.out
    assert "unit-test-code" not in captured.err
