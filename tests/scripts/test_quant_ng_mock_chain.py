from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
T = "2025-04-01T00:00:00Z"


def load_helpers(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")


def run(script: str, plan: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", "-B", str(ROOT / f"scripts/{script}"), str(plan)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_mock_chain_happy_path_accepts_px2_and_fit_refuses_mock(tmp_path: Path) -> None:
    fetch_helpers = load_helpers("mock_fetch_chain_helpers", "tests/scripts/test_quant_ng_fetch.py")
    extract_helpers = load_helpers(
        "mock_extract_chain_helpers", "tests/scripts/test_quant_ng_extract.py"
    )
    policy_helpers = load_helpers(
        "mock_policy_chain_helpers", "tests/scripts/test_quant_ng_policy.py"
    )
    day = 86_400_000
    blob = extract_helpers.zip_blob(
        "AAAUSDT-1d-2025-03-31.zip",
        [extract_helpers.row(extract_helpers.TMS - day, volume="4.25")],
    )
    rel = "data/spot/daily/klines/AAAUSDT/1d/AAAUSDT-1d-2025-03-31.zip"
    fetch_helpers.archive(tmp_path / "archive", rel, blob)
    fetched = tmp_path / "fetched"
    fetch_plan = fetch_helpers.plan_for(tmp_path / "archive", fetched, [rel])
    fetch_path = tmp_path / "fetch-plan.json"
    write(fetch_path, fetch_plan)
    result = run("quant_ng_fetch.py", fetch_path)
    assert result.returncode == 0, result.stdout + result.stderr

    parsed = tmp_path / "parsed"
    extract_plan_path = tmp_path / "extract-plan.json"
    write(
        extract_plan_path,
        {
            "plan_id": "ucpe.quant_ng.extract.v1",
            "fetch_output_dir": str(fetched),
            "cutoff_utc": T,
            "output_dir": str(parsed),
        },
    )
    result = run("quant_ng_extract.py", extract_plan_path)
    assert result.returncode == 0, result.stdout + result.stderr

    non_market = tmp_path / "non-market.json"
    write(
        non_market,
        {
            "evidence_id": "ucpe.quant_ng.non_market_evidence.v1",
            "source": "mock",
            "exclusion_verification": [],
            "not_leveraged_verification": [],
            "freshness": [],
        },
    )
    windows = tmp_path / "windows.json"
    changelog = tmp_path / "changelog.json"
    write(
        changelog,
        {
            "changelog_id": "ucpe.quant_ng.mock_changelog.v1",
            "source": "mock",
            "assumption": (
                "This format is an assumption until the owner authorizes reading "
                "the venue's real files."
            ),
            "entries": [],
        },
    )
    write(
        windows,
        {"windows_id": "ucpe.quant_ng.mock_proxy_windows.v1", "source": "mock", "bases": []},
    )
    policy = policy_helpers.policy()
    policy["parameters"]["D3_evidence"].update(
        value="E-3", non_market_sha256=hashlib.sha256(non_market.read_bytes()).hexdigest()
    )
    policy["parameters"]["D4_availability"]["value"] = "P-2"
    policy["parameters"]["D5_revision"].update(
        value="RP-3", changelog_sha256=hashlib.sha256(changelog.read_bytes()).hexdigest()
    )
    policy["parameters"]["D6_proxy"].update(
        value="PX-2", windows_sha256=hashlib.sha256(windows.read_bytes()).hexdigest()
    )
    policy_path = tmp_path / "policy.json"
    write(policy_path, policy)
    assembled = tmp_path / "assembled"
    assemble_plan = tmp_path / "assemble-plan.json"
    parse_path = parsed / "PARSE.json"
    write(
        assemble_plan,
        {
            "plan_id": "ucpe.quant_ng.assemble.v1",
            "fetch_output_dir": str(fetched),
            "cutoff_utc": T,
            "parse": {
                "path": str(parse_path),
                "sha256": hashlib.sha256(parse_path.read_bytes()).hexdigest(),
            },
            "policy": {
                "path": str(policy_path),
                "sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest(),
            },
            "non_market_evidence": {
                "path": str(non_market),
                "sha256": hashlib.sha256(non_market.read_bytes()).hexdigest(),
            },
            "changelog": {
                "path": str(changelog),
                "sha256": hashlib.sha256(changelog.read_bytes()).hexdigest(),
            },
            "proxy_windows": {
                "path": str(windows),
                "sha256": hashlib.sha256(windows.read_bytes()).hexdigest(),
            },
            "output_dir": str(assembled),
        },
    )
    result = run("quant_ng_assemble.py", assemble_plan)
    assert result.returncode == 0, result.stdout + result.stderr

    evidence_path = assembled / "EVIDENCE.json"
    evidence_raw = evidence_path.read_bytes()
    builder_plan = tmp_path / "builder-plan.json"
    write(
        builder_plan,
        {
            "plan_id": "ucpe.quant_ng.universe.v1",
            "as_of_utc": T,
            "evidence": {
                "path": str(evidence_path),
                "sha256": hashlib.sha256(evidence_raw).hexdigest(),
            },
            "operating_period_start": {"utc": T, "provenance": "owner supplied"},
            "completeness": {"threshold": 0.5, "ruling": "SYNTHETIC_TEST_ONLY"},
            "output_dir": str(tmp_path / "snapshot"),
        },
    )
    result = run("quant_ng_corpus.py", builder_plan)
    assert result.returncode == 0, result.stdout + result.stderr
    snapshot = json.loads(
        (tmp_path / "snapshot" / "UNIVERSE_SNAPSHOT.json").read_bytes()
    )
    assert snapshot["status"] == "MOCK"
    assert snapshot["methodology"]["f3_clean"] is False
    assert snapshot["methodology"]["f3_clean_basis"] == "MOCK"
    assert snapshot["methodology"]["policy_sha256"] == hashlib.sha256(
        policy_path.read_bytes()
    ).hexdigest()
    assert not load_helpers(
        "mock_chain_corpus_firewall", "scripts/quant_ng_corpus.py"
    ).f3_judgment_admissible(snapshot)

    fit_helpers = load_helpers("mock_chain_fit_helpers", "tests/scripts/test_quant_ng_fit.py")
    plan_path, output, _ = fit_helpers.case(
        tmp_path / "fit", universe=json.dumps(snapshot, separators=(",", ":")).encode()
    )
    result = fit_helpers.invoke(plan_path)
    assert result.returncode == 2
    assert json.loads(result.stdout) == {
        "status": "REFUSAL",
        "reason": "universe snapshot status is not SYNTHETIC",
    }
    assert not output.exists()


def test_mock_snapshot_is_not_admissible_and_fit_requires_synthetic(tmp_path: Path) -> None:
    corpus = load_helpers("mock_corpus_firewall_helpers", "scripts/quant_ng_corpus.py")
    assert not corpus.f3_judgment_admissible(
        {
            "status": "MOCK",
            "f3_firewall": "F-C",
            "f3_calendar_overlap": False,
            "methodology": {"f3_clean": False, "f3_clean_basis": "MOCK"},
        }
    )
    fit_helpers = load_helpers("mock_fit_chain_helpers", "tests/scripts/test_quant_ng_fit.py")
    universe = json.dumps(
        {
            **fit_helpers.VALID_UNIVERSE,
            "status": "MOCK",
        },
        separators=(",", ":"),
    ).encode()
    plan_path, output, _ = fit_helpers.case(tmp_path / "fit", universe=universe)
    result = fit_helpers.invoke(plan_path)
    assert result.returncode == 2
    assert json.loads(result.stdout) == {
        "status": "REFUSAL",
        "reason": "universe snapshot status is not SYNTHETIC",
    }
    assert not output.exists()


def test_mock_mode_rejects_a_synthetic_provenance_record() -> None:
    corpus = load_helpers("mock_corpus_provenance_helpers", "scripts/quant_ng_corpus.py")
    record = {
        "source": "synthetic",
        "sha256": "a" * 64,
        "official_checksum": "a" * 64,
        "available_from_utc": "2025-01-01T00:00:00Z",
        "revisions": [{"sha256": "a" * 64, "available_from_utc": "2025-01-01T00:00:00Z"}],
        "revision_history_complete": True,
    }
    with pytest.raises(corpus.Refusal, match="^source must be mock$"):
        corpus._prov(
            record,
            corpus.instant("2025-01-02T00:00:00Z"),
            expected_policy_sha256="b" * 64,
            allowed_source="mock",
        )
