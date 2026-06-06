from __future__ import annotations

import importlib.util
from pathlib import Path

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


def test_make_access_hash_outputs_named_hash_without_plaintext(monkeypatch, capsys) -> None:
    helper = load_helper()
    monkeypatch.setenv("UCPE_ACCESS_CODE_SALT", "unit-test-salt")
    monkeypatch.setenv("UCPE_ACCESS_CODE", "unit-test-code")

    result = helper.main(["--name", "DEV_MODE_CODE_HASH", "--iterations", "1000"])

    captured = capsys.readouterr()
    assert result == 0
    assert captured.out.startswith("DEV_MODE_CODE_HASH=")
    assert "unit-test-code" not in captured.out
    assert len(captured.out.strip().split("=", maxsplit=1)[1]) == 64
