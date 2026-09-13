"""The Postgres seal path, driven with cursor doubles. NO database is contacted.

These prove the order of statements and the refusals the Python layer performs. The SQL
itself is REVIEWED BUT UNEXECUTED until migration 0009 is applied by the owner.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from crypto_probability_engine.persistence import repository as module
from crypto_probability_engine.utils import canonical_json

RUN = "oosb-" + "a" * 32
REF = datetime(2026, 8, 21, 4, tzinfo=UTC)
PIN = "c" * 64


def _prediction_row(arm: str, methodology: str) -> tuple:
    """A tuple in OOS_EVIDENCE_BASE_COLUMNS + OOS_PROBABILITY_FIELDS order, as psycopg returns."""

    return (
        f"{RUN}:4H:{arm}", RUN, "BTC/USDT", "4H", REF, REF, REF,
        "SCHEDULED_SHADOW_EVIDENCE", methodology,
        Decimal("0.6"), Decimal("0.25"), Decimal("0.15"),
    )


class ScriptedCursor:
    """Returns scripted results per statement and records every statement it saw."""

    def __init__(self, *, seal=("CLAIMED", True), capture_lands=True):
        self.statements: list[str] = []
        self.params: list = []
        self._seal = seal
        self._capture_lands = capture_lands
        self._last = ""

    def execute(self, sql, params=None):
        self.statements.append(" ".join(sql.split()))
        self.params.append(params)
        self._last = self.statements[-1]

    def fetchone(self):
        if "FOR UPDATE" in self._last:
            return self._seal
        if self._last.startswith("UPDATE"):
            return ("SINGLETON",) if self._capture_lands else None
        return None

    def fetchall(self):
        if "FROM public.predictions WHERE" in self._last:
            rows = [
                _prediction_row("BASELINE", module.OOS_BASELINE_METHODOLOGY),
                _prediction_row("CANDIDATE", module.OOS_CANDIDATE_METHODOLOGY),
            ]
            # Match the projection actually selected: readiness omits the probabilities.
            width = 12 if "p_up_frac" in self._last else 9
            return [row[:width] for row in rows]
        if "FROM public.prediction_outcomes" in self._last:
            return [(f"{RUN}:4H:BASELINE", "UP"), (f"{RUN}:4H:CANDIDATE", "UP")]
        return []


def test_consumption_read_locks_the_seal_before_reading_anything() -> None:
    cursor = ScriptedCursor()
    module._fetch_oos_paired_evidence_for_consumption(cursor)
    assert "FOR UPDATE" in cursor.statements[0]
    assert "section_5a_evaluation_seal" in cursor.statements[0]


def test_consumption_read_captures_raw_evidence_before_returning_it() -> None:
    """The capture statement is the LAST statement; nothing is returned before it lands."""

    cursor = ScriptedCursor()
    rows = module._fetch_oos_paired_evidence_for_consumption(cursor)
    order = [
        "FOR UPDATE",
        "FROM public.predictions WHERE",
        "FROM public.prediction_outcomes",
        "SET raw_evidence",
    ]
    positions = [
        next(i for i, sql in enumerate(cursor.statements) if marker in sql) for marker in order
    ]
    assert positions == sorted(positions)
    assert positions[-1] == len(cursor.statements) - 1
    assert rows and rows[0]["candidate_p_up_frac"] == Decimal("0.6")


def test_raw_capture_is_lossless_canonical_text() -> None:
    cursor = ScriptedCursor()
    module._fetch_oos_paired_evidence_for_consumption(cursor)
    raw = canonical_json.loads(cursor.params[-1]["raw_evidence"])
    captured = raw["predictions"][0]
    assert captured["p_up_frac"] == Decimal("0.6") and isinstance(captured["p_up_frac"], Decimal)
    assert captured["reference_close_utc"] == REF


@pytest.mark.parametrize(
    "seal",
    [None, ("SEALED_RAW_CAPTURED", True), ("CLAIMED", False), ("CAPTURE_FAILED", True)],
)
def test_probabilities_are_refused_without_a_claimed_uncaptured_seal(seal) -> None:
    cursor = ScriptedCursor(seal=seal)
    with pytest.raises(RuntimeError, match="only under a CLAIMED, uncaptured seal"):
        module._fetch_oos_paired_evidence_for_consumption(cursor)
    assert len(cursor.statements) == 1, "nothing may be read after the lock refuses"


def test_nothing_is_returned_when_the_raw_capture_does_not_land() -> None:
    cursor = ScriptedCursor(capture_lands=False)
    with pytest.raises(RuntimeError, match="raw evidence capture did not land"):
        module._fetch_oos_paired_evidence_for_consumption(cursor)


def test_claim_always_inserts_claimed_with_canonical_json() -> None:
    cursor = ScriptedCursor()
    cursor.fetchone = lambda: ("SINGLETON",)
    assert module._claim_section_5a_seal_row(
        cursor,
        {
            "sealed_at_utc": REF.isoformat(),
            "evaluator_pin_digest": PIN,
            "contract_instants": {"t0": REF},
        },
    )
    assert "'CLAIMED'" in cursor.statements[0]
    assert cursor.params[0]["snapshot_payload"] is None
    assert canonical_json.loads(cursor.params[0]["contract_instants"]) == {"t0": REF}


def test_snapshot_capture_requires_raw_evidence_an_empty_slot_and_the_claimed_pin() -> None:
    cursor = ScriptedCursor()
    module._capture_section_5a_snapshot_row(
        cursor,
        {
            "evidence_snapshot_id": "a" * 64,
            "result_inputs_digest": "b" * 64,
            "evaluator_pin_digest": PIN,
            "rows": [],
        },
    )
    sql = cursor.statements[0]
    for guard in (
        "state = 'CLAIMED'",
        "raw_evidence IS NOT NULL",
        "snapshot_payload IS NULL",
        "evaluator_pin_digest = %(evaluator_pin_digest)s",
    ):
        assert guard in sql


@pytest.mark.parametrize("encoded_as", ["text", "parsed"])
def test_seal_read_decodes_json_losslessly_and_projects_the_raw_capture(encoded_as) -> None:
    raw = {
        "predictions": [
            {
                "prediction_id": f"{RUN}:4H:{arm}", "run_id": RUN,
                "normalized_symbol": "BTC/USDT", "timeframe": "4H",
                "reference_close_utc": REF, "predicted_at_utc": REF, "horizon_end_utc": REF,
                "prediction_origin": "SCHEDULED_SHADOW_EVIDENCE", "methodology_version": method,
                "p_up_frac": Decimal("0.6"), "p_down_frac": Decimal("0.25"),
                "p_timeout_frac": Decimal("0.15"),
            }
            for arm, method in (
                ("BASELINE", module.OOS_BASELINE_METHODOLOGY),
                ("CANDIDATE", module.OOS_CANDIDATE_METHODOLOGY),
            )
        ],
        "outcomes": {f"{RUN}:4H:BASELINE": {"realized_label": "UP"}},
    }

    def column(value):
        text = canonical_json.dumps(value).decode()
        return text if encoded_as == "text" else __import__("json").loads(text)

    row = (
        "SINGLETON", REF, None, None, PIN, column({"t0": "x"}), None, column(raw),
        "CLAIMED", "",
    )
    cursor = ScriptedCursor()
    cursor.fetchone = lambda: row
    seal = module._fetch_section_5a_seal_row(cursor)
    assert "raw_evidence" not in seal
    assert seal["captured_rows"][0]["candidate_p_up_frac"] == Decimal("0.6")


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return self

    def __getattr__(self, name):
        return getattr(self._cursor, name)


def test_postgres_repository_routes_probability_reads_through_capture() -> None:
    cursor = ScriptedCursor()
    repo = module.SupabasePersistenceRepository(
        "postgresql://never-connected", direct_connection_factory=lambda: _Connection(cursor)
    )
    repo.fetch_oos_paired_evidence(include_probabilities=True)
    assert any("FOR UPDATE" in sql for sql in cursor.statements)
    assert any("SET raw_evidence" in sql for sql in cursor.statements)


def test_postgres_readiness_read_takes_no_lock_and_writes_nothing() -> None:
    cursor = ScriptedCursor()
    repo = module.SupabasePersistenceRepository(
        "postgresql://never-connected", direct_connection_factory=lambda: _Connection(cursor)
    )
    repo.fetch_oos_paired_evidence(include_probabilities=False)
    assert not any("FOR UPDATE" in sql for sql in cursor.statements)
    assert not any(sql.startswith("UPDATE") for sql in cursor.statements)


def test_each_repository_declares_its_seal_authority_honestly() -> None:
    assert module.InMemoryPersistenceRepository().section_5a_seal_authority() == "PROCESS_LOCAL"
    assert (
        module.SupabasePersistenceRepository("postgresql://never-connected")
        .section_5a_seal_authority()
        == module.SECTION_5A_SEAL_AUTHORITY_POSTGRES
    )
    rest = module.SupabaseRestRepository.__new__(module.SupabaseRestRepository)
    assert rest.section_5a_seal_authority() == "REST_NOT_A_SEAL_AUTHORITY"
    with pytest.raises(RuntimeError, match="requires the Postgres authority"):
        rest.capture_section_5a_snapshot({})


def test_tier1_arm_comes_only_from_the_prediction_id_suffix() -> None:
    """G7: an arm field SQL cannot see must never qualify a row."""

    assert module._oos_arm({"arm": "BASELINE", "prediction_id": f"{RUN}:4H:OTHER"}) is None
    assert module._oos_arm({"prediction_id": f"{RUN}:4H:CANDIDATE"}) == "CANDIDATE"
