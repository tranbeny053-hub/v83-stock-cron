"""E2: the owner's Space reader login helper (scripts/space_db_credential.py).

It is G1's resolver helper for the role ucpe_space_db; tests/scripts/test_resolver_credential.py
proves the shared rules (RFC 7677's SCRAM, the templates Supabase accepts, the owner-only files).
Here: the role, the files and the secret are the Space's, the resolver's own files are never
touched, and nothing secret is printed. Behind a real PostgreSQL, the privilege rehearsal's E1 logs
in with this helper's secret and URL. Everything is a throwaway in pytest's tmp_path.
"""

from __future__ import annotations

import base64
import os
import re
import stat
from pathlib import Path
from urllib.parse import unquote

import pytest

from scripts import resolver_credential
from scripts import space_db_credential as credential

REF = "abcdefghijklmnopqrst"
POOLER = "aws-0-eu-central-1.pooler.supabase.com"
SESSION = f"postgresql://postgres.{REF}:[YOUR-PASSWORD]@{POOLER}:5432/postgres"


@pytest.fixture()
def made(tmp_path: Path, capsys) -> tuple[Path, list[str], str]:
    folder, clipboard = tmp_path / "ucpe-keys", []
    assert credential.main(["generate", "--dir", str(folder)], paste=lambda: SESSION,
                           clipboard=clipboard.append) == 0
    return folder, clipboard, capsys.readouterr().out


def test_the_names_are_the_space_s_own() -> None:
    assert (credential.ROLE, credential.SQL_NAME, credential.URL_NAME, credential.SECRET_NAME) == (
        "ucpe_space_db", "ucpe-space-db-login.sql", "ucpe-space-db-url.txt", "UCPE_SPACE_DB_URL"
    )
    assert {credential.SQL_NAME, credential.URL_NAME}.isdisjoint(
        {resolver_credential.SQL_NAME, resolver_credential.URL_NAME}
    )


def test_generate_writes_the_space_role_s_login_and_url_that_belong_together(made) -> None:
    folder, _, _ = made
    sql = (folder / credential.SQL_NAME).read_text()
    url = (folder / credential.URL_NAME).read_text()
    match = re.fullmatch(
        r"ALTER ROLE ucpe_space_db WITH LOGIN PASSWORD '(SCRAM-SHA-256\$[^']+)';\n", sql
    )
    assert match is not None
    login = re.fullmatch(
        rf"postgresql://ucpe_space_db\.{REF}:([A-Za-z0-9_%-]+)@{re.escape(POOLER)}:5432/postgres\n",
        url,
    )
    assert login is not None
    plain = unquote(login.group(1))
    assert len(plain) >= 43 and plain not in sql
    verifier = match.group(1)
    salt = base64.b64decode(verifier.rsplit("$", 1)[0].split(":")[1])
    assert resolver_credential.scram_verifier(plain, salt=salt) == verifier, "one credential"
    modes = [stat.S_IMODE(os.stat(path).st_mode) for path in
             (folder, folder / credential.SQL_NAME, folder / credential.URL_NAME)]
    assert modes == [0o700, 0o600, 0o600]
    assert not (folder / resolver_credential.SQL_NAME).exists()
    assert not (folder / resolver_credential.URL_NAME).exists()


def test_the_resolver_s_files_and_the_space_s_live_side_by_side(tmp_path: Path) -> None:
    folder = tmp_path / "ucpe-keys"
    assert resolver_credential.main(["generate", "--dir", str(folder)], paste=lambda: SESSION) == 0
    resolver_url = (folder / resolver_credential.URL_NAME).read_text()
    assert credential.main(["generate", "--dir", str(folder)], paste=lambda: SESSION) == 0
    assert (folder / resolver_credential.URL_NAME).read_text() == resolver_url
    assert "ucpe_resolver." in resolver_url
    assert "ucpe_space_db." in (folder / credential.URL_NAME).read_text()


def test_the_commands_print_names_and_modes_never_the_credential(made, capsys) -> None:
    folder, clipboard, generated = made
    assert credential.main(["copy-sql", "--dir", str(folder)], clipboard=clipboard.append) == 0
    assert credential.main(["copy-url", "--dir", str(folder)], clipboard=clipboard.append) == 0
    printed = generated + capsys.readouterr().out
    sql, url = clipboard
    assert sql == (folder / credential.SQL_NAME).read_text()
    assert url == (folder / credential.URL_NAME).read_text().strip()
    assert "role: ucpe_space_db" in printed
    assert "connection: shared pooler, session mode" in printed
    assert "for the Space secret UCPE_SPACE_DB_URL" in printed
    plain = unquote(url.split(":")[2].split("@")[0])
    for leak in (plain, url, sql.split("'")[1], REF, POOLER):
        assert leak not in printed


def test_generate_never_overwrites_and_a_refused_template_writes_nothing(made, tmp_path, capsys):
    folder, _, _ = made
    before = (folder / credential.URL_NAME).read_text()
    assert credential.main(["generate", "--dir", str(folder)], paste=lambda: SESSION) == 1
    assert (folder / credential.URL_NAME).read_text() == before
    empty = tmp_path / "keys"
    real = SESSION.replace("[YOUR-PASSWORD]", "an-actual-password")
    assert credential.main(["generate", "--dir", str(empty)], paste=lambda: real) == 1
    printed = capsys.readouterr()
    assert "REFUSED: the clipboard is not the dashboard's connection URI" in printed.err
    assert "an-actual-password" not in printed.err + printed.out
    assert not empty.exists()


def test_the_key_folder_must_be_outside_the_repository(capsys) -> None:
    inside = resolver_credential.ROOT / ".work" / "ucpe-keys-never"
    assert credential.main(["generate", "--dir", str(inside)], paste=lambda: SESSION) == 1
    assert "outside this repository" in capsys.readouterr().err
    assert not inside.exists()


def test_a_missing_credential_says_run_generate(tmp_path: Path, capsys) -> None:
    assert credential.main(["copy-url", "--dir", str(tmp_path / "nothing")]) == 1
    assert "run generate first" in capsys.readouterr().err
