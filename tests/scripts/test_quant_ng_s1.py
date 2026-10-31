import ast
import copy
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from scripts import quant_ng_s1 as s1

HOST = "archive.example.invalid"
HERE = Path(__file__).resolve().parents[2]


def plan(source="a", **overrides):
    rulings = {
        "S1-1": "a",
        "S1-2": "a",
        "S1-3": "a",
        "S1-4": source,
        "S1-5": {"stop_evidence": "b", "stop_inconclusive": "run_only"},
        "S1-6": ["a"],
        "S1-7": "D",
        "S1-8": "a",
        "S1-9": "a",
        "S1-10": "b",
        "S1-11": "b",
        "S1-12": "n/a" if source in {"a", "b"} else "b",
        "S1-13": "n/a" if source != "d" else "a",
    }
    value = {
        "schema": "ucpe.s1_plan.v1",
        "status": "MOCK",
        "rulings": rulings,
        "host": HOST,
        "cap": {"number": 20, "m": None, "H": None, "F": None},
        "probes": ["AAAUSDT"] if source in {"a", "b", "d"} else [],
        "draw": None,
    }
    if source in {"c", "d"}:
        value["draw"] = {"kind": "every", "k": None}
    for key, val in overrides.items():
        if key == "rulings":
            rulings.update(val)
        else:
            value[key] = val
    return value


def page(
    names=(),
    *,
    host=HOST,
    capture="2026-03-01T00:00:00Z",
    header="Sun, 01 Mar 2026 00:00:00 GMT",
    p0=False,
    size=100,
):
    value = {"host": host, "capture_utc": capture, "date_header": header, "names": list(names)}
    if p0:
        value["page_size"] = size
    return value


def observation(p0=("AAAUSDT",), folders=None, **overrides):
    value = {
        "schema": "ucpe.s1_observation.v1",
        "source": "mock",
        "marker": "UCPE-MOCK-v1",
        "run_start_utc": "2026-03-01T00:00:00Z",
        "run_end_utc": "2026-03-01T00:01:00Z",
        "flags": dict.fromkeys(
            (
                "redirect",
                "non_https",
                "non_success",
                "unreadable_folder",
                "unparsable_page",
                "protected_fragment",
            ),
            False,
        ),
        "requests_used": 2,
        "p0": {"pages": [page(p0, p0=True)]},
        "p1": folders
        if folders is not None
        else {"AAAUSDT": {"pages": [page(["AAAUSDT-1d-2026-01-29.zip"])]}},
    }
    value.update(overrides)
    return value


def folder(names, *, symbol="AAAUSDT", capture="2026-03-01T00:00:00Z"):
    return {"pages": [page(names, capture=capture)]}


def test_refuses_malformed_plan_and_observation_shapes():
    p = plan()
    p["surprise"] = 1
    with pytest.raises(s1.Refusal, match="malformed plan: surprise"):
        s1.decide(p, observation())
    o = observation()
    o["p0"]["pages"][0]["extra"] = 1
    with pytest.raises(s1.Refusal, match="malformed observation: extra"):
        s1.decide(plan(), o)
    p = plan()
    del p["probes"]
    with pytest.raises(s1.Refusal, match="malformed plan: probes"):
        s1.decide(p, observation())
    o = observation()
    del o["flags"]
    with pytest.raises(s1.Refusal, match="malformed observation: flags"):
        s1.decide(plan(), o)


def test_empty_p0_is_an_early_run_stop_for_every_source_and_applicable_ruling():
    for source in "abcd":
        c3_options = ("n/a",) if source in "ab" else ("a", "b")
        c13_options = ("n/a",) if source != "d" else ("a", "b")
        for absence in ("a", "b"):
            for c3 in c3_options:
                for c13 in c13_options:
                    p = plan(
                        source,
                        rulings={
                            "S1-8": absence,
                            "S1-12": c3,
                            "S1-13": c13,
                        },
                    )
                    o = observation(
                        ["BTCUSDT", "ETHUSDT"],
                        folders={"AAAUSDT": folder(["malformed but not evaluated"])},
                    )
                    out = s1.decide(p, o)
                    assert out["run_outcome"] == "STOP-inconclusive"
                    expected_stops = ["empty P0"]
                    if source == "c":
                        expected_stops.append("K = 0")
                        expected_stops.append("unexpected folder")
                    if source == "d" and c13 == "b":
                        expected_stops.append("empty (c) part")
                    assert out["run_stops"] == expected_stops
                    assert out["probes"] == []
                    assert out["K"] == (0 if source == "c" else len(p["probes"]))
                    assert out["cap"] == 20


def test_empty_p0_and_redirect_collect_both_stops_with_normal_result_shape():
    p = plan()
    o = observation(["BTCUSDT", "ETHUSDT"])
    o["flags"]["redirect"] = True

    out = s1.decide(p, o)
    normal_result = s1.decide(plan(), observation())

    assert out["run_stops"] == ["redirect", "empty P0"]
    assert set(out) == set(normal_result)


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda p: p["rulings"].update({"S1-6": ["b"]}), "malformed plan: S1-6"),
        (lambda p: p["rulings"].update({"S1-7": []}), "malformed plan: S1-7"),
        (lambda p: p.update({"probes": ["bad-symbol!"]}), "malformed plan: probes"),
        (lambda p: p.update({"probes": ["AAAUSDT", "AAAUSDT"]}), "malformed plan: probes"),
        (lambda p: p.update({"probes": []}), "malformed plan: probes"),
        (lambda p: p.update({"draw": {"kind": "every", "k": 1}}), "malformed plan: draw"),
        (
            lambda p: (
                p["rulings"].update({"S1-4": "c", "S1-12": "b"}),
                p.update({"probes": [], "draw": {"kind": "sorted_first_k", "k": 0}}),
            ),
            "malformed plan: draw.k",
        ),
        (lambda p: p["cap"].update({"number": True}), "malformed plan: cap.number"),
    ],
    ids=[
        "s1_6",
        "s1_7",
        "symbol_format",
        "duplicate_probe",
        "probe_source_shape",
        "draw_shape",
        "draw_k",
        "cap_bool",
    ],
)
def test_refuses_invalid_plan_values(change, expected):
    p = plan()
    change(p)
    with pytest.raises(s1.Refusal, match=expected):
        s1.decide(p, observation())


def test_refuses_non_mock_observation_host():
    obs = observation()
    obs["p0"]["pages"][0]["host"] = "real.example.com"
    with pytest.raises(s1.Refusal, match="host must be a MOCK host"):
        s1.decide(plan(), obs)


def test_owner_ruled_requires_allowlist_digest_and_run_path(tmp_path, monkeypatch):
    p = plan()
    p["status"] = "OWNER_RULED"
    assert not s1.OWNER_RULED_S1_PLAN_SHA256
    with pytest.raises(s1.Refusal, match="plan not owner-ruled"):
        plan_path = tmp_path / "plan.json"
        obs_path = tmp_path / "obs.json"
        plan_path.write_text(json.dumps(p))
        obs_path.write_text(json.dumps(observation()))
        s1.run(plan_path, hashlib.sha256(plan_path.read_bytes()).hexdigest(), obs_path)
    with pytest.raises(s1.Refusal, match="owner-ruled plans are decided only through run"):
        s1.decide(p, observation())

    plan_path = tmp_path / "plan.json"
    obs_path = tmp_path / "obs.json"
    plan_path.write_text(json.dumps(p))
    obs_path.write_text(json.dumps(observation()))
    digest = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    monkeypatch.setattr(s1, "OWNER_RULED_S1_PLAN_SHA256", frozenset({digest}))
    assert s1.run(plan_path, digest, obs_path)["schema"] == "ucpe.s1_decision.v1"


@pytest.mark.parametrize(
    ("p", "message"),
    [
        (plan(rulings={"S1-1": "b"}), r"S1-1 \(b\): no run is authorized"),
        (plan(rulings={"S1-2": "c"}), r"S1-2 \(c\): no host, no run"),
        (plan(host="real.example.com"), "host must be a MOCK host"),
        (plan(probes=["BTCUSDT"]), "BTCUSDT and ETHUSDT are never probed"),
        (plan(rulings={"S1-12": "a"}), "malformed plan: S1-12"),
        (plan("c", rulings={"S1-12": "n/a"}), "malformed plan: S1-12"),
        (plan("d", rulings={"S1-13": "n/a"}), "malformed plan: S1-13"),
    ],
    ids=[
        "s1_1_b",
        "s1_2_c",
        "real_host",
        "protected_probe",
        "s1_12_a_n_a_wrong",
        "s1_12_required",
        "s1_13_n_a_wrong",
    ],
)
def test_plan_refusals(p, message):
    with pytest.raises(s1.Refusal, match=message):
        s1.decide(p, observation())


def test_run_refuses_digest_mismatch(tmp_path):
    p, o = tmp_path / "plan.json", tmp_path / "obs.json"
    p.write_text(json.dumps(plan()))
    o.write_text(json.dumps(observation()))
    with pytest.raises(s1.Refusal, match="plan digest mismatch"):
        s1.run(p, "0" * 64, o)


@pytest.mark.parametrize(
    ("plan_json", "observation_json", "message"),
    [
        (
            '{"schema":"first","schema":"second"}',
            json.dumps(observation()),
            "malformed plan: duplicate key",
        ),
        (
            json.dumps(plan()),
            '{"source":"mock","source":"mock"}',
            "malformed observation: duplicate key",
        ),
        (
            json.dumps(plan()),
            '{"schema":"ucpe.s1_observation.v1","source":"mock","marker":"UCPE-MOCK-v1",'
            '"run_start_utc":null,"run_end_utc":null,"flags":{"redirect":false,"redirect":false}}',
            "malformed observation: duplicate key",
        ),
    ],
    ids=["plan_top_level", "observation_top_level", "observation_nested"],
)
def test_run_rejects_duplicate_json_keys(tmp_path, plan_json, observation_json, message):
    p, o = tmp_path / "plan.json", tmp_path / "obs.json"
    p.write_text(plan_json)
    o.write_text(observation_json)
    with pytest.raises(s1.Refusal, match=message):
        s1.run(p, hashlib.sha256(p.read_bytes()).hexdigest(), o)


@pytest.mark.parametrize(
    ("input_file", "content"),
    [
        ("plan", None),
        ("observation", None),
        ("plan", b"\xff"),
        ("observation", b"\xff"),
    ],
    ids=["missing_plan", "missing_observation", "invalid_utf8_plan", "invalid_utf8_observation"],
)
def test_main_refuses_unreadable_inputs(tmp_path, capsys, input_file, content):
    p, o = tmp_path / "plan.json", tmp_path / "obs.json"
    p.write_text(json.dumps(plan()))
    o.write_text(json.dumps(observation()))
    target = p if input_file == "plan" else o
    if content is None:
        target.unlink()
    else:
        target.write_bytes(content)
    digest = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "0" * 64

    assert s1.main([str(p), digest, str(o)]) == 2
    assert capsys.readouterr().err.startswith("REFUSED: unreadable input")


@pytest.mark.parametrize(
    "field,value", [("source", "live"), ("marker", "other")], ids=["source", "marker"]
)
def test_refuses_non_mock_observation(field, value):
    obs = observation()
    obs[field] = value
    with pytest.raises(s1.Refusal, match="observation is not MOCK"):
        s1.decide(plan(), obs)


def test_refuses_malformed_instant():
    obs = observation()
    obs["p0"]["pages"][0]["capture_utc"] = "2026-02-30T00:00:00Z"
    with pytest.raises(s1.Refusal, match="malformed instant"):
        s1.decide(plan(), obs)


@pytest.mark.parametrize(
    "stop",
    [
        "redirect",
        "non_https",
        "non_success",
        "unreadable_folder",
        "unparsable_page",
        "protected_fragment",
        "cap reached",
        "duplicate name",
        "host mismatch",
        "unreadable clock",
        "unexpected folder",
        "unreadable folder",
        "form fault",
    ],
    ids=[
        "redirect",
        "non_https",
        "non_success",
        "unreadable_flag",
        "unparsable_page",
        "protected_fragment",
        "cap",
        "duplicate",
        "host_mismatch",
        "clock_capture",
        "unexpected_folder",
        "missing_folder",
        "form_fault",
    ],
)
def test_every_run_level_stop_omits_probe_outcomes(stop):
    p, obs = plan(), observation()
    if stop in s1._FLAGS:
        obs["flags"][stop] = True
    elif stop == "cap reached":
        obs["requests_used"] = 21
    elif stop == "duplicate name":
        obs["p0"]["pages"][0]["names"].append("AAAUSDT")
    elif stop == "host mismatch":
        obs["p0"]["pages"][0]["host"] = "wrong.invalid"
    elif stop == "unreadable clock":
        obs["p0"]["pages"][0]["capture_utc"] = None
    elif stop == "unexpected folder":
        obs["p1"]["OTHER"] = folder([])
    elif stop == "unreadable folder":
        obs["p1"] = {}
    elif stop == "form fault":
        obs["p1"]["AAAUSDT"] = folder(["bad-name"])
        p["rulings"]["S1-10"] = "a"
    result = s1.decide(p, obs)
    assert result["run_outcome"] == "STOP-inconclusive"
    assert not result["probes"]
    expected_stop = {
        "non_https": "non-HTTPS URL",
        "non_success": "non-success response",
        "unreadable_folder": "unreadable folder",
        "unparsable_page": "unparsable page",
        "protected_fragment": "protected fragment",
    }.get(stop, stop)
    assert expected_stop in result["run_stops"]


@pytest.mark.parametrize(
    ("form_level", "run_stop"), [("a", True), ("b", False)],
    ids=["run_stop", "probe_inconclusive"],
)
def test_repeated_name_within_p1_folder_is_form_fault(form_level, run_stop):
    p = plan(rulings={"S1-9": "a", "S1-10": form_level})
    repeated = "AAAUSDT-1d-2026-01-29.zip"
    obs = observation(folders={"AAAUSDT": folder([repeated, repeated])})

    result = s1.decide(p, obs)

    if run_stop:
        assert result["run_outcome"] == "STOP-inconclusive"
        assert result["run_stops"] == ["form fault"]
        assert result["probes"] == []
    else:
        assert result["probes"][0]["outcome"] == "inconclusive"
        assert result["probes"][0]["reason"] == "form fault"


@pytest.mark.parametrize(
    ("selection", "observation_change"),
    [
        (["a", "b"], lambda o: o["p0"]["pages"][0].update({"date_header": None})),
        (["a", "c"], lambda o: o.update({"run_start_utc": None})),
    ],
    ids=["date_header_missing", "run_instant_missing"],
)
def test_s1_6_clock_witness_variants_stop(selection, observation_change):
    p = plan(rulings={"S1-6": selection})
    o = observation()
    observation_change(o)
    result = s1.decide(p, o)
    assert result["run_outcome"] == "STOP-inconclusive"
    assert result["run_stops"] == ["unreadable clock"]
    assert result["probes"] == []


@pytest.mark.parametrize(
    ("reading", "delta", "passes"),
    [
        ("D", 30, False),
        ("D", 31, True),
        ("D", 32, True),
        ("D+1", 30, False),
        ("D+1", 31, False),
        ("D+1", 32, True),
    ],
    ids=["D_30", "D_31", "D_32", "D_plus_1_30", "D_plus_1_31", "D_plus_1_32"],
)
def test_threshold_boundaries(reading, delta, passes):
    p = plan(rulings={"S1-7": reading})
    day = date(2026, 3, 1) - timedelta(days=delta)
    obs = observation(folders={"AAAUSDT": folder([f"AAAUSDT-1d-{day:%Y-%m-%d}.zip"])})
    result = s1.decide(p, obs)
    assert (result["probes"][0]["outcome"] == "PASS") is passes
    assert result["probes"][0]["delta"] == delta


def test_capture_date_is_earliest_across_p1_pages():
    p = plan(rulings={"S1-7": "D+1"})
    obs = observation(
        folders={
            "AAAUSDT": {
                "pages": [
                    page(["AAAUSDT-1d-2026-01-29.zip"], capture="2026-03-01T00:00:00Z"),
                    page([], capture="2026-03-02T00:00:00Z"),
                ]
            }
        }
    )

    row = s1.decide(p, obs)["probes"][0]

    assert row["C"] == "2026-03-01"
    assert row["delta"] == 31
    assert row["outcome"] == "inconclusive"


def test_latest_counted_date_is_used_for_d_x():
    obs = observation(
        folders={
            "AAAUSDT": folder(
                ["AAAUSDT-1d-2026-01-01.zip", "AAAUSDT-1d-2026-02-28.zip"]
            )
        }
    )

    row = s1.decide(plan(), obs)["probes"][0]

    assert row["D"] == "2026-02-28"
    assert row["delta"] == 1
    assert row["outcome"] == "inconclusive"


@pytest.mark.parametrize(
    ("absence", "pairing", "fault_level", "names", "expected", "reason"),
    [
        ("a", "a", "b", [], "inconclusive", "absent from P0"),
        ("b", "a", "b", [], "STOP-evidence", "absent from P0"),
        ("a", "a", "b", ["AAAUSDT-1d-2026-01-29.zip"], "PASS", "delta meets threshold"),
        ("a", "a", "b", ["AAAUSDT-1d-2026-01-29.zip", "odd"], "inconclusive", "form fault"),
        ("a", "a", "b", ["AAAUSDT-1d-2026-01-29.zip", "odd"], "inconclusive", "form fault"),
        ("a", "a", "b", ["AAAUSDT-1d-2026-01-29.zip.CHECKSUM"], "inconclusive", "no counting name"),
        ("a", "a", "b", ["AAAUSDT-1d-2026-01-29.zip.CHECKSUM"], "inconclusive", "no counting name"),
    ],
    ids=[
        "absent_inconclusive",
        "absent_evidence",
        "counted_pass",
        "form_fault_probe",
        "noncounting_probe",
        "companion_only_s9a",
        "companion_only_s9a_repeat",
    ],
)
def test_per_probe_rows(absence, pairing, fault_level, names, expected, reason):
    p = plan(rulings={"S1-8": absence, "S1-9": pairing, "S1-10": fault_level})
    p0_names = ["BBBUSDT"] if not names else ["AAAUSDT"]
    folders = {} if not names else {"AAAUSDT": folder(names)}
    obs = observation(p0_names, folders=folders)
    if names and "CHECKSUM" in names[0] and pairing == "b":
        names = ["AAAUSDT-1d-2026-01-29.zip.CHECKSUM", "AAAUSDT-1d-2026-01-29.zip"]
        obs["p1"] = {"AAAUSDT": folder(names)}
    result = s1.decide(p, obs)
    assert result["probes"][0]["outcome"] == expected
    assert result["probes"][0]["reason"] == reason


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        (["AAAUSDT-1d-2026-01-29.zip"], "inconclusive"),
        (["AAAUSDT-1d-2026-01-29.zip.CHECKSUM"], "inconclusive"),
        (["AAAUSDT-1d-2026-01-29.zip", "AAAUSDT-1d-2026-01-29.zip.CHECKSUM"], "PASS"),
    ],
    ids=["zip_without_companion", "orphan_companion", "paired_zip"],
)
def test_pairing_rule(names, expected):
    p = plan(rulings={"S1-9": "b"})
    out = s1.decide(p, observation(folders={"AAAUSDT": folder(names)}))
    assert out["probes"][0]["outcome"] == expected


@pytest.mark.parametrize(
    ("source", "ruling", "names", "expected"),
    [
        ("c", "a", ["AAAUSDT"], "STOP-evidence"),
        ("c", "a", ["AAAUSDT", "BBBUSDT"], "STOP-evidence"),
        ("c", "b", ["AAAUSDT"], "STOP-inconclusive"),
        ("d", "a", ["AAAUSDT"], "STOP-inconclusive"),
    ],
    ids=["full_sweep", "full_sweep_many", "probe_only_no_c3", "d_unanimity_unreachable"],
)
def test_aggregation_and_source_reachability(source, ruling, names, expected):
    p = plan(source, rulings={"S1-11": ruling, "S1-12": "a" if source in {"c", "d"} else "n/a"})
    if source == "c" and ruling == "b":
        p["rulings"]["S1-12"] = "b"
    obs = observation(names, {s: folder([f"{s}-1d-2026-02-28.zip"]) for s in names})
    if source == "d":
        p["probes"] = ["CCCUSDT"]
        obs["p0"]["pages"][0]["names"] = ["AAAUSDT", "BBBUSDT"]
        obs["p1"]["CCCUSDT"] = folder(["CCCUSDT-1d-2026-02-28.zip"])
        obs["p1"]["BBBUSDT"] = folder([])
        p["rulings"]["S1-13"] = "a"
    result = s1.decide(p, obs)
    assert result["run_outcome"] == expected


@pytest.mark.parametrize(
    ("source", "s11", "s12", "folder_names", "form_level", "expected"),
    [
        ("c", "b", "a", ["AAAUSDT-1d-2026-02-28.zip"], "b", "STOP-evidence"),
        ("c", "b", "a", [], "b", "STOP-inconclusive"),
        ("c", "b", "a", ["bad-name"], "b", "STOP-inconclusive"),
    ],
    ids=["c3_met", "c3_no_counting_name", "c3_form_fault"],
)
def test_s1_12_full_sweep_requirement(source, s11, s12, folder_names, form_level, expected):
    p = plan(source, rulings={"S1-11": s11, "S1-12": s12, "S1-10": form_level})
    o = observation(folders={"AAAUSDT": folder(folder_names)})
    out = s1.decide(p, o)
    assert out["run_outcome"] == expected


@pytest.mark.parametrize("empty_rule", ["a", "b"], ids=["continue_a", "stop_empty_c_part"])
@pytest.mark.parametrize(
    "draw", [
        {"kind": "sorted_first_k", "k": 1},
        {"kind": "every", "k": None},
    ],
    ids=["sorted_first_k", "every"],
)
def test_s1_13_empty_c_is_only_reachable_through_empty_p0(empty_rule, draw):
    """Both valid draw kinds are non-empty for non-empty P0; empty P0 now stops before S1-13."""
    p = plan("d", draw=draw, rulings={"S1-13": empty_rule})
    o = observation([], folders={"AAAUSDT": folder(["AAAUSDT-1d-2026-02-28.zip"])})
    out = s1.decide(p, o)
    assert out["run_outcome"] == "STOP-inconclusive"
    assert out["run_stops"] == ["empty P0"] + (["empty (c) part"] if empty_rule == "b" else [])
    assert out["probes"] == []


@pytest.mark.parametrize(
    ("p0_names", "folders", "s11", "expected"),
    [
        (["BBBUSDT"], {}, "a", "STOP-evidence"),
        (
            ["BBBUSDT"],
            {"BBBUSDT": folder([]), "AAAUSDT": folder([])},
            "a",
            "STOP-inconclusive",
        ),
        (
            ["BBBUSDT"],
            {"BBBUSDT": folder([]), "AAAUSDT": folder([])},
            "b",
            "STOP-evidence",
        ),
        (["AAAUSDT"], {"AAAUSDT": folder(["AAAUSDT-1d-2026-02-28.zip"])}, "b", "STOP-inconclusive"),
    ],
    ids=["all_evidence", "some_evidence_unanimity", "some_evidence_any", "no_evidence"],
)
def test_case_check_evidence_branches(p0_names, folders, s11, expected):
    probes = ["AAAUSDT", "CCCUSDT"] if p0_names == ["BBBUSDT"] and not folders else (
        ["AAAUSDT", "BBBUSDT"]
        if s11 == "a" or len(p0_names) == 1 and expected == "STOP-evidence"
        else ["AAAUSDT"]
    )
    p = plan("b", probes=probes, rulings={"S1-8": "b", "S1-11": s11})
    out = s1.decide(p, observation(p0_names, folders))
    assert out["run_outcome"] == expected


def test_s1_11_aggregation_differs_with_absent_and_present_recent_probes():
    outcomes = {}
    for rule in ("a", "b"):
        p = plan(
            "b",
            probes=["AAAUSDT", "BBBUSDT"],
            rulings={"S1-8": "b", "S1-11": rule},
        )
        o = observation(
            ["BBBUSDT"],
            {"BBBUSDT": folder(["BBBUSDT-1d-2026-02-28.zip"])},
        )
        out = s1.decide(p, o)
        outcomes[rule] = out["run_outcome"]
        assert [row["outcome"] for row in out["probes"]] == [
            "STOP-evidence",
            "inconclusive",
        ]
    assert outcomes == {"a": "STOP-inconclusive", "b": "STOP-evidence"}


@pytest.mark.parametrize(
    ("mode", "pages", "page_size", "expected"),
    [
        ("a", 1, 100, 7),
        ("c", 1, 100, 7),
        ("b", 1, 100, 10),
        ("b", 2, 1, 5),
        ("b", 2, 1, 4),
    ],
    ids=["cap_a", "cap_c", "cap_b_single_page_h", "cap_b_formula", "cap_b_minimum"],
)
def test_caps(mode, pages, page_size, expected):
    p = plan(rulings={"S1-3": mode})
    if mode == "b":
        p["cap"] = {"number": None, "m": 1, "H": expected if expected == 4 else 10, "F": 1}
    else:
        p["cap"]["number"] = 7
    obs = observation()
    obs["p0"]["pages"] *= pages
    for page0 in obs["p0"]["pages"]:
        page0["page_size"] = page_size
    if expected in {4, 5}:
        obs["p0"]["pages"] = [page(["AAAUSDT"], p0=True, size=1), page(["BBB"], p0=True, size=1)]
    obs["requests_used"] = expected
    result = s1.decide(p, obs)
    assert result["cap"] == expected
    assert "cap reached" not in result["run_stops"]
    obs["requests_used"] = expected + 1
    assert "cap reached" in s1.decide(p, obs)["run_stops"]


@pytest.mark.parametrize(
    ("outcome", "choice", "expected"),
    [
        ("PASS", "a", "pass: some delisted symbols are kept; never proves complete survivorship"),
        ("STOP-evidence", "a", "route ends"),
        ("STOP-evidence", "b", "survivor panel only; no historical-universe claim"),
        ("STOP-inconclusive", "a", "route ends"),
        ("STOP-inconclusive", "b", "survivor panel only; no historical-universe claim"),
        ("STOP-inconclusive", "run_only", "this run only; a new plan may be authorized"),
    ],
    ids=[
        "pass",
        "evidence_ends",
        "evidence_survivor_panel",
        "inconclusive_consume_route_ends",
        "inconclusive_consume_survivor_panel",
        "inconclusive_run_only",
    ],
)
def test_consequences(outcome, choice, expected):
    ruling = {
        "stop_evidence": choice,
        "stop_inconclusive": "consume" if choice in {"a", "b"} else choice,
    }
    assert s1._consequence(outcome, ruling) == expected


def test_protected_names_are_dropped_and_counted():
    out = s1.decide(plan(), observation(["AAAUSDT", "BTCUSDT", "ETHUSDT"]))
    assert out["dropped"] == 2
    assert "BTCUSDT" not in json.dumps(out)


def test_import_allowlist_and_main_cli(tmp_path, capsys):
    source = (HERE / "scripts/quant_ng_s1.py").read_text()
    tree = ast.parse(source)
    imports = {
        node.names[0].name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
    }
    imports |= {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert imports <= {
        "__future__",
        "argparse",
        "hashlib",
        "json",
        "re",
        "sys",
        "datetime",
        "pathlib",
        "typing",
    }
    p, o = tmp_path / "p.json", tmp_path / "o.json"
    encoded = json.dumps(plan()).encode()
    p.write_bytes(encoded)
    o.write_text(json.dumps(observation()))
    assert s1.main([str(p), hashlib.sha256(encoded).hexdigest(), str(o)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["schema"] == "ucpe.s1_decision.v1"
    assert s1.main([str(p), "0" * 64, str(o)]) == 2
    assert capsys.readouterr().err.startswith("REFUSED:")


def test_decision_is_deterministic_and_does_not_mutate_inputs():
    p, o = plan(), observation()
    before = copy.deepcopy((p, o))
    first = s1.decide(p, o)
    assert first == s1.decide(p, o)
    assert (p, o) == before


def _independently_passing_probes(p, o):
    p0_names = {
        name
        for source_page in o["p0"]["pages"]
        for name in source_page["names"]
        if name not in {"BTCUSDT", "ETHUSDT"}
    }
    probes = list(p["probes"])
    if p["rulings"]["S1-4"] in {"c", "d"}:
        draw = sorted(p0_names)
        if p["draw"]["kind"] == "sorted_first_k":
            draw = draw[: p["draw"]["k"]]
        for name in draw:
            if name not in probes:
                probes.append(name)
    theta = 31 if p["rulings"]["S1-7"] == "D" else 32
    passing = set()
    for symbol in probes:
        if symbol not in p0_names or symbol not in o["p1"]:
            continue
        pages = o["p1"][symbol]["pages"]
        names = [name for source_page in pages for name in source_page["names"]]
        fault = len(names) != len(set(names))
        counted, companions = [], []
        for name in names:
            pattern = rf"{re.escape(symbol)}-1d-(\d{{4}})-(\d{{2}})-(\d{{2}})\.zip(\.CHECKSUM)?"
            match = re.fullmatch(pattern, name)
            if not match:
                fault = True
                continue
            try:
                counted_date = date(*(int(part) for part in match.groups()[:3]))
            except ValueError:
                fault = True
                continue
            (companions if match.group(4) else counted).append(counted_date)
        if p["rulings"]["S1-9"] == "b":
            if any(
                counted.count(day) != companions.count(day)
                for day in set(counted + companions)
            ):
                fault = True
        if fault or not counted:
            continue
        latest_counted = max(counted)
        earliest_capture = min(
            datetime.strptime(page["capture_utc"], "%Y-%m-%dT%H:%M:%SZ") for page in pages
        )
        delta = (earliest_capture.date() - latest_counted).days
        if delta >= theta:
            passing.add(symbol)
    return passing


def test_exhaustive_ruling_product_invariants():
    scenarios = [
        ("old", ["AAAUSDT"], {"AAAUSDT": folder(["AAAUSDT-1d-2026-01-29.zip"])}),
        ("recent", ["AAAUSDT"], {"AAAUSDT": folder(["AAAUSDT-1d-2026-02-28.zip"])}),
        ("absent", ["BBBUSDT"], {}),
        ("fault", ["AAAUSDT"], {"AAAUSDT": folder(["odd"])}),
        ("companion", ["AAAUSDT"], {"AAAUSDT": folder(["AAAUSDT-1d-2026-01-29.zip.CHECKSUM"])}),
        ("flag", ["AAAUSDT"], {"AAAUSDT": folder(["AAAUSDT-1d-2026-01-29.zip"])}),
        (
            "two_probe_mixed",
            ["BBBUSDT"],
            {"BBBUSDT": folder(["BBBUSDT-1d-2026-02-28.zip"])},
        ),
    ]
    for source in "abcd":
        for threshold in ("D", "D+1"):
            for absence in ("a", "b"):
                for pairing in ("a", "b"):
                    for form_level in ("a", "b"):
                        for aggregation in ("a", "b"):
                            for c3 in ("n/a",) if source in "ab" else ("a", "b"):
                                for empty_c in ("n/a",) if source != "d" else ("a", "b"):
                                    for scenario, p0names, folders in scenarios:
                                        p = plan(
                                            source,
                                            rulings={
                                                "S1-7": threshold,
                                                "S1-8": absence,
                                                "S1-9": pairing,
                                                "S1-10": form_level,
                                                "S1-11": aggregation,
                                                "S1-12": c3,
                                                "S1-13": empty_c,
                                            },
                                        )
                                        if source in "cd":
                                            p["draw"] = {"kind": "every", "k": None}
                                        if source in "bd":
                                            p["probes"] = ["AAAUSDT"]
                                        if scenario == "two_probe_mixed" and source in "abd":
                                            p["probes"] = ["AAAUSDT", "BBBUSDT"]
                                        o = observation(p0names, copy.deepcopy(folders))
                                        if scenario == "flag":
                                            o["flags"]["redirect"] = True
                                        original = copy.deepcopy((p, o))
                                        out = s1.decide(p, o)
                                        assert out["run_outcome"] in {
                                            "PASS",
                                            "STOP-evidence",
                                            "STOP-inconclusive",
                                        }
                                        assert (p, o) == original
                                        assert out == s1.decide(p, o)
                                        if out["run_stops"]:
                                            assert (
                                                out["run_outcome"] == "STOP-inconclusive"
                                                and not out["probes"]
                                            )
                                        else:
                                            assert (out["run_outcome"] == "PASS") == bool(
                                                _independently_passing_probes(p, o)
                                            )
                                        if absence == "a":
                                            assert all(
                                                row["outcome"] != "STOP-evidence"
                                                for row in out["probes"]
                                            )
                                        assert all(
                                            row["symbol"] in p["probes"] or row["symbol"] in p0names
                                            for row in out["probes"]
                                        )
                                        assert all(
                                            row["outcome"] != "PASS" or row["symbol"] in p0names
                                            for row in out["probes"]
                                        )
                                        assert not any(
                                            symbol in json.dumps(out)
                                            for symbol in ("BTCUSDT", "ETHUSDT")
                                        )
