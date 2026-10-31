from __future__ import annotations

import ast
import hashlib
import importlib.util
import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/quant_ng_assemble.py"
EXTRACT = ROOT / "scripts/quant_ng_extract.py"
T = "2025-04-01T00:00:00Z"

_HELPER_SPEC = importlib.util.spec_from_file_location(
    "extract_test_helpers", ROOT / "tests/scripts/test_quant_ng_extract.py"
)
HELPERS = importlib.util.module_from_spec(_HELPER_SPEC)
_HELPER_SPEC.loader.exec_module(HELPERS)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_file(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, separators=(",", ":")))


def assembled_inputs(tmp_path: Path, *, extra_paths: list[str] | None = None):
    day = 86_400_000
    name = "AAAUSDT-1d-2025-03-31.zip"
    archive_path = HELPERS.archive(
        tmp_path / "archive",
        "1d",
        "2025-03-31",
        HELPERS.zip_blob(name, [HELPERS.row(HELPERS.TMS - day, volume="4.25")]),
    )
    fetched = HELPERS.fetch(tmp_path, [archive_path, *(extra_paths or [])])
    parse_dir = tmp_path / "parsed"
    parse_plan = {
        "plan_id": "ucpe.quant_ng.extract.v1",
        "fetch_output_dir": str(fetched),
        "cutoff_utc": T,
        "output_dir": str(parse_dir),
    }
    parse_plan_path = tmp_path / "parse-plan.json"
    json_file(parse_plan_path, parse_plan)
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(EXTRACT), str(parse_plan_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    parse_path = parse_dir / "PARSE.json"
    policy = tmp_path / "policy.json"
    non_market = tmp_path / "non-market.json"
    json_file(
        non_market,
        {
            "evidence_id": "ucpe.quant_ng.non_market_evidence.v1",
            "source": "mock",
            "exclusion_verification": [],
            "not_leveraged_verification": [],
            "freshness": [],
        },
    )
    write_policy(policy, non_market)
    return fetched, parse_path, policy, non_market


def write_policy(policy: Path, non_market: Path) -> None:
    policy_helpers = importlib.util.spec_from_file_location(
        "policy_test_helpers_for_assemble", ROOT / "tests/scripts/test_quant_ng_policy.py"
    )
    assert policy_helpers and policy_helpers.loader
    policy_module = importlib.util.module_from_spec(policy_helpers)
    policy_helpers.loader.exec_module(policy_module)
    policy_value = policy_module.policy()
    policy_value["parameters"]["D3_evidence"]["non_market_sha256"] = sha(non_market)
    json_file(policy, policy_value)


def plan_for(
    tmp_path: Path, fetched, parse, policy, non_market, *, outname="evidence", changes=None
):
    value = {
        "plan_id": "ucpe.quant_ng.assemble.v1",
        "fetch_output_dir": str(fetched),
        "cutoff_utc": T,
        "parse": {"path": str(parse), "sha256": sha(parse)},
        "policy": {"path": str(policy), "sha256": sha(policy)},
        "non_market_evidence": {"path": str(non_market), "sha256": sha(non_market)},
        "changelog": None,
        "proxy_windows": None,
        "output_dir": str(tmp_path / outname),
    }
    value.update(changes or {})
    path = tmp_path / f"{outname}-plan.json"
    json_file(path, value)
    return path, Path(value["output_dir"])


def invoke(plan: Path):
    return subprocess.run(
        [sys.executable, "-I", "-B", str(SCRIPT), str(plan)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def load_assembler():
    spec = importlib.util.spec_from_file_location("assemble_for_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "availability,revision,held,entry,expected_revisions,complete,available",
    [
        ("P-1", "RP-0", "a", None, [], False, None),
        ("P-1", "RP-3", "a", None, [], False, None),
        (
            "P-2", "RP-0", "a", None,
            [{"sha256": "a" * 64, "available_from_utc": "2025-04-01T00:00:00Z"}],
            False, "2025-04-01T00:00:00Z",
        ),
        (
            "P-2", "RP-3", "b", None,
            [{"sha256": "b" * 64, "available_from_utc": "2025-04-01T00:00:00Z"}],
            True, "2025-04-01T00:00:00Z",
        ),
        (
            "P-2", "RP-3", "b", "replacement",
            [
                {"sha256": "a" * 64, "available_before_utc": "2025-05-01T00:00:00Z"},
                {"sha256": "b" * 64, "available_from_utc": "2025-05-01T00:00:00Z"},
            ], True, "2025-05-01T00:00:00Z",
        ),
        (
            "P-2", "RP-3", "a", "replaced-before",
            [
                {"sha256": "a" * 64, "available_from_utc": "2025-04-01T00:00:00Z"},
                {"sha256": "b" * 64, "available_from_utc": "2025-05-01T00:00:00Z"},
            ], True, "2025-04-01T00:00:00Z",
        ),
        ("P-1", "RP-3", "b", "replacement", [], False, None),
        ("P-1", "RP-3", "a", "replaced-before", [], False, None),
        ("P-1", "RP-3", "a", "replaced-after", [], False, None),
    ],
    ids=[
        "P-1-RP-0", "P-1-RP-3", "P-2-RP-0", "P-2-RP-3-unlisted",
        "P-2-held-replacement", "P-2-held-replaced-before", "P-1-held-replacement",
        "P-1-held-replaced-before", "P-1-held-replaced-no-A-check",
    ],
)
def test_file_provenance_cells_and_cutoff_usability(
    availability, revision, held, entry, expected_revisions, complete, available
):
    assemble = load_assembler()
    corpus = importlib.util.spec_from_file_location(
        "corpus_for_provenance_cells", ROOT / "scripts/quant_ng_corpus.py"
    )
    assert corpus and corpus.loader
    builder = importlib.util.module_from_spec(corpus)
    corpus.loader.exec_module(builder)
    held_digest = held * 64
    case = entry
    item = {
        "path": "AAAUSDT-1d-2025-03-31.zip",
        "sha256": held_digest,
        "official_checksum": held_digest,
        "last_bar_close_utc": "2025-04-01T00:00:00Z",
    }
    if entry == "replacement":
        entry = {
            "replaced_sha256": "a" * 64,
            "replacement_sha256": held_digest,
            "updated_utc": "2025-05-01T00:00:00Z",
        }
    elif entry in {"replaced-before", "replaced-after"}:
        updated = (
            "2025-05-01T00:00:00Z"
            if entry == "replaced-before"
            else "2025-03-01T00:00:00Z"
        )
        entry = {
            "replaced_sha256": "a" * 64,
            "replacement_sha256": "b" * 64,
            "updated_utc": updated,
        }
    record = assemble._file_provenance(item, availability, revision, entry)
    assert {
        key: record[key]
        for key in (
            "source", "sha256", "official_checksum", "available_from_utc",
            "revisions", "revision_history_complete",
        )
    } == {
        "source": "mock", "sha256": held_digest, "official_checksum": held_digest,
        "available_from_utc": available, "revisions": expected_revisions,
        "revision_history_complete": complete,
    }
    synthetic = {**record, "source": "synthetic"}
    expectations = [False, False, False]
    if availability == "P-2" and revision == "RP-3":
        if case == "replacement":
            expectations = [False, True, True]
        elif case == "replaced-before":
            expectations = [True, False, False]
        else:
            expectations = [True, True, True]
    for at, expected in zip(
        ("2025-04-30T23:59:59Z", "2025-05-01T00:00:00Z", "2025-05-02T00:00:00Z"),
        expectations,
        strict=True,
    ):
        assert builder._prov(synthetic, builder.instant(at))[0] is expected


@pytest.mark.parametrize(
    "availability,updated,held_digest,reason",
    [
        ("P-2", "2025-04-01T00:00:00Z", "a" * 64, "invalid changelog"),
        ("P-1", "2025-04-01T00:00:00Z", "c" * 64, "STOP S5: unlisted revision"),
        ("P-2", "2025-04-01T00:00:00Z", "c" * 64, "STOP S5: unlisted revision"),
    ],
    ids=["held-replaced-A-not-before-U", "held-neither-P-1", "held-neither-P-2"],
)
def test_rp3_refusal_cases(availability, updated, held_digest, reason):
    assemble = load_assembler()
    item = {
        "sha256": held_digest,
        "official_checksum": held_digest,
        "last_bar_close_utc": "2025-04-01T00:00:00Z",
    }
    entry = {"replaced_sha256": "a" * 64, "replacement_sha256": "b" * 64, "updated_utc": updated}
    with pytest.raises(assemble.Refusal, match=f"^{reason}$"):
        assemble._file_provenance(item, availability, "RP-3", entry)


@pytest.mark.parametrize("last_bar_close", ["2025-05-01T00:00:00Z", "2025-05-02T00:00:00Z"])
def test_held_replacement_refuses_bar_close_at_or_after_update(last_bar_close):
    assemble = load_assembler()
    digest = "b" * 64
    item = {
        "sha256": digest,
        "official_checksum": digest,
        "last_bar_close_utc": last_bar_close,
    }
    entry = {
        "replaced_sha256": "a" * 64,
        "replacement_sha256": digest,
        "updated_utc": "2025-05-01T00:00:00Z",
    }
    with pytest.raises(assemble.Refusal, match="^invalid changelog$"):
        assemble._file_provenance(item, "P-2", "RP-3", entry)


def test_held_replacement_with_unknown_bar_close_stays_unusable():
    assemble = load_assembler()
    corpus = importlib.util.spec_from_file_location(
        "corpus_for_unknown_held_replacement", ROOT / "scripts/quant_ng_corpus.py"
    )
    assert corpus and corpus.loader
    builder = importlib.util.module_from_spec(corpus)
    corpus.loader.exec_module(builder)
    digest = "b" * 64
    record = assemble._file_provenance(
        {
            "sha256": digest,
            "official_checksum": digest,
            "last_bar_close_utc": None,
        },
        "P-2",
        "RP-3",
        {
            "replaced_sha256": "a" * 64,
            "replacement_sha256": digest,
            "updated_utc": "2025-05-01T00:00:00Z",
        },
    )
    assert record["available_from_utc"] is None
    synthetic = {
        **record,
        "source": "synthetic",
        "path": "synthetic/archive.csv",
        "class": "ok",
        "last_bar_close_utc": None,
    }
    series = {
        "files": [synthetic],
        "series_usable": True,
        "series_reason": "verified",
        "policy_fields": {"policy_sha256": "c" * 64},
    }
    assert builder._prov(series, builder.instant("2025-06-01T00:00:00Z"), "c" * 64)[0] is False


def test_changelog_rejects_identical_replaced_and_replacement_hashes():
    assemble = load_assembler()
    value = {
        "changelog_id": "ucpe.quant_ng.mock_changelog.v1",
        "source": "mock",
        "assumption": assemble.CHANGELOG_ASSUMPTION,
        "entries": [{
            "path": "synthetic/archive.csv",
            "replaced_sha256": "a" * 64,
            "replacement_sha256": "a" * 64,
            "updated_utc": "2025-05-01T00:00:00Z",
        }],
    }
    with pytest.raises(assemble.Refusal, match="^invalid changelog$"):
        assemble.check_changelog(value)


def test_evidence_requires_policy_argument():
    assemble = load_assembler()
    policy_parameter = inspect.signature(assemble.evidence).parameters["policy"]
    assert policy_parameter.default is inspect.Parameter.empty


def test_run_loads_policy_once_and_uses_it_for_evidence(tmp_path: Path, monkeypatch) -> None:
    fetched, parse_path, policy_path, non_market = assembled_inputs(tmp_path)
    plan, _ = plan_for(tmp_path, fetched, parse_path, policy_path, non_market)
    assemble = load_assembler()
    original_load = assemble._POLICY.load
    original_evidence = assemble.evidence
    loaded = []
    passed = []

    def load_once(path, digest):
        policy = original_load(path, digest)
        loaded.append(policy)
        return policy

    def record_evidence(*args, **kwargs):
        passed.append(kwargs["policy"])
        return original_evidence(*args, **kwargs)

    monkeypatch.setattr(assemble._POLICY, "load", load_once)
    monkeypatch.setattr(assemble, "evidence", record_evidence)
    result = assemble.run(str(plan))
    assert result["status"] == "PASS"
    assert len(loaded) == 1
    assert passed == loaded


@pytest.mark.parametrize(
    "revision", ["RP-1", "RP-2", "RP-3+RP-1"],
    ids=["RP-1", "RP-2", "RP-3-plus-RP-1"],
)
def test_capture_time_policies_refuse(revision):
    assemble = load_assembler()
    with pytest.raises(assemble.Refusal, match="^policy detail unruled: capture time$"):
        assemble.evidence(
            {}, fetch_dir=Path("fetch"), parse_sha256="a" * 64,
            policy_path=Path("policy"), policy_sha256="b" * 64,
            non_market_path=Path("non-market"), non_market_sha256="c" * 64,
            non_market={}, policy={"parameters": {
                "D4_availability": {"value": "P-2"},
                "D5_revision": {"value": revision},
            }},
        )


@pytest.mark.parametrize(
    "case,expected",
    [
        ("digest-mismatch", "input digest mismatch"),
        ("digest-not-policy-named", "invalid policy"),
        ("present-when-unnamed", "invalid policy"),
        ("named-but-absent", "policy detail unruled: changelog"),
        ("invalid-changelog", "invalid changelog"),
        ("invalid-proxy-windows", "invalid proxy windows"),
    ],
    ids=[
        "digest-mismatch", "digest-not-policy-named", "present-when-unnamed",
        "named-but-absent", "invalid-changelog", "invalid-proxy-windows",
    ],
)
def test_bound_input_refusals(tmp_path: Path, case: str, expected: str) -> None:
    fetched, parse_path, policy_path, non_market = assembled_inputs(tmp_path)
    policy_helpers = importlib.util.spec_from_file_location(
        "policy_input_refusal_helpers", ROOT / "tests/scripts/test_quant_ng_policy.py"
    )
    assert policy_helpers and policy_helpers.loader
    policy_module = importlib.util.module_from_spec(policy_helpers)
    policy_helpers.loader.exec_module(policy_module)
    policy = policy_module.policy()
    policy["parameters"]["D3_evidence"]["non_market_sha256"] = sha(non_market)
    changes = {}
    changelog = {
        "changelog_id": "ucpe.quant_ng.mock_changelog.v1",
        "source": "mock",
        "assumption": (
            "This format is an assumption until the owner authorizes reading "
            "the venue's real files."
        ),
        "entries": [],
    }
    windows = {"windows_id": "ucpe.quant_ng.mock_proxy_windows.v1", "source": "mock", "bases": []}
    changelog_path, windows_path = tmp_path / "changelog.json", tmp_path / "windows.json"
    json_file(changelog_path, changelog)
    json_file(windows_path, windows)
    changelog_hash, windows_hash = sha(changelog_path), sha(windows_path)
    if case in {"digest-not-policy-named", "named-but-absent"}:
        policy["parameters"]["D5_revision"].update(
            value="RP-3",
            changelog_sha256=("e" * 64 if case == "digest-not-policy-named" else changelog_hash),
        )
        if case != "named-but-absent":
            changes["changelog"] = {"path": str(changelog_path), "sha256": changelog_hash}
    elif case == "digest-mismatch":
        policy["parameters"]["D5_revision"].update(value="RP-3", changelog_sha256=changelog_hash)
        changes["changelog"] = {"path": str(changelog_path), "sha256": "d" * 64}
    elif case == "present-when-unnamed":
        changes["changelog"] = {"path": str(changelog_path), "sha256": changelog_hash}
    elif case == "invalid-changelog":
        json_file(changelog_path, {"invalid": True})
        # Re-pin the invalid bytes and make the policy name those exact bytes.
        changelog_hash = sha(changelog_path)
        policy["parameters"]["D5_revision"].update(
            value="RP-3", changelog_sha256=changelog_hash
        )
        changes["changelog"] = {"path": str(changelog_path), "sha256": changelog_hash}
    elif case == "invalid-proxy-windows":
        json_file(windows_path, {"invalid": True})
        windows_hash = sha(windows_path)
        policy["parameters"]["D6_proxy"].update(value="PX-2", windows_sha256=windows_hash)
        changes["proxy_windows"] = {"path": str(windows_path), "sha256": windows_hash}
    policy_path.write_text(json.dumps(policy, separators=(",", ":")), encoding="utf-8")
    plan, _ = plan_for(tmp_path, fetched, parse_path, policy_path, non_market, changes=changes)
    result = invoke(plan)
    assert result.returncode != 0
    assert json.loads(result.stdout)["reason"] == expected


def test_assembler_uses_parser_refusal_class() -> None:
    module = load_assembler()
    assert module.Refusal is module._EXTRACT.Refusal


def test_evidence_reproduces_parse_and_is_stable(tmp_path: Path) -> None:
    fetched, parse_path, policy, non_market = assembled_inputs(tmp_path)
    plan, output = plan_for(tmp_path, fetched, parse_path, policy, non_market)
    first = invoke(plan)
    assert first.returncode == 0, first.stdout + first.stderr
    evidence_path = output / "EVIDENCE.json"
    raw = evidence_path.read_bytes()
    evidence = json.loads(raw)
    parsed = json.loads(parse_path.read_bytes())
    candidate = evidence["candidates"][0]
    source = parsed["symbols"][0]
    assert candidate["symbol"] == source["symbol"]
    assert candidate["daily_quote_volume"]["bars"] == [
        {key: value for key, value in bar.items() if key != "close_time_anomaly"}
        for bar in source["daily"]["bars"]
    ]
    assert all(
        "close_time_anomaly" not in bar
        for bar in candidate["daily_quote_volume"]["bars"]
    )
    assert candidate["listing"]["first_daily_bar_open_utc"] == source["daily"]["first_open_utc"]
    assert candidate["listing"]["provenance"]["files"] == [
        {
            key: item[key]
            for key in (
                "path",
                "sha256",
                "official_checksum",
                "class",
                "last_bar_close_utc",
            )
        } | {
            "source": "mock",
            "available_from_utc": None,
            "revisions": [],
            "revision_history_complete": False,
        }
        for item in source["daily"]["objects"]
    ]
    assert candidate["coverage"]["15m"]["present_in_window"] is None
    assert (
        candidate["coverage"]["15m"]["provenance"]["files"]
        == [
            {
                key: item[key]
                for key in (
                    "path",
                    "sha256",
                    "official_checksum",
                    "class",
                    "last_bar_close_utc",
                )
            } | {
                "source": "mock",
                "available_from_utc": None,
                "revisions": [],
                "revision_history_complete": False,
            }
            for item in source["coverage"]["15m"]["objects"]
        ]
    )
    assert evidence["binding"]["parse_sha256"] == sha(parse_path)
    assert evidence["binding"]["manifest_sha256"] == parsed["manifest_sha256"]
    assert evidence["binding"]["policy_sha256"] == sha(policy)
    assert evidence["binding"]["non_market_sha256"] == sha(non_market)
    assert evidence["binding"]["assemble_tool_sha256"] == sha(SCRIPT)
    assert evidence_path.stat().st_mode & 0o777 == 0o444
    second_plan, second_output = plan_for(
        tmp_path, fetched, parse_path, policy, non_market, outname="again"
    )
    assert invoke(second_plan).returncode == 0
    assert (second_output / "EVIDENCE.json").read_bytes() == raw


def test_evidence_fields_match_documented_mapping_exactly(tmp_path: Path) -> None:
    fetched, parse_path, policy, non_market = assembled_inputs(tmp_path)
    plan_path, output = plan_for(tmp_path, fetched, parse_path, policy, non_market)
    result = invoke(plan_path)
    assert result.returncode == 0, result.stdout + result.stderr

    parsed = json.loads(parse_path.read_bytes())
    source = parsed["symbols"][0]

    def provenance(series: dict) -> dict:
        policy_value = json.loads(policy.read_bytes())
        availability = policy_value["parameters"]["D4_availability"]["value"]
        revision = policy_value["parameters"]["D5_revision"]["value"]
        return {
            "files": [
                {
                    key: item[key]
                    for key in (
                        "path",
                        "sha256",
                        "official_checksum",
                        "class",
                        "last_bar_close_utc",
                    )
                } | {
                    "source": "mock",
                    "available_from_utc": (
                        item["last_bar_close_utc"] if availability == "P-2" else None
                    ),
                    "revisions": (
                        [{
                            "sha256": item["sha256"],
                            "available_from_utc": (
                                item["last_bar_close_utc"] if availability == "P-2" else None
                            ),
                        }]
                        if revision == "RP-0" and availability == "P-2"
                        else []
                    ),
                    "revision_history_complete": False,
                }
                for item in series["objects"]
            ],
            "series_usable": series["usable"],
            "series_reason": series["reason"],
            "policy_fields": {"policy_sha256": sha(policy)},
        }

    daily_provenance = provenance(source["daily"])
    expected = {
        "evidence_id": "ucpe.quant_ng.universe_evidence.v1",
        "source": "mock",
        "candidates": [
            {
                "symbol": source["symbol"],
                "base": source["symbol"][:-4],
                "quote": "USDT",
                "lineage": None,
                "listing": {
                    "first_daily_bar_open_utc": source["daily"]["first_open_utc"],
                    "provenance": daily_provenance,
                },
                "daily_quote_volume": {
                    "bars": [
                        {key: value for key, value in bar.items() if key != "close_time_anomaly"}
                        for bar in source["daily"]["bars"]
                    ]
                    if source["daily"]["usable"]
                    else None,
                    "provenance": daily_provenance,
                },
                "coverage": {
                    name: {
                        "present_in_window": (
                            source["coverage"][name]["present_in_window"]
                            if source["coverage"][name]["usable"]
                            else None
                        ),
                        "provenance": provenance(source["coverage"][name]),
                    }
                    for name in ("15m", "1H", "4H")
                },
            }
        ],
        "exclusion_verification": json.loads(non_market.read_bytes())["exclusion_verification"],
        "not_leveraged_verification": json.loads(non_market.read_bytes())[
            "not_leveraged_verification"
        ],
        "freshness": json.loads(non_market.read_bytes())["freshness"],
        "binding": {
            "fetch_output_dir": str(fetched),
            "cutoff_utc": T,
            "parse_sha256": sha(parse_path),
            "manifest_sha256": parsed["manifest_sha256"],
            "policy_sha256": sha(policy),
            "policy_path": str(policy.resolve()),
            "non_market_sha256": sha(non_market),
            "non_market_path": str(non_market.resolve()),
            "changelog_path": None,
            "changelog_sha256": None,
            "proxy_windows_path": None,
            "proxy_windows_sha256": None,
            "assemble_tool_sha256": sha(SCRIPT),
        },
    }
    written = json.loads((output / "EVIDENCE.json").read_bytes())
    assert written == expected

    module = load_assembler()
    assert module.evidence(
        parsed,
        fetch_dir=fetched.resolve(),
        parse_sha256=sha(parse_path),
        policy_path=policy.resolve(),
        policy_sha256=sha(policy),
        non_market_path=non_market.resolve(),
        non_market_sha256=sha(non_market),
        non_market=json.loads(non_market.read_bytes()),
        policy=json.loads(policy.read_bytes()),
    ) == written
    invalid_parse = dict(parsed)
    invalid_parse["symbols"] = [dict(parsed["symbols"][0], symbol="AAABTC")]
    with pytest.raises(module.Refusal, match="invalid parse symbol"):
        module.evidence(
            invalid_parse,
            fetch_dir=fetched.resolve(),
            parse_sha256=sha(parse_path),
            policy_path=policy.resolve(),
            policy_sha256=sha(policy),
            non_market_path=non_market.resolve(),
            non_market_sha256=sha(non_market),
            non_market=json.loads(non_market.read_bytes()),
            policy=json.loads(policy.read_bytes()),
        )


def test_binding_has_exact_keys_and_plan_fetch_directory(tmp_path: Path) -> None:
    fetched, parse_path, policy, non_market = assembled_inputs(tmp_path)
    plan_path, output = plan_for(tmp_path, fetched, parse_path, policy, non_market)
    result = invoke(plan_path)
    assert result.returncode == 0, result.stdout + result.stderr
    binding = json.loads((output / "EVIDENCE.json").read_bytes())["binding"]
    assert set(binding) == {
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
    assert binding["fetch_output_dir"] == str(fetched)
    assert binding["policy_path"] == str(policy.resolve())
    assert binding["non_market_path"] == str(non_market.resolve())


@pytest.mark.parametrize(
    "case", ["volume edit", "cutoff change"], ids=["edited parse", "other cutoff"]
)
def test_parse_must_be_rederived(tmp_path: Path, case: str) -> None:
    fetched, parse_path, policy, non_market = assembled_inputs(tmp_path)
    cutoff = T
    if case == "volume edit":
        body = json.loads(parse_path.read_bytes())
        body["symbols"][0]["daily"]["bars"][0]["quote_volume"] = "99"
        parse_path.chmod(0o600)
        parse_path.write_text(json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n")
        parse_path.chmod(0o444)
    else:
        cutoff = "2025-03-31T00:00:00Z"
    plan, output = plan_for(
        tmp_path, fetched, parse_path, policy, non_market, changes={"cutoff_utc": cutoff}
    )
    result = invoke(plan)
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "parse not derived from manifest"
    assert not output.exists()


@pytest.mark.parametrize(
    "case",
    ["parse digest", "policy digest", "nonmarket digest"],
    ids=["parse pin", "policy pin", "nonmarket pin"],
)
def test_input_digest_mismatch_refuses(tmp_path: Path, case: str) -> None:
    fetched, parse_path, policy, non_market = assembled_inputs(tmp_path)
    selected = {
        "parse digest": "parse",
        "policy digest": "policy",
        "nonmarket digest": "non_market_evidence",
    }[case]
    plan, output = plan_for(
        tmp_path,
        fetched,
        parse_path,
        policy,
        non_market,
        changes={
            selected: {
                "path": str(
                    {"parse": parse_path, "policy": policy, "non_market_evidence": non_market}[
                        selected
                    ]
                ),
                "sha256": "0" * 64,
            }
        },
    )
    result = invoke(plan)
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "input digest mismatch"
    assert not output.exists()


@pytest.mark.parametrize(
    "case", ["wrong id", "wrong status"], ids=["policy identity", "policy status"]
)
def test_invalid_policy_refuses(tmp_path: Path, case: str) -> None:
    fetched, parse_path, policy, non_market = assembled_inputs(tmp_path)
    body = json.loads(policy.read_bytes())
    body["policy_id" if case == "wrong id" else "status"] = "wrong"
    json_file(policy, body)
    plan, output = plan_for(tmp_path, fetched, parse_path, policy, non_market)
    result = invoke(plan)
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "invalid policy"
    assert not output.exists()


def test_policy_non_market_digest_mismatch_refuses(tmp_path: Path) -> None:
    fetched, parse_path, policy, non_market = assembled_inputs(tmp_path)
    body = json.loads(policy.read_bytes())
    body["parameters"]["D3_evidence"]["non_market_sha256"] = "b" * 64
    json_file(policy, body)
    plan, output = plan_for(tmp_path, fetched, parse_path, policy, non_market)
    result = invoke(plan)
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "invalid policy"
    assert not output.exists()


@pytest.mark.parametrize(
    "case",
    ["missing key", "extra key", "wrong source"],
    ids=["missing field", "extra field", "source value"],
)
def test_invalid_non_market_refuses(tmp_path: Path, case: str) -> None:
    fetched, parse_path, policy, non_market = assembled_inputs(tmp_path)
    body = json.loads(non_market.read_bytes())
    if case == "missing key":
        body.pop("freshness")
    elif case == "extra key":
        body["other"] = []
    else:
        body["source"] = "other"
    json_file(non_market, body)
    plan, output = plan_for(tmp_path, fetched, parse_path, policy, non_market)
    result = invoke(plan)
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "invalid non-market evidence"
    assert not output.exists()


def test_source_has_no_network_or_process_imports() -> None:
    tree = ast.parse(SCRIPT.read_text())
    forbidden = {
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
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported.isdisjoint(forbidden)


def test_non_mock_manifest_refuses_with_parser_reason(tmp_path: Path) -> None:
    fetched, parse_path, policy, non_market = assembled_inputs(tmp_path)
    manifest_path = fetched / "MANIFEST.json"
    body = json.loads(manifest_path.read_bytes())
    body["status"] = "REAL"
    manifest_path.chmod(0o600)
    json_file(manifest_path, body)
    manifest_path.chmod(0o444)
    plan, output = plan_for(tmp_path, fetched, parse_path, policy, non_market)
    result = invoke(plan)
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "only a mock manifest is accepted"
    assert not output.exists()


def test_unreadable_manifest_refuses_with_parser_reason(tmp_path: Path) -> None:
    fetched, parse_path, policy, non_market = assembled_inputs(tmp_path)
    (fetched / "MANIFEST.json").unlink()
    plan, output = plan_for(tmp_path, fetched, parse_path, policy, non_market)
    result = invoke(plan)
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "manifest unreadable"
    assert not output.exists()


def test_swapped_object_after_verification_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetched, parse_path, policy, non_market = assembled_inputs(tmp_path)
    manifest = json.loads((fetched / "MANIFEST.json").read_bytes())
    digest = manifest["files"][0]["sha256"]
    object_path = fetched / "objects" / digest
    replacement = HELPERS.zip_blob(
        "AAAUSDT-1d-2025-03-31.zip",
        [HELPERS.row(HELPERS.TMS - 86_400_000, volume="7.00")],
    )
    original_read_bytes = Path.read_bytes

    def swap_before_read(path: Path) -> bytes:
        if path == object_path:
            object_path.chmod(0o600)
            object_path.write_bytes(replacement)
            object_path.chmod(0o444)
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", swap_before_read)
    module = load_assembler()
    plan, output = plan_for(tmp_path, fetched, parse_path, policy, non_market)
    with pytest.raises(module.Refusal, match="object changed after verification"):
        module.run(str(plan))
    assert not output.exists()


def test_markerless_object_is_refused(tmp_path: Path) -> None:
    fetched, parse_path, policy, non_market = assembled_inputs(tmp_path)
    manifest_path = fetched / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_bytes())
    row = manifest["files"][0]
    old_path = fetched / "objects" / row["sha256"]
    plain = HELPERS.zip_blob(
        "AAAUSDT-1d-2025-03-31.zip",
        [HELPERS.row(HELPERS.TMS - 86_400_000, volume="4.25")],
        comment=b"",
    )
    new_digest = hashlib.sha256(plain).hexdigest()
    old_path.rename(fetched / "objects" / new_digest)
    markerless_path = fetched / "objects" / new_digest
    markerless_path.chmod(0o600)
    markerless_path.write_bytes(plain)
    markerless_path.chmod(0o444)
    row["sha256"] = new_digest
    row["official_checksum"] = new_digest
    manifest_path.chmod(0o600)
    json_file(manifest_path, manifest)
    manifest_path.chmod(0o444)
    plan, output = plan_for(tmp_path, fetched, parse_path, policy, non_market)
    result = invoke(plan)
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "object is not a mock object"
    assert not output.exists()


def test_nonempty_output_refuses(tmp_path: Path) -> None:
    fetched, parse_path, policy, non_market = assembled_inputs(tmp_path)
    output = tmp_path / "evidence"
    output.mkdir()
    (output / "keep.txt").write_text("occupied")
    plan, _ = plan_for(tmp_path, fetched, parse_path, policy, non_market)
    result = invoke(plan)
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "output folder is not empty"
    assert (output / "keep.txt").read_text() == "occupied"


def test_unusable_coverage_is_unknown_and_keeps_identities(tmp_path: Path) -> None:
    missing = "data/spot/daily/klines/AAAUSDT/15m/AAAUSDT-15m-2025-03-31.zip"
    hourly = HELPERS.archive(
        tmp_path / "archive",
        "1h",
        "2025-03",
        HELPERS.zip_blob(
            "AAAUSDT-1h-2025-03.zip",
            [HELPERS.row(HELPERS.TMS - 3_600_000)],
        ),
        granularity="monthly",
    )
    fetched, parse_path, policy, non_market = assembled_inputs(
        tmp_path, extra_paths=[missing, hourly]
    )
    plan, output = plan_for(tmp_path, fetched, parse_path, policy, non_market)
    result = invoke(plan)
    assert result.returncode == 0, result.stdout + result.stderr
    candidate = json.loads((output / "EVIDENCE.json").read_bytes())["candidates"][0]
    series = candidate["coverage"]["15m"]
    assert series["present_in_window"] is None
    assert series["provenance"]["series_usable"] is False
    assert series["provenance"]["files"][0]["class"] == "missing"
    assert candidate["coverage"]["1H"]["present_in_window"] == 1
    assert candidate["coverage"]["1H"]["provenance"]["series_usable"] is True


def test_unusable_daily_is_unknown(tmp_path: Path) -> None:
    hourly = HELPERS.archive(
        tmp_path / "archive",
        "1h",
        "2025-03",
        HELPERS.zip_blob(
            "AAAUSDT-1h-2025-03.zip",
            [HELPERS.row(HELPERS.TMS - 3_600_000)],
        ),
        granularity="monthly",
    )
    missing_daily = "data/spot/daily/klines/AAAUSDT/1d/AAAUSDT-1d-2025-03-31.zip"
    fetched = HELPERS.fetch(tmp_path, [hourly, missing_daily])
    parse_dir = tmp_path / "parsed"
    parse_plan = {
        "plan_id": "ucpe.quant_ng.extract.v1",
        "fetch_output_dir": str(fetched),
        "cutoff_utc": T,
        "output_dir": str(parse_dir),
    }
    parse_plan_path = tmp_path / "parse-plan.json"
    json_file(parse_plan_path, parse_plan)
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(EXTRACT), str(parse_plan_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    parse_path = parse_dir / "PARSE.json"
    policy = tmp_path / "policy.json"
    non_market = tmp_path / "non-market.json"
    json_file(
        non_market,
        {
            "evidence_id": "ucpe.quant_ng.non_market_evidence.v1",
            "source": "mock",
            "exclusion_verification": [],
            "not_leveraged_verification": [],
            "freshness": [],
        },
    )
    write_policy(policy, non_market)
    plan, output = plan_for(tmp_path, fetched, parse_path, policy, non_market)
    result = invoke(plan)
    assert result.returncode == 0, result.stdout + result.stderr
    candidate = json.loads((output / "EVIDENCE.json").read_bytes())["candidates"][0]
    assert candidate["daily_quote_volume"]["bars"] is None
    assert candidate["listing"]["first_daily_bar_open_utc"] is None


def test_after_cutoff_count_does_not_change_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetched, parse_path, policy, non_market = assembled_inputs(tmp_path)
    plan_path, output = plan_for(tmp_path, fetched, parse_path, policy, non_market)
    module = load_assembler()
    original = json.loads(parse_path.read_bytes())
    changed = dict(original)
    changed["files_after_cutoff"] = 43
    derived = module._output_bytes(changed)
    monkeypatch.setattr(module._EXTRACT, "derive", lambda *_: derived)
    plan = json.loads(plan_path.read_bytes())
    parse_path.chmod(0o600)
    parse_path.write_bytes(derived)
    parse_path.chmod(0o444)
    plan["parse"]["sha256"] = sha(parse_path)
    json_file(plan_path, plan)
    assert module.run(str(plan_path))["status"] == "PASS"
    changed_evidence = json.loads((output / "EVIDENCE.json").read_bytes())

    second_plan, second_output = plan_for(
        tmp_path, fetched, parse_path, policy, non_market, outname="baseline"
    )
    baseline_parse = dict(changed)
    baseline_parse["files_after_cutoff"] = original["files_after_cutoff"]
    baseline_bytes = module._output_bytes(baseline_parse)
    baseline_path = tmp_path / "baseline-parse.json"
    baseline_path.write_bytes(baseline_bytes)
    baseline_plan = json.loads(second_plan.read_bytes())
    baseline_plan["parse"] = {"path": str(baseline_path), "sha256": sha(baseline_path)}
    json_file(second_plan, baseline_plan)
    monkeypatch.setattr(module._EXTRACT, "derive", lambda *_: baseline_bytes)
    assert module.run(str(second_plan))["status"] == "PASS"
    baseline_evidence = json.loads((second_output / "EVIDENCE.json").read_bytes())
    assert changed_evidence["candidates"] == baseline_evidence["candidates"]
