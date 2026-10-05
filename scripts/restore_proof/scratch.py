"""Scratch PostgreSQL clusters for the restore proof: private, socket-only, never a real database.

Every cluster is made here by initdb in a fresh work directory and listens on a private socket
only (no TCP), so nothing in this package can reach any other server. Its bootstrap superuser has
the hosting platform's bootstrap name (Supabase: ``supabase_admin``), for two reasons:
- a roles dump records the platform's role grants as GRANTED BY that role, and PostgreSQL (16 and
  later) accepts such a grantor only when it is the bootstrap superuser;
- it is never the migration owner ``postgres``, which a Supabase dump sets NOSUPERUSER: restoring
  the dump can then never take superuser from the role running the restore. The proof also refuses
  an export that does not keep the bootstrap name a superuser (prove.py).
psql always reads its input as UTF-8 here, the encoding the export gate checks the files in. No
server log keeps the text of a statement it refused, and a cluster's log is deleted with it.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

BOOTSTRAP_SUPERUSER = "supabase_admin"
# The role that runs the migrations: a non-superuser with CREATEROLE, as Supabase's postgres is.
MIGRATION_OWNER = "postgres"
_PSQL_ERROR = re.compile(r"^psql:(?P<file>[^:]*):(?P<line>\d+): ERROR:  (?P<message>.*)$")
# A refused setting's error repeats its value: only the parameter's name is kept.
_ECHOED_VALUE = re.compile(r'^(invalid value for parameter "[^"]*"): .*$')
_VERSION = re.compile(r"\(PostgreSQL\) (\d+)\.(\d+)")


@dataclass(frozen=True)
class Cluster:
    bin: Path
    data: Path
    socket: Path
    log: Path
    superuser: str = BOOTSTRAP_SUPERUSER

    def url(self, database: str, user: str | None = None) -> str:
        return f"postgresql:///{database}?host={self.socket}&user={user or self.superuser}"

    def psql(
        self,
        *,
        database: str = "postgres",
        user: str | None = None,
        command: str | None = None,
        file: Path | None = None,
        variables: dict[str, str] | None = None,
        stop_on_error: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        args = [
            str(self.bin / "psql"),
            "-X",
            "-q",
            "-v",
            f"ON_ERROR_STOP={1 if stop_on_error else 0}",
            "-h",
            str(self.socket),
            "-U",
            user or self.superuser,
            "-d",
            database,
        ]
        for name, value in (variables or {}).items():
            args += ["-v", f"{name}={value}"]
        if command is not None:
            args += ["-c", command]
        if file is not None:
            args += ["-f", str(file)]
        done = subprocess.run(  # noqa: S603
            args,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
            env={**os.environ, "PGCLIENTENCODING": "UTF8"},
        )
        if stop_on_error and done.returncode != 0:
            # psql's own ERROR line only: never the statement it echoes, which may hold a value.
            reason = next((line for line in done.stderr.splitlines() if "ERROR:" in line), "")
            raise RuntimeError(f"psql failed on {file or 'a command'}: {reason}")
        return done


@contextmanager
def clean_pg_environment() -> Iterator[None]:
    """No PG* variable of the caller's (PGHOST, PGHOSTADDR, PGSERVICE, ...) reaches psql, pg_ctl or
    psycopg while the proof runs, so they connect to the scratch socket they are given and nowhere
    else (psql is given PGCLIENTENCODING=UTF8 alone)."""

    saved = {name: os.environ.pop(name) for name in list(os.environ) if name.startswith("PG")}
    try:
        yield
    finally:
        os.environ.update(saved)


def server_version(bin_dir: Path) -> tuple[int, int] | None:
    """The PostgreSQL release these binaries are (major, minor), or None when they cannot say."""

    try:
        done = subprocess.run(  # noqa: S603
            [str(bin_dir / "postgres"), "--version"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except OSError:
        return None
    match = _VERSION.search(done.stdout)
    return (int(match[1]), int(match[2])) if match else None


def start(bin_dir: Path, work: Path, name: str, *, superuser: str = BOOTSTRAP_SUPERUSER) -> Cluster:
    """A new cluster in work/name, started on a private socket only."""

    data = work / name
    subprocess.run(  # noqa: S603
        [
            str(bin_dir / "initdb"),
            "-D",
            str(data),
            "-U",
            superuser,
            "--auth=trust",
            "--encoding=UTF8",
            "--locale=C",
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=True,
    )
    socket = Path(tempfile.mkdtemp(prefix=f"rp-{name[:8]}.", dir="/tmp"))  # short: a socket path
    log = work / f"{name}.log"
    try:
        subprocess.run(  # noqa: S603
            [
                str(bin_dir / "pg_ctl"),
                "-D",
                str(data),
                "-l",
                str(log),
                "-w",
                "start",
                "-o",
                f"-c listen_addresses='' -c unix_socket_directories='{socket}' -c fsync=off "
                "-c log_min_error_statement=panic",
            ],
            capture_output=True,
            text=True,
            timeout=300,
            check=True,
        )
    except BaseException:
        shutil.rmtree(socket, ignore_errors=True)
        shutil.rmtree(data, ignore_errors=True)
        raise
    return Cluster(bin=bin_dir, data=data, socket=socket, log=log, superuser=superuser)


def stop(cluster: Cluster, *, remove: bool = True) -> None:
    subprocess.run(  # noqa: S603
        [str(cluster.bin / "pg_ctl"), "-D", str(cluster.data), "-m", "fast", "-w", "stop"],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    shutil.rmtree(cluster.socket, ignore_errors=True)
    if remove:
        shutil.rmtree(cluster.data, ignore_errors=True)
        cluster.log.unlink(missing_ok=True)


def build_from_migrations(cluster: Cluster, root: Path, database: str) -> None:
    """The structure the migrations declare: the Supabase-like role and grant fixtures every
    migration rehearsal uses, then every migration in order, as the non-superuser owner."""

    fixtures = root / "scripts"
    owner = {"owner": MIGRATION_OWNER}
    cluster.psql(command=f'CREATE ROLE "{MIGRATION_OWNER}" LOGIN')
    cluster.psql(file=fixtures / "migration_0013_rehearsal/00_supabase_like_roles.sql")
    cluster.psql(
        file=fixtures / "migration_0016_rehearsal/00_supabase_like_authenticator.sql",
        variables=owner,
    )
    cluster.psql(command=f'CREATE DATABASE {database} OWNER "{MIGRATION_OWNER}"')
    cluster.psql(
        database=database,
        file=fixtures / "migration_0013_rehearsal/01_supabase_like_grants.sql",
        variables=owner,
    )
    cluster.psql(
        database=database,
        file=fixtures / "migration_0015_rehearsal/00_supabase_like_function_grants.sql",
        variables=owner,
    )
    for migration in sorted((root / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql")):
        cluster.psql(database=database, user=MIGRATION_OWNER, file=migration)


@dataclass(frozen=True)
class RestoreError:
    file: str
    line: int
    message: str


def restore(cluster: Cluster, export: Path, database: str) -> list[RestoreError]:
    """The export as it is, roles first, then the schema into a new database; every error kept."""

    errors = _errors(cluster.psql(file=export / "roles.sql", stop_on_error=False), "roles.sql")
    cluster.psql(command=f"CREATE DATABASE {database}")
    done = cluster.psql(database=database, file=export / "schema.sql", stop_on_error=False)
    return errors + _errors(done, "schema.sql")


def _errors(done: subprocess.CompletedProcess[str], name: str) -> list[RestoreError]:
    errors = []
    for line in done.stderr.splitlines():
        match = _PSQL_ERROR.match(line)
        if match:
            message = _ECHOED_VALUE.sub(r"\1", match["message"])[:200]
            errors.append(RestoreError(name, int(match["line"]), message))
    return errors
