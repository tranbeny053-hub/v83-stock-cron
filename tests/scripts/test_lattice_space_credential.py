import re
from pathlib import Path
from urllib.parse import unquote

from scripts import lattice_space_credential as credential
from scripts import resolver_credential

ROOT = Path(__file__).resolve().parents[2]
REF = "abcdefghijklmnopqrst"
POOLER = "aws-0-eu-central-1.pooler.supabase.com"
SESSION = f"postgresql://postgres.{REF}:[YOUR-PASSWORD]@{POOLER}:5432/postgres"


def test_identity_matches_migration_and_runbook():
    migration = (ROOT / "migrations/authored/0020_lattice_space_login.sql").read_text()
    runbook = (ROOT / "docs/runbooks/NG4_PILOT_W2.md").read_text()
    assert re.search(rf"CREATE ROLE {credential.ROLE}\b", migration)
    assert credential.SECRET_NAME in runbook


def test_commands_keep_secret_values_off_output(tmp_path, capsys):
    assert credential.main(["generate", "--dir", str(tmp_path)], paste=lambda: SESSION) == 0
    assert credential.main(["copy-sql", "--dir", str(tmp_path)], clipboard=lambda _: None) == 0
    assert credential.main(["copy-url", "--dir", str(tmp_path)], clipboard=lambda _: None) == 0
    output = capsys.readouterr().out
    sql = (tmp_path / credential.SQL_NAME).read_text()
    url = (tmp_path / credential.URL_NAME).read_text().strip()
    plain = unquote(url.split(":")[2].split("@")[0])
    assert all(value not in output for value in (sql, url, plain, REF, POOLER))
    assert credential.ROLE == "ucpe_lattice_space"
    assert credential.SQL_NAME == "ucpe-lattice-space-login.sql"
    assert credential.URL_NAME == "ucpe-lattice-space-db-url.txt"
    assert resolver_credential.ROLE != credential.ROLE


def _assert_guarded_structure(sql: str) -> None:
    alter = sql.index("ALTER ROLE")
    assert sql.count("DO $ucpe_login$") == 1
    assert sql.count("$ucpe_login$;") == 1
    assert sql.count("ALTER ROLE") == 1
    for code in (f"UPL{i:02}" for i in range(1, 7)):
        refusal = sql.index(f"USING ERRCODE = '{code}'")
        assert refusal < alter


def test_generate_writes_guarded_login_sql_and_qualifies_catalog_access(tmp_path, capsys):
    assert credential.main(
        ["generate", "--dir", str(tmp_path)], paste=lambda: SESSION
    ) == 0
    sql = (tmp_path / credential.SQL_NAME).read_text()
    url = (tmp_path / credential.URL_NAME).read_text()
    plain = unquote(url.split(":")[2].split("@")[0])
    verifier = re.search(r"SCRAM-SHA-256\$[^']+", sql).group()
    assert plain not in sql
    assert sql.count(verifier) == 1
    _assert_guarded_structure(sql)
    set_config = "PERFORM pg_catalog.set_config('search_path', 'pg_catalog, pg_temp', true);"
    assert sql.count(set_config) == 1
    assert sql.index(set_config) < sql.index("USING ERRCODE = 'UPL01'")
    accepted_sets = re.findall(r"c\.relname IN \(([^)]*)\)", sql)
    assert accepted_sets and all(
        [name.strip().strip("'") for name in accepted.split(",")]
        == ["pg_stat_statements", "pg_stat_statements_info"]
        for accepted in accepted_sets
    )
    assert unquote(url.split(":")[2].split("@")[0]) not in sql
    listed = (
        "pg_roles", "pg_auth_members", "pg_db_role_setting", "pg_class", "pg_namespace",
        "pg_has_role", "has_table_privilege", "has_any_column_privilege",
        "has_sequence_privilege", "has_schema_privilege", "format", "string_agg",
        "array_agg", "unnest", "quote_ident", "count",
    )
    for name in listed:
        assert not re.search(rf"(?<!pg_catalog\.)\b{re.escape(name)}\b", sql)


def test_resolver_generate_keeps_default_login_sql_shape(tmp_path):
    folder = tmp_path / "resolver-keys"
    resolver_credential.generate(folder, SESSION)
    sql = (folder / resolver_credential.SQL_NAME).read_text()
    assert re.fullmatch(
        r"ALTER ROLE ucpe_resolver WITH LOGIN PASSWORD 'SCRAM-SHA-256\$[^']+';\n", sql
    )


def test_guard_structure_rejects_each_missing_upl_check():
    sql = credential.guarded_login_sql("test-only-password")
    _assert_guarded_structure(sql)
    for code in (f"UPL{i:02}" for i in range(1, 7)):
        mutated = re.sub(
            rf"^.*USING ERRCODE = '{code}'.*\n", "", sql, count=1, flags=re.MULTILINE
        )
        import pytest

        with pytest.raises((AssertionError, ValueError)):
            _assert_guarded_structure(mutated)


def test_guarded_login_sql_rejects_other_role():
    import pytest

    with pytest.raises(ValueError, match="the guarded login is only for ucpe_lattice_space"):
        credential.guarded_login_sql("test-only-password", role="other")
