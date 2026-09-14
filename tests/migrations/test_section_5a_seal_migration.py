"""The one-look seal migration. Authored, NOT applied.

No test here executes SQL against a database; these contracts are asserted on the DDL text,
and the Postgres path they govern is REVIEWED BUT UNEXECUTED until the owner applies it.
"""

from __future__ import annotations

from pathlib import Path

SQL = (
    Path(__file__).resolve().parents[2]
    / "migrations/0009_section_5a_evaluation_seal.sql"
).read_text(encoding="utf-8")

# Column alignment is cosmetic; collapse whitespace so these assert structure, not layout.
FLAT = " ".join(SQL.split())


def test_the_table_can_hold_at_most_one_seal() -> None:
    assert "seal_id TEXT PRIMARY KEY CHECK (seal_id = 'SINGLETON')" in FLAT


def test_a_claimed_seal_cannot_carry_evidence() -> None:
    """Claim-before-read cannot be bypassed by handing evidence to the claim."""

    assert "CONSTRAINT section_5a_claimed_has_no_snapshot CHECK" in FLAT
    assert (
        "state <> 'CLAIMED' OR (snapshot_payload IS NULL AND evidence_snapshot_id IS NULL "
        "AND result_inputs_digest IS NULL)"
    ) in FLAT


def test_a_captured_state_requires_the_raw_capture_it_was_exposed_from() -> None:
    assert "CONSTRAINT section_5a_captured_is_complete CHECK" in FLAT
    assert (
        "raw_evidence IS NOT NULL AND snapshot_payload IS NOT NULL "
        "AND evidence_snapshot_id IS NOT NULL AND result_inputs_digest IS NOT NULL"
    ) in FLAT


def test_every_lifecycle_state_is_declared_and_nothing_else() -> None:
    assert (
        "CHECK (state IN ('CLAIMED', 'SEALED_RAW_CAPTURED', 'COMPLETE', "
        "'SEALED_NO_RESULT', 'CAPTURE_FAILED'))"
    ) in FLAT


def test_claim_fields_are_immutable() -> None:
    assert "RAISE EXCEPTION 'section 5A seal claim fields are immutable'" in FLAT
    for column in ("sealed_at_utc", "evaluator_pin_digest", "contract_instants", "run_provenance"):
        assert f"NEW.{column} IS DISTINCT FROM OLD.{column}" in FLAT


def test_captured_evidence_is_write_once() -> None:
    assert "RAISE EXCEPTION 'section 5A captured evidence is write-once'" in FLAT
    for column in (
        "raw_evidence",
        "snapshot_payload",
        "evidence_snapshot_id",
        "result_inputs_digest",
    ):
        assert f"OLD.{column} IS NOT NULL" in FLAT


def test_only_legal_transitions_are_accepted() -> None:
    assert "RAISE EXCEPTION 'illegal section 5A seal transition % -> %'" in FLAT
    assert "(OLD.state = 'COMPLETE' AND NEW.state = 'COMPLETE')" in FLAT
    assert "(OLD.state = 'CAPTURE_FAILED' AND NEW.state = 'CAPTURE_FAILED')" in FLAT


def test_the_seal_cannot_be_deleted() -> None:
    assert "BEFORE UPDATE OR DELETE ON public.section_5a_evaluation_seal" in FLAT
    assert "RAISE EXCEPTION 'section 5A seal cannot be deleted" in FLAT


def test_it_is_idempotent_and_replaces_the_superseded_trigger() -> None:
    assert "CREATE TABLE IF NOT EXISTS" in FLAT
    assert "DROP TRIGGER IF EXISTS section_5a_seal_immutable" in FLAT
    assert "DROP TRIGGER IF EXISTS section_5a_seal_guard" in FLAT


def test_it_records_that_it_is_not_applied_and_how_to_apply_it_safely() -> None:
    """K2=A: one dispatch-only route applies it; the default runner would drag in 0008."""

    assert "AUTHORED, NOT APPLIED" in SQL
    assert ".github/workflows/section-5a-apply-seal-migration.yml" in FLAT
    assert "scripts/apply_section_5a_seal.py" in FLAT
    assert "--only 0009_section_5a_evaluation_seal.sql" in SQL
    assert "must never be used for it" in FLAT


def test_the_seal_cannot_be_truncated() -> None:
    """V807-F8. TRUNCATE fires no row-level trigger, so it needs its own statement-level guard."""

    assert "BEFORE TRUNCATE ON public.section_5a_evaluation_seal" in FLAT
    assert "FOR EACH STATEMENT EXECUTE FUNCTION public.section_5a_seal_truncate_guard()" in FLAT
    assert "RAISE EXCEPTION 'section 5A seal cannot be truncated" in FLAT


def test_the_residual_limit_is_stated_rather_than_hidden() -> None:
    assert "DROP TABLE" in SQL and "outside what a table trigger can prevent" in SQL


def test_every_claim_must_carry_a_verified_run_provenance() -> None:
    """E2=A. The authority itself refuses a claim not made by a verified dispatch."""

    assert "run_provenance JSONB NOT NULL" in FLAT
    assert "CONSTRAINT section_5a_claim_has_verified_provenance CHECK (COALESCE(" in FLAT
    for clause in (
        "jsonb_typeof(run_provenance) = 'object'",
        "run_provenance ->> 'schema_version' = 'section-5a-run-provenance.v1'",
        "run_provenance -> 'dispatch_verified' = 'true'::jsonb",
        "run_provenance ->> 'event_name' = 'workflow_dispatch'",
        "run_provenance ->> 'ref' = 'refs/heads/main'",
        "|| '/.github/workflows/section-5a-evaluation.yml@refs/heads/main'",
        "run_provenance ->> 'expected_sha' ~ '^[0-9a-f]{40}$'",
        "run_provenance ->> 'sha' = run_provenance ->> 'expected_sha'",
        "run_provenance ->> 'git_head' = run_provenance ->> 'expected_sha'",
        "run_provenance ->> 'pin_digest' = evaluator_pin_digest",
        # G1=A: only an isolated start-up with verified installed files may spend the look
        "run_provenance ->> 'interpreter_flags' = "
        "'isolated,ignore_environment,no_user_site,safe_path,no_site,dont_write_bytecode'",
        "run_provenance ->> 'installed_files_sha256' ~ '^[0-9a-f]{64}$'",
    ):
        assert clause in FLAT, clause


def test_the_provenance_check_cannot_pass_on_null() -> None:
    """A CHECK whose expression is NULL passes; a missing key makes ->> NULL. COALESCE closes it."""

    constraint = FLAT.split("CONSTRAINT section_5a_claim_has_verified_provenance CHECK (", 1)[1]
    condition, _, rest = constraint.partition(", false)),")
    assert condition.startswith("COALESCE(") and rest, "the whole conjunction sits inside COALESCE"
    assert "CONSTRAINT" not in condition
    assert condition.rstrip().endswith("run_provenance ->> 'pin_digest' = evaluator_pin_digest")


def test_the_sql_record_shape_matches_what_the_verifier_produces() -> None:
    """Every key the CHECK reads is a key the verifier writes, spelled identically."""

    import re

    from tests.oos.evaluation.conftest import verified_provenance

    record = verified_provenance()
    keys = set(re.findall(r"run_provenance -(?:>>|>) '([a-z_0-9]+)'", FLAT))
    assert keys and keys <= set(record), keys - set(record)


def test_the_sql_flag_text_is_the_isolation_module_s() -> None:
    from crypto_probability_engine.runtime_isolation import REQUIRED_FLAGS_TEXT

    assert f"= '{REQUIRED_FLAGS_TEXT}'" in FLAT


# --------------------------------------------------------------------------- no API role reaches it


def _code() -> str:
    """The DDL without comments, so prose can never satisfy a structural assertion."""

    return " ".join(
        " ".join(line.split("--", 1)[0] for line in SQL.splitlines()).split()
    )


def test_row_level_security_is_enabled_on_the_seal() -> None:
    """F-0009-A, owner ruling K1=A. With RLS off, an anon-key INSERT could squat the singleton."""

    assert "ALTER TABLE public.section_5a_evaluation_seal ENABLE ROW LEVEL SECURITY;" in _code()


def test_every_api_role_loses_every_privilege_and_nothing_is_granted() -> None:
    code = _code()
    assert (
        "REVOKE ALL ON TABLE public.section_5a_evaluation_seal "
        "FROM PUBLIC, anon, authenticated, service_role;"
    ) in code
    assert "GRANT " not in code, "the seal has no REST path; no role is granted anything"
    assert "FORCE ROW LEVEL SECURITY" not in code, "the owning evaluator must not be locked out"


def test_the_lock_down_follows_everything_it_protects() -> None:
    code = _code()
    assert code.index("ENABLE ROW LEVEL SECURITY") > code.index("CREATE TABLE IF NOT EXISTS")
    assert code.index("REVOKE ALL ON TABLE") > code.index("BEFORE TRUNCATE ON")


def test_every_object_is_schema_qualified() -> None:
    """The repository reads public.section_5a_evaluation_seal; the DDL must create exactly that."""

    import re

    code = _code()
    table_references = re.findall(r"(\S*)section_5a_evaluation_seal\b", code)
    assert table_references and all(prefix.endswith("public.") for prefix in table_references), (
        table_references
    )
    for function in ("section_5a_seal_guard", "section_5a_seal_truncate_guard"):
        assert f"CREATE OR REPLACE FUNCTION public.{function}()" in code
        assert f"EXECUTE FUNCTION public.{function}()" in code
