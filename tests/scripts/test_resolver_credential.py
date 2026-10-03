"""G1: the owner's resolver login helper (scripts/resolver_credential.py).

Everything here is a throwaway in pytest's tmp_path; no real credential is ever made. The SCRAM
secret is checked against RFC 7677's own worked example, independently of the code under test. The
connection rules are Supabase's (guides/database/connecting-to-postgres, re-read 2026-10-03):
direct connections and the dedicated pooler use `postgres`, the shared pooler `postgres.[REF]`, and
"if you connect as a custom role through the shared pooler, the username is [ROLE].[PROJECT-REF]".
Behind a real PostgreSQL, the privilege rehearsal's R1 logs in with the helper's secret and URL.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import stat
import subprocess
from pathlib import Path
from urllib.parse import unquote

import pytest

from scripts import resolver_credential as credential

REF = "abcdefghijklmnopqrst"
POOLER = "aws-0-eu-central-1.pooler.supabase.com"
SESSION = f"postgresql://postgres.{REF}:[YOUR-PASSWORD]@{POOLER}:5432/postgres"
_VERIFIER = re.compile(
    r"SCRAM-SHA-256\$4096:([A-Za-z0-9+/]{22}==)\$([A-Za-z0-9+/]{43}=):([A-Za-z0-9+/]{43}=)"
)


def _keys(verifier: str) -> tuple[bytes, bytes, bytes]:
    salt, stored, server = _VERIFIER.fullmatch(verifier).groups()
    return base64.b64decode(salt), base64.b64decode(stored), base64.b64decode(server)


def test_the_scram_secret_reproduces_rfc_7677_s_worked_example() -> None:
    """RFC 7677 §3: user "user", "pencil", salt W22ZaJ0SNY7soEsUEjb6gQ==, 4096 iterations."""

    phrase, salt = "pencil", base64.b64decode("W22ZaJ0SNY7soEsUEjb6gQ==")
    head, keys = credential.scram_verifier(phrase, salt=salt).rsplit("$", 1)
    assert head == "SCRAM-SHA-256$4096:W22ZaJ0SNY7soEsUEjb6gQ=="
    stored_key, server_key = (base64.b64decode(key) for key in keys.split(":"))
    salted = hashlib.pbkdf2_hmac("sha256", phrase.encode(), salt, 4096)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    assert hashlib.sha256(client_key).digest() == stored_key
    nonce = "rOprNGfwEbeRWgbNEkqO%hvYDpWUa2RaTCAfuxFIlj)hNlF$k0"
    auth = (f"n=user,r=rOprNGfwEbeRWgbNEkqO,r={nonce},s=W22ZaJ0SNY7soEsUEjb6gQ==,i=4096,"
            f"c=biws,r={nonce}").encode()
    signature = hmac.new(stored_key, auth, hashlib.sha256).digest()
    proof = bytes(left ^ right for left, right in zip(client_key, signature, strict=True))
    assert base64.b64encode(proof).decode() == "dHzbZapWIk4jUhN+Ute9ytag9zjfMHgsqmmiz7AndVQ="
    assert base64.b64encode(hmac.new(server_key, auth, hashlib.sha256).digest()).decode() == (
        "6rriTRBi23WpRR/wtup+mMhUZUn/dB5nLTJRsjl95G4="
    )


def test_each_secret_has_postgresql_s_format_and_a_fresh_salt() -> None:
    first, second = credential.scram_verifier("x" * 43), credential.scram_verifier("x" * 43)
    assert _VERIFIER.fullmatch(first) and _VERIFIER.fullmatch(second)
    assert len(_keys(first)[0]) == 16 and _keys(first)[0] != _keys(second)[0]
    with pytest.raises(credential.CredentialError, match="ASCII"):
        credential.scram_verifier("pässword")


@pytest.mark.parametrize(
    ("template", "user", "mode"),
    [
        (SESSION, f"ucpe_resolver.{REF}", "shared pooler, session mode"),
        (SESSION.replace(":5432/", ":6543/"), f"ucpe_resolver.{REF}",
         "shared pooler, transaction mode"),
        (f"postgresql://postgres:[YOUR-PASSWORD]@db.{REF}.supabase.co:5432/postgres",
         "ucpe_resolver", "direct connection"),
        (f"postgresql://postgres:[YOUR-PASSWORD]@db.{REF}.supabase.co:6543/postgres",
         "ucpe_resolver", "dedicated pooler, transaction mode"),
        (f"  {SESSION}?sslmode=require\n", f"ucpe_resolver.{REF}", "shared pooler, session mode"),
    ],
    ids=["session", "transaction", "direct", "dedicated", "options-and-whitespace"],
)
def test_the_role_replaces_postgres_and_the_rest_of_the_template_stays(
    template: str, user: str, mode: str
) -> None:
    url, found = credential.resolver_url(template, "Plain_token-123")
    assert found == mode
    expected = template.strip().replace("[YOUR-PASSWORD]", "Plain_token-123")
    expected = re.sub(r"//postgres(\.[a-z0-9]{20})?:", f"//{user}:", expected)
    assert url == expected


@pytest.mark.parametrize(
    "template",
    [
        SESSION.replace("[YOUR-PASSWORD]", "an-actual-password"),
        SESSION.replace("postgres.", "authenticator."),
        SESSION.replace(POOLER, "db.example.com"),
        SESSION.replace(f"postgres.{REF}", "postgres"),
        f"postgresql://postgres.{REF}:[YOUR-PASSWORD]@db.{REF}.supabase.co:5432/postgres",
        SESSION.replace(":5432/", ":5433/"),
        SESSION.replace("postgresql://", "https://"),
        "",
    ],
    ids=["a-real-password", "another-user", "not-supabase", "pooler-without-ref",
         "direct-with-ref", "port", "scheme", "empty"],
)
def test_anything_but_the_dashboard_s_template_is_refused_and_never_echoed(template: str) -> None:
    with pytest.raises(credential.CredentialError) as refused:
        credential.resolver_url(template, "Plain_token-123")
    assert "an-actual-password" not in str(refused.value)
    assert REF not in str(refused.value)


def test_the_url_quotes_a_password_s_reserved_characters() -> None:
    url = credential.build_url("postgresql", "ucpe_resolver", "a/b@c:d", "h", "5432", "postgres")
    assert url == "postgresql://ucpe_resolver:a%2Fb%40c%3Ad@h:5432/postgres"


@pytest.fixture()
def made(tmp_path: Path, capsys) -> tuple[Path, list[str], str]:
    folder, clipboard = tmp_path / "ucpe-keys", []
    assert credential.main(["generate", "--dir", str(folder)], paste=lambda: SESSION,
                           clipboard=clipboard.append) == 0
    return folder, clipboard, capsys.readouterr().out


def test_generate_writes_two_owner_only_files_that_belong_together(made) -> None:
    folder, _, _ = made
    sql = (folder / credential.SQL_NAME).read_text()
    url = (folder / credential.URL_NAME).read_text()
    match = re.fullmatch(
        r"ALTER ROLE ucpe_resolver WITH LOGIN PASSWORD '(SCRAM-SHA-256\$[^']+)';\n", sql
    )
    assert match is not None
    login = re.fullmatch(
        rf"postgresql://ucpe_resolver\.{REF}:([A-Za-z0-9_%-]+)@{re.escape(POOLER)}:5432/postgres\n",
        url,
    )
    assert login is not None
    plain = unquote(login.group(1))
    assert len(plain) >= 43 and plain not in sql, "the SQL never holds the password itself"
    salt, stored, server = _keys(match.group(1))
    assert credential.scram_verifier(plain, salt=salt) == match.group(1), "one credential"
    modes = [stat.S_IMODE(os.stat(path).st_mode) for path in
             (folder, folder / credential.SQL_NAME, folder / credential.URL_NAME)]
    assert modes == [0o700, 0o600, 0o600]


def test_the_commands_print_names_and_modes_never_the_credential(made, capsys) -> None:
    folder, clipboard, generated = made
    assert credential.main(["copy-sql", "--dir", str(folder)], clipboard=clipboard.append) == 0
    assert credential.main(["copy-url", "--dir", str(folder)], clipboard=clipboard.append) == 0
    printed = generated + capsys.readouterr().out
    sql, url = clipboard
    assert sql == (folder / credential.SQL_NAME).read_text()
    assert url == (folder / credential.URL_NAME).read_text().strip()
    assert "connection: shared pooler, session mode" in printed
    assert credential.SECRET_NAME in printed and "UCPE_RESOLVER_DB_URL" == credential.SECRET_NAME
    plain = unquote(url.split(":")[2].split("@")[0])
    for leak in (plain, url, sql.split("'")[1], REF, POOLER):
        assert leak not in printed


def test_generate_never_overwrites(made) -> None:
    folder, _, _ = made
    before = (folder / credential.URL_NAME).read_text()
    assert credential.main(["generate", "--dir", str(folder)], paste=lambda: SESSION) == 1
    assert (folder / credential.URL_NAME).read_text() == before


def test_a_refused_template_writes_nothing(tmp_path: Path, capsys) -> None:
    folder = tmp_path / "keys"
    real = SESSION.replace("[YOUR-PASSWORD]", "an-actual-password")
    assert credential.main(["generate", "--dir", str(folder)], paste=lambda: real) == 1
    printed = capsys.readouterr()
    assert "REFUSED: the clipboard is not the dashboard's connection URI" in printed.err
    assert "an-actual-password" not in printed.err + printed.out
    assert not folder.exists()


def test_the_key_folder_must_be_outside_the_repository() -> None:
    inside = credential.ROOT / ".work" / "ucpe-keys-never"
    with pytest.raises(credential.CredentialError, match="outside this repository"):
        credential.generate(inside, SESSION)
    assert not inside.exists()
    assert credential.KEY_DIR == Path.home() / "ucpe-keys"


@pytest.mark.parametrize("name", [None, credential.SQL_NAME, credential.URL_NAME])
def test_a_credential_open_to_others_is_refused(made, name: str | None) -> None:
    folder, _, _ = made
    (folder / name if name else folder).chmod(0o755 if name is None else 0o644)
    with pytest.raises(credential.CredentialError, match="open to others"):
        credential.read(folder, credential.SQL_NAME if name is None else name)


def test_a_missing_credential_says_run_generate(tmp_path: Path) -> None:
    with pytest.raises(credential.CredentialError, match="run generate first"):
        credential.read(tmp_path / "nothing", credential.URL_NAME)


def test_without_pbcopy_the_url_is_never_printed_instead(made, capsys, monkeypatch) -> None:
    folder, _, _ = made

    class NoPbcopy:
        @staticmethod
        def run(arguments, **options):
            if arguments[0] == "pbcopy":
                raise FileNotFoundError("pbcopy")
            return subprocess.run(arguments, **options)

    monkeypatch.setattr(credential, "subprocess", NoPbcopy)
    assert credential.main(["copy-url", "--dir", str(folder)]) == 1
    printed = capsys.readouterr()
    assert "REFUSED: pbcopy (the macOS clipboard) is missing" in printed.err
    assert printed.out == ""
