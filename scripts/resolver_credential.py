"""G1: the owner's login credential for the hourly resolver's least-privilege role, ucpe_resolver.

Owner-only, on the owner's own Mac, run from the repository root. Migration 0016 made the role
NOLOGIN until the owner's credential step (docs/runbooks/RESOLVER_CUTOVER.md). Three commands:

    .venv/bin/python -m scripts.resolver_credential generate
    .venv/bin/python -m scripts.resolver_credential copy-sql
    .venv/bin/python -m scripts.resolver_credential copy-url

- generate reads a connection string TEMPLATE from the clipboard: the URI in the dashboard's
  "Connect to your project" sheet, its [YOUR-PASSWORD] placeholder still in it. Any other password
  is refused. It makes a random password and writes two owner-only files in ~/ucpe-keys, never
  inside this repository, never over an existing file:
  - ucpe-resolver-login.sql: ALTER ROLE ucpe_resolver WITH LOGIN PASSWORD '<SCRAM-SHA-256 secret>'.
    The secret is computed here, in PostgreSQL's own format (RFC 5802 and RFC 7677), so the
    password itself never reaches the database, its logs or the SQL Editor's history;
  - ucpe-resolver-db-url.txt: the template with the role as its user and the password. Supabase:
    "If you connect as a custom role through the shared pooler, the username is
    [ROLE].[PROJECT-REF]"; a direct connection and the dedicated pooler use the role alone. The
    host, port, database and options stay the template's own.
  It prints only the connection mode and the two file names.
- copy-sql copies the SQL, for the dashboard's SQL Editor; copy-url copies the URL, for the GitHub
  secret UCPE_RESOLVER_DB_URL.
Nothing secret is ever printed: not the password, the SCRAM secret or the URL.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import os
import re
import secrets
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
KEY_DIR = Path.home() / "ucpe-keys"
ROLE = "ucpe_resolver"
SQL_NAME = "ucpe-resolver-login.sql"
URL_NAME = "ucpe-resolver-db-url.txt"
SECRET_NAME = "UCPE_RESOLVER_DB_URL"
ITERATIONS = 4096  # PostgreSQL's default scram_iterations.
_TEMPLATE = re.compile(
    r"(?P<scheme>postgres(?:ql)?)://(?P<user>postgres(?:\.(?P<ref>[a-z0-9]{20}))?)"
    r":\[YOUR-PASSWORD\]@(?P<host>[a-z0-9.-]+):(?P<port>5432|6543)/(?P<database>[A-Za-z0-9_]+)"
    r"(?P<options>\?[A-Za-z0-9_=&%.-]*)?"
)
_SHARED_POOLER = re.compile(r"aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com")


class CredentialError(Exception):
    """A refusal. Its message never carries the template, the password or the URL."""


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def scram_verifier(plain: str, *, salt: bytes | None = None, iterations: int = ITERATIONS) -> str:
    """PostgreSQL's stored SCRAM-SHA-256 secret: SCRAM-SHA-256$iterations:salt$StoredKey:ServerKey.

    The password is ASCII from token_urlsafe, so SASLprep leaves it unchanged.
    """

    if not plain.isascii():
        raise CredentialError("the password must be ASCII")
    salt = secrets.token_bytes(16) if salt is None else salt
    salted = hashlib.pbkdf2_hmac("sha256", plain.encode("ascii"), salt, iterations)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()
    return (f"SCRAM-SHA-256${iterations}:{_b64(salt)}"
            f"${_b64(stored_key)}:{_b64(server_key)}")


def login_sql(plain: str) -> str:
    return f"ALTER ROLE {ROLE} WITH LOGIN PASSWORD '{scram_verifier(plain)}';\n"


def build_url(scheme: str, user: str, plain: str, host: str, port: str, database: str,
              options: str = "") -> str:
    return f"{scheme}://{user}:{quote(plain, safe='')}@{host}:{port}/{database}{options}"


def resolver_url(template: str, plain: str) -> tuple[str, str]:
    """The resolver's URL from the dashboard's template, and its connection mode."""

    match = _TEMPLATE.fullmatch(template.strip())
    if match is None:
        raise CredentialError(
            "the clipboard is not the dashboard's connection URI with [YOUR-PASSWORD] still in it"
        )
    ref, host, port = match["ref"], match["host"], match["port"]
    if ref is not None and _SHARED_POOLER.fullmatch(host):
        user = f"{ROLE}.{ref}"
        mode = "shared pooler, " + ("session mode" if port == "5432" else "transaction mode")
    elif ref is None and re.fullmatch(r"db\.[a-z0-9]{20}\.supabase\.co", host):
        user = ROLE
        mode = "direct connection" if port == "5432" else "dedicated pooler, transaction mode"
    else:
        raise CredentialError("the URI's user and host are not one of Supabase's connection types")
    return build_url(match["scheme"], user, plain, host, port, match["database"],
                     match["options"] or ""), mode


def _key_folder(directory: Path) -> Path:
    folder = directory.expanduser().resolve()
    if folder == ROOT or ROOT in folder.parents:
        raise CredentialError(f"the key folder must be outside this repository, not {folder}")
    return folder


def _owner_only(path: Path) -> None:
    if path.stat().st_mode & 0o077:
        raise CredentialError(f"{path} is open to others: chmod 600 the files, 700 the folder")


def _write_owner_only(path: Path, data: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="ascii") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(data)


def generate(directory: Path, template: str) -> dict[str, str]:
    """One new password, written as the login SQL and the resolver's URL. Never overwrites."""

    folder = _key_folder(directory)
    sql_path, url_path = folder / SQL_NAME, folder / URL_NAME
    existing = [path.name for path in (sql_path, url_path) if path.exists()]
    if existing:
        raise CredentialError(f"refusing to overwrite {', '.join(existing)} in {folder}")
    plain = secrets.token_urlsafe(32)
    url, mode = resolver_url(template, plain)
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder.chmod(0o700)
    written: list[Path] = []
    try:
        for path, data in ((sql_path, login_sql(plain)), (url_path, url + "\n")):
            _write_owner_only(path, data)
            written.append(path)
    except BaseException:
        # Only what this call wrote: a half-made credential must not stay behind.
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return {"mode": mode, "sql": str(sql_path), "url": str(url_path)}


def read(directory: Path, name: str) -> str:
    """One of generate's files, owner-only, as written."""

    folder = _key_folder(directory)
    path = folder / name
    for item in (folder, path):
        if not item.exists():
            raise CredentialError(f"{item} is missing: run generate first")
        _owner_only(item)
    return path.read_text(encoding="ascii")


def pbpaste() -> str:
    try:
        copied = subprocess.run(["pbpaste"], capture_output=True, check=True).stdout
    except FileNotFoundError:
        raise CredentialError("pbpaste (the macOS clipboard) is missing") from None
    return copied.decode("utf-8", errors="replace")


def pbcopy(text: str) -> None:
    """macOS's clipboard. Without it, refuse: a secret is never printed instead."""

    try:
        subprocess.run(["pbcopy"], input=text.encode("ascii"), check=True)
    except FileNotFoundError:
        raise CredentialError(
            "pbcopy (the macOS clipboard) is missing; nothing was copied"
        ) from None


def main(
    argv: Sequence[str] | None = None,
    *,
    paste: Callable[[], str] = pbpaste,
    clipboard: Callable[[str], None] = pbcopy,
) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.resolver_credential",
        description="G1: the resolver's login (generate), its SQL (copy-sql) and URL (copy-url).",
    )
    parser.add_argument("command", choices=("generate", "copy-sql", "copy-url"))
    parser.add_argument("--dir", type=Path, default=KEY_DIR,
                        help="the key folder, outside this repository (default: ~/ucpe-keys)")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "generate":
            made = generate(arguments.dir, paste())
            print(f"role: {ROLE}")
            print(f"connection: {made['mode']}")
            print(f"login SQL: {made['sql']}")
            print(f"resolver URL: {made['url']}")
            print("Both files are secret: never in a repository, a chat or a log.")
        elif arguments.command == "copy-sql":
            clipboard(read(arguments.dir, SQL_NAME))
            print("The login SQL is on the clipboard, for the dashboard's SQL Editor.")
        else:
            clipboard(read(arguments.dir, URL_NAME).strip())
            print(f"The resolver URL is on the clipboard, for the GitHub secret {SECRET_NAME}.")
    except CredentialError as refusal:
        print(f"REFUSED: {refusal}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
