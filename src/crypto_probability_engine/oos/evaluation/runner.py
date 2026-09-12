"""Readiness and consumption runs for the section 5A evaluation.

Semantics are pre-registered in ``docs/SECTION_5A_EVALUATION_PREREGISTRATION.md``
§1 (readiness vs consumption), §3 (the five guards), §11 (snapshot identity) and
§12 (one-shot failure states).

THE LOOK IS CONSUMED WHEN THE PROBABILITIES ARE READ, not when a result is produced.
The seal is therefore armed immediately after the raw capture and before any statistic.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from crypto_probability_engine.oos.evaluation import diagnostics as diagnostics_module
from crypto_probability_engine.oos.evaluation.admission import admit
from crypto_probability_engine.oos.evaluation.decision import evaluate_timeframe
from crypto_probability_engine.oos.evaluation.evaluator_pin import (
    assert_evaluator_pin,
    current_pin_artifacts,
)
from crypto_probability_engine.oos.evaluation.lattice import window_count

MODE_READINESS = "readiness"
MODE_CONSUME = "consume"

CONFIRMATION_TOKEN = "CONSUME-SECTION-5A-ONE-LOOK"

STATE_NOT_STARTED = "NOT_STARTED"
STATE_SEALED_RAW_CAPTURED = "SEALED_RAW_CAPTURED"
STATE_COMPLETE = "COMPLETE"
STATE_SEALED_NO_RESULT = "SEALED_NO_RESULT"

# Contract instants (V1_QUANT_CONTRACT §5A.2). Not configurable: they are the contract.
T_FREEZE = datetime(2026, 8, 20, 11, 35, 56, tzinfo=UTC)
T0 = datetime(2026, 8, 21, 4, 0, 0, tzinfo=UTC)
T_CLOSE = datetime(2026, 9, 12, 4, 0, 0, tzinfo=UTC)
TIMEFRAMES = ("15m", "1H", "4H")
ATTAINABILITY_FLOOR_K4 = 5

SNAPSHOT_FILENAME = "snapshot.json"
RESULT_FILENAME = "result.json"
STATE_FILENAME = "state.json"


class OneLookAlreadyConsumed(RuntimeError):
    """A consumption artifact already exists; the holdout is evaluated exactly once."""


class ConsumptionRefused(RuntimeError):
    """A consumption guard refused before anything was read."""


class SnapshotTampered(RuntimeError):
    """The stored evidence or the rules changed since the seal was claimed."""


def evidence_snapshot_id(
    rows: Sequence[Mapping[str, Any]],
    *,
    feature_rows: Sequence[Mapping[str, Any]] = (),
    origin_anomalies: int = 0,
) -> str:
    """SHA-256 over ALL captured evidence, not only the scored rows (§11, finding F5).

    Feature rows and the anomaly count determine mandatory §5A.10 output, so two captures
    differing only in those are genuinely different evidence and must not share an id.
    """

    return hashlib.sha256(
        _canonical_json(
            {
                "rows": list(rows),
                "feature_rows": list(feature_rows),
                "origin_anomalies": int(origin_anomalies),
            }
        )
    ).hexdigest()


def result_inputs_digest(snapshot_id: str, pin_digest: str) -> str:
    """Bind the evidence to the RULES and the contract instants that scored it.

    Kept separate from ``evidence_snapshot_id`` deliberately: the evidence identity must
    stay stable when the evaluator changes, or drift could not be detected by comparison.
    """

    return hashlib.sha256(
        _canonical_json(
            {
                "evidence_snapshot_id": snapshot_id,
                "evaluator_pin_digest": pin_digest,
                "t_freeze": T_FREEZE.isoformat(),
                "t0": T0.isoformat(),
                "t_close": T_CLOSE.isoformat(),
                "timeframes": list(TIMEFRAMES),
            }
        )
    ).hexdigest()


def run_readiness(
    repository,
    *,
    now_utc: datetime | None = None,
    verify_pin: bool = True,
) -> dict[str, Any]:
    """Answer whether the evidence is adequate. Repeatable; never consumes the look.

    The probabilities are never loaded, so nothing here can compute a Brier value, a
    ``d``, or an ECE even by mistake.
    """

    # The pre-registration's freeze ordering says readiness may touch live data only
    # under a verified pin. The CLI reaches this directly, so the check belongs HERE and
    # not only in the workflow.
    if verify_pin:
        assert_evaluator_pin()

    evidence = repository.fetch_oos_paired_evidence(include_probabilities=False)
    _reject_any_probability(evidence)
    admission = admit(evidence, t0=T0, t_close=T_CLOSE)

    feature_rows = repository.fetch_oos_feature_diagnostics()
    origin_anomalies = repository.count_oos_origin_anomalies()
    block = diagnostics_module.build(
        admission,
        t0=T0,
        t_close=T_CLOSE,
        t_freeze=T_FREEZE,
        timeframes=TIMEFRAMES,
        feature_rows=feature_rows,
        origin_anomalies=origin_anomalies,
    )
    attainability = {
        timeframe: _attainability(timeframe, admission)
        for timeframe in TIMEFRAMES
    }
    return {
        "mode": MODE_READINESS,
        "generated_at_utc": (now_utc or datetime.now(UTC)).isoformat(),
        "consumes_one_look": False,
        "evidence_snapshot_id": evidence_snapshot_id(
            evidence, feature_rows=feature_rows, origin_anomalies=origin_anomalies
        ),
        "attainability": attainability,
        "diagnostics": block,
        "note": (
            "Readiness omits every probability column by construction, so no Brier, d "
            "or ECE is computable from what this run held."
        ),
    }


def run_consumption(
    repository,
    *,
    confirmation: str,
    artifact_dir: Path,
    now_utc: datetime | None = None,
    verify_pin: bool = True,
) -> dict[str, Any]:
    """Take the one look. Guards run first; the seal arms before any statistic."""

    moment = now_utc or datetime.now(UTC)
    artifact_dir = Path(artifact_dir)

    # G5, G1, G3 — strictly before anything is read.
    if moment < T_CLOSE:
        raise ConsumptionRefused(f"T_close has not passed: {T_CLOSE.isoformat()}")
    pin = current_pin_artifacts()
    if verify_pin:
        assert_evaluator_pin()
    if confirmation != CONFIRMATION_TOKEN:
        raise ConsumptionRefused("confirmation token absent or wrong; run is inert")

    # G2 — the DURABLE cross-run seal. A filesystem check is useless here: the workflow
    # gets a fresh runner per dispatch, so a local seal is always empty (finding F2).
    existing = repository.fetch_section_5a_seal()
    if existing is not None:
        raise OneLookAlreadyConsumed(
            "a durable section 5A seal already exists "
            f"(state={existing.get('state')}, evidence={existing.get('evidence_snapshot_id')}); "
            "the holdout is evaluated exactly once"
        )
    refuse_existing(artifact_dir)

    # Non-consequential reads happen BEFORE the probabilities, so that no fallible call
    # sits between the consumption and the seal (finding F3).
    origin_anomalies = repository.count_oos_origin_anomalies()
    feature_rows = repository.fetch_oos_feature_diagnostics()

    # Reading the probabilities IS the consumption.
    evidence = repository.fetch_oos_paired_evidence(include_probabilities=True)

    snapshot_id = evidence_snapshot_id(
        evidence, feature_rows=feature_rows, origin_anomalies=origin_anomalies
    )
    pin_digest = str(pin["closure_digest"])
    snapshot = {
        "captured_at_utc": moment.isoformat(),
        "evidence_snapshot_id": snapshot_id,
        "result_inputs_digest": result_inputs_digest(snapshot_id, pin_digest),
        "evaluator_pin_digest": pin_digest,
        "t_freeze": T_FREEZE.isoformat(),
        "t0": T0.isoformat(),
        "t_close": T_CLOSE.isoformat(),
        "timeframes": list(TIMEFRAMES),
        "origin_anomalies": origin_anomalies,
        "feature_rows": feature_rows,
        "rows": list(evidence),
    }

    # G4 — ONE atomic write claims the seal and captures the raw evidence together.
    # There is no interval in which the look is spent but unrecorded.
    claimed = repository.claim_section_5a_seal(
        {
            "sealed_at_utc": moment.isoformat(),
            "evidence_snapshot_id": snapshot_id,
            "result_inputs_digest": snapshot["result_inputs_digest"],
            "evaluator_pin_digest": pin_digest,
            "contract_instants": {
                "t_freeze": T_FREEZE.isoformat(),
                "t0": T0.isoformat(),
                "t_close": T_CLOSE.isoformat(),
                "timeframes": list(TIMEFRAMES),
            },
            "snapshot_payload": snapshot,
        }
    )
    if not claimed:
        raise OneLookAlreadyConsumed(
            "another run claimed the durable seal first; refusing a second look"
        )

    # The local artifact is SECONDARY: convenience and upload, never the authority.
    artifact_dir.mkdir(parents=True, exist_ok=True)
    _write(artifact_dir / SNAPSHOT_FILENAME, snapshot)
    _write_state(artifact_dir, STATE_SEALED_RAW_CAPTURED)

    try:
        result = compute_from_snapshot(snapshot, now_utc=moment)
    except Exception as exc:
        _write_state(artifact_dir, STATE_SEALED_NO_RESULT, detail=repr(exc))
        repository.advance_section_5a_seal_state(STATE_SEALED_NO_RESULT, repr(exc))
        raise
    _write(artifact_dir / RESULT_FILENAME, result)
    _write_state(artifact_dir, STATE_COMPLETE)
    repository.advance_section_5a_seal_state(STATE_COMPLETE)
    return result


def recompute_from_snapshot(
    artifact_dir: Path, *, now_utc: datetime | None = None, verify_pin: bool = True
) -> dict:
    """Recompute the decision from the immutable snapshot. NO database access.

    This is the recovery path for ``SEALED_NO_RESULT`` (§12): a statistics defect costs
    a recomputation, never the holdout. It may be run any number of times.
    """

    artifact_dir = Path(artifact_dir)
    snapshot = json.loads((artifact_dir / SNAPSHOT_FILENAME).read_text(encoding="utf-8"))

    # "Same evidence, same rules" must be ENFORCED, not asserted (finding F4).
    if verify_pin:
        assert_evaluator_pin()
    recomputed = evidence_snapshot_id(
        snapshot["rows"],
        feature_rows=snapshot.get("feature_rows", ()),
        origin_anomalies=int(snapshot.get("origin_anomalies", 0)),
    )
    if recomputed != snapshot.get("evidence_snapshot_id"):
        raise SnapshotTampered(
            "stored evidence does not match its recorded snapshot id; recomputation "
            f"refused (recorded={snapshot.get('evidence_snapshot_id')}, actual={recomputed})"
        )
    pin_digest = str(current_pin_artifacts()["closure_digest"])
    recorded_pin = snapshot.get("evaluator_pin_digest")
    if recorded_pin is not None and recorded_pin != pin_digest:
        raise SnapshotTampered(
            "the evaluator has changed since this snapshot was sealed; recomputing "
            "under different rules would be retuning against a holdout already seen"
        )

    result = compute_from_snapshot(snapshot, now_utc=now_utc)
    _write(artifact_dir / RESULT_FILENAME, result)
    _write_state(artifact_dir, STATE_COMPLETE)
    return result


def compute_from_snapshot(
    snapshot: Mapping[str, Any], *, now_utc: datetime | None = None
) -> dict[str, Any]:
    """Pure: snapshot in, decision out. Touches no repository and no clock-dependent state."""

    rows = [_revive(row) for row in snapshot["rows"]]
    admission = admit(rows, t0=T0, t_close=T_CLOSE)
    per_timeframe = {
        timeframe: evaluate_timeframe(timeframe, admission, t0=T0, t_close=T_CLOSE)
        for timeframe in TIMEFRAMES
    }
    block = diagnostics_module.build(
        admission,
        t0=T0,
        t_close=T_CLOSE,
        t_freeze=T_FREEZE,
        timeframes=TIMEFRAMES,
        feature_rows=snapshot.get("feature_rows", ()),
        origin_anomalies=int(snapshot.get("origin_anomalies", 0)),
    )
    return {
        "mode": MODE_CONSUME,
        "generated_at_utc": (now_utc or datetime.now(UTC)).isoformat(),
        "consumes_one_look": True,
        "evidence_snapshot_id": snapshot["evidence_snapshot_id"],
        "result_inputs_digest": snapshot.get("result_inputs_digest"),
        "evaluator_pin_digest": snapshot.get("evaluator_pin_digest"),
        "boundary_convention": 0.05,
        "boundary_convention_note": (
            "A pre-committed decision boundary, not a hypothesis test. It has no error "
            "rate and no reported quantity is a probability of being wrong."
        ),
        "per_timeframe": {
            timeframe: _render(result) for timeframe, result in per_timeframe.items()
        },
        "authorized_cells": sorted(
            cell
            for result in per_timeframe.values()
            for cell in result.authorized_cells
        ),
        "diagnostics": block,
        "licence_note": (
            "A PASS authorizes only the listed cells. No profitability claim, no "
            "per-asset superiority claim, and no claim beyond an authorized cell."
        ),
    }


def refuse_existing(artifact_dir: Path) -> None:
    snapshot = Path(artifact_dir) / SNAPSHOT_FILENAME
    if snapshot.exists():
        raise OneLookAlreadyConsumed(
            f"a consumption snapshot already exists at {snapshot}; refusing a second look"
        )


def read_state(artifact_dir: Path) -> str:
    path = Path(artifact_dir) / STATE_FILENAME
    if not path.exists():
        return STATE_NOT_STARTED
    return str(json.loads(path.read_text(encoding="utf-8")).get("state", STATE_NOT_STARTED))


def _attainability(timeframe: str, admission) -> dict[str, Any]:
    k4 = window_count(timeframe, 4, T0, T_CLOSE)
    usable = len(
        {
            _window_key(row, timeframe)
            for row in admission.admitted
            if row.get("timeframe") == timeframe
        }
        - {None}
    )
    verdict = "ATTAINABLE" if usable >= ATTAINABILITY_FLOOR_K4 else "PASS_UNATTAINABLE"
    return {
        "k_4_pre_drop": k4,
        "usable_windows_c4": usable,
        "floor": ATTAINABILITY_FLOOR_K4,
        "verdict": verdict,
        "basis": (
            "Follows from the lattice and the sampling frame alone (§5A.8); it cannot "
            "depend on candidate performance and can never create a PASS."
        ),
    }


def _window_key(row: Mapping[str, Any], timeframe: str) -> int | None:
    from crypto_probability_engine.oos.evaluation.lattice import assign_window_index

    return assign_window_index(row["reference_close_utc"], timeframe, 4, T0, T_CLOSE)


def _reject_any_probability(rows: Sequence[Mapping[str, Any]]) -> None:
    """Belt and braces: a readiness projection must carry no probability at all."""

    for row in rows:
        for key in row:
            if key.endswith(("_p_up_frac", "_p_down_frac", "_p_timeout_frac")):
                raise RuntimeError(
                    "readiness evidence carries a probability column; the structural "
                    "boundary that prevents a readiness run from scoring has been broken"
                )


def _render(result) -> dict[str, Any]:
    return {
        "state": result.state,
        "authorized": bool(result.authorized_cells),
        "reason": result.reason,
        "admitted_pairs": result.admitted_pairs,
        "a_holds": result.a_holds,
        "coarsenings": [
            {
                "coarsening": c.coarsening,
                "k_pre_drop": c.k_pre_drop,
                "usable_windows": c.usable_windows,
                "dropped_windows": c.dropped_windows,
                "a1_holds": c.a1_holds,
                "a1_boundary_statistic": c.a1_boundary_statistic,
                "a2_holds": c.a2_holds,
                "a2_boundary_statistic": c.a2_boundary_statistic,
                "a2_negative_windows": c.a2_negative_windows,
            }
            for c in result.coarsenings
        ],
        "b1_holds": result.b1_holds,
        "b1_ece_baseline": result.b1_ece_baseline,
        "b1_ece_candidate": result.b1_ece_candidate,
        "b2_holds": result.b2_holds,
        "b2_n_worse": result.b2_n_worse,
        "b2_n_better": result.b2_n_better,
        "b_holds": result.b_holds,
        "per_symbol": {
            symbol: {
                "covered": value.covered,
                "n_worse": value.n_worse,
                "n_better": value.n_better,
                "holds": value.holds,
            }
            for symbol, value in result.per_symbol.items()
        },
        "fail_checks": [
            {"name": c.name, "status": c.status, "detail": c.detail}
            for c in result.fail_checks
        ],
        "authorized_cells": list(result.authorized_cells),
    }


def _revive(row: Mapping[str, Any]) -> dict[str, Any]:
    revived = dict(row)
    for key, value in list(revived.items()):
        if key.endswith("_utc") or key == "reference_close_utc":
            revived[key] = _parse(value)
    return revived


def _parse(value: Any) -> Any:
    if isinstance(value, datetime) or value is None:
        return value
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _write(path: Path, payload: Any) -> None:
    path.write_bytes(_pretty_json(payload))


def _write_state(artifact_dir: Path, state: str, *, detail: str = "") -> None:
    _write(Path(artifact_dir) / STATE_FILENAME, {"state": state, "detail": detail})


def _default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"unserializable value in evidence: {type(value)!r}")


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=_default,
    ).encode("utf-8")


def _pretty_json(value: Any) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True, default=_default).encode("utf-8")
