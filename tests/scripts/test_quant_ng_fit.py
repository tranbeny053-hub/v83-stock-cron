"""The NG fit precondition gate: every refusal, the artifact, and its determinism.

Synthetic only, and entirely inside pytest's temporary folder: the tool accepts an input anywhere on
disk because the digest pin, not the location, is what fixes the bytes. Nothing here writes into the
repository, and nothing reads a real corpus.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/quant_ng_fit.py"
INSTANT = "2025-01-01T00:00:00Z"
LATER = "2025-01-01T00:00:01Z"
CUTOFF = "2025-01-02T00:00:00Z"
RULE = ROOT / "ops/quant_ng/UNIVERSE_RULE_v1.json"
RULE_SHA = hashlib.sha256(RULE.read_bytes()).hexdigest()
VALID_UNIVERSE = {
    "snapshot_id": "ucpe.universe.asof.v2",
    "status": "SYNTHETIC",
    "rule_sha256": RULE_SHA,
    "f3_firewall": "F-C",
}
ROW = {
    "symbol": "BTCUSDT",
    "timeframe": "1h",
    "predicted_at_utc": INSTANT,
    "horizon_end_utc": LATER,
    "label": "UP",
}


EXPECTED_REASON = {
    "wrong_plan_id": "invalid plan",
    "unknown_key": "invalid plan",
    "missing_key": "invalid plan",
    "bad_instant": "malformed instant",
    "corpus_digest": "corpus digest mismatch",
    "universe_digest": "universe_snapshot digest mismatch",
    "corpus_missing": "corpus unreadable",
    "unmatured": "rows not matured before the cutoff: 1",
    "unmatured_exactly_at_cutoff": "rows not matured before the cutoff: 1",
    "consumed": "rows inside consumed spans: 1; spans: fold-a",
    "nonempty_output": "output folder is not empty",
    "protected_path": "protected path",
    "forbidden_tree": "forbidden tree",
    "relative_path": "path must be absolute",
    "bad_row_label": "malformed row",
    "bad_row_interval": "malformed row interval",
    "empty_corpus": "malformed corpus",
    "bad_span_bounds": "invalid consumed span bounds",
    "span_unknown_key": "invalid consumed span",
    "duplicate_plan_key": "plan unreadable",
}


def _load_module(name: str, path: Path = SCRIPT):
    """Import the tool by path without writing bytecode beside it.

    verify.sh runs pytest without -B, and exec_module on a file path would cache a .pyc in
    scripts/__pycache__ — a write inside the repository tree, which these tests must never make.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def invoke(plan: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", "-B", str(SCRIPT), "--plan", str(plan)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def case(
    base: Path, *, rows=None, spans=None, output_name="out", extra=None, universe=None
) -> tuple[Path, Path, dict]:
    """Write a synthetic plan with its corpus and universe snapshot under base; return the paths."""
    base.mkdir(parents=True, exist_ok=True)
    corpus_bytes = json.dumps(
        {"rows": [ROW] if rows is None else rows}, separators=(",", ":")
    ).encode()
    (base / "corpus.json").write_bytes(corpus_bytes)
    if universe is None:
        universe = json.dumps(VALID_UNIVERSE, separators=(",", ":")).encode()
    (base / "universe.json").write_bytes(universe)
    plan = {
        "plan_id": "ucpe.quant_ng.fit.v1",
        "cutoff_utc": CUTOFF,
        "corpus": {
            "path": str(base / "corpus.json"),
            "sha256": hashlib.sha256(corpus_bytes).hexdigest(),
        },
        "universe_snapshot": {
            "path": str(base / "universe.json"),
            "sha256": hashlib.sha256(universe).hexdigest(),
        },
        "consumed_spans": [] if spans is None else spans,
        "output_dir": str(base / output_name),
    }
    if extra:
        plan.update(extra)
    plan_path = base / "plan.json"
    plan_path.write_text(json.dumps(plan, separators=(",", ":")), encoding="utf-8")
    return plan_path, base / output_name, plan


def test_pass_writes_a_complete_read_only_artifact(tmp_path: Path) -> None:
    plan_path, output, plan = case(tmp_path / "a")
    completed = invoke(plan_path)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    artifact = json.loads((output / "ARTIFACT.json").read_bytes())
    plan_sha = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    corpus_sha = plan["corpus"]["sha256"]
    universe_sha = plan["universe_snapshot"]["sha256"]
    expected_id = (
        "ngfit-"
        + hashlib.sha256(
            "\n".join([plan_sha, corpus_sha, universe_sha, CUTOFF]).encode()
        ).hexdigest()[:16]
    )
    assert artifact == {
        "artifact_id": expected_id,
        "plan_id": "ucpe.quant_ng.fit.v1",
        "tool_sha256": hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
        "plan_sha256": plan_sha,
        "corpus_sha256": corpus_sha,
        "universe_snapshot_sha256": universe_sha,
        "universe_snapshot_id": "ucpe.universe.asof.v2",
        "universe_status": "SYNTHETIC",
        "universe_rule_sha256": RULE_SHA,
        "cutoff_utc": CUTOFF,
        "consumed_spans": [],
        "rows_total": 1,
        "rows_by_symbol_timeframe": {"BTCUSDT|1h": 1},
        "label_counts": {"UP": 1, "DOWN": 0, "TIMEOUT": 0},
        "estimator": "NOT_IMPLEMENTED_PENDING_OD_NG_2_AND_OD_NG_7",
        "inputs_read": ["corpus", "plan", "tool", "universe_snapshot"],
        "input_names": {
            "corpus": "corpus.json",
            "plan": "plan.json",
            "tool": "quant_ng_fit.py",
            "universe_snapshot": "universe.json",
        },
        "tool_version": "2",
        "schema_version": "2",
    }
    assert os.stat(output / "ARTIFACT.json").st_mode & 0o777 == 0o444
    assert sorted(p.name for p in output.iterdir()) == ["ARTIFACT.json"]
    assert json.loads(completed.stdout) == {"status": "PASS", "artifact_id": expected_id}


def test_the_artifact_holds_no_absolute_path(tmp_path: Path) -> None:
    """No absolute path, so the artifact cannot depend on the checkout it ran in."""
    plan_path, output, _ = case(tmp_path / "b")
    assert invoke(plan_path).returncode == 0
    raw = (output / "ARTIFACT.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in raw
    assert str(ROOT) not in raw
    assert "/" not in raw.replace("ucpe.quant_ng.fit.v1", "")


def test_a_rerun_into_a_fresh_folder_is_byte_identical(tmp_path: Path) -> None:
    plan_path, output, _ = case(tmp_path / "c")
    assert invoke(plan_path).returncode == 0
    first = (output / "ARTIFACT.json").read_bytes()
    os.chmod(output / "ARTIFACT.json", 0o644)
    (output / "ARTIFACT.json").unlink()
    output.rmdir()
    assert invoke(plan_path).returncode == 0
    assert (output / "ARTIFACT.json").read_bytes() == first


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_plan_id",
        "unknown_key",
        "missing_key",
        "bad_instant",
        "corpus_digest",
        "universe_digest",
        "corpus_missing",
        "unmatured",
        "unmatured_exactly_at_cutoff",
        "consumed",
        "nonempty_output",
        "protected_path",
        "forbidden_tree",
        "duplicate_plan_key",
        "relative_path",
        "bad_row_label",
        "bad_row_interval",
        "empty_corpus",
        "bad_span_bounds",
        "span_unknown_key",
    ],
)
def test_every_refusal_creates_nothing(tmp_path: Path, mutation: str) -> None:
    base = tmp_path / mutation
    rows, spans, extra, output_name = None, None, None, "out"
    if mutation == "wrong_plan_id":
        extra = {"plan_id": "ucpe.quant_ng.fit.v0"}
    elif mutation == "unknown_key":
        extra = {"surprise": True}
    elif mutation == "bad_instant":
        extra = {"cutoff_utc": "2025-01-02 00:00:00"}
    elif mutation == "unmatured":
        rows = [{**ROW, "horizon_end_utc": "2026-01-01T00:00:00Z"}]
    elif mutation == "unmatured_exactly_at_cutoff":
        rows = [{**ROW, "horizon_end_utc": CUTOFF}]
    elif mutation == "consumed":
        spans = [{"label": "fold-a", "start_utc": INSTANT, "end_utc": CUTOFF}]
    elif mutation == "protected_path":
        output_name = "holdout-out"
    elif mutation == "bad_row_label":
        rows = [{**ROW, "label": "SIDEWAYS"}]
    elif mutation == "bad_row_interval":
        rows = [{**ROW, "predicted_at_utc": LATER, "horizon_end_utc": INSTANT}]
    elif mutation == "empty_corpus":
        rows = []
    elif mutation == "bad_span_bounds":
        spans = [{"label": "f", "start_utc": CUTOFF, "end_utc": INSTANT}]
    elif mutation == "span_unknown_key":
        spans = [{"label": "f", "start_utc": INSTANT, "end_utc": LATER, "note": "x"}]

    plan_path, output, plan = case(
        base, rows=rows, spans=spans, output_name=output_name, extra=extra
    )
    if mutation == "missing_key":
        del plan["consumed_spans"]
    elif mutation == "corpus_digest":
        plan["corpus"]["sha256"] = "0" * 64
    elif mutation == "universe_digest":
        plan["universe_snapshot"]["sha256"] = "f" * 64
    elif mutation == "corpus_missing":
        Path(plan["corpus"]["path"]).unlink()
    elif mutation == "forbidden_tree":
        plan["corpus"]["path"] = (
            "/Users/kha/Documents/Kha-app/UCPE/.work/v1d_1w_20261023/eval/output/EVAL_RESULT.json"
        )
    elif mutation == "duplicate_plan_key":
        # Written as text, because a dict cannot hold the same key twice.
        raw = json.dumps(plan, separators=(",", ":"))
        plan_path.write_text(raw[:-1] + ',"cutoff_utc":"2099-01-01T00:00:00Z"}', encoding="utf-8")
        completed_dup = invoke(plan_path)
        assert completed_dup.returncode == 2
        assert json.loads(completed_dup.stdout)["reason"] == "plan unreadable"
        assert not output.exists()
        return
    elif mutation == "relative_path":
        plan["corpus"]["path"] = "corpus.json"
    elif mutation == "nonempty_output":
        output.mkdir(parents=True)
        (output / "already-here").write_text("x", encoding="utf-8")
    plan_path.write_text(json.dumps(plan, separators=(",", ":")), encoding="utf-8")

    completed = invoke(plan_path)
    assert completed.returncode == 2, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "REFUSAL"
    assert payload["reason"] == EXPECTED_REASON[mutation], payload["reason"]
    if mutation == "nonempty_output":
        assert sorted(p.name for p in output.iterdir()) == ["already-here"]
    else:
        assert not output.exists()


@pytest.mark.parametrize(
    "universe,reason",
    [
        (b"[]", "universe snapshot is not a ruled snapshot"),
        (
            json.dumps({**VALID_UNIVERSE, "snapshot_id": "wrong"}).encode(),
            "universe snapshot id is not ucpe.universe.asof.v2",
        ),
        (
            json.dumps({**VALID_UNIVERSE, "status": "DECIDED"}).encode(),
            "universe snapshot status is not SYNTHETIC",
        ),
        (
            json.dumps({**VALID_UNIVERSE, "rule_sha256": "0" * 64}).encode(),
            "universe snapshot was not built under the ruled spec",
        ),
        (
            json.dumps({**VALID_UNIVERSE, "f3_firewall": "other"}).encode(),
            "universe snapshot firewall is not F-C",
        ),
    ],
)
def test_unruled_snapshot_refusals_leave_no_output(
    tmp_path: Path, universe: bytes, reason: str
) -> None:
    plan_path, output, _ = case(tmp_path / "snapshot", universe=universe)
    completed = invoke(plan_path)
    assert completed.returncode == 2
    assert json.loads(completed.stdout) == {"status": "REFUSAL", "reason": reason}
    assert not output.exists()


def test_fit_rule_digest_matches_spec_and_corpus_pin() -> None:
    fit = _load_module("quant_ng_fit_digest")
    corpus = _load_module("quant_ng_corpus_digest", ROOT / "scripts/quant_ng_corpus.py")
    assert fit.UNIVERSE_RULE_V1_SHA256 == hashlib.sha256(RULE.read_bytes()).hexdigest()
    assert fit.UNIVERSE_RULE_V1_SHA256 == corpus.UNIVERSE_RULE_V1_SHA256


@pytest.mark.parametrize(
    "wrong_fields,reason",
    [
        (("snapshot_id", "status"), "universe snapshot id is not ucpe.universe.asof.v2"),
        (("status", "rule_sha256"), "universe snapshot status is not SYNTHETIC"),
        (("rule_sha256", "f3_firewall"), "universe snapshot was not built under the ruled spec"),
    ],
)
def test_snapshot_checks_are_ordered(tmp_path: Path, wrong_fields, reason: str) -> None:
    universe = dict(VALID_UNIVERSE)
    for field in wrong_fields:
        universe[field] = "wrong"
    plan_path, output, _ = case(
        tmp_path / "snapshot-order", universe=json.dumps(universe).encode()
    )
    completed = invoke(plan_path)
    assert completed.returncode == 2
    assert json.loads(completed.stdout)["reason"] == reason
    assert not output.exists()


def test_corpus_builder_snapshot_passes_fit_gate(tmp_path: Path) -> None:
    """An actual ruled snapshot from the corpus CLI is accepted by the fit gate."""
    corpus_script = ROOT / "scripts/quant_ng_corpus.py"
    digest = "a" * 64
    prov = {
        "source": "synthetic",
        "sha256": digest,
        "official_checksum": digest,
        "available_from_utc": "2025-01-01T00:00:00Z",
        "revisions": [{"sha256": digest, "available_from_utc": "2025-01-01T00:00:00Z"}],
        "revision_history_complete": True,
    }
    as_of = datetime(2025, 6, 1, tzinfo=UTC)
    bars = [
        {
            "open_utc": (as_of - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "quote_volume": str(days),
        }
        for days in range(90, 0, -1)
    ]
    candidate = {
        "symbol": "XYZUSDT",
        "base": "XYZ",
        "quote": "USDT",
        "lineage": None,
        "listing": {"first_daily_bar_open_utc": "2024-01-01T00:00:00Z", "provenance": prov},
        "daily_quote_volume": {"bars": bars, "provenance": prov},
        "coverage": {
            tf: {"present_in_window": count, "provenance": prov}
            for tf, count in {"15m": 678, "1H": 678, "4H": 174}.items()
        },
    }
    evidence = {
        "evidence_id": "ucpe.quant_ng.universe_evidence.v1",
        "source": "synthetic",
        "candidates": [candidate],
        "exclusion_verification": [],
        "not_leveraged_verification": [],
        "freshness": [],
    }
    evidence_bytes = json.dumps(evidence, separators=(",", ":")).encode()
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_bytes(evidence_bytes)
    corpus_plan = {
        "plan_id": "ucpe.quant_ng.universe.v1",
        "as_of_utc": "2025-06-01T00:00:00Z",
        "evidence": {
            "path": str(evidence_path),
            "sha256": hashlib.sha256(evidence_bytes).hexdigest(),
        },
        "operating_period_start": {"utc": None, "provenance": None},
        "completeness": {"threshold": 0.9, "ruling": "SYNTHETIC_TEST_ONLY"},
        "output_dir": str(tmp_path / "universe-out"),
    }
    corpus_plan_path = tmp_path / "universe-plan.json"
    corpus_plan_path.write_text(json.dumps(corpus_plan, separators=(",", ":")), encoding="utf-8")
    built = subprocess.run(
        [sys.executable, "-I", "-B", str(corpus_script), str(corpus_plan_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert built.returncode == 0, built.stdout + built.stderr
    snapshot_bytes = (tmp_path / "universe-out/UNIVERSE_SNAPSHOT.json").read_bytes()
    fit_plan, output, _ = case(tmp_path / "fit", universe=snapshot_bytes)
    fit_result = invoke(fit_plan)
    assert fit_result.returncode == 0, fit_result.stdout + fit_result.stderr
    artifact = json.loads((output / "ARTIFACT.json").read_bytes())
    snapshot = json.loads(snapshot_bytes)
    assert artifact["universe_snapshot_id"] == snapshot["snapshot_id"]
    assert artifact["universe_status"] == snapshot["status"]
    assert artifact["universe_rule_sha256"] == snapshot["rule_sha256"]


def test_the_forbidden_tree_refusal_reads_no_byte_of_it(tmp_path: Path) -> None:
    """A consumed output folder is refused by name: its bytes are never opened."""
    consumed = "/Users/kha/Documents/Kha-app/UCPE/.work/v1d_1w_20261023/s1_output/BTCUSDT_1D.json"
    plan_path, output, plan = case(tmp_path / "ft")
    plan["corpus"]["path"] = consumed
    plan_path.write_text(json.dumps(plan, separators=(",", ":")), encoding="utf-8")
    completed = invoke(plan_path)
    assert completed.returncode == 2
    assert json.loads(completed.stdout)["reason"] == "forbidden tree"
    assert not output.exists()


def test_a_row_maturing_one_millisecond_before_the_cutoff_passes(tmp_path: Path) -> None:
    rows = [{**ROW, "horizon_end_utc": "2025-01-01T23:59:59.999Z"}]
    plan_path, output, _ = case(tmp_path / "edge", rows=rows)
    assert invoke(plan_path).returncode == 0
    assert (output / "ARTIFACT.json").is_file()


def test_consumed_spans_are_half_open(tmp_path: Path) -> None:
    span = [{"label": "fold", "start_utc": LATER, "end_utc": CUTOFF}]
    ending_at_start = [{**ROW, "horizon_end_utc": LATER}]
    plan_path, output, _ = case(tmp_path / "touch", rows=ending_at_start, spans=span)
    assert invoke(plan_path).returncode == 0, (
        "a row ending exactly at the span's start is admissible"
    )
    assert (output / "ARTIFACT.json").is_file()

    starting_at_start = [
        {**ROW, "predicted_at_utc": LATER, "horizon_end_utc": "2025-01-01T00:00:02Z"}
    ]
    plan_path, output, _ = case(tmp_path / "inside", rows=starting_at_start, spans=span)
    completed = invoke(plan_path)
    assert completed.returncode == 2, "a row starting exactly at the span's start is consumed"
    assert "fold" in json.loads(completed.stdout)["reason"]
    assert not output.exists()


def test_the_refusal_names_every_span_hit_and_counts_rows(tmp_path: Path) -> None:
    rows = [ROW, {**ROW, "predicted_at_utc": LATER, "horizon_end_utc": "2025-01-01T00:00:02Z"}]
    spans = [
        {"label": "fold-b", "start_utc": INSTANT, "end_utc": LATER},
        {"label": "fold-a", "start_utc": LATER, "end_utc": CUTOFF},
        {
            "label": "fold-unused",
            "start_utc": "2024-01-01T00:00:00Z",
            "end_utc": "2024-06-01T00:00:00Z",
        },
    ]
    plan_path, _, _ = case(tmp_path / "labels", rows=rows, spans=spans)
    completed = invoke(plan_path)
    assert completed.returncode == 2
    reason = json.loads(completed.stdout)["reason"]
    assert reason == "rows inside consumed spans: 2; spans: fold-a,fold-b"


def test_many_rows_are_counted_per_symbol_timeframe_and_label(tmp_path: Path) -> None:
    rows = [
        {**ROW, "symbol": symbol, "timeframe": timeframe, "label": label}
        for symbol, timeframe, label in (
            ("BTCUSDT", "1h", "UP"),
            ("BTCUSDT", "1h", "DOWN"),
            ("BTCUSDT", "4h", "TIMEOUT"),
            ("ETHUSDT", "1h", "UP"),
        )
    ]
    plan_path, output, _ = case(tmp_path / "counts", rows=rows)
    assert invoke(plan_path).returncode == 0
    artifact = json.loads((output / "ARTIFACT.json").read_bytes())
    assert artifact["rows_total"] == 4
    assert artifact["rows_by_symbol_timeframe"] == {
        "BTCUSDT|1h": 2,
        "BTCUSDT|4h": 1,
        "ETHUSDT|1h": 1,
    }
    assert artifact["label_counts"] == {"UP": 2, "DOWN": 1, "TIMEOUT": 1}
    assert list(artifact["rows_by_symbol_timeframe"]) == sorted(
        artifact["rows_by_symbol_timeframe"]
    )


def test_guard_reason_refuses_network_processes_and_outside_writes(tmp_path: Path) -> None:
    """The guard's decision, as a pure function: never install a hook in the test process."""
    module = _load_module("quant_ng_fit_guard")
    allowed = tmp_path / "out"
    assert (
        module.guard_reason("socket.connect", ((),), allowed) == "forbidden event: socket.connect"
    )
    assert module.guard_reason("subprocess.Popen", ((),), allowed).startswith("forbidden event:")
    outside = str(tmp_path / "elsewhere.txt")
    assert (
        module.guard_reason("open", (outside, "w", 0), allowed) == "write outside the output folder"
    )
    inside = str(allowed / "ARTIFACT.json")
    assert module.guard_reason("open", (inside, "w", 0), allowed) is None
    # A read is never a write, wherever it points.
    assert module.guard_reason("open", (outside, "r", 0), allowed) is None
    # Before the output folder is known, every write is refused.
    assert module.guard_reason("open", (inside, "w", 0), None) == "write outside the output folder"
    # Flag form, and an unresolvable argument (a file descriptor) is not a path write.
    assert module.guard_reason("open", (outside, None, os.O_WRONLY), allowed) is not None
    assert module.guard_reason("open", (4, None, os.O_WRONLY), allowed) is None
    # An unrelated event is ignored.
    assert module.guard_reason("object.__getattr__", ((),), allowed) is None


def test_create_readonly_removes_its_file_when_the_write_fails(tmp_path: Path, monkeypatch) -> None:
    module = _load_module("quant_ng_fit_rw")
    target = tmp_path / "ARTIFACT.json"
    monkeypatch.setattr(os, "write", lambda fd, data: (_ for _ in ()).throw(OSError("synthetic")))
    with pytest.raises(OSError, match="synthetic"):
        module.create_readonly(target, b"{}")
    monkeypatch.undo()
    assert not target.exists()
    module.create_readonly(target, b"{}\n")
    assert target.read_bytes() == b"{}\n"
    assert os.stat(target).st_mode & 0o777 == 0o444


@pytest.mark.parametrize(
    "tree",
    [
        ".work/v1d_1w_20261023/s1_output/BTCUSDT_1D.json",
        ".work/v1d_1w_20261023/eval/output/EVAL_RESULT.json",
        ".work/research3/r2/corpus.py",
        ".work/research/cache/anything.json",
    ],
)
def test_every_forbidden_tree_is_refused_by_name(tmp_path: Path, tree: str) -> None:
    """Each consumed or research tree is refused before a byte of it is opened."""
    plan_path, output, plan = case(tmp_path / "ft")
    plan["corpus"]["path"] = f"/Users/kha/Documents/Kha-app/UCPE/{tree}"
    plan_path.write_text(json.dumps(plan, separators=(",", ":")), encoding="utf-8")
    completed = invoke(plan_path)
    assert completed.returncode == 2
    assert json.loads(completed.stdout)["reason"] == "forbidden tree"
    assert not output.exists()


def test_an_unwritable_output_parent_is_a_refusal_not_a_crash(tmp_path: Path) -> None:
    """The documented contract is exit 0 or exit 2 with JSON; never a traceback."""
    parent = tmp_path / "locked"
    parent.mkdir()
    plan_path, _, plan = case(tmp_path / "u")
    plan["output_dir"] = str(parent / "out")
    plan_path.write_text(json.dumps(plan, separators=(",", ":")), encoding="utf-8")
    parent.chmod(0o500)
    try:
        completed = invoke(plan_path)
    finally:
        parent.chmod(0o700)
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert completed.stderr == ""
    assert json.loads(completed.stdout)["reason"].startswith("cannot create the output folder")
    assert not (parent / "out").exists()


def test_a_failed_write_unwinds_every_folder_it_created(tmp_path: Path, monkeypatch) -> None:
    """mkdir(parents=True) can create several levels; a refusal must leave none of them."""
    module = _load_module("quant_ng_fit_unwind")
    deep = tmp_path / "a" / "b" / "c"
    created = module._make_output(deep)
    assert [p.name for p in created] == ["c", "b", "a"]
    assert deep.is_dir()
    module._unwind(created)
    assert not (tmp_path / "a").exists()
    # An existing folder is never unwound, because this run did not create it.
    existing = tmp_path / "kept"
    existing.mkdir()
    assert module._make_output(existing) == []


def test_the_guard_also_refuses_filesystem_changes_outside_the_output(tmp_path: Path) -> None:
    """The inventory claims writes are confined; `open` alone would not deliver that."""
    module = _load_module("quant_ng_fit_fs")
    allowed = tmp_path / "out"
    outside = str(tmp_path / "elsewhere")
    for event in ("os.mkdir", "os.remove", "os.rename", "os.symlink", "os.truncate", "os.rmdir"):
        reason = module.guard_reason(event, (outside,), allowed)
        assert reason == f"filesystem change outside the output folder: {event}", event
        assert module.guard_reason(event, (str(allowed / "x"),), allowed) is None, event
    assert module.guard_reason("shutil.rmtree", (outside,), allowed) is not None


def test_the_same_corpus_from_two_locations_gives_the_same_body(tmp_path: Path) -> None:
    """Layout independence: only the plan's own digest may differ between two locations.

    The artifact was once built from the audit hook's opened paths, which made its content depend
    on where it ran (a checkout whose .venv sits inside the repository recorded hundreds of extra
    files). This asserts the property that defect violated.
    """
    volatile = {"plan_sha256", "artifact_id"}
    bodies = []
    for name in ("left", "right/deeper"):
        plan_path, output, _ = case(tmp_path / name)
        assert invoke(plan_path).returncode == 0
        artifact = json.loads((output / "ARTIFACT.json").read_bytes())
        bodies.append({k: v for k, v in artifact.items() if k not in volatile})
    assert bodies[0] == bodies[1]
    assert list(bodies[0]) == list(bodies[1]), "the key order must match too"
