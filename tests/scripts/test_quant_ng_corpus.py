"""Synthetic-only contract tests for the dormant universe snapshot builder."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/quant_ng_corpus.py"
RULE = ROOT / "ops/quant_ng/UNIVERSE_RULE_v1.json"
T = datetime(2025, 6, 1, tzinfo=UTC)
T_STR = T.strftime("%Y-%m-%dT%H:%M:%SZ")


def module():
    spec = importlib.util.spec_from_file_location("quant_ng_corpus_test", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    was = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = was
    return mod


def prov():
    digest = "a" * 64
    return {
        "source": "synthetic",
        "sha256": digest,
        "official_checksum": digest,
        "available_from_utc": "2025-01-01T00:00:00Z",
        "revisions": [{"sha256": digest, "available_from_utc": "2025-01-01T00:00:00Z"}],
        "revision_history_complete": True,
    }


def _file_provenance(**changes):
    entry = {**prov(), "path": "AAAUSDT-1d-2025-03-31.zip", "class": "ok"}
    entry.update(changes)
    return entry


def _series_provenance(files=None, **changes):
    raw = {
        "files": [_file_provenance()] if files is None else files,
        "series_usable": True,
        "series_reason": "verified",
        "policy_fields": "complete",
    }
    raw.update(changes)
    return raw


def test_assembler_provenance_with_pending_policy_fields_is_unusable(tmp_path: Path):
    mod = module()
    bundle, _ = _assembled_bundle(tmp_path)
    raw = bundle["candidates"][0]["listing"]["provenance"]
    assert raw["policy_fields"] == "PENDING_CHANGE_3"
    assert set(raw["files"][0]) == {"path", "sha256", "official_checksum", "class"}
    assert mod._prov(raw, T)[0] is False


def test_full_file_provenance_uses_single_record_validation():
    mod = module()
    raw = _series_provenance()
    assert mod._prov(raw, T) == (True, {"files": [{
        "sha256": "a" * 64,
        "available_from_utc": "2025-01-01T00:00:00Z",
    }]})

    bad_class = _series_provenance(files=[_file_provenance(**{"class": "bad"})])
    assert mod._prov(bad_class, T)[0] is False

    mismatched = _file_provenance(official_checksum="b" * 64)
    assert mod._prov(_series_provenance(files=[mismatched]), T)[0] is False


def test_series_provenance_requires_true_and_exact_series_keys():
    mod = module()
    assert mod._prov(_series_provenance(series_usable=False), T)[0] is False
    assert mod._prov(_series_provenance(extra=True), T)[0] is False
    missing = _series_provenance()
    del missing["series_reason"]
    assert mod._prov(missing, T)[0] is False


@pytest.mark.parametrize(
    "at,expected",
    [("2025-03-31T23:59:59Z", False), ("2025-04-01T00:00:00Z", True)],
)
def test_file_bound_revision_is_validated_at_cutoff(at, expected):
    mod = module()
    held, old = "a" * 64, "b" * 64
    entry = _file_provenance(
        available_from_utc="2025-04-01T00:00:00Z",
        revisions=[
            {"sha256": old, "available_before_utc": "2025-04-01T00:00:00Z"},
            {"sha256": held, "available_from_utc": "2025-04-01T00:00:00Z"},
        ],
    )
    assert mod._prov(_series_provenance(files=[entry]), mod.instant(at))[0] is expected


def test_prov_file_branch_does_not_infer_availability_from_period():
    mod = module()
    source = __import__("inspect").getsource(mod._prov)
    assert "period +" not in source
    assert '"T00:00:00Z"' not in source


@pytest.mark.parametrize(
    "at,expected",
    [
        ("2025-03-31T23:59:59Z", False),
        ("2025-04-01T00:00:00Z", True),
        ("2025-04-02T00:00:00Z", True),
    ],
)
def test_bound_revision_is_current_only_from_replacement_instant(at, expected):
    mod = module()
    old, held = "b" * 64, "a" * 64
    raw = prov()
    raw["sha256"] = raw["official_checksum"] = held
    raw["available_from_utc"] = "2025-04-01T00:00:00Z"
    raw["revisions"] = [
        {"sha256": old, "available_before_utc": "2025-04-01T00:00:00Z"},
        {"sha256": held, "available_from_utc": "2025-04-01T00:00:00Z"},
    ]
    assert mod._prov(raw, mod.instant(at))[0] is expected


@pytest.mark.parametrize(
    "held,at",
    [
        ("a" * 64, "2025-03-31T23:59:59Z"),
        ("a" * 64, "2025-04-01T00:00:00Z"),
        ("a" * 64, "2025-04-02T00:00:00Z"),
        ("b" * 64, "2025-03-31T23:59:59Z"),
        ("b" * 64, "2025-04-01T00:00:00Z"),
        ("b" * 64, "2025-04-02T00:00:00Z"),
    ],
)
def test_bound_revision_does_not_match_an_unlisted_held_copy(held, at):
    mod = module()
    raw = prov()
    raw["sha256"] = raw["official_checksum"] = held
    raw["revisions"] = [
        {"sha256": "a" * 64, "available_before_utc": "2025-04-01T00:00:00Z"},
        {"sha256": "d" * 64, "available_from_utc": "2025-04-01T00:00:00Z"},
    ]
    assert mod._prov(raw, mod.instant(at))[0] is False


def _assembled_bundle(tmp_path: Path):
    helper_spec = importlib.util.spec_from_file_location(
        "assemble_test_helpers_for_corpus", ROOT / "tests/scripts/test_quant_ng_assemble.py"
    )
    assert helper_spec and helper_spec.loader
    helpers = importlib.util.module_from_spec(helper_spec)
    helper_spec.loader.exec_module(helpers)
    fetched, parse_path, policy, non_market_path = helpers.assembled_inputs(tmp_path)
    assembler = module()._ASSEMBLE
    parse_raw = parse_path.read_bytes()
    parse = assembler._json(parse_raw)
    non_market = assembler._json(non_market_path.read_bytes())
    bundle = assembler.evidence(
        parse,
        fetch_dir=fetched,
        parse_sha256=hashlib.sha256(parse_raw).hexdigest(),
        policy_path=policy,
        policy_sha256=hashlib.sha256(policy.read_bytes()).hexdigest(),
        non_market_path=non_market_path,
        non_market_sha256=hashlib.sha256(non_market_path.read_bytes()).hexdigest(),
        non_market=non_market,
    )
    return bundle, non_market_path


def test_derived_evidence_is_reproducible(tmp_path: Path):
    mod = module()
    bundle, _ = _assembled_bundle(tmp_path)
    mod.verify_derived(bundle)


def test_edited_market_field_is_not_derived_from_parse(tmp_path: Path):
    mod = module()
    bundle, _ = _assembled_bundle(tmp_path)
    bundle["candidates"][0]["lineage"] = "AAA"
    with pytest.raises(mod.Refusal, match="^evidence not derived from parse$"):
        mod.verify_derived(bundle)


def test_edited_non_market_field_is_not_derived_from_parse(tmp_path: Path):
    mod = module()
    bundle, _ = _assembled_bundle(tmp_path)
    bundle["freshness"].append({"edited": True})
    with pytest.raises(mod.Refusal, match="^evidence not derived from parse$"):
        mod.verify_derived(bundle)


def test_replaced_non_market_file_is_not_bound(tmp_path: Path):
    mod = module()
    bundle, non_market_path = _assembled_bundle(tmp_path)
    non_market_path.chmod(0o600)
    non_market_path.write_text("{}", encoding="utf-8")
    with pytest.raises(mod.Refusal, match="^evidence not bound$"):
        mod.verify_derived(bundle)


def test_edited_parse_with_its_new_digest_is_not_derived(tmp_path: Path):
    mod = module()
    bundle, _ = _assembled_bundle(tmp_path)
    parse_raw = mod._ASSEMBLE._EXTRACT.derive(
        Path(bundle["binding"]["fetch_output_dir"]), mod.instant(bundle["binding"]["cutoff_utc"])
    )
    edited = json.loads(parse_raw)
    edited["symbols"][0]["daily"]["bars"][0]["quote_volume"] = "99"
    edited_raw = (
        json.dumps(edited, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        + b"\n"
    )
    bundle["binding"]["parse_sha256"] = hashlib.sha256(edited_raw).hexdigest()
    with pytest.raises(mod.Refusal, match="^parse not derived from manifest$"):
        mod.verify_derived(bundle)


@pytest.mark.parametrize("edit", ["missing", "extra"])
def test_binding_requires_exactly_its_fields(tmp_path: Path, edit):
    mod = module()
    bundle, _ = _assembled_bundle(tmp_path)
    if edit == "missing":
        del bundle["binding"]["manifest_sha256"]
    else:
        bundle["binding"]["extra"] = "value"
    with pytest.raises(mod.Refusal, match="^evidence not bound$"):
        mod.verify_derived(bundle)


def test_changed_object_keeps_the_parser_refusal_reason(tmp_path: Path):
    mod = module()
    bundle, _ = _assembled_bundle(tmp_path)
    obj_dir = Path(bundle["binding"]["fetch_output_dir"]) / "objects"
    manifest = json.loads((obj_dir.parent / "MANIFEST.json").read_bytes())
    digest = next(row["sha256"] for row in manifest["files"] if row["class"] == "ok")
    object_path = obj_dir / digest
    object_path.chmod(0o600)
    object_path.write_bytes(object_path.read_bytes() + b"changed")
    with pytest.raises(mod.Refusal, match="^object does not match the manifest$"):
        mod.verify_derived(bundle)


def candidate(symbol="XYZUSDT", base="XYZ", bars=None, coverage_counts=None):
    bars = (
        bars
        if bars is not None
        else [
            {
                "open_utc": (T - timedelta(days=d)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "quote_volume": str(d),
            }
            for d in range(90, 0, -1)
        ]
    )
    counts = coverage_counts or {"15m": 678, "1H": 678, "4H": 174}
    return {
        "symbol": symbol,
        "base": base,
        "quote": "USDT",
        "lineage": None,
        "listing": {"first_daily_bar_open_utc": "2024-01-01T00:00:00Z", "provenance": prov()},
        "daily_quote_volume": {"bars": bars, "provenance": prov()},
        "coverage": {
            tf: {"present_in_window": n, "provenance": prov()} for tf, n in counts.items()
        },
    }


def bundle(candidates=None, **changes):
    out = {
        "evidence_id": "ucpe.quant_ng.universe_evidence.v1",
        "source": "synthetic",
        "candidates": candidates if candidates is not None else [candidate()],
        "exclusion_verification": [],
        "not_leveraged_verification": [],
        "freshness": [],
    }
    out.update(changes)
    return out


def case(base: Path, *, evidence=None, plan_changes=None):
    base.mkdir(parents=True, exist_ok=True)
    ev = json.dumps(evidence or bundle(), separators=(",", ":")).encode()
    ev_path = base / "evidence.json"
    ev_path.write_bytes(ev)
    plan = {
        "plan_id": "ucpe.quant_ng.universe.v1",
        "as_of_utc": T_STR,
        "evidence": {"path": str(ev_path), "sha256": hashlib.sha256(ev).hexdigest()},
        "operating_period_start": {"utc": None, "provenance": None},
        "completeness": {"threshold": 0.9, "ruling": "SYNTHETIC_TEST_ONLY"},
        "output_dir": str(base / "out"),
    }
    if plan_changes:
        plan.update(plan_changes)
    path = base / "plan.json"
    path.write_text(json.dumps(plan, separators=(",", ":")), encoding="utf-8")
    return path, base / "out", plan


def invoke(path: Path):
    return subprocess.run(
        [sys.executable, "-I", "-B", str(SCRIPT), str(path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_valid_bundle_passes_readonly_and_deterministic(tmp_path: Path):
    """Pins run's create_readonly call, canonical serialization and stable snapshot body."""
    p1, out1, _ = case(tmp_path / "alpha")
    p2, out2, _ = case(tmp_path / "beta")
    a = invoke(p1)
    b = invoke(p2)
    assert a.returncode == b.returncode == 0
    assert json.loads(a.stdout)["status"] == "PASS"
    data = (out1 / "UNIVERSE_SNAPSHOT.json").read_bytes()
    assert data == (out2 / "UNIVERSE_SNAPSHOT.json").read_bytes()
    assert os.stat(out1 / "UNIVERSE_SNAPSHOT.json").st_mode & 0o777 == 0o444
    assert hashlib.sha256(RULE.read_bytes()).hexdigest() == module().UNIVERSE_RULE_V1_SHA256


def test_shared_fit_safety_objects_are_identical():
    """Pins the path-discipline aliases to the fit module's own objects."""
    m = module()
    fit = sys.modules["quant_ng_fit"]
    assert m.PROTECTED is fit.PROTECTED
    assert m.FORBIDDEN_TREES is fit.FORBIDDEN_TREES


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"as_of_utc": "2025-06-01T00:00:01Z"}, "as_of_utc must be UTC midnight"),
        ({"unknown": 1}, "invalid plan"),
        (
            {"completeness": {"threshold": None, "ruling": None}},
            "completeness threshold unruled: OD-NG-7 item 7.1",
        ),
        (
            {"completeness": {"threshold": 0.9, "ruling": "OTHER"}},
            "completeness threshold requires SYNTHETIC_TEST_ONLY",
        ),
    ],
)
def test_plan_refusals_leave_no_output(tmp_path: Path, change, reason):
    """Pins run's plan validation before output creation."""
    path, output, _ = case(tmp_path / "trial", plan_changes=change)
    result = invoke(path)
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"status": "REFUSAL", "reason": reason}
    assert not output.exists()


def test_evidence_digest_mismatch_leaves_no_output(tmp_path: Path):
    """Pins run's evidence digest check."""
    path, output, plan = case(tmp_path / "trial")
    plan["evidence"]["sha256"] = "0" * 64
    path.write_text(json.dumps(plan), encoding="utf-8")
    result = invoke(path)
    assert json.loads(result.stdout)["reason"] == "evidence digest mismatch"
    assert not output.exists()


def test_spec_tamper_refused(tmp_path: Path):
    """Pins load_rule's immutable spec digest check."""
    m = module()
    copy = tmp_path / "rule.json"
    copy.write_bytes(RULE.read_bytes() + b" ")
    with pytest.raises(m.Refusal, match="rule digest mismatch"):
        m.load_rule(copy)


def test_cli_guard_is_installed_only_by_main():
    """Pins guard installation to the CLI entrypoint."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.count("install_guard(_OUTPUT_HOLDER)") == 1
    assert "def main" in text


def test_firewall_admissibility_requires_all_three_conditions():
    """Pins f3_judgment_admissible's firewall, calendar and methodology conditions."""
    fn = module().f3_judgment_admissible
    good = {"f3_firewall": "F-C", "f3_calendar_overlap": False, "methodology": {"f3_clean": True}}
    assert fn(good)
    assert not fn({**good, "f3_calendar_overlap": True})
    assert not fn({**good, "f3_firewall": "other"})


def test_whole_run_refusal_for_non_synthetic_source(tmp_path: Path):
    """Pins evidence source enforcement in _candidate_rows."""
    ev = bundle()
    ev["source"] = "exchange"
    path, output, _ = case(tmp_path / "trial", evidence=ev)
    result = invoke(path)
    assert json.loads(result.stdout)["reason"] == "source must be synthetic"
    assert not output.exists()


def test_a_listing_exactly_ninety_days_old_is_a_candidate(tmp_path: Path):
    """Pins the strict `<` of the new-listing rule: 90 days old is old enough."""
    c = candidate()
    c["listing"]["first_daily_bar_open_utc"] = (T - timedelta(days=90)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    path, out, _ = case(tmp_path / "trial", evidence=bundle([c]))
    assert invoke(path).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert snap["new_listings"] == []
    assert snap["symbols"][0]["timeframes"]["15m"]["reason"] is None


def test_new_listing_boundary_and_known_absence(tmp_path: Path):
    """Pins the spec-driven new_listing_min_age_days boundary."""
    c = candidate()
    c["listing"]["first_daily_bar_open_utc"] = (T - timedelta(days=89)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    path, out, _ = case(tmp_path / "trial", evidence=bundle([c]))
    assert invoke(path).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert snap["new_listings"] == [{"symbol": "XYZUSDT", "age_days": 89}]


def test_verified_exclusion_and_unverified_trigger(tmp_path: Path):
    """Pins B1's as-of exclusion verification and trigger handling."""
    item = {
        "base": "USDC",
        "class": "pegged",
        "valid_from_utc": "2024-01-01T00:00:00Z",
        "valid_to_utc": None,
        "provenance": prov(),
    }
    c = candidate("USDCUSDT", "USDC")
    path, out, _ = case(tmp_path / "verified", evidence=bundle([c], exclusion_verification=[item]))
    assert invoke(path).returncode == 0
    assert json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())["excluded"] == [
        {"symbol": "USDCUSDT", "class": "pegged"}
    ]
    c = candidate("XRPUPUSDT", "XRPUP")
    path, out, _ = case(tmp_path / "trigger", evidence=bundle([c]))
    assert invoke(path).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert {entry["reason"] for entry in snap["not_admitted"]} == {"exclusion_unverified"}


def test_incomplete_history_is_not_admitted_per_timeframe(tmp_path: Path):
    """Pins spec-driven per-timeframe completeness and exact reason naming."""
    counts = {"15m": 677, "1H": 678, "4H": 174}
    path, out, _ = case(tmp_path / "trial", evidence=bundle([candidate(coverage_counts=counts)]))
    plan = json.loads(path.read_text())
    plan["completeness"]["threshold"] = 0.999
    path.write_text(json.dumps(plan, separators=(",", ":")))
    assert invoke(path).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert snap["members"]["15m"] == {"status": "DECIDED", "symbols": []}
    assert {x["reason"] for x in snap["not_admitted"]} == {"incomplete_15m"}


def test_known_freshness_contradiction_is_refused(tmp_path: Path):
    """Pins refusal of fresh evidence for a cell ruled known_not_fresh."""
    c = candidate("ADAUSDT", "ADA")
    fresh = {
        "symbol": "ADAUSDT",
        "timeframe": "4H",
        "span_start_utc": "2025-05-01T00:00:00Z",
        "span_end_utc": "2025-08-30T00:00:00Z",
        "state": "fresh",
        "provenance": prov(),
    }
    path, out, _ = case(tmp_path / "trial", evidence=bundle([c], freshness=[fresh]))
    result = invoke(path)
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason"] == "freshness contradicts known_not_fresh"
    assert not out.exists()


def test_freshness_known_four_hour_cell_is_unspent_unproven(tmp_path: Path):
    """Pins the R5 known freshness state for the synthetic known cell."""
    c = candidate("ADAUSDT", "ADA")
    path, out, _ = case(tmp_path / "trial", evidence=bundle([c]))
    plan = json.loads(path.read_text())
    plan["operating_period_start"] = {
        "utc": "2025-09-01T00:00:00Z",
        "provenance": "synthetic ruling",
    }
    path.write_text(json.dumps(plan, separators=(",", ":")))
    assert invoke(path).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert snap["symbols"][0]["freshness"]["4H"] == "unspent_unproven"


def test_firewall_boundary_uses_governed_span_end(tmp_path: Path):
    """Pins the strict governed-span comparison against the spec calendar boundary."""
    late = datetime(2026, 6, 23, tzinfo=UTC)
    bars = [
        {"open_utc": (late - timedelta(days=d)).strftime("%Y-%m-%dT%H:%M:%SZ"), "quote_volume": "2"}
        for d in range(90, 0, -1)
    ]
    p, out, plan = case(tmp_path / "before", evidence=bundle([candidate(bars=bars)]))
    plan["as_of_utc"] = late.strftime("%Y-%m-%dT%H:%M:%SZ")
    p.write_text(json.dumps(plan, separators=(",", ":")))
    assert invoke(p).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert snap["f3_calendar_overlap"] is False

    late += timedelta(days=1)
    bars = [
        {"open_utc": (late - timedelta(days=d)).strftime("%Y-%m-%dT%H:%M:%SZ"), "quote_volume": "2"}
        for d in range(90, 0, -1)
    ]
    p, out, plan = case(tmp_path / "after", evidence=bundle([candidate(bars=bars)]))
    plan["as_of_utc"] = late.strftime("%Y-%m-%dT%H:%M:%SZ")
    p.write_text(json.dumps(plan, separators=(",", ":")))
    assert invoke(p).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert snap["f3_calendar_overlap"] is True


def test_median_uses_present_values_and_window_includes_lower_edge(tmp_path: Path):
    """Pins the ranking interval, missing-day treatment and decimal median."""
    bars = [
        {
            "open_utc": (T - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "quote_volume": "1.0",
        },
        {
            "open_utc": (T - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "quote_volume": "2.00",
        },
        {"open_utc": (T - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"), "quote_volume": "4"},
    ]
    path, out, _ = case(
        tmp_path / "trial",
        evidence=bundle([candidate(bars=bars)]),
        plan_changes={"completeness": {"threshold": 0.03, "ruling": "SYNTHETIC_TEST_ONLY"}},
    )
    assert invoke(path).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert snap["symbols"][0]["median_daily_quote_volume"] == "2.00"


@pytest.mark.parametrize(
    "mutation",
    ["missing", "checksum", "incomplete", "held_late", "stale", "pair", "superseded", "pair_date"],
)
def test_provenance_invalid_cases_are_unknown_membership(tmp_path: Path, mutation):
    p = prov()
    if mutation == "missing":
        del p["revisions"]
    elif mutation == "checksum":
        p["official_checksum"] = "b" * 64
    elif mutation == "incomplete":
        p["revision_history_complete"] = False
    elif mutation == "held_late":
        p["available_from_utc"] = "2025-07-01T00:00:00Z"
        p["revisions"] = [{"sha256": p["sha256"], "available_from_utc": p["available_from_utc"]}]
    elif mutation == "stale":
        p["revisions"].append({"sha256": "b" * 64, "available_from_utc": "2025-07-01T00:00:00Z"})
        p["sha256"] = p["official_checksum"] = "b" * 64
        p["available_from_utc"] = "2025-07-01T00:00:00Z"
    elif mutation == "superseded":
        # The revision held is older than one already published before T, so it was not the one
        # current at T. Holding it would be reading a superseded file.
        p["revisions"].append({"sha256": "b" * 64, "available_from_utc": "2025-03-01T00:00:00Z"})
    elif mutation == "pair_date":
        # The held digest is in the history, but under a different date than the one claimed for
        # it: the held (digest, date) pair is not a published revision.
        p["available_from_utc"] = "2025-02-01T00:00:00Z"
    else:
        p["revisions"] = []
    c = candidate()
    c["listing"]["provenance"] = p
    path, out, _ = case(tmp_path / mutation, evidence=bundle([c]))
    assert invoke(path).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert snap["symbols"][0]["timeframes"]["15m"]["reason"] == "provenance_unknown"


def test_provenance_later_revision_after_cutoff_is_allowed(tmp_path: Path):
    c = candidate()
    c["listing"]["provenance"]["revisions"].append(
        {"sha256": "b" * 64, "available_from_utc": "2025-07-01T00:00:00Z"}
    )
    path, out, _ = case(tmp_path / "trial", evidence=bundle([c]))
    assert invoke(path).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert snap["symbols"][0]["timeframes"]["15m"]["reason"] is None


def test_future_verification_and_freshness_are_accepted(tmp_path: Path):
    c = candidate()
    verification = {
        "base": "XYZ",
        "class": "pegged",
        "valid_from_utc": "2025-07-01T00:00:00Z",
        "valid_to_utc": None,
        "provenance": prov(),
    }
    spent = {
        "symbol": "XYZUSDT",
        "timeframe": "15m",
        "span_start_utc": "2025-06-02T00:00:00Z",
        "span_end_utc": "2025-09-01T00:00:00Z",
        "state": "spent",
        "provenance": prov(),
    }
    path, out, plan = case(
        tmp_path / "trial",
        evidence=bundle([c], exclusion_verification=[verification], freshness=[spent]),
    )
    plan["operating_period_start"] = {"utc": "2026-01-01T00:00:00Z", "provenance": "synthetic"}
    path.write_text(json.dumps(plan))
    assert invoke(path).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert snap["symbols"][0]["freshness"]["15m"] == "spent"


def test_daily_bar_and_listing_at_cutoff_are_refused(tmp_path: Path):
    for key in ("bar", "listing"):
        c = candidate()
        if key == "bar":
            c["daily_quote_volume"]["bars"].append({"open_utc": T_STR, "quote_volume": "1"})
        else:
            c["listing"]["first_daily_bar_open_utc"] = T_STR
        path, _, _ = case(tmp_path / key, evidence=bundle([c]))
        assert json.loads(invoke(path).stdout)["reason"] in {
            "daily bar at or after T",
            "evidence date at or after T",
        }


def test_known_incompleteness_precedes_unverified_exclusion(tmp_path: Path):
    """Pins known-before-unknown: a known disqualifier is recorded ahead of an unknown one.

    USDC is on the pegged list with no verification, which alone would make it an unknown
    contender (`exclusion_unverified`); it also has 80 of 90 daily bars at the plan's 0.9
    threshold, which is a known disqualifier (`incomplete_1d`). The known reason must win, so the
    15m subset stays DECIDED. An earlier version of this test gave the symbol a full window, so it
    could not tell the two orders apart.
    """
    bars = [
        {"open_utc": (T - timedelta(days=d)).strftime("%Y-%m-%dT%H:%M:%SZ"), "quote_volume": "5"}
        for d in range(80, 0, -1)
    ]
    p, out, _ = case(
        tmp_path / "trial", evidence=bundle([candidate("USDCUSDT", "USDC", bars=bars)])
    )
    assert invoke(p).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert snap["symbols"][0]["timeframes"]["15m"]["reason"] == "incomplete_1d"
    assert snap["members"]["15m"]["status"] == "DECIDED"


def test_unknown_contender_makes_cap_undecidable_records_agree(tmp_path: Path):
    c1, c2 = candidate("AAAUSDT", "AAA"), candidate("BBBUSDT", "BBB")
    c2["daily_quote_volume"]["provenance"]["official_checksum"] = "b" * 64
    path, out, _ = case(tmp_path / "trial", evidence=bundle([c1, c2]))
    assert invoke(path).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert snap["members"]["15m"]["status"] == "UNDECIDABLE"
    assert snap["members"]["15m"]["symbols"] == []
    assert snap["members"]["15m"]["blocking"] == ["BBBUSDT"]
    for rec in snap["symbols"]:
        if rec["symbol"] == "AAAUSDT":
            assert rec["timeframes"]["15m"] == {
                "status": "undecidable",
                "reason": "top_n_undecidable",
            }
            assert rec["rank_15m"] is None


def test_cap_discloses_excluded_rank(tmp_path: Path):
    coins = [candidate(f"S{i:02d}USDT", f"S{i:02d}") for i in range(31)]
    for i, coin in enumerate(coins):
        for bar in coin["daily_quote_volume"]["bars"]:
            bar["quote_volume"] = str(i + 1)
    path, out, _ = case(tmp_path / "trial", evidence=bundle(coins))
    assert invoke(path).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert len(snap["members"]["15m"]["symbols"]) == 30
    assert {x["symbol"] for x in snap["not_admitted"] if x["reason"] == "cap"} == {"S00USDT"}


def test_calendar_flag_ignores_verification_upper_bound(tmp_path: Path):
    c = candidate()
    c["listing"]["provenance"].update(
        available_from_utc="2020-01-01T00:00:00Z",
        revisions=[{"sha256": "a" * 64, "available_from_utc": "2020-01-01T00:00:00Z"}],
    )
    verification = {
        "base": "USDC",
        "class": "pegged",
        "valid_from_utc": "2020-01-01T00:00:00Z",
        "valid_to_utc": "2026-09-22T00:00:00Z",
        "provenance": prov(),
    }
    path, out, plan = case(
        tmp_path / "trial", evidence=bundle([c], exclusion_verification=[verification])
    )
    plan["as_of_utc"] = "2026-06-23T00:00:00Z"
    plan["operating_period_start"] = {"utc": None, "provenance": None}
    path.write_text(json.dumps(plan))
    assert invoke(path).returncode == 0
    assert json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())["f3_calendar_overlap"] is False


@pytest.mark.parametrize(
    "kind", ["quote", "duplicate", "negative", "nonfinite", "bar_time", "source"]
)
def test_whole_run_input_refusals(tmp_path: Path, kind):
    c = candidate()
    ev = bundle([c])
    expected = {
        "quote": "quote mismatch",
        "duplicate": "duplicate or malformed symbol",
        "negative": "malformed volume",
        "nonfinite": "malformed volume",
        "bar_time": "daily bar is not UTC midnight",
        "source": "source must be synthetic",
    }[kind]
    if kind == "quote":
        c["quote"] = "BTC"
    elif kind == "duplicate":
        ev["candidates"].append(candidate())
    elif kind in {"negative", "nonfinite"}:
        c["daily_quote_volume"]["bars"][0]["quote_volume"] = "-1" if kind == "negative" else "NaN"
    elif kind == "bar_time":
        c["daily_quote_volume"]["bars"][0]["open_utc"] = "2025-03-03T01:00:00Z"
    else:
        c["listing"]["provenance"]["source"] = "exchange"
    path, output, _ = case(tmp_path / kind, evidence=ev)
    assert json.loads(invoke(path).stdout)["reason"] == expected
    assert not output.exists()


@pytest.mark.parametrize("symbol", ["BTCUSDT", "ETHUSDT"])
def test_reserved_symbols_are_not_candidates(tmp_path: Path, symbol):
    path, _, _ = case(tmp_path / symbol, evidence=bundle([candidate(symbol, symbol[:-4])]))
    assert json.loads(invoke(path).stdout)["reason"] == "not a candidate"


def test_unknown_listing_is_not_a_new_listing_and_blocks_subset(tmp_path: Path):
    c = candidate()
    c["listing"]["first_daily_bar_open_utc"] = "2025-05-15T00:00:00Z"
    c["listing"]["provenance"]["official_checksum"] = "b" * 64
    path, out, _ = case(tmp_path / "trial", evidence=bundle([c]))
    assert invoke(path).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert snap["symbols"][0]["timeframes"]["15m"]["reason"] == "provenance_unknown"
    assert snap["new_listings"] == []
    assert snap["members"]["15m"]["status"] == "UNDECIDABLE"


def test_uncapped_timeframes_retain_every_known_member(tmp_path: Path):
    coins = [candidate(f"C{i:02d}USDT", f"C{i:02d}") for i in range(35)]
    coins[-1]["coverage"]["1H"]["provenance"]["official_checksum"] = "b" * 64
    path, out, _ = case(tmp_path / "trial", evidence=bundle(coins))
    assert invoke(path).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert len(snap["members"]["1H"]["symbols"]) == 34
    assert len(snap["members"]["4H"]["symbols"]) == 35
    assert snap["members"]["1H"]["status"] == "DECIDED"


@pytest.mark.parametrize(
    "tf,count,expected",
    [
        ("15m", 611, None),
        ("15m", 610, "incomplete_15m"),
        ("1H", 611, None),
        ("1H", 610, "incomplete_1H"),
    ],
)
def test_exact_threshold_comparison(tmp_path: Path, tf, count, expected):
    counts = {"15m": 678, "1H": 678, "4H": 174}
    counts[tf] = count
    path, out, _ = case(
        tmp_path / f"{tf}{count}", evidence=bundle([candidate(coverage_counts=counts)])
    )
    assert invoke(path).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert snap["symbols"][0]["timeframes"][tf]["reason"] == expected


def freshness_item(
    symbol,
    timeframe,
    state,
    *,
    start="2025-06-01T00:00:00Z",
    end="2025-08-30T00:00:00Z",
    provenance=None,
):
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "span_start_utc": start,
        "span_end_utc": end,
        "state": state,
        "provenance": provenance if provenance is not None else prov(),
    }


def assert_freshness_result(tmp_path, name, symbol, timeframe, entries, operating, expected):
    plan_changes = {
        "operating_period_start": {
            "utc": operating,
            "provenance": None if operating is None else "synthetic ruling",
        }
    }
    path, out, _ = case(
        tmp_path / name,
        evidence=bundle([candidate(symbol, symbol.removesuffix("USDT"))], freshness=entries),
        plan_changes=plan_changes,
    )
    assert invoke(path).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert snap["symbols"][0]["freshness"][timeframe] == expected


def test_freshness_selects_each_governed_quarter_branch(tmp_path: Path):
    after_quarter = "2025-12-01T00:00:00Z"
    assert_freshness_result(tmp_path, "no_start", "XYZUSDT", "15m", [], None, "unknown")
    assert_freshness_result(
        tmp_path, "inside_start", "XYZUSDT", "15m", [], "2025-07-01T00:00:00Z", "operating_period"
    )
    assert_freshness_result(
        tmp_path,
        "known_cell",
        "ADAUSDT",
        "4H",
        [],
        "2025-07-01T00:00:00Z",
        "unspent_unproven",
    )
    assert_freshness_result(
        tmp_path,
        "spent_entry",
        "XYZUSDT",
        "15m",
        [
            freshness_item(
                "XYZUSDT", "15m", "spent", start="2025-06-15T00:00:00Z", end="2025-07-01T00:00:00Z"
            )
        ],
        after_quarter,
        "spent",
    )
    covering = freshness_item("XYZUSDT", "15m", "fresh")
    spent = freshness_item(
        "XYZUSDT", "15m", "spent", start="2025-06-15T00:00:00Z", end="2025-07-01T00:00:00Z"
    )
    assert_freshness_result(
        tmp_path, "spent_then_fresh", "XYZUSDT", "15m", [spent, covering], after_quarter, "spent"
    )
    assert_freshness_result(
        tmp_path, "fresh_then_spent", "XYZUSDT", "15m", [covering, spent], after_quarter, "spent"
    )
    unusable = prov()
    unusable["official_checksum"] = "b" * 64
    assert_freshness_result(
        tmp_path,
        "unusable_overlap",
        "XYZUSDT",
        "15m",
        [covering, freshness_item("XYZUSDT", "15m", "spent", provenance=unusable)],
        after_quarter,
        "unknown",
    )
    assert_freshness_result(
        tmp_path, "fresh_whole", "XYZUSDT", "15m", [covering], after_quarter, "fresh"
    )
    partial = freshness_item("XYZUSDT", "15m", "fresh", end="2025-07-01T00:00:00Z")
    assert_freshness_result(
        tmp_path, "fresh_partial", "XYZUSDT", "15m", [partial], after_quarter, "unknown"
    )


def verification(base, cls, *, valid_from="2024-01-01T00:00:00Z", valid_to=None, provenance=None):
    entry = {
        "base": base,
        "class": cls,
        "valid_from_utc": valid_from,
        "valid_to_utc": valid_to,
        "provenance": provenance if provenance is not None else prov(),
    }
    return entry


def test_trigger_suffix_requires_not_leveraged_verification(tmp_path: Path):
    c = candidate("JUPUSDT", "JUP")
    evidence = bundle(
        [c],
        not_leveraged_verification=[
            {k: v for k, v in verification("JUP", "leveraged").items() if k != "class"}
        ],
    )
    path, out, _ = case(tmp_path / "confirmed", evidence=evidence)
    assert invoke(path).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert snap["members"]["15m"]["symbols"] == ["JUPUSDT"]

    path, out, _ = case(tmp_path / "uncertain", evidence=bundle([c]))
    assert invoke(path).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert snap["symbols"][0]["timeframes"]["15m"]["reason"] == "exclusion_unverified"


def test_leveraged_enumeration_and_unusable_list_verifications(tmp_path: Path):
    leveraged = verification("XRPUP", "leveraged")
    path, out, _ = case(
        tmp_path / "leveraged",
        evidence=bundle([candidate("XRPUPUSDT", "XRPUP")], exclusion_verification=[leveraged]),
    )
    assert invoke(path).returncode == 0
    assert json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())["excluded"] == [
        {"symbol": "XRPUPUSDT", "class": "leveraged"}
    ]

    cases = [
        ("expired", verification("USDC", "pegged", valid_to="2025-05-31T00:00:00Z")),
        ("wrong_class", verification("USDC", "wrapped")),
    ]
    for name, entry in cases:
        path, out, _ = case(
            tmp_path / name,
            evidence=bundle([candidate("USDCUSDT", "USDC")], exclusion_verification=[entry]),
        )
        assert invoke(path).returncode == 0
        snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
        assert snap["symbols"][0]["timeframes"]["15m"]["reason"] == "exclusion_unverified"


def test_equal_volume_at_cap_uses_symbol_order(tmp_path: Path):
    coins = [candidate(f"C{i:02d}USDT", f"C{i:02d}") for i in range(29)]
    tie_a, tie_z = candidate("AAAUSDT", "AAA"), candidate("ZZZUSDT", "ZZZ")
    coins.extend([tie_z, tie_a])
    for coin in coins[:29]:
        for bar in coin["daily_quote_volume"]["bars"]:
            bar["quote_volume"] = "100"
    for coin in (tie_a, tie_z):
        for bar in coin["daily_quote_volume"]["bars"]:
            bar["quote_volume"] = "10"
    path, out, _ = case(tmp_path / "trial", evidence=bundle(coins))
    assert invoke(path).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    members = snap["members"]["15m"]["symbols"]
    assert len(members) == 30
    assert "AAAUSDT" in members and "ZZZUSDT" not in members
    assert {x["symbol"] for x in snap["not_admitted"] if x["reason"] == "cap"} == {"ZZZUSDT"}


def test_unverified_rank_only_blocks_when_it_can_change_the_cap(tmp_path: Path):
    eligible = [candidate(f"E{i:02d}USDT", f"E{i:02d}") for i in range(30)]
    for i, coin in enumerate(eligible):
        for bar in coin["daily_quote_volume"]["bars"]:
            bar["quote_volume"] = str(100 - i)
    unknown = candidate("USDCUSDT", "USDC")
    for bar in unknown["daily_quote_volume"]["bars"]:
        bar["quote_volume"] = "85"
    low_unknown = candidate("USDCUSDT", "USDC")
    for bar in low_unknown["daily_quote_volume"]["bars"]:
        bar["quote_volume"] = "0.5"
    low_trigger = candidate("JUPUSDT", "JUP")
    for bar in low_trigger["daily_quote_volume"]["bars"]:
        bar["quote_volume"] = "0.25"
    cases = [
        ("inside", "UNDECIDABLE", [*eligible, unknown, low_trigger]),
        ("outside", "DECIDED", [*eligible, low_unknown]),
    ]
    for name, status, coins in cases:
        path, out, _ = case(tmp_path / name, evidence=bundle(coins))
        assert invoke(path).returncode == 0
        members = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())["members"]["15m"]
        assert members["status"] == status
        if name == "inside":
            assert members["blocking"] == ["USDCUSDT"]
        else:
            assert "blocking" not in members


@pytest.mark.parametrize("count,expected", [(81, None), (80, "incomplete_1d")])
def test_one_day_completeness_boundary(tmp_path: Path, count, expected):
    bars = candidate()["daily_quote_volume"]["bars"]
    selected = [*bars[: count - 1], bars[-1]]
    c = candidate(bars=selected)
    path, out, _ = case(tmp_path / str(count), evidence=bundle([c]))
    assert invoke(path).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert snap["symbols"][0]["timeframes"]["15m"]["reason"] == expected


def test_incomplete_one_day_volume_is_known_without_listing_provenance(tmp_path: Path):
    bars = candidate()["daily_quote_volume"]["bars"]
    c = candidate(bars=[*bars[:79], bars[-1]])
    c["listing"]["provenance"]["official_checksum"] = "b" * 64
    path, out, _ = case(tmp_path / "trial", evidence=bundle([c]))
    assert invoke(path).returncode == 0
    snap = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert snap["symbols"][0]["timeframes"]["15m"]["reason"] == "incomplete_1d"


@pytest.mark.parametrize(
    "boundary,expected",
    [
        ("absent", "not_trading_at_t"),
        ("zero", "not_trading_at_t"),
        ("fraction", "not_trading_at_t"),
        ("positive", None),
    ],
    ids=["absent", "zero", "fraction", "positive"],
)
def test_trading_at_t_requires_positive_boundary_volume(tmp_path: Path, boundary, expected):
    bars = candidate()["daily_quote_volume"]["bars"]
    if boundary == "absent":
        bars = bars[:-1]
    elif boundary == "zero":
        bars[-1]["quote_volume"] = "0"
    elif boundary == "fraction":
        bars[-1]["quote_volume"] = "0.000"
    path, out, _ = case(tmp_path / boundary, evidence=bundle([candidate(bars=bars)]))
    snap = _snapshot(path, out)
    rec = snap["symbols"][0]
    for tf in ("15m", "1H", "4H"):
        assert rec["timeframes"][tf]["reason"] == expected
        if expected:
            assert rec["timeframes"][tf]["status"] == "not_admitted: not_trading_at_t"
            assert {
                "symbol": "XYZUSDT",
                "reason": "not_trading_at_t",
                "timeframe": tf,
            } in snap["not_admitted"]
    if expected:
        assert not any(item["symbol"] == "XYZUSDT" for item in snap["excluded"])
    else:
        assert rec["timeframes"]["15m"]["status"] == "member"


def test_trading_at_t_reason_precedence(tmp_path: Path):
    bars = candidate()["daily_quote_volume"]["bars"]
    bars[-1]["quote_volume"] = "0"
    bars = bars[:70] + bars[-1:]
    incomplete = candidate("LOWUSDT", "LOW", bars=bars)
    recent = candidate("NEWUSDT", "NEW")
    recent["listing"]["first_daily_bar_open_utc"] = (T - timedelta(days=30)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    recent["daily_quote_volume"]["bars"][-1]["quote_volume"] = "0"
    unknown = candidate("UNKUSDT", "UNK")
    unknown["daily_quote_volume"]["bars"][-1]["quote_volume"] = "0"
    unknown["daily_quote_volume"]["provenance"]["official_checksum"] = "b" * 64
    path, out, _ = case(tmp_path / "precedence", evidence=bundle([incomplete, recent, unknown]))
    snap = _snapshot(path, out)
    reasons = {rec["symbol"]: rec["timeframes"]["15m"]["reason"] for rec in snap["symbols"]}
    assert reasons == {
        "LOWUSDT": "not_trading_at_t",
        "NEWUSDT": "new_listing",
        "UNKUSDT": "provenance_unknown",
    }


def test_trading_at_t_failure_is_removed_before_the_rank_cap(tmp_path: Path):
    coins = []
    phantom = candidate("TOPUSDT", "TOP")
    for bar in phantom["daily_quote_volume"]["bars"]:
        bar["quote_volume"] = "1000"
    phantom["daily_quote_volume"]["bars"][-1]["quote_volume"] = "0"
    coins.append(phantom)
    for index in range(30):
        coins.append(candidate(f"C{index:02d}USDT", f"C{index:02d}"))
    path, out, _ = case(tmp_path / "rank", evidence=bundle(coins))
    snap = _snapshot(path, out)
    assert snap["members"]["15m"]["status"] == "DECIDED"
    assert len(snap["members"]["15m"]["symbols"]) == 30
    assert "TOPUSDT" not in snap["members"]["15m"]["symbols"]
    assert snap["symbols"][0]["timeframes"]["15m"]["reason"] == "not_trading_at_t"
    assert {
        "symbol": "TOPUSDT",
        "reason": "not_trading_at_t",
        "timeframe": "15m",
    } in snap["not_admitted"]
    assert not any(
        item["symbol"] == "TOPUSDT" and item["reason"] == "cap" for item in snap["not_admitted"]
    )


def test_zero_volume_earlier_in_window_still_counts_for_completeness(tmp_path: Path):
    bars = candidate()["daily_quote_volume"]["bars"]
    bars[0]["quote_volume"] = "0"
    path, out, _ = case(tmp_path / "coverage", evidence=bundle([candidate(bars=bars)]))
    snap = _snapshot(path, out)
    assert snap["symbols"][0]["timeframes"]["1H"]["reason"] is None
    assert snap["members"]["1H"] == {"status": "DECIDED", "symbols": ["XYZUSDT"]}


# --- The consolidated repair after the independent review (Claude, 2026-10-25) -----------------
# Each test below pins one rule the review showed could be broken without any test failing.


def _snapshot(path: Path, out: Path) -> dict:
    result = invoke(path)
    assert result.returncode == 0, result.stdout
    return json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())


def _refusal(path: Path) -> str:
    result = invoke(path)
    assert result.returncode == 2, result.stdout
    return json.loads(result.stdout)["reason"]


@pytest.mark.parametrize(
    "symbol,base,reason",
    [
        # BTC and ETH must not be admissible under any spelling.
        ("btcusdt", "BTC", "non-canonical symbol"),
        ("ETHUSDT ", "ETH", "non-canonical symbol"),
        ("btcusdt", "btc", "non-canonical base"),
        # A declared base that is not the symbol's would slip past the exclusion lists.
        ("USDCUSDT", "XYZ", "non-canonical symbol"),
        ("PAXGUSDT", "PAXG ", "non-canonical base"),
        ("USDCBUSD", "USDC", "non-canonical symbol"),
        # ... and past the leveraged-token trigger.
        ("XRPUPUSDT", "XRP", "non-canonical symbol"),
        # The quote is not a base, and an empty base is not one either.
        ("USDTUSDT", "USDT", "non-canonical symbol"),
        ("USDT", "", "non-canonical base"),
    ],
)
def test_a_symbol_is_exactly_its_canonical_base_and_the_quote(tmp_path: Path, symbol, base, reason):
    path, out, _ = case(tmp_path / "trial", evidence=bundle([candidate(symbol, base)]))
    assert _refusal(path) == reason
    assert not out.exists()


def test_a_non_canonical_freshness_symbol_cannot_reach_a_known_cell(tmp_path: Path):
    """`adausdt` once came out 4H fresh, because the known cell is matched on `ADAUSDT`."""
    entry = {
        "symbol": "adausdt",
        "timeframe": "4H",
        "span_start_utc": "2025-05-01T00:00:00Z",
        "span_end_utc": "2025-09-01T00:00:00Z",
        "state": "fresh",
        "provenance": prov(),
    }
    ev = bundle([candidate("ADAUSDT", "ADA")], freshness=[entry])
    path, out, _ = case(tmp_path / "trial", evidence=ev)
    assert _refusal(path) == "malformed freshness entry"
    assert not out.exists()


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("exclusion_verification", "usdc", "malformed exclusion verification"),
        ("not_leveraged_verification", "JUP ", "malformed not-leveraged verification"),
    ],
)
def test_verification_bases_are_canonical(tmp_path: Path, field, value, reason):
    entry = {"base": value, "valid_from_utc": "2024-01-01T00:00:00Z", "valid_to_utc": None}
    if field == "exclusion_verification":
        entry["class"] = "pegged"
    entry["provenance"] = prov()
    path, _, _ = case(tmp_path / "trial", evidence=bundle(**{field: [entry]}))
    assert _refusal(path) == reason


@pytest.mark.parametrize("held_first", [True, False])
def test_two_digests_at_the_latest_date_leave_no_current_revision(tmp_path: Path, held_first):
    """No single revision was current at T, whichever order the history lists them in."""
    p = prov()
    other = {"sha256": "b" * 64, "available_from_utc": p["available_from_utc"]}
    p["revisions"] = [p["revisions"][0], other] if held_first else [other, p["revisions"][0]]
    c = candidate()
    c["listing"]["provenance"] = p
    path, out, _ = case(tmp_path / "trial", evidence=bundle([c]))
    assert _snapshot(path, out)["symbols"][0]["timeframes"]["15m"]["reason"] == "provenance_unknown"


def test_a_held_copy_dated_after_t_is_unknown_even_with_an_identical_earlier_revision(
    tmp_path: Path,
):
    """Pins `available <= cutoff`: the copy held claims availability only after T."""
    p = prov()
    p["revisions"].append({"sha256": p["sha256"], "available_from_utc": "2025-07-01T00:00:00Z"})
    p["available_from_utc"] = "2025-07-01T00:00:00Z"
    c = candidate()
    c["listing"]["provenance"] = p
    path, out, _ = case(tmp_path / "trial", evidence=bundle([c]))
    assert _snapshot(path, out)["symbols"][0]["timeframes"]["15m"]["reason"] == "provenance_unknown"


@pytest.mark.parametrize(
    "value", [0.1, True, " 1_000 ", "1e3", "+1", "1.", ".5", "\u0661\u0662\u0663"]
)
def test_a_volume_is_a_plain_decimal_string(tmp_path: Path, value):
    c = candidate()
    c["daily_quote_volume"]["bars"][0]["quote_volume"] = value
    path, out, _ = case(tmp_path / "trial", evidence=bundle([c]))
    assert _refusal(path) == "malformed volume"
    assert not out.exists()


def test_large_medians_rank_exactly(tmp_path: Path):
    """Medians beyond 28 significant digits must neither round nor reorder."""
    big = "1000000000000000000000000000"
    coins = []
    for i in range(30):
        coin = candidate(f"M{i:02d}USDT", f"M{i:02d}")
        for bar in coin["daily_quote_volume"]["bars"]:
            bar["quote_volume"] = big + ".2"
        coins.append(coin)
    top = candidate("ZTOPUSDT", "ZTOP")
    for bar in top["daily_quote_volume"]["bars"]:
        bar["quote_volume"] = big + ".4"
    coins.append(top)
    even = candidate("EVENUSDT", "EVEN")
    for n, bar in enumerate(even["daily_quote_volume"]["bars"]):
        bar["quote_volume"] = big + (".1" if n % 2 else ".2")
    coins.append(even)
    path, out, _ = case(tmp_path / "trial", evidence=bundle(coins))
    snap = _snapshot(path, out)
    by = {r["symbol"]: r for r in snap["symbols"]}
    assert by["ZTOPUSDT"]["rank_15m"] == 1 and "ZTOPUSDT" in snap["members"]["15m"]["symbols"]
    assert by["EVENUSDT"]["median_daily_quote_volume"] == big + ".15"


@pytest.mark.parametrize(
    "symbol,timeframe,state",
    [("ADAUSDT", "4H", "spent"), ("ETCUSDT", "15m", "unspent_unproven")],
)
def test_evidence_contradicting_a_known_cell_in_any_state_is_refused(
    tmp_path: Path, symbol, timeframe, state
):
    entry = {
        "symbol": symbol,
        "timeframe": timeframe,
        "span_start_utc": "2025-05-01T00:00:00Z",
        "span_end_utc": "2025-09-01T00:00:00Z",
        "state": state,
        "provenance": prov(),
    }
    ev = bundle([candidate(symbol, symbol[:-4])], freshness=[entry])
    path, _, _ = case(tmp_path / "trial", evidence=ev)
    assert _refusal(path) == "freshness contradicts known_not_fresh"


def test_evidence_restating_a_known_cell_is_accepted(tmp_path: Path):
    entry = {
        "symbol": "ADAUSDT",
        "timeframe": "4H",
        "span_start_utc": "2025-05-01T00:00:00Z",
        "span_end_utc": "2025-09-01T00:00:00Z",
        "state": "unspent_unproven",
        "provenance": prov(),
    }
    path, out, _ = case(
        tmp_path / "trial", evidence=bundle([candidate("ADAUSDT", "ADA")], freshness=[entry])
    )
    assert _snapshot(path, out)["symbols"][0]["freshness"]["4H"] == "unspent_unproven"


def test_a_non_synthetic_provenance_is_refused_even_when_malformed(tmp_path: Path):
    c = candidate()
    c["listing"]["provenance"]["source"] = "exchange"
    c["listing"]["provenance"]["extra"] = 1
    path, _, _ = case(tmp_path / "trial", evidence=bundle([c]))
    assert _refusal(path) == "source must be synthetic"


def test_a_listing_date_is_a_utc_midnight(tmp_path: Path):
    c = candidate()
    c["listing"]["first_daily_bar_open_utc"] = "2024-03-02T23:00:00Z"
    path, _, _ = case(tmp_path / "trial", evidence=bundle([c]))
    assert _refusal(path) == "listing date is not UTC midnight"


@pytest.mark.parametrize("count,expected", [(157, None), (156, "incomplete_4H")])
def test_four_hour_completeness_at_the_threshold(tmp_path: Path, count, expected):
    counts = {"15m": 678, "1H": 678, "4H": count}
    path, out, _ = case(tmp_path / "trial", evidence=bundle([candidate(coverage_counts=counts)]))
    assert _snapshot(path, out)["symbols"][0]["timeframes"]["4H"]["reason"] == expected


def test_admissibility_requires_a_clean_methodology_record():
    fn = module().f3_judgment_admissible
    good = {"f3_firewall": "F-C", "f3_calendar_overlap": False, "methodology": {"f3_clean": True}}
    assert not fn({**good, "methodology": {}})
    assert not fn({**good, "methodology": {"f3_clean": False}})
    assert not fn({k: v for k, v in good.items() if k != "methodology"})


def test_the_snapshot_carries_the_ruling_and_a_clean_methodology(tmp_path: Path):
    """The value test the determinism test lacked."""
    path, out, _ = case(tmp_path / "trial")
    snap = _snapshot(path, out)
    m = module()
    assert snap["status"] == "SYNTHETIC" and snap["snapshot_id"] == "ucpe.universe.asof.v2"
    assert snap["rule_sha256"] == m.UNIVERSE_RULE_V1_SHA256
    assert snap["ruling"]["R1"] == 90 and snap["ruling"]["R2"] == 30
    assert snap["ruling"]["R3"] == {"1H": None, "4H": None} and snap["ruling"]["R7"] == "F-C"
    assert snap["ruling"]["G1"] == (
        "a_prime: daily bar [T-1d, T) present with quote volume > 0; "
        "owner-ruled 2026-10-29; SYNTHETIC_ONLY"
    )
    assert snap["methodology"]["f3_clean"] is True and snap["f3_firewall"] == "F-C"
    assert snap["f3_calendar_overlap"] is False and m.f3_judgment_admissible(snap)
    assert snap["members"]["1H"] == {"status": "DECIDED", "symbols": ["XYZUSDT"]}
    # The default bars are 1 … 90: an even count, so the median is the mean of 45 and 46.
    assert snap["symbols"][0]["median_daily_quote_volume"] == "45.5"


def test_a_fresh_entry_starting_after_t_does_not_cover_the_quarter(tmp_path: Path):
    entry = {
        "symbol": "XYZUSDT",
        "timeframe": "15m",
        "span_start_utc": "2025-06-01T00:00:01Z",
        "span_end_utc": "2026-01-01T00:00:00Z",
        "state": "fresh",
        "provenance": prov(),
    }
    assert_freshness_result(
        tmp_path, "late_fresh", "XYZUSDT", "15m", [entry], "2025-12-01T00:00:00Z", "unknown"
    )


@pytest.mark.parametrize(
    "operating,expected",
    [("2025-08-30T00:00:00Z", "fresh"), ("2025-08-29T23:59:59Z", "operating_period")],
)
def test_the_operating_period_boundary_is_the_quarter_end(tmp_path: Path, operating, expected):
    """The quarter is [2025-06-01, 2025-08-30): a start at its end does not overlap it."""
    entry = {
        "symbol": "XYZUSDT",
        "timeframe": "15m",
        "span_start_utc": "2025-06-01T00:00:00Z",
        "span_end_utc": "2025-08-30T00:00:00Z",
        "state": "fresh",
        "provenance": prov(),
    }
    assert_freshness_result(
        tmp_path, operating[:10], "XYZUSDT", "15m", [entry], operating, expected
    )


def test_a_null_start_does_not_mask_a_known_cell(tmp_path: Path):
    assert_freshness_result(tmp_path, "null_known", "ADAUSDT", "4H", [], None, "unspent_unproven")


def test_a_verification_ending_at_t_does_not_cover_t(tmp_path: Path):
    item = {
        "base": "USDC",
        "class": "pegged",
        "valid_from_utc": "2024-01-01T00:00:00Z",
        "valid_to_utc": T_STR,
        "provenance": prov(),
    }
    ev = bundle([candidate("USDCUSDT", "USDC")], exclusion_verification=[item])
    path, out, _ = case(tmp_path / "trial", evidence=ev)
    assert (
        _snapshot(path, out)["symbols"][0]["timeframes"]["15m"]["reason"] == "exclusion_unverified"
    )


@pytest.mark.parametrize("contender,expected", [("A00", "UNDECIDABLE"), ("Z00", "DECIDED")])
def test_an_unknown_contender_tied_at_rank_thirty_blocks_only_if_it_sorts_first(
    tmp_path: Path, contender, expected
):
    """30 eligible at an equal volume; an unknown contender at the same volume ranks by symbol."""
    coins = []
    for i in range(30):
        coin = candidate(f"M{i:02d}USDT", f"M{i:02d}")
        for bar in coin["daily_quote_volume"]["bars"]:
            bar["quote_volume"] = "10"
        coins.append(coin)
    unknown = candidate(f"{contender}USDT", contender)
    for bar in unknown["daily_quote_volume"]["bars"]:
        bar["quote_volume"] = "10"
    unknown["coverage"]["15m"]["provenance"]["official_checksum"] = "b" * 64
    coins.append(unknown)
    path, out, _ = case(tmp_path / "trial", evidence=bundle(coins))
    assert _snapshot(path, out)["members"]["15m"]["status"] == expected


def _guarded_cli(tmp_path: Path, mode: str) -> subprocess.CompletedProcess:
    """Run the real CLI in a child process with `build` wrapped to attempt `mode` first."""
    path, _, _ = case(tmp_path / mode)
    outside = tmp_path / f"outside_{mode}.txt"
    driver = tmp_path / f"driver_{mode}.py"
    driver.write_text(
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('corpus_guarded', {str(SCRIPT)!r})\n"
        "m = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(m)\n"
        "real = m.build\n"
        "def build(*a, **k):\n"
        f"    if {mode!r} == 'write':\n"
        f"        open({str(outside)!r}, 'w').write('x')\n"
        f"    elif {mode!r} == 'socket':\n"
        "        import socket\n"
        "        socket.socket()\n"
        "    return real(*a, **k)\n"
        "m.build = build\n"
        f"raise SystemExit(m.main([{str(path)!r}]))\n",
        encoding="utf-8",
    )
    return subprocess.run(
        [sys.executable, "-I", "-B", str(driver)], cwd=ROOT, capture_output=True, text=True
    )


def test_the_cli_guard_is_live_in_main(tmp_path: Path):
    """The guard stops a write outside the output folder and a socket; a control run passes.

    The reasons are asserted, not only the exit code, so a socket failing for some unrelated
    reason could not pass this test.
    """
    assert _guarded_cli(tmp_path, "none").returncode == 0
    write = _guarded_cli(tmp_path, "write")
    assert write.returncode == 2
    assert "write outside the output folder" in json.loads(write.stdout)["reason"]
    assert not (tmp_path / "outside_write.txt").exists()
    sock = _guarded_cli(tmp_path, "socket")
    assert sock.returncode == 2
    assert "socket.__new__" in json.loads(sock.stdout)["reason"]


def test_a_lineage_is_a_canonical_ticker(tmp_path: Path):
    c = candidate()
    c["lineage"] = "oldxyzusdt"
    path, _, _ = case(tmp_path / "trial", evidence=bundle([c]))
    assert _refusal(path) == "malformed lineage"


def test_a_median_beyond_exact_precision_is_a_named_refusal(tmp_path: Path):
    """Two middle values whose mean needs more than the exact context's digits are refused."""
    c = candidate()
    long_a = "1" + "0" * 999 + ".1"
    long_b = "1" + "0" * 999 + ".2"
    for n, bar in enumerate(c["daily_quote_volume"]["bars"]):
        bar["quote_volume"] = long_a if n % 2 else long_b
    path, out, _ = case(tmp_path / "trial", evidence=bundle([c]))
    assert _refusal(path) == "volume beyond exact precision"
    assert not out.exists()


def test_a_daily_bar_may_carry_only_open_time_and_quote_volume(tmp_path: Path):
    """A daily bar carries only its open time and quote volume; any other field, a price
    included, is refused."""
    c = candidate()
    c["daily_quote_volume"]["bars"][0]["close"] = "1.0"
    path, out, _ = case(tmp_path / "trial", evidence=bundle([c]))
    assert _refusal(path) == "malformed daily bar"
    assert not out.exists()


def test_a_candidate_may_not_carry_an_unrecognized_key(tmp_path: Path):
    """A candidate's keys are closed, so a field such as a later delisting date is refused."""
    c = candidate()
    c["delisted_utc"] = "2025-07-01T00:00:00Z"
    path, out, _ = case(tmp_path / "trial", evidence=bundle([c]))
    assert _refusal(path) == "malformed candidate"
    assert not out.exists()


@pytest.mark.parametrize(
    "timeframe,count",
    [("15m", 679), ("1H", 679), ("4H", 175)],
    ids=["fifteen_minute", "one_hour", "four_hour"],
)
def test_coverage_count_may_not_exceed_its_history_window(tmp_path: Path, timeframe, count):
    """A coverage count above its timeframe's history window is refused."""
    counts = {"15m": 678, "1H": 678, "4H": 174}
    counts[timeframe] = count
    path, out, _ = case(tmp_path / timeframe, evidence=bundle([candidate(coverage_counts=counts)]))
    assert _refusal(path) == "invalid coverage count"
    assert not out.exists()


def test_missing_freshness_entries_are_reported_as_unknown(tmp_path: Path):
    """With a known operating-period start and no freshness entry, every timeframe is unknown
    (B2)."""
    path, out, _ = case(
        tmp_path / "trial",
        plan_changes={
            "operating_period_start": {
                "utc": "2025-12-01T00:00:00Z",
                "provenance": "synthetic",
            }
        },
    )
    result = invoke(path)
    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "PASS"
    snapshot = json.loads((out / "UNIVERSE_SNAPSHOT.json").read_bytes())
    assert snapshot["symbols"][0]["freshness"] == {
        "15m": "unknown",
        "1H": "unknown",
        "4H": "unknown",
    }
