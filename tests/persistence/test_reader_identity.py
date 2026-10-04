"""E2 (plan §8.3): the evidence reader's redacted, catalog-only capability report.

Everything here is synthetic: no database, no real URL, no credential. The same production code runs
against real PostgreSQL in the privilege rehearsal's E1, as ucpe_space_db, as the owner and as
ucpe_resolver.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from crypto_probability_engine.config.build_info import RELEASE_ID
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence import reader_identity as ri
from crypto_probability_engine.telemetry.events import TelemetrySink
from scripts import core_write_inventory

ROOT = Path(__file__).resolve().parents[2]
LEGACY = "postgresql://legacy-synthetic.invalid/none"
CUTOVER = "postgresql://cutover-synthetic.invalid/none"
TABLES = (*ri.CORE_TABLES, "automation_credential", "automation_radar_ledger", "watchlist")
PRIVILEGES_17 = (*ri.TABLE_PRIVILEGES, "MAINTAIN")


def relations(held: set[tuple[str, str]], *, maintain: bool = True) -> list[tuple]:
    privileges = PRIVILEGES_17 if maintain else ri.TABLE_PRIVILEGES
    return [(table, *((table, p) in held for p in privileges)) for table in TABLES]


def policy(table: str, command: str, *, permissive: bool = True, using: str | None = "true",
           check: str | None = None, applies: bool = True, rowsecurity: bool = True,
           forced: bool = False, owner: bool = False) -> tuple:
    return (table, rowsecurity, forced, owner, command, permissive, using, check, applies)


DESIGNED_POLICIES = (
    policy("automation_credential", "r"),
    policy("automation_radar_ledger", "a", using=None, check="true"),
    policy("automation_radar_ledger", "r"),
    policy("automation_radar_ledger", "w", check="true"),
    policy("prediction_outcomes", "r"),
    policy("predictions", "r"),
)
ATTRIBUTES = ("superuser", "createrole", "createdb", "replication", "bypassrls", "inherit")


def designed_facts(**changes) -> dict:
    facts = {
        "maintain": True,
        "current_user": "ucpe_space_db",
        "session_user": "ucpe_space_db",
        "attributes": dict.fromkeys(ATTRIBUTES, False),
        "memberships": 0,
        "owner_rights": False,
        "relations": relations(set(ri.NEEDED)),
        "sequences": 0,
        "schema_create": False,
        "database_create": False,
        "definers": 0,
        "policies": list(DESIGNED_POLICIES),
    }
    facts.update(changes)
    return facts


def owner_facts() -> dict:
    every = {(table, privilege) for table in TABLES for privilege in PRIVILEGES_17}
    return designed_facts(
        current_user="postgres",
        session_user="postgres",
        attributes={**dict.fromkeys(ATTRIBUTES, True), "superuser": False},
        memberships=7,
        owner_rights=True,
        relations=relations(every),
        sequences=3,
        schema_create=True,
        database_create=True,
        definers=2,
        policies=[(row[0], True, False, True, *row[4:]) for row in DESIGNED_POLICIES],
    )


# --- the URL the reader uses ---------------------------------------------------------------------


def test_without_the_cutover_secret_nothing_changes() -> None:
    settings = Settings(**{"supabase_db_url": LEGACY})
    chosen, source = ri.evidence_reader_settings(settings, {})
    assert chosen is settings
    assert source == "SUPABASE_DB_URL"
    assert ri.evidence_reader_settings(Settings(), {}) == (Settings(), "none")


def test_the_cutover_secret_wins_and_leaves_the_original_settings_alone() -> None:
    settings = Settings(**{"supabase_db_url": LEGACY})
    chosen, source = ri.evidence_reader_settings(settings, {"UCPE_SPACE_DB_URL": f"  {CUTOVER}\n"})
    assert (chosen.supabase_db_url, chosen.external_store_configured, source) == (
        CUTOVER, True, "UCPE_SPACE_DB_URL"
    )
    assert (settings.supabase_db_url,) == (LEGACY,), "the original settings are untouched"
    alone, alone_source = ri.evidence_reader_settings(Settings(), {"UCPE_SPACE_DB_URL": CUTOVER})
    assert (alone.supabase_db_url, alone_source) == (CUTOVER, "UCPE_SPACE_DB_URL")


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_a_blank_cutover_secret_is_ignored(blank: str) -> None:
    settings = Settings(**{"supabase_db_url": LEGACY})
    assert ri.evidence_reader_settings(settings, {"UCPE_SPACE_DB_URL": blank}) == (
        settings, "SUPABASE_DB_URL"
    )


def test_the_process_environment_is_read_when_none_is_given(monkeypatch) -> None:
    monkeypatch.setenv("UCPE_SPACE_DB_URL", CUTOVER)
    assert ri.evidence_reader_settings(Settings())[1] == "UCPE_SPACE_DB_URL"
    monkeypatch.delenv("UCPE_SPACE_DB_URL")
    assert ri.evidence_reader_settings(Settings())[1] == "none"


# --- the design it checks against ----------------------------------------------------------------


def test_the_core_tables_are_the_inventory_s() -> None:
    assert ri.CORE_TABLES == core_write_inventory.CORE_TABLES


def test_the_needed_privileges_are_exactly_migration_0016_s_grants() -> None:
    text = (ROOT / "migrations" / "0016_least_privilege_roles.sql").read_text(encoding="utf-8")
    granted = set()
    for privileges, tables in re.findall(
        r"^GRANT ([A-Z, ]+) ON TABLE ([a-z_., ]+) TO ucpe_space_db;$", text, flags=re.M
    ):
        granted |= {
            (table.strip().removeprefix("public."), privilege.strip())
            for table in tables.split(",") for privilege in privileges.split(",")
        }
    assert granted == set(ri.NEEDED)


# --- classification ------------------------------------------------------------------------------


def test_the_designed_role_is_designed() -> None:
    assert ri.classify(designed_facts()) == {
        "db_role": "ucpe_space_db",
        "login_is_role": True,
        **dict.fromkeys(ATTRIBUTES, False),
        "role_memberships": 0,
        "owner_rights": False,
        "core_write": False,
        "definer_execute": 0,
        "needed_privileges": True,
        "rls_allows_all": True,
        "extra_privileges": 0,
        "verdict": "DESIGNED",
    }


def test_the_owner_is_named_other_and_reported_by_its_capabilities() -> None:
    fields = ri.classify(owner_facts())
    every = len(TABLES) * len(PRIVILEGES_17)
    assert fields == {
        "db_role": "OTHER",
        "login_is_role": True,
        **dict.fromkeys(ATTRIBUTES, True),
        "superuser": False,
        "role_memberships": 7,
        "owner_rights": True,
        "core_write": True,
        "definer_execute": 2,
        "needed_privileges": True,
        "rls_allows_all": True,
        "extra_privileges": every - len(ri.NEEDED) + 3 + 1 + 1,
        "verdict": "NOT_DESIGNED",
    }
    assert "postgres" not in json.dumps(fields)


def test_a_core_write_is_never_designed_even_if_the_design_listed_it(monkeypatch) -> None:
    """X3's backstop: a core write blocks DESIGNED on its own, not only as an extra privilege."""

    wrong_design = (*ri.NEEDED, ("predictions", "INSERT"))
    monkeypatch.setattr(ri, "NEEDED", wrong_design)
    fields = ri.classify(designed_facts(
        relations=relations(set(wrong_design)),
        policies=[*DESIGNED_POLICIES, policy("predictions", "a", using=None, check="true")],
    ))
    assert (fields["extra_privileges"], fields["needed_privileges"]) == (0, True)
    assert fields["rls_allows_all"] is True
    assert (fields["core_write"], fields["verdict"]) == (True, "NOT_DESIGNED")


def _held(*extra: tuple[str, str], missing: tuple[str, str] | None = None) -> list[tuple]:
    return relations((set(ri.NEEDED) | set(extra)) - {missing})


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"current_user": "ucpe_resolver", "session_user": "ucpe_resolver"},
         {"db_role": "ucpe_resolver"}),
        ({"current_user": "authenticator", "session_user": "authenticator"}, {"db_role": "OTHER"}),
        ({"session_user": "postgres"}, {"login_is_role": False}),
        *[({"attributes": {**dict.fromkeys(ATTRIBUTES, False), name: True}}, {name: True})
          for name in ATTRIBUTES],
        ({"memberships": 1}, {"role_memberships": 1}),
        ({"owner_rights": True}, {"owner_rights": True}),
        ({"relations": _held(("predictions", "DELETE"))},
         {"core_write": True, "extra_privileges": 1}),
        ({"relations": _held(("analysis_runs", "SELECT"))}, {"extra_privileges": 1}),
        ({"relations": _held(("prediction_outcomes", "MAINTAIN"))},
         {"core_write": True, "extra_privileges": 1}),
        ({"relations": _held(("watchlist", "INSERT"))}, {"extra_privileges": 1}),
        ({"relations": _held(missing=("automation_radar_ledger", "UPDATE"))},
         {"needed_privileges": False}),
        ({"relations": _held(missing=("predictions", "SELECT"))}, {"needed_privileges": False}),
        ({"sequences": 1}, {"extra_privileges": 1}),
        ({"schema_create": True}, {"extra_privileges": 1}),
        ({"database_create": True}, {"extra_privileges": 1}),
        ({"definers": 1}, {"definer_execute": 1}),
    ],
)
def test_every_deviation_is_not_designed(changes: dict, expected: dict) -> None:
    fields = ri.classify(designed_facts(**changes))
    assert fields["verdict"] == "NOT_DESIGNED"
    baseline = ri.classify(designed_facts())
    assert {key: value for key, value in fields.items()
            if key != "verdict" and baseline[key] != value} == expected


def _policies(*replace: tuple, drop: str | None = None) -> list[tuple]:
    rows = [row for row in DESIGNED_POLICIES if f"{row[0]}/{row[4]}" != drop]
    return rows + list(replace)


def _no_policy(table: str, *, rowsecurity: bool = True) -> tuple:
    """The LEFT JOIN's row for a table without any policy."""

    return (table, rowsecurity, False, False, None, None, None, None, False)


NO_PREDICTIONS_POLICY = _policies(drop="predictions/r") + [_no_policy("predictions")]


@pytest.mark.parametrize(
    "policies",
    [
        NO_PREDICTIONS_POLICY,  # row security on and no policy: no row is visible
        _policies(policy("predictions", "r", permissive=False, using="false")),
        _policies(drop="prediction_outcomes/r") + [
            policy("prediction_outcomes", "r", using="(prediction_id IS NOT NULL)")
        ],
        _policies(drop="automation_radar_ledger/a") + [
            policy("automation_radar_ledger", "a", using=None, check="false")
        ],
        _policies(drop="automation_radar_ledger/w") + [
            policy("automation_radar_ledger", "w", check="false")
        ],
        _policies(drop="predictions/r") + [policy("predictions", "r", applies=False)],
        [row for row in DESIGNED_POLICIES if row[0] != "automation_credential"],  # table missing
    ],
)
def test_row_security_that_hides_any_row_is_caught(policies: list[tuple]) -> None:
    fields = ri.classify(designed_facts(policies=policies))
    assert (fields["rls_allows_all"], fields["verdict"]) == (False, "NOT_DESIGNED")


@pytest.mark.parametrize(
    "policies",
    [
        # row security off on a table: every row is visible to whoever may SELECT
        _policies(drop="predictions/r") + [_no_policy("predictions", rowsecurity=False)],
        # a PUBLIC or FOR ALL policy that is true covers the command
        _policies(drop="predictions/r") + [policy("predictions", "*")],
        _policies(drop="automation_radar_ledger/a") + [policy("automation_radar_ledger", "*")],
        # a restrictive policy that is true hides nothing
        _policies(policy("predictions", "r", permissive=False)),
    ],
)
def test_row_security_that_hides_nothing_is_accepted(policies: list[tuple]) -> None:
    assert ri.classify(designed_facts(policies=policies))["rls_allows_all"] is True


def test_bypass_and_ownership_reach_every_row_unless_forced() -> None:
    hidden = NO_PREDICTIONS_POLICY
    bypass = {**dict.fromkeys(ATTRIBUTES, False), "bypassrls": True}
    assert ri.classify(designed_facts(policies=hidden, attributes=bypass))["rls_allows_all"]
    owned = [(*row[:3], True, *row[4:]) for row in hidden]
    assert ri.classify(designed_facts(policies=owned))["rls_allows_all"] is True
    forced = [(row[0], row[1], True, True, *row[4:]) for row in hidden]
    assert ri.classify(designed_facts(policies=forced))["rls_allows_all"] is False


def test_before_postgresql_17_maintain_is_not_asked() -> None:
    facts = designed_facts(maintain=False, relations=relations(set(ri.NEEDED), maintain=False))
    assert ri.classify(facts)["verdict"] == "DESIGNED"
    with pytest.raises(ri.ReaderIdentityError):
        ri.classify(designed_facts(maintain=False))


@pytest.mark.parametrize(
    "changes",
    [
        {"current_user": "Postgres"},
        {"current_user": "x" * 64},
        {"current_user": None},
        {"attributes": {**dict.fromkeys(ATTRIBUTES, False), "bypassrls": None}},
        {"memberships": True},
        {"memberships": -1},
        {"owner_rights": None},
        {"definers": "0"},
        {"schema_create": 0},
        {"relations": [("predictions", True)]},
        {"relations": [("predictions", *[None] * len(PRIVILEGES_17))]},
        {"policies": [policy("predictions", "r", rowsecurity=None)]},
        {"policies": [*DESIGNED_POLICIES, policy("predictions", "x")]},
        {"policies": [*DESIGNED_POLICIES, policy("predictions", "r", applies=None)]},
        {"policies": [*DESIGNED_POLICIES, policy("predictions", "r", using=1)]},
        {"policies": [*DESIGNED_POLICIES, (*_no_policy("predictions")[:8], True)]},
        {"policies": [*DESIGNED_POLICIES, ("predictions", True)]},
    ],
)
def test_a_malformed_fact_is_an_error_never_a_verdict(changes: dict) -> None:
    with pytest.raises(ri.ReaderIdentityError):
        ri.classify(designed_facts(**changes))


# --- the catalog read ----------------------------------------------------------------------------


class FakeCursor:
    def __init__(self, answers: dict[str, list[tuple]]):
        self.answers = answers
        self.statements: list[tuple[str, object]] = []
        self.rows: list[tuple] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, statement: str, params: object = None) -> None:
        self.statements.append((statement, params))
        self.rows = next(
            (rows for marker, rows in self.answers.items() if marker in statement), []
        )

    def fetchone(self) -> tuple | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple]:
        return list(self.rows)


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self.fake_cursor = cursor
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> FakeCursor:
        return self.fake_cursor

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def catalog(version: int = 170006, **overrides: list[tuple]) -> dict[str, list[tuple]]:
    facts = designed_facts(maintain=version >= 170000)
    if version < 170000:
        facts["relations"] = relations(set(ri.NEEDED), maintain=False)
    answers = {
        "server_version_num": [(version, "ucpe_space_db", "ucpe_space_db")],
        "rolsuper": [tuple(facts["attributes"][name] for name in ATTRIBUTES)],
        "pg_auth_members": [(0,)],
        "bool_or(": [(False,)],
        "has_any_column_privilege": facts["relations"],
        "has_sequence_privilege": [(0,)],
        "has_schema_privilege": [(False, False)],
        "prosecdef": [(0,)],
        "pg_policy": facts["policies"],
    }
    answers.update(overrides)
    return answers


class Driver:
    def __init__(self, answers: dict[str, list[tuple]]):
        self.cursor = FakeCursor(answers)
        self.connection = FakeConnection(self.cursor)
        self.calls: list[tuple[tuple, dict]] = []

    def connect(self, *args: object, **kwargs: object) -> FakeConnection:
        self.calls.append((args, kwargs))
        return self.connection


def test_the_read_is_one_read_only_transaction_of_the_catalog_rolled_back() -> None:
    driver = Driver(catalog())
    facts = ri.read_facts(CUTOVER, connect=driver.connect)
    assert driver.calls == [((CUTOVER,), {"connect_timeout": 10, "autocommit": False,
                                           "prepare_threshold": None,
                                           "tcp_user_timeout": 10_000})]
    statements = [statement for statement, _ in driver.cursor.statements]
    assert statements[0] == "SET TRANSACTION READ ONLY"
    assert statements[1] == "SET LOCAL statement_timeout = 5000"
    assert all(statement.startswith("SELECT ") for statement in statements[2:])
    for statement in statements[2:]:
        for source in re.findall(r"\b(?:FROM|JOIN)\s+(\S+)", statement):
            assert source.startswith(("pg_catalog.", "(")), (source, statement)
    assert driver.connection.rolled_back and driver.connection.closed
    assert ri.classify(facts)["verdict"] == "DESIGNED"


def test_a_type_bound_privilege_check_only_ever_sees_its_own_kind() -> None:
    """has_sequence_privilege fails on a table (42809), and PostgreSQL may evaluate WHERE conditions
    in any order: the first E1 run on real PostgreSQL failed that way. Only a CASE guarantees it."""

    assert "WHERE CASE WHEN c.relkind = 'S' THEN pg_catalog.has_sequence_privilege(" in " ".join(
        ri._SEQUENCES_SQL.split()
    )
    for statement in (ri._SESSION_SQL, ri._ATTRIBUTES_SQL, ri._MEMBERSHIPS_SQL, ri._OWNER_SQL,
                      ri._CREATE_SQL, ri._DEFINERS_SQL, ri._POLICIES_SQL, ri._relations_sql(True)):
        assert "has_sequence_privilege" not in statement


def test_maintain_is_asked_from_postgresql_17_only() -> None:
    for version, asked in ((170006, True), (160004, False)):
        driver = Driver(catalog(version))
        facts = ri.read_facts(CUTOVER, connect=driver.connect)
        privileges = next(s for s, _ in driver.cursor.statements if "has_any_column" in s)
        assert ("'MAINTAIN'" in privileges, facts["maintain"]) == (asked, asked)
        assert ri.classify(facts)["verdict"] == "DESIGNED"


def test_the_policies_are_read_for_the_needed_tables_only() -> None:
    driver = Driver(catalog())
    ri.read_facts(CUTOVER, connect=driver.connect)
    params = next(p for s, p in driver.cursor.statements if "pg_policy" in s)
    assert params == {"tables": sorted({table for table, _ in ri.NEEDED})}


def test_a_missing_answer_raises_and_still_closes() -> None:
    driver = Driver(catalog(rolsuper=[]))
    with pytest.raises(ri.ReaderIdentityError):
        ri.read_facts(CUTOVER, connect=driver.connect)
    assert driver.connection.closed


# --- the event -----------------------------------------------------------------------------------


def test_no_url_is_not_configured_and_connects_nowhere() -> None:
    sink = TelemetrySink()

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("connected")

    fields = ri.report(None, "none", connect=refuse, sink=sink)
    assert fields == {"db_role": "n/a", "verdict": "NOT_CONFIGURED", "release_id": RELEASE_ID,
                      "db_url_source": "none"}
    assert list(sink.events) == [{"event": "evidence_reader_identity", **fields}]


def test_the_designed_report_survives_the_telemetry_allowlist_whole() -> None:
    sink = TelemetrySink()
    fields = ri.report(CUTOVER, "UCPE_SPACE_DB_URL", connect=Driver(catalog()).connect, sink=sink)
    assert fields["verdict"] == "DESIGNED"
    assert (fields["release_id"], fields["db_url_source"]) == (RELEASE_ID, "UCPE_SPACE_DB_URL")
    assert list(sink.events) == [{"event": "evidence_reader_identity", **fields}]


def test_a_failure_is_unknown_with_its_class_only(capsys) -> None:
    sink = TelemetrySink()
    secret_url = "postgresql://ucpe_space_db.abcdefghijklmnopqrst:synthetic-pw@host.invalid/db"

    def fail(*_args: object, **_kwargs: object) -> None:
        raise ConnectionError(f"could not connect to {secret_url}")

    fields = ri.report(secret_url, "UCPE_SPACE_DB_URL", connect=fail, sink=sink)
    assert fields == {"db_role": "error", "verdict": "UNKNOWN", "error_class": "ConnectionError",
                      "release_id": RELEASE_ID, "db_url_source": "UCPE_SPACE_DB_URL"}
    printed = capsys.readouterr().out + json.dumps(list(sink.events))
    assert "synthetic-pw" not in printed and "postgresql://" not in printed
    assert "abcdefghijklmnopqrst" not in printed


def test_a_malformed_catalog_is_unknown_never_designed() -> None:
    sink = TelemetrySink()
    fields = ri.report(CUTOVER, "UCPE_SPACE_DB_URL",
                       connect=Driver(catalog(**{"bool_or(": [(None,)]})).connect, sink=sink)
    assert (fields["verdict"], fields["error_class"]) == ("UNKNOWN", "ReaderIdentityError")


def test_start_report_without_a_url_reports_at_once_and_starts_no_thread(monkeypatch) -> None:
    from crypto_probability_engine.telemetry.events import EVENTS_SINK

    def no_thread(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a thread was started")

    monkeypatch.setattr(ri.threading, "Thread", no_thread)
    ri.start_report(Settings(), "none")
    assert EVENTS_SINK.events[-1]["verdict"] == "NOT_CONFIGURED"


def test_start_report_with_a_url_probes_in_one_daemon_thread(monkeypatch) -> None:
    started: list[dict] = []

    class Recorder:
        def __init__(self, **kwargs: object):
            self.kwargs = kwargs

        def start(self) -> None:
            started.append(self.kwargs)

    monkeypatch.setattr(ri.threading, "Thread", Recorder)
    ri.start_report(Settings(**{"supabase_db_url": CUTOVER}), "UCPE_SPACE_DB_URL")
    assert started == [{"target": ri.report, "args": (CUTOVER, "UCPE_SPACE_DB_URL"),
                        "name": "ucpe-reader-identity", "daemon": True}]


def test_start_report_never_raises(monkeypatch) -> None:
    def broken(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("no threads")

    monkeypatch.setattr(ri.threading, "Thread", broken)
    assert ri.start_report(Settings(**{"supabase_db_url": CUTOVER}), "UCPE_SPACE_DB_URL") is None
