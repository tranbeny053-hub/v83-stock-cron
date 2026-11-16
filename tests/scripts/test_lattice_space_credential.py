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
