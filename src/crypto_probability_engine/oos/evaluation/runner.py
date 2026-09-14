"""Readiness and consumption runs for the section 5A evaluation.

Semantics are pre-registered in ``docs/SECTION_5A_EVALUATION_PREREGISTRATION.md``
§1 (readiness vs consumption), §3 (the guards), §11 (snapshot identity) and §12 (one-shot
failure states), as amended by the owner rulings of Addendum 2.

THE LOOK IS SPENT WHEN THE PROBABILITIES ARE EXPOSED. So the one-shot seal is claimed,
durably and atomically, BEFORE any probability is exposed — never after (findings G1.1, G3).
On Postgres the probabilities are additionally returned only once they are durably captured
into that claimed seal, so there is no state in which the look was exposed but unrecorded.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from crypto_probability_engine.oos.evaluation import diagnostics as diagnostics_module
from crypto_probability_engine.oos.evaluation.admission import admit
from crypto_probability_engine.oos.evaluation.decision import evaluate_timeframe
from crypto_probability_engine.oos.evaluation.evaluator_pin import (
    assert_evaluator_pin,
    current_pin_artifacts,
)
from crypto_probability_engine.oos.evaluation.lattice import (
    assign_window_index,
    window_count,
)
from crypto_probability_engine.oos.evaluation.provenance import (
    ProvenanceRefused,
    require_verified_provenance,
)
from crypto_probability_engine.oos.evaluation.scope import TRANCHE_1_TIMEFRAMES
from crypto_probability_engine.utils import canonical_json
from crypto_probability_engine.utils.canonical_json import CanonicalEncodingError

MODE_READINESS = "readiness"
MODE_CONSUME = "consume"

CONFIRMATION_TOKEN = "CONSUME-SECTION-5A-ONE-LOOK"

SEAL_AUTHORITY_POSTGRES = "POSTGRES_DURABLE"

STATE_NOT_STARTED = "NOT_STARTED"
STATE_CLAIMED = "CLAIMED"
STATE_SEALED_RAW_CAPTURED = "SEALED_RAW_CAPTURED"
STATE_COMPLETE = "COMPLETE"
STATE_SEALED_NO_RESULT = "SEALED_NO_RESULT"
STATE_CAPTURE_FAILED = "CAPTURE_FAILED"

# Contract instants (V1_QUANT_CONTRACT §5A.2). Not configurable: they are the contract.
T_FREEZE = datetime(2026, 8, 20, 11, 35, 56, tzinfo=UTC)
T0 = datetime(2026, 8, 21, 4, 0, 0, tzinfo=UTC)
T_CLOSE = datetime(2026, 9, 12, 4, 0, 0, tzinfo=UTC)
TIMEFRAMES = TRANCHE_1_TIMEFRAMES  # one scope definition (V807-F1)
ATTAINABILITY_FLOOR_K4 = 5

SNAPSHOT_FILENAME = "snapshot.json"
RESULT_FILENAME = "result.json"
STATE_FILENAME = "state.json"

# Every field recomputation trusts. Absence is tampering, never permission (G2.1, G10).
REQUIRED_SNAPSHOT_FIELDS = (
    "evidence_snapshot_id",
    "result_inputs_digest",
    "evaluator_pin_digest",
    "t_freeze",
    "t0",
    "t_close",
    "timeframes",
    "origin_anomalies",
    "feature_rows",
    "rows",
)
_DIGEST_FIELDS = ("evidence_snapshot_id", "result_inputs_digest", "evaluator_pin_digest")


class OneLookAlreadyConsumed(RuntimeError):
    """A durable seal already exists; the holdout is evaluated exactly once."""


class ConsumptionRefused(RuntimeError):
    """A consumption guard refused before any probability was exposed."""


class ReadinessRefused(RuntimeError):
    """A readiness run refused its inputs (V807-R2: readiness is not a consumption)."""


class SnapshotTampered(RuntimeError):
    """Captured evidence, its digests, or the rules differ from what was sealed."""


# --------------------------------------------------------------------------- identity


def evidence_snapshot_id(
    rows: Sequence[Mapping[str, Any]],
    *,
    feature_rows: Sequence[Mapping[str, Any]] = (),
    origin_anomalies: int | Decimal = 0,
) -> str:
    """SHA-256 over ALL captured evidence, canonically and order-independently.

    - Rows and feature rows are MULTISETS: driver order carries no meaning and cannot change
      the identity (G5.3).
    - Values are canonicalized losslessly and driver-independently, so ``Decimal`` from psycopg
      and ``float`` hash identically when they are the same value (G1.3, G1.4), and a snapshot
      read back from disk digests exactly as it did when captured.
    """

    body = {
        "rows": canonical_json.canonical_multiset(rows),
        "feature_rows": canonical_json.canonical_multiset(feature_rows),
        "origin_anomalies": canonical_json.encode(origin_anomalies),
    }
    return hashlib.sha256(canonical_json.serialize(body)).hexdigest()


_PROBABILITY_SUFFIXES = ("_p_up_frac", "_p_down_frac", "_p_timeout_frac")


def decision_population_id(rows: Sequence[Mapping[str, Any]]) -> str:
    """Probability-free identity of the population that can affect the decision (ruling D4).

    DISTINCT FROM ``evidence_snapshot_id``. That identity authenticates everything a consumption
    captured, probabilities included, and so can never equal anything a readiness run computes.
    This one is computed identically by readiness and by consumption, so comparing the two is a
    genuine drift check (V807-F2, pre-registration §11 as corrected).

    Its population is exactly what admission can admit: IN SCOPE (tranche-1 cells) and IN THE
    HOLDOUT (T0 <= reference_close_utc < T_close). Rows collected after T_close, rows of other
    assets, feature rows and the anomaly count are excluded, so the identity cannot drift when no
    decision input changed (V807-F9). Outcome labels ARE included: a pair resolving between
    readiness and consumption changes what is admitted, and must change the identity.
    """

    population = []
    for row in rows:
        admitted_now = admit([row], t0=T0, t_close=T_CLOSE)
        if not (admitted_now.tier1_in_holdout):
            continue
        population.append(
            {key: value for key, value in row.items() if not key.endswith(_PROBABILITY_SUFFIXES)}
        )
    return hashlib.sha256(
        canonical_json.serialize({"population": canonical_json.canonical_multiset(population)})
    ).hexdigest()


def result_inputs_digest(snapshot_id: str, pin_digest: str) -> str:
    """Bind the evidence to the RULES and contract instants that scored it.

    Separate from ``evidence_snapshot_id`` on purpose: the evidence identity must stay stable
    when the evaluator changes, or drift could not be detected by comparison.
    """

    return hashlib.sha256(
        canonical_json.dumps(
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


# --------------------------------------------------------------------------- readiness


def run_readiness(
    repository,
    *,
    now_utc: datetime | None = None,
    verify_pin: bool = True,
) -> dict[str, Any]:
    """Answer whether the evidence is adequate. Repeatable; never consumes the look.

    The probabilities are never loaded, so nothing here can compute a Brier value, a ``d``,
    or an ECE even by mistake.
    """

    if verify_pin:
        assert_evaluator_pin()

    evidence = repository.fetch_oos_paired_evidence(include_probabilities=False)
    _reject_any_probability(evidence)
    admission = admit(evidence, t0=T0, t_close=T_CLOSE)

    feature_rows = repository.fetch_oos_feature_diagnostics()
    origin_anomalies = _measured_count(
        repository.count_oos_origin_anomalies(), error=ReadinessRefused
    )
    block = diagnostics_module.build(
        admission,
        t0=T0,
        t_close=T_CLOSE,
        t_freeze=T_FREEZE,
        timeframes=TIMEFRAMES,
        feature_rows=feature_rows,
        origin_anomalies=origin_anomalies,
    )
    return {
        "mode": MODE_READINESS,
        "generated_at_utc": (now_utc or datetime.now(UTC)).isoformat(),
        "consumes_one_look": False,
        "decision_population_id": decision_population_id(evidence),
        "evidence_snapshot_id": evidence_snapshot_id(
            evidence, feature_rows=feature_rows, origin_anomalies=origin_anomalies
        ),
        "identity_note": (
            "Compare decision_population_id with a consumption's to detect drift. "
            "evidence_snapshot_id authenticates a capture and differs by construction."
        ),
        "attainability": {
            timeframe: _attainability(timeframe, admission) for timeframe in TIMEFRAMES
        },
        "diagnostics": block,
        "note": (
            "Readiness omits every probability column by construction, so no Brier, d or ECE "
            "is computable from what this run held."
        ),
    }


# --------------------------------------------------------------------------- consumption


def run_consumption(
    repository,
    *,
    confirmation: str,
    artifact_dir: Path,
    now_utc: datetime | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Take the one look.

    Order is the safety property: every guard, then a DURABLE ATOMIC CLAIM, then — and only
    then — the probability read. A failure after the claim leaves the look durably recorded as
    spent; a failure before it spends nothing.

    OWNER RULING D3: there is no switch to skip pin verification and no acceptance of an
    undeclared authority. Both are verified positively, every time, before anything is claimed.

    OWNER RULING E2=A: ``provenance`` is the verified dispatch record from
    :func:`provenance.attest`. When given it is re-verified before the repository is touched,
    then written into the durable claim and the snapshot. The production entrypoint always
    supplies it, and the durable Postgres authority refuses a claim without it, so its absence
    is permitted only for declared test doubles, exactly as D3 permits them to declare the
    authority.
    """

    moment = now_utc or datetime.now(UTC)
    if moment.tzinfo is None:
        raise ConsumptionRefused("now_utc must be timezone-aware")
    artifact_dir = Path(artifact_dir)

    # Guards, strictly before anything is claimed or read.
    if moment < T_CLOSE:
        raise ConsumptionRefused(f"T_close has not passed: {T_CLOSE.isoformat()}")
    require_durable_authority(repository)
    assert_evaluator_pin()
    pin_digest = str(current_pin_artifacts()["closure_digest"])
    if confirmation != CONFIRMATION_TOKEN:
        raise ConsumptionRefused("confirmation token absent or wrong; run is inert")
    if provenance is not None:
        provenance = require_verified_provenance(provenance)

    existing = repository.fetch_section_5a_seal()
    if existing is not None:
        raise OneLookAlreadyConsumed(
            "a durable section 5A seal already exists "
            f"(state={existing.get('state')}); the holdout is evaluated exactly once"
        )
    refuse_existing(artifact_dir)

    # Non-consequential reads: no probability is exposed by either.
    origin_anomalies = _measured_count(repository.count_oos_origin_anomalies())
    feature_rows = list(repository.fetch_oos_feature_diagnostics())

    # THE CLAIM — durable and atomic, BEFORE any probability exposure. Only the claimant may
    # read, so two concurrent consumers can never both see the holdout (G3.1).
    claimed = repository.claim_section_5a_seal(
        {
            "sealed_at_utc": moment.isoformat(),
            "evaluator_pin_digest": pin_digest,
            "contract_instants": _contract_instants(),
            "run_provenance": provenance,
        }
    )
    if not claimed:
        raise OneLookAlreadyConsumed(
            "another run claimed the durable seal first; refusing a second look"
        )

    # From here the look is durably recorded as spent, whatever happens next.
    try:
        evidence = list(repository.fetch_oos_paired_evidence(include_probabilities=True))
        snapshot = _build_snapshot(
            moment=moment,
            pin_digest=pin_digest,
            evidence=evidence,
            feature_rows=feature_rows,
            origin_anomalies=origin_anomalies,
            provenance=provenance,
        )
        repository.capture_section_5a_snapshot(snapshot)
    except Exception as exc:
        _record_terminal_state(repository, STATE_CAPTURE_FAILED, exc)
        raise

    # The local artifact is SECONDARY: convenience and upload, never the authority.
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / SNAPSHOT_FILENAME).write_bytes(_pretty_json(snapshot))
    _write_state(artifact_dir, STATE_SEALED_RAW_CAPTURED)

    try:
        result = compute_from_snapshot(snapshot, now_utc=moment)
    except Exception as exc:
        _write_state(artifact_dir, STATE_SEALED_NO_RESULT, detail=repr(exc))
        _record_terminal_state(repository, STATE_SEALED_NO_RESULT, exc)
        raise
    _write_report(artifact_dir / RESULT_FILENAME, result)
    _write_state(artifact_dir, STATE_COMPLETE)
    repository.advance_section_5a_seal_state(STATE_COMPLETE)
    return result


# --------------------------------------------------------------------------- recovery


def verify_snapshot_integrity(snapshot: Any, *, verify_pin: bool = True) -> None:
    """Fail closed unless the snapshot is complete, untampered, and scored by today's rules.

    Every trusted field is checked (G2.3). A missing field is tampering, not a default (G2.1,
    G10). The recorded pin is compared with the running evaluator regardless of
    ``verify_pin``, which only additionally checks the on-disk files against the committed pin.
    """

    if not isinstance(snapshot, Mapping):
        raise SnapshotTampered("snapshot is not a mapping")
    missing = [field for field in REQUIRED_SNAPSHOT_FIELDS if field not in snapshot]
    if missing:
        raise SnapshotTampered(f"snapshot is missing trusted field(s) {missing}; refused")
    for field in _DIGEST_FIELDS:
        if not _is_sha256_hex(snapshot[field]):
            raise SnapshotTampered(f"snapshot {field} is not a SHA-256 digest; refused")
    for field, expected in _contract_instants().items():
        if snapshot[field] != expected:
            raise SnapshotTampered(
                f"snapshot {field} is {snapshot[field]!r}, not the contract's {expected!r}"
            )
    if not isinstance(snapshot["rows"], list) or not isinstance(snapshot["feature_rows"], list):
        raise SnapshotTampered("snapshot rows and feature_rows must be lists; refused")
    anomalies = _measured_count(snapshot["origin_anomalies"], tampered=True)

    if verify_pin:
        assert_evaluator_pin()
    current_pin = str(current_pin_artifacts()["closure_digest"])
    if snapshot["evaluator_pin_digest"] != current_pin:
        raise SnapshotTampered(
            "the evaluator has changed since this snapshot was sealed; recomputing under "
            "different rules would be retuning against a holdout already seen"
        )
    recomputed = evidence_snapshot_id(
        snapshot["rows"], feature_rows=snapshot["feature_rows"], origin_anomalies=anomalies
    )
    if recomputed != snapshot["evidence_snapshot_id"]:
        raise SnapshotTampered(
            "stored evidence does not match its recorded snapshot id; recomputation refused "
            f"(recorded={snapshot['evidence_snapshot_id']}, actual={recomputed})"
        )
    expected_inputs = result_inputs_digest(recomputed, snapshot["evaluator_pin_digest"])
    if expected_inputs != snapshot["result_inputs_digest"]:
        raise SnapshotTampered(
            "result_inputs_digest does not bind this evidence to these rules; it is "
            "recomputed and compared, never trusted as recorded"
        )


def recompute_from_snapshot(
    artifact_dir: Path, *, now_utc: datetime | None = None, verify_pin: bool = True
) -> dict:
    """Offline audit: recompute from a local artifact. NO database access.

    The local artifact is secondary; the durable authority is the Postgres seal, which
    :func:`recompute_from_seal` reads. Both apply identical integrity verification.
    """

    artifact_dir = Path(artifact_dir)
    raw = (artifact_dir / SNAPSHOT_FILENAME).read_bytes()
    try:
        snapshot = canonical_json.loads(raw)
    except (ValueError, CanonicalEncodingError) as exc:
        raise SnapshotTampered(f"snapshot cannot be decoded canonically: {exc}") from exc
    verify_snapshot_integrity(snapshot, verify_pin=verify_pin)
    result = compute_from_snapshot(snapshot, now_utc=now_utc)
    _write_report(artifact_dir / RESULT_FILENAME, result)
    _write_state(artifact_dir, STATE_COMPLETE)
    return result


def recompute_from_seal(repository, *, now_utc: datetime | None = None) -> dict:
    """Recover from the DURABLE seal. Reads the captured evidence, never the predictions.

    Recomputing from captured evidence under verified-identical rules is the same look, not a
    second one. It also cross-checks the snapshot against the raw rows Postgres captured
    before exposure, so a snapshot that diverges from what was actually read is refused.
    """

    require_durable_authority(repository)
    assert_evaluator_pin()
    seal = repository.fetch_section_5a_seal()
    if seal is None:
        raise ConsumptionRefused("no section 5A seal exists; there is nothing to recompute")
    snapshot = seal.get("snapshot_payload")
    if snapshot is None:
        raise ConsumptionRefused(
            f"the seal is {seal.get('state')} with no captured snapshot; recovery needs an "
            "owner decision and must not re-read the holdout"
        )
    verify_snapshot_integrity(snapshot, verify_pin=True)
    for field in _DIGEST_FIELDS:
        if seal.get(field) != snapshot[field]:
            raise SnapshotTampered(f"seal {field} disagrees with its captured snapshot")
    # V807-F10: the durable claim's own contract instants must agree with the contract.
    if seal.get("contract_instants") != _contract_instants():
        raise SnapshotTampered("the seal's claimed contract instants disagree with the contract")
    # E2=A: recovery blesses only a look taken by a verified dispatch, and the snapshot must name
    # the same run the durable claim recorded.
    try:
        recorded_run = require_verified_provenance(seal.get("run_provenance"))
    except ProvenanceRefused as exc:
        raise SnapshotTampered(
            f"the durable seal does not carry a verified run provenance: {exc}"
        ) from exc
    if canonical_json.dumps(snapshot.get("run_provenance")) != canonical_json.dumps(recorded_run):
        raise SnapshotTampered("the snapshot's run provenance differs from the durable claim's")
    captured = seal.get("captured_rows")
    if captured is None:
        raise SnapshotTampered("the durable seal lacks the raw capture it was exposed from")
    if canonical_json.canonical_multiset(captured) != canonical_json.canonical_multiset(
        snapshot["rows"]
    ):
        raise SnapshotTampered(
            "the snapshot's rows differ from what Postgres captured before exposure"
        )
    result = compute_from_snapshot(snapshot, now_utc=now_utc)
    if seal.get("state") in {STATE_SEALED_RAW_CAPTURED, STATE_SEALED_NO_RESULT}:
        repository.advance_section_5a_seal_state(STATE_COMPLETE)
    return result


def compute_from_snapshot(
    snapshot: Mapping[str, Any], *, now_utc: datetime | None = None
) -> dict[str, Any]:
    """Pure: snapshot in, decision out. Touches no repository."""

    missing = [field for field in REQUIRED_SNAPSHOT_FIELDS if field not in snapshot]
    if missing:
        raise SnapshotTampered(f"snapshot is missing trusted field(s) {missing}; refused")
    rows = [dict(row) for row in snapshot["rows"]]
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
        feature_rows=snapshot["feature_rows"],
        origin_anomalies=_measured_count(snapshot["origin_anomalies"], tampered=True),
    )
    return {
        "mode": MODE_CONSUME,
        "generated_at_utc": (now_utc or datetime.now(UTC)).isoformat(),
        "consumes_one_look": True,
        "decision_population_id": decision_population_id(snapshot["rows"]),
        "evidence_snapshot_id": snapshot["evidence_snapshot_id"],
        "result_inputs_digest": snapshot["result_inputs_digest"],
        "evaluator_pin_digest": snapshot["evaluator_pin_digest"],
        "run_provenance": snapshot.get("run_provenance"),
        "boundary_convention": 0.05,
        "boundary_convention_note": (
            "A pre-committed decision boundary, not a hypothesis test. It has no error rate "
            "and no reported quantity is a probability of being wrong."
        ),
        "per_timeframe": {
            timeframe: _render(result) for timeframe, result in per_timeframe.items()
        },
        "authorized_cells": sorted(
            cell for result in per_timeframe.values() for cell in result.authorized_cells
        ),
        "diagnostics": block,
        "licence_note": (
            "A PASS authorizes only the listed cells. No profitability claim, no per-asset "
            "superiority claim, and no claim beyond an authorized cell."
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


# --------------------------------------------------------------------------- helpers


def require_durable_authority(repository) -> None:
    """Fail closed unless the repository POSITIVELY declares the durable Postgres authority.

    OWNER RULING D3 (V807-F4). Absence of a declaration is refusal, never permission: a repository
    that does not say what kind of seal it provides cannot be trusted to provide a durable one.
    """

    declare = getattr(repository, "section_5a_seal_authority", None)
    if not callable(declare):
        raise ConsumptionRefused(
            "repository does not declare a seal authority; the one-look seal requires a "
            "positively declared durable Postgres authority, so this is refused"
        )
    authority = declare()
    if authority != SEAL_AUTHORITY_POSTGRES:
        raise ConsumptionRefused(
            f"repository declares seal authority {authority!r}; the one-look seal must be a "
            "durable Postgres authority, so this is refused"
        )


def _contract_instants() -> dict[str, Any]:
    return {
        "t_freeze": T_FREEZE.isoformat(),
        "t0": T0.isoformat(),
        "t_close": T_CLOSE.isoformat(),
        "timeframes": list(TIMEFRAMES),
    }


def _build_snapshot(
    *,
    moment: datetime,
    pin_digest: str,
    evidence: list[Mapping[str, Any]],
    feature_rows: list[Mapping[str, Any]],
    origin_anomalies: int,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot_id = evidence_snapshot_id(
        evidence, feature_rows=feature_rows, origin_anomalies=origin_anomalies
    )
    return {
        "captured_at_utc": moment.isoformat(),
        "evidence_snapshot_id": snapshot_id,
        "result_inputs_digest": result_inputs_digest(snapshot_id, pin_digest),
        "evaluator_pin_digest": pin_digest,
        **_contract_instants(),
        "origin_anomalies": origin_anomalies,
        "feature_rows": feature_rows,
        "rows": evidence,
        "run_provenance": None if provenance is None else dict(provenance),
    }


def _record_terminal_state(repository, state: str, exc: BaseException) -> None:
    """Record a failure on the durable seal without masking the failure that caused it."""

    try:
        repository.advance_section_5a_seal_state(state, repr(exc))
    except Exception as secondary:  # the seal remains CLAIMED at minimum: still recorded
        exc.add_note(f"additionally, recording state {state} failed: {secondary!r}")


def _measured_count(
    value: Any, *, tampered: bool = False, error: type[Exception] | None = None
) -> int:
    """A count that was actually measured: a non-negative integer, never a stand-in."""

    error = error or (SnapshotTampered if tampered else ConsumptionRefused)
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise error(f"origin anomaly count is not a measured integer: {value!r}")
    if isinstance(value, Decimal) and (not value.is_finite() or value != value.to_integral()):
        raise error(f"origin anomaly count is not an integer: {value!r}")
    if value < 0:
        raise error(f"origin anomaly count is negative: {value!r}")
    return int(value)


def _is_sha256_hex(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _attainability(timeframe: str, admission) -> dict[str, Any]:
    usable = len(
        {
            assign_window_index(row["reference_close_utc"], timeframe, 4, T0, T_CLOSE)
            for row in admission.admitted
            if row.get("timeframe") == timeframe
        }
        - {None}
    )
    return {
        "k_4_pre_drop": window_count(timeframe, 4, T0, T_CLOSE),
        "usable_windows_c4": usable,
        "floor": ATTAINABILITY_FLOOR_K4,
        "verdict": "ATTAINABLE" if usable >= ATTAINABILITY_FLOOR_K4 else "PASS_UNATTAINABLE",
        "basis": (
            "Follows from the lattice and the sampling frame alone (§5A.8); it cannot depend on "
            "candidate performance and can never create a PASS."
        ),
    }


def _reject_any_probability(rows: Sequence[Mapping[str, Any]]) -> None:
    """Belt and braces: a readiness projection must carry no probability at all."""

    for row in rows:
        for key in row:
            if key.endswith(("_p_up_frac", "_p_down_frac", "_p_timeout_frac")):
                raise RuntimeError(
                    "readiness evidence carries a probability column; the structural boundary "
                    "that prevents a readiness run from scoring has been broken"
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


def _canonical_json(value: Any) -> bytes:
    """The single evidence serializer (shared with the Postgres seal; finding G9)."""

    return canonical_json.dumps(value)


def _pretty_json(value: Any) -> bytes:
    """Canonical, round-trip-stable snapshot text: a written snapshot digests as captured."""

    return canonical_json.pretty(value)


def _write_state(artifact_dir: Path, state: str, *, detail: str = "") -> None:
    _write_report(Path(artifact_dir) / STATE_FILENAME, {"state": state, "detail": detail})


def _write_report(path: Path, payload: Any) -> None:
    """Human-readable report JSON. Not part of the integrity chain; the snapshot is."""

    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )
