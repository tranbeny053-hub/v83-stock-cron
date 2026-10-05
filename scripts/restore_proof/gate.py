"""The export gate of the structure-first restore proof (governing plan §12.1 and §23 "Backup";
owner ruling DP-D=2, 2026-10-05).

Before anything is restored, the owner's two export files are read as text and refused unless they
are what the export card's two commands make (docs/runbooks/RESTORE_PROOF_EXPORT.md):
- schema.sql, from ``pg_dump --schema-only --schema=public`` (pg_dump 17). It may hold no data:
  a data entry or a COPY block is refused, and so is any statement whose leading words are not a
  kind pg_dump writes for schema DDL, so no row (and no probability from the section-5A window)
  can ever be loaded. The scan stops at the first data marker and never reads past it. The kinds
  are judged by their leading words, and a SET by its whole line; the owner's digests pin the
  bytes themselves.
- roles.sql, from ``pg_dumpall --roles-only --no-role-passwords`` (pg_dumpall 17, which writes no
  version line, so only schema.sql's major is checked). Any password clause or password hash is
  refused at its first sight, and its value is never printed.
In both, the only psql meta-commands allowed are the ``\\restrict`` and ``\\unrestrict`` pair that
pg_dump 17.6 writes, with one key, first and last: any other (``\\!`` runs a shell command) could
act outside the scratch server, and ``\\restrict`` keeps psql from running any meta-command between
them. The files are split by psql's own lexing rules (scan), and whatever would make psql lex them
otherwise than this scan is refused: a NUL character (psql's line reader stops at it), an escape
string, a psql variable reference, and a SET of standard_conforming_strings or client_encoding to
anything but what pg_dump writes. A refusal names the file, the line and the kind, never the
line's content.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

MAX_BYTES = 16 * 1024 * 1024
DUMP_MAJOR = 17
# A pg_dump table of contents entry: "-- Name: x; Type: TABLE; Schema: public; Owner: postgres",
# and "-- Data for Name: x; Type: TABLE DATA; ..." for data.
_TOC_TYPE = re.compile(r"^-- (?:Data for )?Name: .*; Type: ([A-Z ]+);")
_DATA_TYPES = frozenset(
    {
        "TABLE DATA",
        "SEQUENCE SET",
        "BLOB",
        "BLOBS",
        "BLOB DATA",
        "BLOB METADATA",
        "LARGE OBJECT",
        "MATERIALIZED VIEW DATA",
    }
)
_COPY_FROM_STDIN = re.compile(r"^COPY .* FROM stdin;\s*$")
_PASSWORD = re.compile(r"\bPASSWORD\b", re.IGNORECASE)
_PASSWORD_HASH = re.compile(r"SCRAM-SHA-256\$|\bmd5[0-9a-f]{32}\b")
_DUMPED_BY = re.compile(r"^-- Dumped by pg_dump version (\d+)\.(\d+)\b")
_DUMPED_FROM = re.compile(r"^-- Dumped from database version (\d+)\.(\d+)\b")
_CLUSTER_DUMP = "-- PostgreSQL database cluster dump"
_RESTRICT_KEY = re.compile(r"[A-Za-z0-9]{1,64}")
# psql's lexer classes (psqlscan.l), exact for UTF-8 text: every non-ASCII character is an
# identifier character (psql reads each of its bytes as one), whitespace is these six only, and an
# identifier takes its "$", so a "$" on its own (after a number, say) starts a dollar quote.
_SPACE = " \t\n\r\f\v"
_WORD = re.compile(r"[A-Za-z_\u0080-\U0010FFFF][A-Za-z0-9_$\u0080-\U0010FFFF]*")
_DOLLAR_TAG = re.compile(r"\$(?:[A-Za-z_\u0080-\U0010FFFF][A-Za-z0-9_\u0080-\U0010FFFF]*)?\$")
# What follows ":" when psql substitutes a variable (:name, :'name', :"name", :{?name}).
_VARIABLE = re.compile(r"[A-Za-z_\u0080-\U0010FFFF'\"{]")
# The one SELECT pg_dump writes, exactly.
_SEARCH_PATH_LINE = "SELECT pg_catalog.set_config('search_path', '', false);"
# pg_dump's SET lines: a parameter's value, or the session authorization of a grant another role
# made. psql reads these two back from the server and lexes by them: only pg_dump's values pass.
_SET_LINE = re.compile(r"SET ([a-z_]+) = ([^;]+);")
_SESSION_AUTHORIZATION = re.compile(
    r'SET SESSION AUTHORIZATION (?:[a-z_][a-z0-9_$]*|"(?:[^"]|"")+");'
)
_LEXING_SETTINGS = {"standard_conforming_strings": "on", "client_encoding": "'UTF8'"}
# What each file may hold: the leading words of every top-level statement.
# pg_dump's schema DDL: RESET closes a SET SESSION AUTHORIZATION it writes for a grant made by a
# role other than the owner, and SECURITY opens a SECURITY LABEL.
_SCHEMA_STATEMENTS = frozenset(
    {"SET", "RESET", "CREATE", "ALTER", "COMMENT", "GRANT", "REVOKE", "SECURITY"}
)
_SEARCH_PATH = ("SELECT", "PG_CATALOG", "SET_CONFIG")
# pg_dumpall's roles: CREATE/ALTER ROLE, GRANT (memberships), COMMENT ON ROLE, SECURITY LABEL.
_ROLE_STATEMENTS = frozenset({"SET", "CREATE", "ALTER", "GRANT", "COMMENT", "SECURITY"})


@dataclass(frozen=True)
class Refusal:
    file: str
    line: int | None
    kind: str


@dataclass(frozen=True)
class ExportFile:
    name: str
    sha256: str
    bytes: int
    tool_major: int | None = None
    tool_minor: int | None = None
    server_major: int | None = None
    server_minor: int | None = None


@dataclass
class GateResult:
    files: list[ExportFile] = field(default_factory=list)
    refusals: list[Refusal] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.refusals


def check_export(directory: Path) -> GateResult:
    """Both files of one export, each refused or described; nothing is restored here."""

    result = GateResult()
    for name, check in (("schema.sql", check_schema_dump), ("roles.sql", check_roles_dump)):
        path = directory / name
        if not path.is_file() or path.is_symlink():
            result.refusals.append(Refusal(name, None, "MISSING_OR_NOT_A_REGULAR_FILE"))
            continue
        size = path.stat().st_size
        if size > MAX_BYTES:
            result.refusals.append(Refusal(name, None, "TOO_LARGE_FOR_A_STRUCTURE_EXPORT"))
            continue
        raw = path.read_bytes()
        described, refusals = check(name, raw)
        result.files.append(described)
        result.refusals.extend(refusals)
    return result


def check_schema_dump(name: str, raw: bytes) -> tuple[ExportFile, list[Refusal]]:
    described = _describe(name, raw)
    text, refusals = _decode(name, raw)
    if text is None:
        return described, refusals
    # Data first, line by line, stopping at the first marker: nothing past it is read.
    for number, line in enumerate(text.split("\n"), start=1):
        toc = _TOC_TYPE.match(line)
        if line.startswith("-- Data for Name:") or (toc and toc.group(1) in _DATA_TYPES):
            return described, [*refusals, Refusal(name, number, "DATA_ENTRY")]
        if _COPY_FROM_STDIN.match(line) or line == "\\.":
            return described, [*refusals, Refusal(name, number, "DATA_ENTRY")]
    described = _with_versions(described, text, tool=_DUMPED_BY)
    if described.tool_major != DUMP_MAJOR:
        refusals.append(Refusal(name, None, "NOT_PG_DUMP_17"))
    statements, metas, hazards = scan(text)
    refusals.extend(_meta_refusals(name, statements, metas))
    refusals.extend(Refusal(name, line, kind) for line, kind in hazards)
    lines = text.split("\n")
    for line, lead in statements:
        if lead[:1] == ("SET",):
            kind = _set_refusal(lines[line - 1])
            if kind is not None:
                refusals.append(Refusal(name, line, kind))
            continue
        if lead[:3] == _SEARCH_PATH and lines[line - 1] == _SEARCH_PATH_LINE:
            continue
        if lead and lead[0] in _SCHEMA_STATEMENTS:
            continue
        refusals.append(Refusal(name, line, f"STATEMENT_{_kind(lead)}"))
    return described, refusals


def check_roles_dump(name: str, raw: bytes) -> tuple[ExportFile, list[Refusal]]:
    described = _describe(name, raw)
    text, refusals = _decode(name, raw)
    if text is None:
        return described, refusals
    # Passwords first, line by line, stopping at the first: its value is never kept or shown.
    for number, line in enumerate(text.split("\n"), start=1):
        if _PASSWORD.search(line):
            return described, [*refusals, Refusal(name, number, "PASSWORD_CLAUSE")]
        if _PASSWORD_HASH.search(line):
            return described, [*refusals, Refusal(name, number, "PASSWORD_HASH")]
    if _CLUSTER_DUMP not in text.split("\n")[:3]:
        refusals.append(Refusal(name, None, "NOT_A_PG_DUMPALL_ROLES_DUMP"))
    statements, metas, hazards = scan(text)
    refusals.extend(_meta_refusals(name, statements, metas))
    refusals.extend(Refusal(name, line, kind) for line, kind in hazards)
    lines = text.split("\n")
    for line, lead in statements:
        if lead[:1] == ("SET",):
            kind = _set_refusal(lines[line - 1])
            if kind is not None:
                refusals.append(Refusal(name, line, kind))
        elif not lead or lead[0] not in _ROLE_STATEMENTS:
            refusals.append(Refusal(name, line, f"STATEMENT_{_kind(lead)}"))
        elif lead[0] in {"CREATE", "ALTER"} and lead[1:2] != ("ROLE",):
            refusals.append(Refusal(name, line, f"STATEMENT_{lead[0]}_{_kind(lead[1:])}"))
        elif lead[0] == "COMMENT" and lead[1:3] != ("ON", "ROLE"):
            refusals.append(Refusal(name, line, f"STATEMENT_COMMENT_{_kind(lead[2:])}"))
        elif lead[0] == "SECURITY" and lead[1:2] != ("LABEL",):
            refusals.append(Refusal(name, line, "STATEMENT_SECURITY"))
    return described, refusals


def scan(
    text: str,
) -> tuple[list[tuple[int, tuple[str, ...]]], list[tuple[int, str, str]], list[tuple[int, str]]]:
    """Split a psql script by psql's own lexing rules (psqlscan.l): the top-level statements (the
    line each starts on and its first five words, upper-cased), the top-level meta-commands (line,
    command and its arguments) and the hazards (line and kind). Quoted strings, quoted identifiers,
    dollar-quoted bodies and comments are skipped by psql's own character classes, so nothing inside
    a function body is mistaken for a statement or a meta-command. Where psql's lexing would depend
    on what this scan does not model, it does not guess: an escape string (E'...', whose backslashes
    psql reads; pg_dump never writes one) and a psql variable reference (:name, which psql would
    substitute and lex again) are hazards, which the gate refuses. It assumes standard strings and
    UTF-8, which the gate enforces. It is stricter than psql in two ways that pg_dump's schema
    output never meets: a semicolon inside parentheses or a BEGIN ATOMIC body ends a statement
    here."""

    statements: list[tuple[int, tuple[str, ...]]] = []
    metas: list[tuple[int, str, str]] = []
    hazards: list[tuple[int, str]] = []
    i, n, line = 0, len(text), 1
    first_line: int | None = None
    lead: list[str] = []
    while i < n:
        char = text[i]
        if char == "\n":
            line += 1
            i += 1
        elif char in _SPACE:
            i += 1
        elif text.startswith("--", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
        elif text.startswith("/*", i):
            depth, i = 1, i + 2
            while i < n and depth:
                if text.startswith("/*", i):
                    depth, i = depth + 1, i + 2
                elif text.startswith("*/", i):
                    depth, i = depth - 1, i + 2
                else:
                    line += text[i] == "\n"
                    i += 1
        elif char == "\\":
            end = text.find("\n", i)
            end = n if end < 0 else end
            words = [word for word in re.split(r"[ \t\r\f\v]+", text[i + 1 : end]) if word]
            metas.append((line, words[0] if words else "", " ".join(words[1:])))
            i = end
        elif char == ";":
            statements.append((first_line if first_line is not None else line, tuple(lead)))
            first_line, lead = None, []
            i += 1
        else:
            if first_line is None:
                first_line = line
            if char == "'" and i > 0 and text[i - 1] in "eE":
                hazards.append((line, "ESCAPE_STRING"))
            elif char == ":" and not text.startswith("::", i) and _VARIABLE.match(text, i + 1):
                hazards.append((line, "PSQL_VARIABLE"))
            i, line = _skip_token(text, i, line, lead)
    if first_line is not None:
        statements.append((first_line, tuple(lead)))
    return statements, metas, hazards


def _skip_token(text: str, i: int, line: int, lead: list[str]) -> tuple[int, int]:
    n = len(text)
    char = text[i]
    if char in "'\"":
        i += 1
        while i < n:
            if text[i] == "\n":
                line += 1
            if text[i] == char:
                if text.startswith(char * 2, i):
                    i += 2
                    continue
                return i + 1, line
            i += 1
        return n, line
    if char == "$":
        tag = _DOLLAR_TAG.match(text, i)
        if tag:
            close = text.find(tag.group(0), tag.end())
            end = n if close < 0 else close + len(tag.group(0))
            return end, line + text.count("\n", i, end)
    if text.startswith("::", i):
        return i + 2, line  # a cast, never the start of a variable reference
    word = _WORD.match(text, i)
    if word:
        if len(lead) < 5:
            lead.append(word.group(0).upper())
        return word.end(), line
    return i + 1, line


def _set_refusal(line: str) -> str | None:
    """A SET statement must be one of pg_dump's own lines, standing alone on its line; the two
    settings psql lexes by may hold only pg_dump's values."""

    if _SESSION_AUTHORIZATION.fullmatch(line):
        return None
    match = _SET_LINE.fullmatch(line)
    if match is None:
        return "STATEMENT_SET_FORM"
    expected = _LEXING_SETTINGS.get(match[1])
    if expected is not None and match[2] != expected:
        return f"STATEMENT_SET_{match[1].upper()}"
    return None


def _meta_refusals(
    name: str, statements: list[tuple[int, tuple[str, ...]]], metas: list[tuple[int, str, str]]
) -> list[Refusal]:
    """Exactly ``\\restrict K`` before every statement and ``\\unrestrict K`` after all of them."""

    refusals = [
        Refusal(name, line, "META_COMMAND")
        for line, command, _ in metas
        if command not in {"restrict", "unrestrict"}
    ]
    restricts = [meta for meta in metas if meta[1] == "restrict"]
    unrestricts = [meta for meta in metas if meta[1] == "unrestrict"]
    if len(restricts) != 1 or len(unrestricts) != 1:
        return [*refusals, Refusal(name, None, "RESTRICT_PAIR_MISSING")]
    (opened, _, key), (closed, _, closing_key) = restricts[0], unrestricts[0]
    if not _RESTRICT_KEY.fullmatch(key) or key != closing_key:
        refusals.append(Refusal(name, opened, "RESTRICT_KEY_MISMATCH"))
    first = min((line for line, _ in statements), default=opened + 1)
    last = max((line for line, _ in statements), default=closed - 1)
    if not opened < first or not last < closed:
        refusals.append(Refusal(name, opened, "STATEMENT_OUTSIDE_RESTRICT"))
    return refusals


def _decode(name: str, raw: bytes) -> tuple[str | None, list[Refusal]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, [Refusal(name, None, "NOT_UTF8_TEXT")]
    if "\x00" in text:
        return None, [Refusal(name, None, "NUL_CHARACTER")]  # psql's line reader stops at one
    return text, []


def _describe(name: str, raw: bytes) -> ExportFile:
    return ExportFile(name=name, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def _with_versions(described: ExportFile, text: str, *, tool: re.Pattern[str]) -> ExportFile:
    head = text.split("\n")[:40]
    by = next((match for line in head if (match := tool.match(line))), None)
    origin = next((match for line in head if (match := _DUMPED_FROM.match(line))), None)
    return ExportFile(
        name=described.name,
        sha256=described.sha256,
        bytes=described.bytes,
        tool_major=int(by.group(1)) if by else None,
        tool_minor=int(by.group(2)) if by else None,
        server_major=int(origin.group(1)) if origin else None,
        server_minor=int(origin.group(2)) if origin else None,
    )


def _kind(lead: tuple[str, ...] | list[str]) -> str:
    return lead[0] if lead else "EMPTY"
