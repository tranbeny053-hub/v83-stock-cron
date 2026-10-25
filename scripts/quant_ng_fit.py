#!/usr/bin/env python3
"""Offline precondition gate and deterministic artifact writer for a future NG fit.

What this tool is for: before any fit may run, prove that the rows it would train
on are admissible. It refuses a corpus that reaches into the future (any row whose
horizon ends at or after the cutoff) or into a span already spent on a look, writes
a deterministic artifact describing exactly what it accepted, and does nothing else.

What it deliberately does NOT do, because the owner has not decided it yet:

* **No estimator and no fitted constant.** The method and the proposed constants are
  open decisions (OD-NG-2 and OD-NG-7), so the artifact records
  ``"estimator": "NOT_IMPLEMENTED_PENDING_OD_NG_2_AND_OD_NG_7"`` and carries no
  number from a fit.
* **Snapshot validation without row membership checks.** The snapshot must carry the
  ruled builder's identity — its id, status, ruled rule digest and firewall. Those are
  identity fields only: they do not prove the builder produced the file, and its
  members and evidence are not re-checked. This tool does not check that each row's
  symbol is a member of the snapshot. A fit spanning several quarters needs several
  snapshots, and how a plan names them is an open design question.
* **No network and no real-data mode.** There is no fetch and no flag that enables
  one. The consumed one-shot output folders and the research trees are refused by
  name, wherever they resolve.

Plan schema (all keys required; an unknown key is a REFUSAL)::

    {"plan_id": "ucpe.quant_ng.fit.v1",
     "cutoff_utc": "<ISO-8601 Z>",      # a row may mature strictly before this only
     "corpus": {"path": "<file>", "sha256": "<64 lowercase hex>"},
     "universe_snapshot": {"path": "<file>", "sha256": "<64 lowercase hex>"},
     "consumed_spans": [{"label": "<s>", "start_utc": "<ISO Z>", "end_utc": "<ISO Z>"}],
     "output_dir": "<a new or empty folder>"}

``consumed_spans`` must be present; an empty list states that none apply. Spans are
half-open ``[start, end)``, so a row ending exactly at ``start`` is admissible and one
beginning there is not.

The corpus is ``{"rows": [{"symbol", "timeframe", "predicted_at_utc",
"horizon_end_utc", "label"}]}`` with ``label`` in {UP, DOWN, TIMEOUT}. The universe
snapshot is pinned and checked against the ruled snapshot identity.

A plan may name an input anywhere on disk: the digest pin, not the location, fixes the
bytes. What a path may never be is a symlink, a protected name, or inside a forbidden
tree.

``artifact_id`` is ``"ngfit-"`` plus the first 16 hex characters of SHA-256 over
``"\\n".join([plan_sha256, corpus_sha256, universe_snapshot_sha256, cutoff_utc])``.

Determinism is the acceptance property: the artifact holds no timestamp, hostname,
absolute path or random value, and every mapping this tool builds is written in a fixed
order, so the same plan run twice into two fresh output folders produces byte-identical
files. (``consumed_spans`` echoes the plan's own key order, which the plan's digest pins.)

Usage: ``python -I -B scripts/quant_ng_fit.py --plan <plan.json>``; exit 0 PASS,
exit 2 REFUSAL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PLAN_KEYS = {
    "plan_id",
    "cutoff_utc",
    "corpus",
    "universe_snapshot",
    "consumed_spans",
    "output_dir",
}
PIN_KEYS = {"path", "sha256"}
SPAN_KEYS = {"label", "start_utc", "end_utc"}
ROW_KEYS = {"symbol", "timeframe", "predicted_at_utc", "horizon_end_utc", "label"}
LABELS = ("UP", "DOWN", "TIMEOUT")
# Digest of the owner-ruled ops/quant_ng/UNIVERSE_RULE_v1.json, also pinned by quant_ng_corpus.py.
UNIVERSE_RULE_V1_SHA256 = "1f81113bb00983a17fa5924569c30a9982efac83676f9495c106cd5bf3cfbb39"
PROTECTED = ("5a", "f3", "look_run", "holdout", "sealed", "f2_")
# Consumed one-shot outputs and the research trees: never an input to this tool.
# These are deliberately absolute, not relative to the checkout: the data they protect exists at
# exactly this location on the owner's machine, and a worktree's own .work holds no such data. A
# clone elsewhere therefore has nothing to refuse; the protected-name fragments above still apply.
_WORK = Path("/Users/kha/Documents/Kha-app/UCPE/.work")
FORBIDDEN_TREES = (
    _WORK / "v1d_1w_20261023/s1_output",
    _WORK / "v1d_1w_20261023/eval/output",
    _WORK / "research3",
    _WORK / "research",
)
UTC_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")
HEX_RE = re.compile(r"^[0-9a-f]{64}$")
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
FS_EVENTS = {
    "os.mkdir",
    "os.rename",
    "os.remove",
    "os.rmdir",
    "os.chmod",
    "os.chown",
    "os.truncate",
    "os.link",
    "os.symlink",
    "os.utime",
}
PROCESS_EVENTS = (
    "subprocess.",
    "os.system",
    "os.exec",
    "os.spawn",
    "os.posix_spawn",
    "os.fork",
)


class Refusal(Exception):
    pass


def _instant(value: Any) -> datetime:
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        raise Refusal("malformed instant")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise Refusal("malformed instant") from exc


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject a duplicated JSON key instead of silently keeping the last one."""
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate key: {key}")
        seen[key] = value
    return seen


def _json_bytes(path: Path, reason: str) -> tuple[bytes, Any]:
    try:
        data = path.read_bytes()
        return data, json.loads(data, object_pairs_hook=_no_duplicate_keys)
    except (OSError, UnicodeError, ValueError) as exc:
        raise Refusal(reason) from exc


def _path(value: Any) -> Path:
    """Resolve a plan-named path, refusing symlinks, protected names and the trees above."""
    if not isinstance(value, str) or not value:
        raise Refusal("invalid path")
    candidate = Path(value)
    if not candidate.is_absolute():
        raise Refusal("path must be absolute")
    walked = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        walked = walked / part
        if walked.is_symlink():
            raise Refusal("symlink path")
    if any(fragment in part.lower() for part in candidate.parts for fragment in PROTECTED):
        raise Refusal("protected path")
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, ValueError) as exc:
        raise Refusal("invalid path") from exc
    for tree in FORBIDDEN_TREES:
        if resolved == tree or tree in resolved.parents:
            raise Refusal("forbidden tree")
    return resolved


def create_readonly(path: Path, payload: bytes) -> None:
    """Create path exclusively at 0444, set the mode first, and remove it on any failure."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        os.fchmod(fd, 0o444)
        view = memoryview(payload)
        while view:
            view = view[os.write(fd, view) :]
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    finally:
        os.close(fd)


def _inside(target: Path, allowed: Path | None) -> bool:
    return allowed is not None and (target == allowed or allowed in target.parents)


def guard_reason(event: str, args: tuple[Any, ...], allowed: Path | None) -> str | None:
    """Return why this audit event must be refused, or None.

    A pure decision, so it can be tested without installing a hook: an audit hook
    cannot be uninstalled, and installing one inside a test process would make every
    later write in that process raise.
    """
    if event.startswith("socket.") or event.startswith(PROCESS_EVENTS):
        return f"forbidden event: {event}"
    if event.startswith("shutil.") or event in FS_EVENTS:
        for arg in args:
            if isinstance(arg, (str, bytes, os.PathLike)):
                try:
                    target = Path(os.fsdecode(arg)).resolve(strict=False)
                except (OSError, ValueError, TypeError):
                    continue
                if not _inside(target, allowed):
                    return f"filesystem change outside the output folder: {event}"
        return None
    if event != "open":
        return None
    mode = args[1] if len(args) > 1 else None
    flags = args[2] if len(args) > 2 else None
    writing = (
        any(flag in mode for flag in "wax+")
        if isinstance(mode, str)
        else isinstance(flags, int) and bool(flags & WRITE_FLAGS)
    )
    if not writing:
        return None
    try:
        target = Path(os.fsdecode(args[0])).resolve(strict=False)
    except BaseException:
        # An open this cannot resolve (a file descriptor, say) is never a path write.
        return None
    if not _inside(target, allowed):
        return "write outside the output folder"
    return None


def install_guard(output_holder: list[Path | None]) -> None:
    """Refuse network, processes and any write outside the output folder.

    The hook only refuses; it never contributes to the artifact, so what the artifact
    says does not depend on which files an interpreter happens to open.
    """

    def hook(event: str, args: tuple[Any, ...]) -> None:
        reason = guard_reason(event, args, output_holder[0])
        if reason:
            raise Refusal(reason)

    sys.addaudithook(hook)


def _digested_input(plan: dict[str, Any], name: str) -> tuple[Path, Any, str]:
    pin = plan[name]
    if (
        not isinstance(pin, dict)
        or set(pin) != PIN_KEYS
        or not isinstance(pin["sha256"], str)
        or not HEX_RE.fullmatch(pin["sha256"])
    ):
        raise Refusal(f"malformed {name} pin")
    path = _path(pin["path"])
    data, parsed = _json_bytes(path, f"{name} unreadable")
    digest = hashlib.sha256(data).hexdigest()
    if digest != pin["sha256"]:
        raise Refusal(f"{name} digest mismatch")
    return path, parsed, digest


def _spans(plan: dict[str, Any]) -> list[tuple[dict[str, Any], datetime, datetime]]:
    raw = plan["consumed_spans"]
    if not isinstance(raw, list):
        raise Refusal("invalid consumed spans")
    out = []
    for span in raw:
        if (
            not isinstance(span, dict)
            or set(span) != SPAN_KEYS
            or not isinstance(span["label"], str)
        ):
            raise Refusal("invalid consumed span")
        start, end = _instant(span["start_utc"]), _instant(span["end_utc"])
        if start >= end:
            raise Refusal("invalid consumed span bounds")
        out.append((span, start, end))
    return out


def _rows(corpus: Any) -> list[tuple[dict[str, Any], datetime, datetime]]:
    if (
        not isinstance(corpus, dict)
        or set(corpus) != {"rows"}
        or not isinstance(corpus["rows"], list)
        or not corpus["rows"]
    ):
        raise Refusal("malformed corpus")
    out = []
    for row in corpus["rows"]:
        if (
            not isinstance(row, dict)
            or set(row) != ROW_KEYS
            or row.get("label") not in LABELS
            or not isinstance(row.get("symbol"), str)
            or not isinstance(row.get("timeframe"), str)
        ):
            raise Refusal("malformed row")
        predicted = _instant(row["predicted_at_utc"])
        horizon_end = _instant(row["horizon_end_utc"])
        if predicted >= horizon_end:
            raise Refusal("malformed row interval")
        out.append((row, predicted, horizon_end))
    return out


def _make_output(output: Path) -> list[Path]:
    """Create the output folder, returning the folders this call created, deepest first.

    A refusal must leave nothing behind, so the caller can unwind exactly what was made —
    ``mkdir(parents=True)`` can create several levels, not only the leaf.
    """
    missing: list[Path] = []
    probe = output
    while not probe.exists():
        missing.append(probe)
        if probe.parent == probe:
            break
        probe = probe.parent
    if not missing:
        return []
    try:
        output.mkdir(parents=True)
    except (OSError, ValueError) as exc:
        raise Refusal(f"cannot create the output folder: {type(exc).__name__}") from exc
    return missing


def _unwind(created: list[Path]) -> None:
    for path in created:
        try:
            path.rmdir()
        except OSError:
            return


def _overlaps(predicted: datetime, horizon_end: datetime, start: datetime, end: datetime) -> bool:
    """A row [predicted, horizon_end) against a half-open span [start, end)."""
    return predicted < end and horizon_end > start


def run(plan_arg: str) -> dict[str, Any]:
    output_holder: list[Path | None] = [None]
    install_guard(output_holder)

    plan_path = _path(plan_arg)
    plan_bytes, plan = _json_bytes(plan_path, "plan unreadable")
    if (
        not isinstance(plan, dict)
        or set(plan) != PLAN_KEYS
        or plan.get("plan_id") != "ucpe.quant_ng.fit.v1"
    ):
        raise Refusal("invalid plan")
    cutoff = _instant(plan["cutoff_utc"])
    corpus_path, corpus, corpus_sha = _digested_input(plan, "corpus")
    universe_path, universe, universe_sha = _digested_input(plan, "universe_snapshot")
    if not isinstance(universe, dict):
        raise Refusal("universe snapshot is not a ruled snapshot")
    if universe.get("snapshot_id") != "ucpe.universe.asof.v2":
        raise Refusal("universe snapshot id is not ucpe.universe.asof.v2")
    if universe.get("status") != "SYNTHETIC":
        raise Refusal("universe snapshot status is not SYNTHETIC")
    if universe.get("rule_sha256") != UNIVERSE_RULE_V1_SHA256:
        raise Refusal("universe snapshot was not built under the ruled spec")
    if universe.get("f3_firewall") != "F-C":
        raise Refusal("universe snapshot firewall is not F-C")
    spans = _spans(plan)

    output = _path(plan["output_dir"])
    output_holder[0] = output
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise Refusal("output folder is not empty")

    rows = _rows(corpus)
    unmatured = sum(horizon_end >= cutoff for _, _, horizon_end in rows)
    if unmatured:
        raise Refusal(f"rows not matured before the cutoff: {unmatured}")

    consumed = sum(
        any(_overlaps(predicted, horizon_end, start, end) for _, start, end in spans)
        for _, predicted, horizon_end in rows
    )
    if consumed:
        labels = sorted(
            span["label"]
            for span, start, end in spans
            if any(_overlaps(p, h, start, end) for _, p, h in rows)
        )
        raise Refusal(f"rows inside consumed spans: {consumed}; spans: {','.join(labels)}")

    tool_path = Path(__file__).resolve()
    plan_sha = hashlib.sha256(plan_bytes).hexdigest()
    artifact_id = (
        "ngfit-"
        + hashlib.sha256(
            "\n".join([plan_sha, corpus_sha, universe_sha, plan["cutoff_utc"]]).encode()
        ).hexdigest()[:16]
    )

    by_pair: dict[str, int] = {}
    label_counts = dict.fromkeys(LABELS, 0)
    for row, _, _ in rows:
        key = f"{row['symbol']}|{row['timeframe']}"
        by_pair[key] = by_pair.get(key, 0) + 1
        label_counts[row["label"]] += 1

    artifact = {
        "artifact_id": artifact_id,
        "plan_id": plan["plan_id"],
        "tool_sha256": hashlib.sha256(tool_path.read_bytes()).hexdigest(),
        "plan_sha256": plan_sha,
        "corpus_sha256": corpus_sha,
        "universe_snapshot_sha256": universe_sha,
        "universe_snapshot_id": universe["snapshot_id"],
        "universe_status": universe["status"],
        "universe_rule_sha256": universe["rule_sha256"],
        "cutoff_utc": plan["cutoff_utc"],
        "consumed_spans": [span for span, _, _ in spans],
        "rows_total": len(rows),
        "rows_by_symbol_timeframe": {key: by_pair[key] for key in sorted(by_pair)},
        "label_counts": {label: label_counts[label] for label in LABELS},
        "estimator": "NOT_IMPLEMENTED_PENDING_OD_NG_2_AND_OD_NG_7",
        # The inputs this run read, by base name only: a closed set fixed by the plan,
        # so the artifact never depends on an interpreter's own opens or on a checkout.
        "inputs_read": ["corpus", "plan", "tool", "universe_snapshot"],
        "input_names": {
            "corpus": corpus_path.name,
            "plan": plan_path.name,
            "tool": tool_path.name,
            "universe_snapshot": universe_path.name,
        },
        "tool_version": "2",
        "schema_version": "2",
    }
    created = _make_output(output)
    try:
        payload = json.dumps(artifact, separators=(",", ":"), ensure_ascii=False) + "\n"
        create_readonly(output / "ARTIFACT.json", payload.encode())
    except (OSError, ValueError) as exc:
        _unwind(created)
        raise Refusal(f"cannot write the artifact: {type(exc).__name__}") from exc
    except BaseException:
        _unwind(created)
        raise
    return {"status": "PASS", "artifact_id": artifact_id}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    try:
        result = run(parser.parse_args(argv).plan)
    except Refusal as exc:
        print(json.dumps({"status": "REFUSAL", "reason": str(exc)}, separators=(",", ":")))
        return 2
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
