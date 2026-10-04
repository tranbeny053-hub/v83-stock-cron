"""D6's core-write inventory route: core_write_inventory.py --mode attest|rehearse|inventory.

The route reads production's catalogs with the owner URL, so it carries the other database routes'
trust boundary: a verified dispatch of THIS workflow on main at expected_sha, the isolated runtime,
one read-only snapshot that is always rolled back. The repository is public, so its logs are too:
only API, pg_* and ucpe_* role names are published, never the server version or the URL. No
database is contacted here: the driver is a scripted fake.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from crypto_probability_engine.runtime_isolation import REQUIRED_FLAGS_TEXT, ProvenanceRefused
from scripts import core_write_inventory as inventory

ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40
URL = "postgresql://owner-login:never-printed@db.example.invalid:5432/postgres"
REHEARSAL_URL = "postgresql:///inventory_rehearsal?host=/var/run/postgresql"
FORECAST = "public.save_forecast_bundle(jsonb, jsonb, jsonb, jsonb, jsonb)"


# --------------------------------------------------------------------------- the dispatch


def _dispatch(**changes: str) -> dict[str, str]:
    dispatch = {
        "github_actions": "true",
        "event_name": "workflow_dispatch",
        "repository": inventory.EXPECTED_REPOSITORY,
        "workflow_ref": f"{inventory.EXPECTED_REPOSITORY}/{inventory.WORKFLOW}@refs/heads/main",
        "ref": "refs/heads/main",
        "sha": SHA,
        "run_id": "37150000000",
        "run_attempt": "1",
    }
    return {**dispatch, **changes}


def _runtime(**changes: object) -> dict[str, object]:
    runtime = {
        "git_head": SHA,
        "tracked_tree_clean": True,
        "python_implementation": "CPython",
        "python_version": "3.13.14",
        "interpreter_flags": REQUIRED_FLAGS_TEXT,
        "installed_files_sha256": "b" * 64,
    }
    return {**runtime, **changes}


def test_a_manual_dispatch_of_this_workflow_on_main_at_the_sha_verifies() -> None:
    record = inventory.verify_dispatch(_dispatch(), _runtime(), expected_sha=SHA)
    assert record["dispatch_verified"] is True and record["workflow"] == inventory.WORKFLOW
    assert record["schema_version"] == inventory.DISPATCH_SCHEMA and record["sha"] == SHA


@pytest.mark.parametrize(
    ("dispatch", "runtime", "expected_sha", "message"),
    [
        ({"github_actions": "false"}, {}, SHA, "not running inside GitHub Actions"),
        ({"repository": "someone/fork"}, {}, SHA, "not the owner repository"),
        ({"event_name": "push"}, {}, SHA, "not a manual workflow_dispatch"),
        ({"ref": "refs/heads/feature"}, {}, SHA, "not refs/heads/main"),
        (
            {"workflow_ref": f"{inventory.EXPECTED_REPOSITORY}/.github/workflows/"
                             "audit-table-privileges.yml@refs/heads/main"},
            {}, SHA, f"not {inventory.WORKFLOW}",
        ),
        ({"sha": "c" * 40}, {}, SHA, "is not expected_sha"),
        ({}, {"git_head": "c" * 40}, SHA, "the checked-out commit"),
        ({}, {"tracked_tree_clean": False}, SHA, "tracked files differ"),
        ({}, {"python_version": "3.13.13"}, SHA, "interpreter is CPython 3.13.13"),
        ({}, {"interpreter_flags": ""}, SHA, "did not start isolated"),
        ({}, {"installed_files_sha256": ""}, SHA, "installed files were not verified"),
        ({"run_id": "x"}, {}, SHA, "run_id is not a GitHub run id"),
        ({"run_attempt": ""}, {}, SHA, "run_attempt is not a number"),
        ({}, {}, SHA.upper(), "expected_sha must be the full"),
        ({}, {}, SHA[:12], "expected_sha must be the full"),
    ],
)
def test_anything_else_is_refused(dispatch, runtime, expected_sha, message) -> None:
    with pytest.raises(ProvenanceRefused, match=message):
        inventory.verify_dispatch(_dispatch(**dispatch), _runtime(**runtime),
                                  expected_sha=expected_sha)


# --------------------------------------------------------------------------- a scripted server


class Cursor:
    """A cursor answering by statement; every statement is kept in order."""

    def __init__(self, answers) -> None:
        self.answers, self.executed, self.rows = answers, [], []

    def execute(self, sql: str, values=None) -> None:
        self.executed.append(sql)
        self.rows = list(self.answers(sql))

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


class Connection:
    def __init__(self, answers) -> None:
        self.cursor_, self.rolled_back = Cursor(answers), False

    def cursor(self) -> Cursor:
        return self.cursor_

    def rollback(self) -> None:
        self.rolled_back = True

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


def _server(*, read_only: str = "on", version: str = "170006", extra=None, held=()):
    """Production as D6 expects it before freeze, plus ``extra`` surfaces by kind."""

    surfaces = {
        "T": [(table, "INSERT") for table in inventory.CORE_TABLES],
        "F": [(FORECAST, "ucpe_bundle_owner")],
    }
    for kind, rows in (extra or {}).items():
        surfaces[kind] = surfaces.get(kind, []) + rows
    by_sql = {inventory.QUERIES[kind]: rows for kind, rows in surfaces.items()}
    by_sql.update({
        inventory.TRANSACTION_READ_ONLY_SQL: [(read_only,)],
        inventory.SERVER_VERSION_SQL: [(version,)],
        inventory.INFORMATION["bypassrls"]: [(True,)],
        inventory.INFORMATION["memberships"]: [("supabase_admin",)],
        inventory.INFORMATION["default_privileges"]: [
            ("postgres", "public", "r", "service_role=arwdDxtm/postgres,=r/supabase_admin"),
        ],
        inventory.REHEARSAL_HELD_SQL: [(table,) for table in held],
    })
    return lambda sql: by_sql.get(sql, [])


def _route(monkeypatch, connection: Connection) -> list[dict]:
    connects: list[dict] = []

    def connect(url: str, **options):
        connects.append({"url": url, **options})
        return connection

    monkeypatch.setattr(inventory, "enter_isolated_runtime", lambda wheelhouse: object())
    monkeypatch.setattr(inventory, "attest_dispatch",
                        lambda sha, environ, isolation: {"dispatch_verified": True})
    monkeypatch.setattr(inventory, "attest_loaded_modules", lambda isolation: 1)
    monkeypatch.setattr(inventory, "load_driver", lambda: SimpleNamespace(connect=connect))
    return connects


def _inventory_args(tmp_path: Path, expect: str = "before") -> list[str]:
    return ["--mode=inventory", f"--expect={expect}", f"--confirm={inventory.CONFIRMATION}",
            "--wheelhouse=wheels", f"--expected-sha={SHA}",
            f"--report={tmp_path / 'core-write-inventory.json'}"]


# --------------------------------------------------------------------------- the inventory


def test_a_clean_inventory_passes_and_publishes_no_unlisted_name(monkeypatch, tmp_path, capsys):
    connection = Connection(_server())
    connects = _route(monkeypatch, connection)
    assert inventory.main(_inventory_args(tmp_path), environ={"SUPABASE_DB_URL": URL}) == 0
    printed = capsys.readouterr().out
    report = json.loads((tmp_path / "core-write-inventory.json").read_text())
    assert report["outcome"] == "INVENTORIED" and report["verdict"] == "PASS"
    assert report["snapshot"] == {"transaction_read_only": "on", "rolled_back": True}
    assert report["failures"] == [] and report["expect"] == "before"
    assert report["committed"] is False and connection.rolled_back
    published = json.dumps(report) + printed
    for private in ("postgres", "supabase_admin", "owner-login", "never-printed", "example.invalid",
                    "170006", "server_version_num"):
        assert private not in published, private
    assert report["inventory"]["maintain_inventoried"] is True
    assert report["inventory"]["surfaces"]["F"] == [[FORECAST, "ucpe_bundle_owner"]]
    assert report["inventory"]["information"]["default_privileges"] == [
        [inventory.WITHHELD, "public", "r",
         f"service_role=arwdDxtm/{inventory.WITHHELD},=r/{inventory.WITHHELD}"],
    ]
    assert connects == [{"url": URL, "connect_timeout": 8, "autocommit": False,
                         "prepare_threshold": None}]


def test_the_snapshot_is_read_only_first_and_always_rolled_back(monkeypatch, tmp_path) -> None:
    connection = Connection(_server())
    _route(monkeypatch, connection)
    inventory.main(_inventory_args(tmp_path), environ={"SUPABASE_DB_URL": URL})
    executed = connection.cursor_.executed
    assert executed[:3] == list(inventory.GUARD_STATEMENTS)
    assert executed[3:5] == [inventory.TRANSACTION_READ_ONLY_SQL, inventory.SERVER_VERSION_SQL]
    assert inventory.REHEARSAL_HELD_SQL not in executed, "current_user is a rehearsal-only read"


def test_a_server_that_is_not_read_only_is_refused_and_rolled_back(monkeypatch, tmp_path) -> None:
    connection = Connection(_server(read_only="off"))
    _route(monkeypatch, connection)
    assert inventory.main(_inventory_args(tmp_path), environ={"SUPABASE_DB_URL": URL}) == 2
    report = json.loads((tmp_path / "core-write-inventory.json").read_text())
    assert report["outcome"] == "REFUSED" and "transaction_read_only='off'" in report["detail"]
    assert connection.rolled_back


def test_an_omitted_surface_fails_the_step_with_its_redacted_row(monkeypatch, tmp_path) -> None:
    connection = Connection(_server(extra={"F": [("public.other_definer()", "postgres")]}))
    _route(monkeypatch, connection)
    assert inventory.main(_inventory_args(tmp_path), environ={"SUPABASE_DB_URL": URL}) == 1
    report = json.loads((tmp_path / "core-write-inventory.json").read_text())
    assert report["verdict"] == "FAIL"
    assert report["failures"] == [f"F public.other_definer() {inventory.WITHHELD}"]


def test_after_d6_any_surface_left_fails(monkeypatch, tmp_path) -> None:
    _route(monkeypatch, Connection(_server()))
    assert inventory.main(_inventory_args(tmp_path, "after"),
                          environ={"SUPABASE_DB_URL": URL}) == 1
    report = json.loads((tmp_path / "core-write-inventory.json").read_text())
    assert report["verdict"] == "FAIL" and len(report["failures"]) == 7


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--mode=inventory", "--expect=before", "--confirm=yes"], "--confirm must be exactly"),
        (["--mode=inventory", "--expect=sometimes", f"--confirm={inventory.CONFIRMATION}"],
         "--expect must be exactly before or after"),
        (["--mode=inventory", "--expect=", f"--confirm={inventory.CONFIRMATION}"],
         "--expect must be exactly before or after"),
    ],
)
def test_the_inventory_needs_the_exact_token_and_expectation(arguments, message, capsys) -> None:
    assert inventory.main(arguments, environ={"SUPABASE_DB_URL": URL}) == 2
    assert message in capsys.readouterr().err


def test_without_the_secret_the_inventory_refuses_after_attesting(monkeypatch, tmp_path, capsys):
    _route(monkeypatch, Connection(_server()))
    assert inventory.main(_inventory_args(tmp_path), environ={}) == 2
    assert "SUPABASE_DB_URL is not set" in capsys.readouterr().err


def test_an_unexpected_failure_is_reported_by_its_type_only(monkeypatch, tmp_path, capsys):
    def boom(url: str, **options):
        raise RuntimeError(f"could not connect to {url}")

    _route(monkeypatch, Connection(_server()))
    monkeypatch.setattr(inventory, "load_driver", lambda: SimpleNamespace(connect=boom))
    assert inventory.main(_inventory_args(tmp_path), environ={"SUPABASE_DB_URL": URL}) == 1
    published = capsys.readouterr().err + (tmp_path / "core-write-inventory.json").read_text()
    assert "RuntimeError" in published and "never-printed" not in published
    assert "example.invalid" not in published


def test_attest_mode_never_touches_a_database(monkeypatch, tmp_path) -> None:
    _route(monkeypatch, Connection(_server()))
    monkeypatch.setattr(inventory, "load_driver", lambda: SimpleNamespace(
        connect=lambda *a, **k: pytest.fail("attest connected")))
    import crypto_probability_engine.runtime_isolation as isolation

    monkeypatch.setattr(isolation, "loaded_dynamic_helpers", lambda: [])
    report = tmp_path / "attest.json"
    assert inventory.main(["--mode=attest", f"--expected-sha={SHA}", "--wheelhouse=wheels",
                           f"--report={report}"], environ={"SUPABASE_DB_URL": URL}) == 0
    assert json.loads(report.read_text())["touches_database"] is False


# --------------------------------------------------------------------------- the rehearsal


PLANTED = {
    "F": [("public.inventory_probe_definer()", "postgres"),
          ("public.inventory_probe_trigger()", "postgres")],
    "V": [("public.inventory_probe_view", "predictions")],
    "R": [("public.inventory_probe_rule_table.inventory_probe_rule", "prediction_outcomes")],
    "G": [("public.inventory_probe_trigger_table.inventory_probe_trigger", "postgres")],
    "K": [("analysis_run_details_inventory_probe_fkey",
           "analysis_run_details -> public.inventory_probe_parent")],
}


def _rehearse(monkeypatch, tmp_path, connection, environ=None) -> int:
    monkeypatch.setattr(inventory, "load_driver",
                        lambda: SimpleNamespace(connect=lambda url, **options: connection))
    return inventory.main(
        ["--mode=rehearse", f"--report={tmp_path / 'rehearsal.json'}"],
        environ={inventory.REHEARSAL_URL_VARIABLE: REHEARSAL_URL} if environ is None else environ,
    )


def test_the_rehearsal_passes_when_every_planted_surface_and_nothing_else_is_caught(
    monkeypatch, tmp_path
) -> None:
    connection = Connection(_server(version="160004", extra=PLANTED))
    assert _rehearse(monkeypatch, tmp_path, connection) == 0
    report = json.loads((tmp_path / "rehearsal.json").read_text())
    assert report["outcome"] == "REHEARSED" and connection.rolled_back
    assert {row.split()[0] for row in report["omitted"]} == set(inventory.REHEARSAL_PLANTED_KINDS)
    assert inventory.REHEARSAL_HELD_SQL in connection.cursor_.executed
    assert report["inventory"]["maintain_inventoried"] is False


@pytest.mark.parametrize(
    ("server", "message"),
    [
        ({"extra": {k: v for k, v in PLANTED.items() if k != "R"}},
         "the planted R surface was not caught"),
        ({"extra": {**PLANTED, "V": PLANTED["V"] + [("public.some_view", "predictions")]}},
         "a surface outside the planted ones is omitted"),
        ({"extra": PLANTED, "held": ("predictions",)}, "catalogs only is not proven"),
    ],
)
def test_the_rehearsal_refuses_anything_its_fixtures_were_not_built_to_show(
    monkeypatch, tmp_path, server, message
) -> None:
    connection = Connection(_server(version="160004", **server))
    assert _rehearse(monkeypatch, tmp_path, connection) == 2
    assert message in json.loads((tmp_path / "rehearsal.json").read_text())["detail"]


def test_the_rehearsal_refuses_a_missing_insert_on_a_core_table(monkeypatch, tmp_path) -> None:
    def answers(sql: str):
        rows = _server(version="160004", extra=PLANTED)(sql)
        if sql == inventory.QUERIES["T"]:
            return [row for row in rows if row[0] != "predictions"]
        return rows

    assert _rehearse(monkeypatch, tmp_path, Connection(answers)) == 2
    detail = json.loads((tmp_path / "rehearsal.json").read_text())["detail"]
    assert "service_role INSERT on predictions was not seen" in detail


@pytest.mark.parametrize(
    "environ",
    [
        {inventory.REHEARSAL_URL_VARIABLE: "postgresql://db.example.invalid/inventory_rehearsal"},
        {inventory.REHEARSAL_URL_VARIABLE: ""},
        {inventory.REHEARSAL_URL_VARIABLE: REHEARSAL_URL, "SUPABASE_DB_URL": URL},
    ],
    ids=["network-host", "missing", "beside-the-production-secret"],
)
def test_the_rehearsal_only_ever_reaches_a_local_scratch_server(monkeypatch, tmp_path, environ):
    connection = Connection(_server(extra=PLANTED))
    assert _rehearse(monkeypatch, tmp_path, connection, environ) == 2
    assert connection.cursor_.executed == []


# --------------------------------------------------------------------------- what is published


@pytest.mark.parametrize(
    ("name", "published"),
    [
        ("anon", "anon"),
        ("authenticated", "authenticated"),
        ("authenticator", "authenticator"),
        ("service_role", "service_role"),
        ("ucpe_bundle_owner", "ucpe_bundle_owner"),
        ("pg_read_all_data", "pg_read_all_data"),
        ("postgres", inventory.WITHHELD),
        ("supabase_admin", inventory.WITHHELD),
        ("Owner Login", inventory.WITHHELD),
        ("ucpe_", inventory.WITHHELD),
        ("", inventory.WITHHELD),
    ],
)
def test_only_api_pg_and_ucpe_role_names_are_published(name: str, published: str) -> None:
    assert inventory.reported_role(name) == published


@pytest.mark.parametrize(
    ("acl", "published"),
    [
        ("service_role=arwdDxt/postgres", f"service_role=arwdDxt/{inventory.WITHHELD}"),
        ("=X/postgres", f"=X/{inventory.WITHHELD}"),
        ("anon=r/ucpe_bundle_owner,postgres=arwdDxtm/postgres",
         f"anon=r/ucpe_bundle_owner,{inventory.WITHHELD}=arwdDxtm/{inventory.WITHHELD}"),
        ('"owner, login"=r/postgres',
         f"{inventory.WITHHELD},{inventory.WITHHELD}=r/{inventory.WITHHELD}"),
        ("garbage", inventory.WITHHELD),
    ],
)
def test_an_acl_is_published_item_by_item(acl: str, published: str) -> None:
    assert inventory.reported_acl(acl) == published


def test_the_module_imports_only_the_standard_library_at_module_level() -> None:
    tree = ast.parse((ROOT / inventory.SCRIPT).read_text(encoding="utf-8"))
    imported = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module)
    assert imported <= {"__future__", "argparse", "json", "os", "platform", "re", "subprocess",
                        "sys", "collections.abc", "pathlib", "typing"}, imported
