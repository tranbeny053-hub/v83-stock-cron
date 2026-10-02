"""Migration 0015 (B9, plan §8.1): one least-privilege bundle function, and nothing else.

Read from the file itself. Its row keys must be exactly the columns the writers already insert,
so the RPC stores what the per-row writes store; its comparisons cover every inserted column but
the id. Its behaviour on a real PostgreSQL is proven by the 0015 rehearsal and PERS-0 in CI.
"""

from __future__ import annotations

import re
from pathlib import Path

from crypto_probability_engine.persistence.repository import (
    _insert_derivatives_snapshot,
    _insert_feature_snapshot,
    _insert_prediction,
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (ROOT / "migrations/0015_prediction_bundle_rpc.sql").read_text(encoding="utf-8")
STAMPED_PREDICTION = {
    "prediction_id": "p", "target_version": "tc-v1", "reference_venue": "BINANCE_PUBLIC",
    "core_computed_at_utc": "t", "issued_at_utc": "t",
}




def _array(name: str) -> list[str]:
    match = re.search(rf"{name} CONSTANT text\[\] := ARRAY\[(.*?)\];", MIGRATION, re.S)
    assert match is not None, name
    return re.findall(r"'([a-z0-9_]+)'", match.group(1))


class _Recorder:
    def __init__(self) -> None:
        self.sql = ""

    def execute(self, statement, params=None) -> None:
        self.sql = self.sql or str(statement)

    def fetchone(self):
        return ("x",)


def _inserted_columns(insert, row: dict) -> list[str]:
    recorder = _Recorder()
    insert(recorder, row)
    columns = re.search(r"INSERT INTO [a-z_.]+ \((.*?)\)", recorder.sql, re.S).group(1)
    return [name.strip() for name in columns.split(",")]


def test_its_keys_are_exactly_the_columns_the_writers_insert() -> None:
    assert _array("prediction_keys") == _inserted_columns(_insert_prediction, STAMPED_PREDICTION)
    feature_row = {"prediction_id": "p", "snapshot_hash": "x"}
    assert _array("feature_keys") == _inserted_columns(_insert_feature_snapshot, feature_row)
    assert _array("derivatives_keys") == _inserted_columns(_insert_derivatives_snapshot,
                                                           feature_row)


def test_its_comparisons_cover_every_inserted_column_but_the_id() -> None:
    rows = re.findall(r"IF ROW\((.*?)\) IS NOT DISTINCT FROM ROW\((.*?)\) THEN", MIGRATION, re.S)
    assert len(rows) == 3
    for (stored, incoming), keys in zip(
        rows, ("prediction_keys", "feature_keys", "derivatives_keys"), strict=True
    ):
        expected = [key for key in _array(keys) if key != "prediction_id"]
        assert [name.split(".")[1].strip() for name in stored.split(",")] == expected
        assert [name.split(".")[1].strip() for name in incoming.split(",")] == expected


def test_it_is_one_least_privilege_function_and_nothing_else() -> None:
    body = re.sub(r"--[^\n]*", "", MIGRATION)
    assert body.count("CREATE OR REPLACE FUNCTION") == 1
    assert "public.save_prediction_bundle(" in body
    assert "SECURITY INVOKER" in body and "SECURITY DEFINER" not in body
    assert "SET search_path = pg_catalog, pg_temp" in body
    assert ("REVOKE ALL ON FUNCTION public.save_prediction_bundle(jsonb, jsonb, jsonb)\n"
            "FROM PUBLIC, anon, authenticated;") in body
    assert ("GRANT EXECUTE ON FUNCTION public.save_prediction_bundle(jsonb, jsonb, jsonb) "
            "TO service_role;") in body
    assert body.count("GRANT ") == 1
    for forbidden in ("CREATE TABLE", "ALTER TABLE", "DROP ", "CREATE TRIGGER", "CREATE POLICY",
                      "UPDATE public.", "DELETE FROM", "TRUNCATE", "DO UPDATE"):
        assert forbidden not in body, forbidden
    # Every table it touches is schema-qualified, as its fixed search_path requires.
    assert not re.search(r"INSERT INTO\s+(?!public\.)", body)
    assert not re.search(r"SELECT \* INTO \w+ FROM\s+(?!public\.)", body)
    assert not re.search(r"NULL::(?!public\.)", body)
    assert not re.search(r"FROM\s+(?:pg_catalog\.)?jsonb_object_keys", body.replace(
        "FROM pg_catalog.jsonb_object_keys", ""))
