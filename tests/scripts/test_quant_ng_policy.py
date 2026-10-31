from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/quant_ng_policy.py"


def module():
    spec = importlib.util.spec_from_file_location("quant_ng_policy_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def sample():
    return {
        "size": 1,
        "selection": {
            "method": "LISTED",
            "paths": ["data/spot/monthly/klines/ADAUSDT/1h/ADAUSDT-1h-2025-01.zip"],
        },
        "exclusions": ["F3", "BTCUSDT", "ETHUSDT", "BTC_ETH_PROXIES"],
        "interval_days": 30,
    }


def policy():
    return {
        "policy_id": "ucpe.quant_ng.corpus_policy.v1",
        "status": "MOCK",
        "parameters": {
            "D2_provenance": {"value": "FP-1", "ruling": "SYNTHETIC_TEST_ONLY"},
            "D3_evidence": {
                "value": "E-1",
                "ruling": "SYNTHETIC_TEST_ONLY",
                "non_market_sha256": "a" * 64,
            },
            "D4_availability": {"value": "P-1", "ruling": "SYNTHETIC_TEST_ONLY"},
            "D5_revision": {
                "value": "RP-0",
                "ruling": "SYNTHETIC_TEST_ONLY",
                "sample": None,
                "changelog_sha256": None,
            },
            "D6_proxy": {
                "value": "PX-1",
                "ruling": "SYNTHETIC_TEST_ONLY",
                "windows_sha256": None,
            },
            "D7_completeness": {
                "value": {"shape": "ONE", "values": {"all": "0.5"}},
                "ruling": "SYNTHETIC_TEST_ONLY",
            },
            "D8_close_time": {"value": "CT-1", "ruling": "SYNTHETIC_TEST_ONLY"},
            "operating_period_start": {
                "utc": {"value": "2025-04-01T00:00:00Z", "ruling": "SYNTHETIC_TEST_ONLY"},
                "provenance": {"value": "owner supplied", "ruling": "SYNTHETIC_TEST_ONLY"},
            },
        },
    }


def store(tmp_path: Path, value, raw: bytes | None = None) -> tuple[Path, str]:
    path = tmp_path / "policy.json"
    data = raw if raw is not None else json.dumps(value, separators=(",", ":")).encode()
    path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest()


def expect(tmp_path: Path, value, reason: str, raw: bytes | None = None):
    mod = module()
    path, digest = store(tmp_path, value, raw)
    with pytest.raises(mod.Refusal) as caught:
        mod.load(path, digest)
    assert str(caught.value) == reason


@pytest.mark.parametrize(
    "name,value",
    [
        ("D2_provenance", "FP-1"),
        ("D3_evidence", "E-1"),
        ("D3_evidence", "E-2"),
        ("D3_evidence", "E-3"),
        ("D4_availability", "P-1"),
        ("D4_availability", "P-2"),
        ("D5_revision", "RP-0"),
        ("D5_revision", "RP-1"),
        ("D5_revision", "RP-2"),
        ("D5_revision", "RP-3"),
        ("D5_revision", "RP-3+RP-1"),
        ("D6_proxy", "PX-1"),
        ("D6_proxy", "PX-2"),
        ("D7_completeness", "ONE"),
        ("D7_completeness", "PER_WINDOW"),
        ("D8_close_time", "CT-1"),
        ("D8_close_time", "CT-2"),
        ("D8_close_time", "CT-3"),
    ],
    ids=[
        "provenance-one",
        "evidence-one",
        "evidence-two",
        "evidence-three",
        "availability-one",
        "availability-two",
        "revision-zero",
        "revision-one",
        "revision-two",
        "revision-three",
        "revision-mixed",
        "proxy-one",
        "proxy-two",
        "completeness-one",
        "completeness-windows",
        "close-one",
        "close-two",
        "close-three",
    ],
)
def test_each_accepted_option_loads(tmp_path: Path, name: str, value: str):
    body = policy()
    detail = body["parameters"][name]
    if name == "D7_completeness":
        detail["value"] = (
            {"shape": value, "values": {"all": "1.0"}}
            if value == "ONE"
            else {"shape": value, "values": {key: "0.5" for key in ("1D", "15m", "1H", "4H")}}
        )
    else:
        detail["value"] = value
        if name == "D5_revision" and value in {"RP-1", "RP-2", "RP-3+RP-1"}:
            detail["sample"] = sample()
        if name == "D5_revision" and value in {"RP-3", "RP-3+RP-1"}:
            detail["changelog_sha256"] = "a" * 64
        if name == "D6_proxy" and value == "PX-2":
            detail["windows_sha256"] = "b" * 64
    path, digest = store(tmp_path, body)
    assert module().load(path, digest) == body


def test_complete_mock_policy_loads(tmp_path: Path):
    body = policy()
    path, digest = store(tmp_path, body)
    assert module().load(path, digest) == body


def test_refusal_order_is_stable_across_hash_seeds(tmp_path: Path):
    body = policy()
    body["parameters"]["D2_provenance"]["value"] = "FP-0"
    body["parameters"]["D8_close_time"]["value"] = "CT-4"
    path, digest = store(tmp_path, body)
    code = (
        "import importlib.util, pathlib, sys; "
        "spec = importlib.util.spec_from_file_location('quant_ng_policy', sys.argv[1]); "
        "module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); "
        "module.load(pathlib.Path(sys.argv[2]), sys.argv[3])"
    )

    for seed in ("0", "1", "2"):
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = seed
        result = subprocess.run(
            [sys.executable, "-c", code, str(SCRIPT), str(path), digest],
            capture_output=True,
            check=False,
            env=env,
            text=True,
        )
        assert result.returncode != 0
        assert "policy option refused: FP-0" in result.stderr


@pytest.mark.parametrize(
    "change,reason",
    [
        ("provenance-option", "policy option refused: FP-0"),
        ("revision-option", "policy option refused: RP-1′ (it reads retained research data)"),
        ("close-direction", "policy detail unruled: close-time direction"),
        ("evidence-amendment", "policy option refused: E-2 amends ruled R4"),
        ("missing-sample", "policy detail unruled: sample"),
        ("missing-exclusions", "policy detail unruled: sample exclusions"),
        ("extra-exclusion", "invalid policy"),
        ("duplicate-exclusion", "invalid policy"),
        ("missing-changelog", "policy detail unruled: changelog"),
        ("null-changelog", "policy detail unruled: changelog"),
        ("bad-changelog", "invalid policy"),
        ("unexpected-changelog", "invalid policy"),
        ("missing-proxy-windows", "policy detail unruled: proxy windows"),
        ("null-proxy-windows", "policy detail unruled: proxy windows"),
        ("bad-proxy-windows", "invalid policy"),
        ("unexpected-proxy-windows", "invalid policy"),
        ("duplicate-sample-path", "invalid policy"),
        ("bad-sample-path", "invalid policy"),
        ("sample-btc-path", "invalid policy"),
        ("sample-path-mismatch", "invalid policy"),
        ("bad-size", "invalid policy"),
        ("sample-not-allowed", "invalid policy"),
        ("bad-decimal", "invalid policy"),
        ("zero-decimal", "invalid policy"),
    ],
    ids=[
        "provenance-refused",
        "revision-refused",
        "close-detail",
        "evidence-refused",
        "sample-unruled",
        "exclusions-unruled",
        "exclusion-unknown",
        "exclusion-duplicate",
        "changelog-missing",
        "changelog-null",
        "changelog-format",
        "changelog-unexpected",
        "proxy-windows-missing",
        "proxy-windows-null",
        "proxy-windows-format",
        "proxy-windows-unexpected",
        "sample-path-duplicate",
        "sample-path-layout",
        "sample-path-btc",
        "sample-path-mismatch",
        "sample-size",
        "sample-forbidden",
        "decimal-format",
        "decimal-zero",
    ],
)
def test_specific_and_detail_refusals(tmp_path: Path, change: str, reason: str):
    body = policy()
    params = body["parameters"]
    if change == "provenance-option":
        params["D2_provenance"]["value"] = "FP-0"
    elif change == "revision-option":
        params["D5_revision"]["value"] = "RP-1′"
    elif change == "close-direction":
        params["D8_close_time"]["value"] = "CT-4"
    elif change == "evidence-amendment":
        params["D3_evidence"].update(value="E-2", ruling="OWNER_RULED")
        body["status"] = "OWNER_RULED"
        for key, detail in params.items():
            if key == "operating_period_start":
                detail["utc"]["ruling"] = detail["provenance"]["ruling"] = "OWNER_RULED"
            else:
                detail["ruling"] = "OWNER_RULED"
    elif change == "missing-sample":
        params["D5_revision"].update(value="RP-1", sample=None)
    elif change == "missing-exclusions":
        params["D5_revision"].update(value="RP-1", sample=sample())
        params["D5_revision"]["sample"]["exclusions"] = ["F3"]
    elif change in {"extra-exclusion", "duplicate-exclusion"}:
        params["D5_revision"].update(value="RP-1", sample=sample())
        exclusions = params["D5_revision"]["sample"]["exclusions"]
        exclusions.append("OTHER" if change == "extra-exclusion" else "F3")
    elif change in {
        "missing-changelog",
        "null-changelog",
        "bad-changelog",
        "unexpected-changelog",
    }:
        revision = params["D5_revision"]
        revision["value"] = "RP-3"
        if change == "missing-changelog":
            del revision["changelog_sha256"]
        elif change == "null-changelog":
            revision["changelog_sha256"] = None
        elif change == "bad-changelog":
            revision["changelog_sha256"] = "A" * 64
        else:
            revision["value"] = "RP-0"
            revision["changelog_sha256"] = "a" * 64
    elif change in {
        "missing-proxy-windows",
        "null-proxy-windows",
        "bad-proxy-windows",
        "unexpected-proxy-windows",
    }:
        proxy = params["D6_proxy"]
        proxy["value"] = "PX-2"
        if change == "missing-proxy-windows":
            del proxy["windows_sha256"]
        elif change == "null-proxy-windows":
            proxy["windows_sha256"] = None
        elif change == "bad-proxy-windows":
            proxy["windows_sha256"] = "A" * 64
        else:
            proxy["value"] = "PX-1"
            proxy["windows_sha256"] = "b" * 64
    elif change in {
        "duplicate-sample-path",
        "bad-sample-path",
        "sample-btc-path",
        "sample-path-mismatch",
    }:
        params["D5_revision"].update(value="RP-1", sample=sample())
        paths = params["D5_revision"]["sample"]["selection"]["paths"]
        if change == "duplicate-sample-path":
            paths.append(paths[0])
            params["D5_revision"]["sample"]["size"] = 2
        elif change == "bad-sample-path":
            paths[0] = "listed-one"
        elif change == "sample-btc-path":
            paths[0] = "data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2025-01.zip"
        else:
            paths[0] = "data/spot/monthly/klines/ADAUSDT/1h/ADAUSDT-4h-2025-01.zip"
    elif change == "bad-size":
        params["D5_revision"].update(value="RP-1", sample=sample())
        params["D5_revision"]["sample"]["size"] = 2
    elif change == "sample-not-allowed":
        params["D5_revision"]["sample"] = sample()
    elif change == "bad-decimal":
        params["D7_completeness"]["value"]["values"]["all"] = ".5"
    elif change == "zero-decimal":
        params["D7_completeness"]["value"]["values"]["all"] = "0.0"
    else:
        params["D7_completeness"]["value"]["values"]["all"] = (
            "0.0000000000000000000000000000000000000001"
        )
    expect(tmp_path, body, reason)


@pytest.mark.parametrize(
    "fault",
    [
        "root-missing",
        "root-extra",
        "root-type",
        "parameters-missing",
        "parameters-extra",
        "parameter-type",
        "detail-missing",
        "detail-extra",
        "sample-missing-key",
        "sample-extra-key",
        "selection-missing-key",
        "selection-extra-key",
        "completeness-missing-key",
        "completeness-extra-key",
        "values-missing-key",
        "values-extra-key",
        "period-missing-key",
        "period-extra-key",
        "period-item-missing-key",
        "period-item-extra-key",
        "wrong-ruling-type",
        "bad-evidence-hash",
        "bad-window-key",
        "bad-period-instant",
        "bad-period-provenance",
        "duplicate-key",
        "bad-json",
    ],
    ids=[
        "root-missing",
        "root-extra",
        "root-type",
        "parameters-missing",
        "parameters-extra",
        "parameter-type",
        "detail-missing",
        "detail-extra",
        "sample-missing-key",
        "sample-extra-key",
        "selection-missing-key",
        "selection-extra-key",
        "completeness-missing-key",
        "completeness-extra-key",
        "values-missing-key",
        "values-extra-key",
        "period-missing-key",
        "period-extra-key",
        "period-item-missing-key",
        "period-item-extra-key",
        "ruling-type",
        "evidence-hash",
        "window-key",
        "period-instant",
        "period-provenance",
        "duplicate-key",
        "json-format",
    ],
)
def test_structural_faults_refuse(tmp_path: Path, fault: str):
    body = policy()
    raw = None
    if fault == "root-missing":
        del body["status"]
    elif fault == "root-extra":
        body["extra"] = 1
    elif fault == "root-type":
        body["status"] = []
    elif fault == "parameters-missing":
        del body["parameters"]["D2_provenance"]
    elif fault == "parameters-extra":
        body["parameters"]["extra"] = {}
    elif fault == "parameter-type":
        body["parameters"]["D4_availability"] = "P-1"
    elif fault == "detail-missing":
        del body["parameters"]["D2_provenance"]["ruling"]
    elif fault == "detail-extra":
        body["parameters"]["D2_provenance"]["extra"] = 1
    elif fault in {"sample-missing-key", "sample-extra-key"}:
        revision = body["parameters"]["D5_revision"]
        revision.update(value="RP-1", sample=sample())
        if fault == "sample-missing-key":
            del revision["sample"]["interval_days"]
        else:
            revision["sample"]["extra"] = 1
    elif fault in {"selection-missing-key", "selection-extra-key"}:
        revision = body["parameters"]["D5_revision"]
        revision.update(value="RP-1", sample=sample())
        if fault == "selection-missing-key":
            del revision["sample"]["selection"]["paths"]
        else:
            revision["sample"]["selection"]["extra"] = 1
    elif fault in {"completeness-missing-key", "completeness-extra-key"}:
        value = body["parameters"]["D7_completeness"]["value"]
        if fault == "completeness-missing-key":
            del value["shape"]
        else:
            value["extra"] = 1
    elif fault in {"values-missing-key", "values-extra-key"}:
        values = body["parameters"]["D7_completeness"]["value"]["values"]
        if fault == "values-missing-key":
            del values["all"]
        else:
            values["extra"] = "0.5"
    elif fault in {"period-missing-key", "period-extra-key"}:
        period = body["parameters"]["operating_period_start"]
        if fault == "period-missing-key":
            del period["provenance"]
        else:
            period["extra"] = {}
    elif fault in {"period-item-missing-key", "period-item-extra-key"}:
        item = body["parameters"]["operating_period_start"]["utc"]
        if fault == "period-item-missing-key":
            del item["ruling"]
        else:
            item["extra"] = 1
    elif fault == "wrong-ruling-type":
        body["parameters"]["D2_provenance"]["ruling"] = False
    elif fault == "bad-evidence-hash":
        body["parameters"]["D3_evidence"]["non_market_sha256"] = "A" * 64
    elif fault == "bad-window-key":
        body["parameters"]["D7_completeness"]["value"] = {
            "shape": "PER_WINDOW",
            "values": {"1D": "0.5", "15m": "0.5", "1H": "0.5", "4h": "0.5"},
        }
    elif fault == "bad-period-instant":
        body["parameters"]["operating_period_start"]["utc"]["value"] = "2025-02-30T00:00:00Z"
    elif fault == "bad-period-provenance":
        body["parameters"]["operating_period_start"]["provenance"]["value"] = ""
    elif fault == "duplicate-key":
        raw = (
            b'{"policy_id":"ucpe.quant_ng.corpus_policy.v1",'
            b'"policy_id":"ucpe.quant_ng.corpus_policy.v1"}'
        )
    else:
        raw = b"{"
    expect(tmp_path, body, "invalid policy", raw)


def test_owner_rules_fail_closed_and_mock_requires_synthetic_rulings(tmp_path: Path):
    owner = policy()
    owner["status"] = "OWNER_RULED"
    for detail in owner["parameters"].values():
        if "utc" in detail:
            detail["utc"]["ruling"] = detail["provenance"]["ruling"] = "OWNER_RULED"
        else:
            detail["ruling"] = "OWNER_RULED"
    expect(tmp_path, owner, "policy not owner-ruled")

    mock = policy()
    mock["parameters"]["D2_provenance"]["ruling"] = "OWNER_RULED"
    expect(tmp_path, mock, "invalid policy")


def test_digest_checked_and_refusal_identity(tmp_path: Path):
    mod = module()
    path, digest = store(tmp_path, policy())
    with pytest.raises(mod.Refusal) as caught:
        mod.load(path, "0" * 64)
    assert str(caught.value) == "policy digest mismatch"
    assert mod.Refusal is mod._EXTRACT._FIT.Refusal


def test_operating_period_rejects_non_ascii_digits(tmp_path: Path):
    body = policy()
    body["parameters"]["operating_period_start"]["utc"]["value"] = (
        "٢٠٢٥-04-01T00:00:00Z"
    )
    expect(tmp_path, body, "invalid policy")


@pytest.mark.parametrize(
    "utc_value,provenance_value,accepted",
    [
        (None, None, True),
        ("2025-04-01T00:00:00Z", "owner supplied", True),
        (None, "owner supplied", False),
        ("2025-04-01T00:00:00Z", None, False),
        ("2025-04-01T00:00:00Z", "  ", False),
    ],
    ids=["null-null", "date-text", "null-text", "date-null", "date-blank"],
)
def test_operating_period_builder_combinations(
    tmp_path: Path, utc_value, provenance_value, accepted: bool
):
    body = policy()
    period = body["parameters"]["operating_period_start"]
    period["utc"]["value"] = utc_value
    period["provenance"]["value"] = provenance_value
    if accepted:
        path, digest = store(tmp_path, body)
        assert module().load(path, digest) == body
    else:
        expect(tmp_path, body, "invalid policy")


def test_load_writes_nothing(tmp_path: Path, monkeypatch):
    mod = module()
    path, digest = store(tmp_path, policy())
    before = set(tmp_path.iterdir())

    def forbidden(*args, **kwargs):
        raise AssertionError("load attempted a write")

    monkeypatch.setattr(Path, "write_bytes", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    assert mod.load(path, digest)["status"] == "MOCK"
    assert set(tmp_path.iterdir()) == before


def test_source_has_no_network_or_process_imports():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    forbidden = {"http", "urllib", "requests", "socket", "subprocess", "multiprocessing"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(forbidden)
