"""Migration 0014 (DBI-1, plan §8.2): NOT VALID checks and append-only core evidence, nothing else.

The statements are read from the file itself, comments removed and whitespace collapsed. Every
constraint is NOT VALID: no existing row is scanned, so no holdout probability is read and no
existing evidence is rejected or repaired. The probability tolerance is the pipeline's own. The
trigger function has a fixed search_path and no API role may execute it.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from crypto_probability_engine.utils.invariants import PROBABILITY_TOLERANCE

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / "migrations/0014_core_evidence_invariants.sql").read_text(encoding="utf-8")
CODE = " ".join(re.sub(r"--[^\n]*", "", TEXT).split())
GUARDED_CHECK = re.compile(
    r"IF NOT EXISTS \( SELECT 1 FROM pg_catalog\.pg_constraint "
    r"WHERE conname = '(?P<guard>[a-z_]+)' "
    r"AND conrelid = 'public\.(?P<guarded>[a-z_]+)'::regclass \) "
    r"THEN ALTER TABLE public\.(?P<table>[a-z_]+) ADD CONSTRAINT (?P<name>[a-z_]+) "
    r"CHECK (?P<check>\(.*?\)) NOT VALID; END IF;"
)
EXPECTED_CHECKS = {
    ("predictions", "predictions_probability_simplex_chk"): (
        "( p_up_frac >= 0 AND p_up_frac <= 1 AND p_down_frac >= 0 AND p_down_frac <= 1 "
        "AND p_timeout_frac >= 0 AND p_timeout_frac <= 1 "
        "AND abs(p_up_frac + p_down_frac + p_timeout_frac - 1) <= 0.000001 )"
    ),
    ("predictions", "predictions_reference_price_chk"): (
        "(reference_price > 0 AND reference_price < 'Infinity'::numeric)"
    ),
    ("predictions", "predictions_horizon_chronology_chk"): (
        "( horizon_bars > 0 AND horizon_end_utc > reference_close_utc "
        "AND reference_close_utc <= predicted_at_utc )"
    ),
    ("prediction_outcomes", "prediction_outcomes_reference_price_chk"): (
        "(outcome_reference_price > 0 AND outcome_reference_price < 'Infinity'::numeric)"
    ),
}
CORE_TABLES = ("predictions", "prediction_outcomes", "prediction_feature_snapshots")


def test_exactly_four_checks_each_guarded_by_its_own_name_and_not_valid() -> None:
    matches = list(GUARDED_CHECK.finditer(CODE))
    assert {(m["table"], m["name"]): m["check"] for m in matches} == EXPECTED_CHECKS
    for match in matches:
        assert (match["guard"], match["guarded"]) == (match["name"], match["table"])
    assert CODE.count("ADD CONSTRAINT") == 4 and CODE.count(" NOT VALID;") == 4


def test_the_probability_tolerance_is_the_pipelines_own() -> None:
    literal = re.search(r"- 1\) <= ([0-9.]+)", CODE)
    assert literal is not None
    assert Decimal(literal.group(1)) == Decimal(str(PROBABILITY_TOLERANCE))


def test_nothing_scans_repairs_references_or_touches_protected_data() -> None:
    for forbidden in ("VALIDATE CONSTRAINT", "FOREIGN KEY", "REFERENCES", "INSERT", "DROP ",
                      "GRANT ", "SECURITY DEFINER", "section_5a", "SET DEFAULT"):
        assert forbidden not in CODE, forbidden
    # UPDATE, DELETE and TRUNCATE appear only as the events the triggers refuse.
    for match in re.finditer(r"\b(UPDATE|DELETE|TRUNCATE)\b", CODE):
        assert CODE[: match.start()].endswith("BEFORE "), CODE[match.start() - 30 : match.end()]


def test_the_trigger_function_has_a_fixed_search_path_and_no_api_execute() -> None:
    assert (
        "CREATE OR REPLACE FUNCTION public.reject_core_evidence_mutation() RETURNS trigger "
        "LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$"
    ) in CODE
    assert (
        "REVOKE ALL ON FUNCTION public.reject_core_evidence_mutation() "
        "FROM PUBLIC, anon, authenticated, service_role;"
    ) in CODE


def test_every_core_table_refuses_update_delete_and_truncate() -> None:
    tables = ", ".join(f"'{table}'" for table in CORE_TABLES)
    assert f"FOREACH target IN ARRAY ARRAY[{tables}]" in CODE
    for event, level in (("UPDATE", "ROW"), ("DELETE", "ROW"), ("TRUNCATE", "STATEMENT")):
        statement = (
            f"'CREATE TRIGGER %I BEFORE {event} ON public.%I FOR EACH {level} ' "
            "'EXECUTE FUNCTION public.reject_core_evidence_mutation()'"
        )
        assert CODE.count(statement) == 1, event
        # one name for the existence guard, one for the trigger it creates
        assert CODE.count(f"'trg_' || short || '_reject_{event.lower()}'") == 2, event
