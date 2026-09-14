"""Synthetic section 5A evidence. No live data, ever."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

T0 = datetime(2026, 8, 21, 4, 0, 0, tzinfo=UTC)
T_CLOSE = datetime(2026, 9, 12, 4, 0, 0, tzinfo=UTC)
T_FREEZE = datetime(2026, 8, 20, 11, 35, 56, tzinfo=UTC)

UNSET = object()
"""Sentinel: distinguishes "not overridden" from an explicit unresolved ``None``."""


def evidence_row(
    reference_close_utc: datetime,
    *,
    symbol: str = "BTC/USDT",
    timeframe: str = "4H",
    candidate_up: float = 0.60,
    baseline_up: float = 0.50,
    label: str | None = "UP",
    baseline_label: Any = UNSET,
    candidate_label: Any = UNSET,
    horizon_end_utc: datetime | None = None,
    with_probabilities: bool = True,
) -> dict[str, Any]:
    """One flat paired-evidence row, exactly as the repository projection emits it."""

    identifier = f"oosb-{abs(hash((reference_close_utc, symbol, timeframe))):032x}"[:37]
    horizon_end = horizon_end_utc or (reference_close_utc + timedelta(hours=24))
    row: dict[str, Any] = {
        "run_id": identifier,
        "normalized_symbol": symbol,
        "timeframe": timeframe,
        "reference_close_utc": reference_close_utc,
    }
    labels = {
        "baseline": label if baseline_label is UNSET else baseline_label,
        "candidate": label if candidate_label is UNSET else candidate_label,
    }
    tops = {"baseline": baseline_up, "candidate": candidate_up}
    for arm in ("baseline", "candidate"):
        row[f"{arm}_prediction_id"] = f"{identifier}:{timeframe}:{arm.upper()}"
        row[f"{arm}_predicted_at_utc"] = reference_close_utc
        row[f"{arm}_horizon_end_utc"] = horizon_end
        row[f"{arm}_prediction_origin"] = "SCHEDULED_SHADOW_EVIDENCE"
        row[f"{arm}_realized_label"] = labels[arm]
        if with_probabilities:
            top = tops[arm]
            remainder = 1.0 - top
            row[f"{arm}_p_up_frac"] = top
            row[f"{arm}_p_down_frac"] = remainder * 0.6
            row[f"{arm}_p_timeout_frac"] = remainder * 0.4
    return row


def daily_4h_evidence(
    *,
    candidate_ups: list[float] | None = None,
    symbol: str = "BTC/USDT",
    days: int = 22,
) -> list[dict[str, Any]]:
    """One pair per day at the T0 hour.

    This placement populates every window at all three coarsenings for 4H: c=1 takes
    the even days (11 windows), c=2 every third day (7), c=4 every fifth day (5) — the
    contract's own k_1/k_2/k_4.  Slight variation in candidate confidence is required
    because a zero-dispersion sample makes A1 fail closed by design.
    """

    # Length 7 is deliberate: coprime with the 2-, 3- and 5-day strides that the c=1,
    # c=2 and c=4 lattices sample, so no coarsening aliases onto a constant sample.
    # A 5-long cycle makes every c=4 window identical, s == 0, and A1 fail closed.
    ups = candidate_ups or [0.60, 0.61, 0.59, 0.62, 0.58, 0.63, 0.575]
    return [
        evidence_row(
            T0 + timedelta(days=day),
            symbol=symbol,
            candidate_up=ups[day % len(ups)],
        )
        for day in range(days)
    ]


SYNTHETIC_REPOSITORY = "synthetic/ucpe"
SYNTHETIC_SHA = "a" * 40


def synthetic_dispatch(**overrides: str) -> dict[str, str]:
    """GitHub dispatch facts for a verified evaluation run. Synthetic; nothing is dispatched."""

    from crypto_probability_engine.oos.evaluation import provenance

    facts = {
        "github_actions": "true",
        "event_name": provenance.REQUIRED_EVENT,
        "repository": SYNTHETIC_REPOSITORY,
        "workflow_ref": (
            f"{SYNTHETIC_REPOSITORY}/{provenance.EVALUATION_WORKFLOW}@{provenance.REQUIRED_REF}"
        ),
        "ref": provenance.REQUIRED_REF,
        "sha": SYNTHETIC_SHA,
        "run_id": "123456789",
        "run_attempt": "1",
        "runner_os": "Linux",
        "runner_arch": "X64",
        "image_os": "ubuntu24",
        "image_version": "20260907.1",
    }
    facts.update(overrides)
    return facts


def synthetic_runtime(**overrides: Any) -> dict[str, Any]:
    """Runtime facts of the PINNED interpreter and lock, whatever interpreter runs the tests."""

    from crypto_probability_engine.oos.evaluation import evaluator_pin, provenance

    facts = {
        "python_implementation": provenance.PINNED_PYTHON_IMPLEMENTATION,
        "python_version": provenance.PINNED_PYTHON_VERSION,
        "git_head": SYNTHETIC_SHA,
        "tracked_tree_clean": True,
        "lock_sha256": provenance.lock_sha256(),
        "installed": {**provenance.read_lock(), "pip": "26.1.2"},
        "pin_digest": str(evaluator_pin.current_pin_artifacts()["closure_digest"]),
        "interpreter_flags": provenance.REQUIRED_FLAGS_TEXT,
        "installed_files_sha256": SYNTHETIC_INSTALLED_FILES_SHA256,
    }
    facts.update(overrides)
    return facts


SYNTHETIC_INSTALLED_FILES_SHA256 = "e" * 64


def synthetic_isolation(**overrides: Any):
    """An isolation report shaped as ``runtime_isolation.enter`` returns it; nothing was audited."""

    from crypto_probability_engine import runtime_isolation

    fields = {
        "interpreter_flags": runtime_isolation.REQUIRED_FLAGS_TEXT,
        "stdlib_roots": ("/synthetic/lib/python3.13",),
        "site_dirs": ("/synthetic/lib/python3.13/site-packages",),
        "source_root": "/synthetic/checkout/src",
        "installed": {},
        "installed_files_sha256": SYNTHETIC_INSTALLED_FILES_SHA256,
        "locked_files": frozenset(),
    }
    fields.update(overrides)
    return runtime_isolation.IsolationReport(**fields)


def verified_provenance() -> dict[str, Any]:
    """A run provenance produced by the REAL verifier from synthetic facts, never hand-built.

    Verified once per session (the pin cannot change inside one) and copied, so a test that
    rewrites a record never alters another test's.
    """

    return deepcopy(_verified_provenance_once())


@lru_cache(maxsize=1)
def _verified_provenance_once() -> dict[str, Any]:
    from crypto_probability_engine.oos.evaluation import provenance

    return provenance.verify_run_provenance(
        synthetic_dispatch(),
        synthetic_runtime(),
        expected_sha=SYNTHETIC_SHA,
        lock_pins=provenance.read_lock(),
    )
