"""Isolated startup and code-origin attestation for the section 5A evaluation.

OWNER RULING G1=A, strengthened (2026-09-14; pre-registration Addendum 6), closing V809-F1.

task-809 showed that the exact-runtime attestation bound package METADATA, not the code Python
actually imports. A shadow module ran under locked version numbers, and a committed
``scripts/platform.py`` ran inside the evaluator while the pin still passed. The evaluator imported
third-party code before anything was attested, searched the script directory first, ignored
untracked files, and could not tell two copies of one version apart.

This module runs FIRST, in a process started as ``python -I -S -B``, before any module beyond the
standard library and this package's empty ``__init__`` can load:

  -I  isolated: ``PYTHON*`` environment variables are ignored, the script directory is not on
      ``sys.path``, and user site-packages is off;
  -S  no ``site``: no ``.pth`` file and no ``sitecustomize`` can execute before these checks, so
      refusing them is a refusal, not a detection after the fact;
  -B  no bytecode is written, so nothing a run compiles can later stand in for a verified source.

:func:`enter` then refuses unless:

- the start-up path is the interpreter's own standard library;
- site-packages holds exactly the hash-locked set (plus the installer), no distribution twice, and
  no ``.pth``, ``sitecustomize`` or legacy egg;
- every file in site-packages is owned by a distribution record, and every locked file matches its
  recorded SHA-256;
- the checkout holds no untracked or ignored code, bytecode or path file, and ``src/`` holds only
  the first-party package.

Only then does it place site-packages, and after it the first-party source root, on ``sys.path``,
so first-party files can never shadow a verified module.

After the evaluator's imports, :func:`attest_loaded_modules` verifies the ORIGIN of every module
actually loaded: the interpreter's standard library, a hash-verified file of a locked distribution,
or a file of the reviewed pin. It is repeated immediately before the one-look claim.

STANDARD LIBRARY IMPORTS ONLY, by contract and by test. The ``crypto_probability_engine.oos``
package imports pydantic when it loads, so nothing here may import from it: this module must finish
before anything it checks could have run.

RESIDUAL, stated rather than hidden. The interpreter's standard library is trusted as installed by
actions/setup-python. The installer is inventoried and must own its files, but it is not
hash-verified, and nothing but a locked distribution's verified files may be a module origin. Code
supplied by a compromised owner credential is out of reach, as Addendum 5 §30 records.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import os
import re
import subprocess
import sys
import sysconfig
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from email.parser import HeaderParser
from pathlib import Path
from typing import Any

EVALUATOR_LOCK = "ops/section_5a_evaluator_requirements.lock"
SOURCE_ROOT = "src"
FIRST_PARTY_PACKAGE = "crypto_probability_engine"
ISOLATED_STARTUP = "python -I -S -B"

# The installer is present in every interpreter image. It may own files, never supply modules.
INSTALLER_DISTRIBUTIONS = frozenset({"pip", "setuptools", "wheel"})

# The flags `python -I -S -B` sets, in a fixed order; recorded verbatim in the run provenance.
REQUIRED_INTERPRETER_FLAGS = (
    "isolated",
    "ignore_environment",
    "no_user_site",
    "safe_path",
    "no_site",
    "dont_write_bytecode",
)
REQUIRED_FLAGS_TEXT = ",".join(REQUIRED_INTERPRETER_FLAGS)

# CPython's own install places this in site-packages without a distribution record.
UNOWNED_SITE_FILES = frozenset({"README.txt"})

# Code, bytecode and path-configuration files: never untracked or ignored in the checkout.
CODE_SUFFIXES = (".py", ".pyc", ".pyo", ".pyd", ".so", ".dylib", ".pth")
COMPILED_SUFFIXES = (".pyc", ".pyo", ".pyd", ".so", ".dylib", ".pth")

_LOCK_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9.+!_-]+) \\$")
_LOCK_HASH = re.compile(r"^    --hash=sha256:[0-9a-f]{64}( \\)?$")
_MAX_LISTED_FAILURES = 25


class ProvenanceRefused(RuntimeError):
    """The run is not a verified, isolated dispatch under the pinned runtime; nothing was read."""


class IsolationRefused(ProvenanceRefused):
    """The process did not start isolated, or what it can import is not exactly the verified set."""


@dataclass(frozen=True)
class IsolationReport:
    """What :func:`enter` verified. ``locked_files`` are the only third-party module origins."""

    interpreter_flags: str
    stdlib_roots: tuple[str, ...]
    site_dirs: tuple[str, ...]
    source_root: str
    installed: Mapping[str, str]
    installed_files_sha256: str
    locked_files: frozenset[str]


# --------------------------------------------------------------------------- the lock


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def canonical_distribution_name(name: str) -> str:
    """PEP 503 normalization, so ``Pygments`` and ``pygments`` are one distribution."""

    return re.sub(r"[-_.]+", "-", name).lower()


def read_lock(root: Path | None = None) -> dict[str, str]:
    """Exact pins from the evaluator lock, fail-closed.

    Every requirement must be ``name==version`` followed by at least one SHA-256 hash, which is
    what ``pip --require-hashes`` enforces at install. A range, an unhashed pin, a duplicate or any
    unrecognized line refuses: a lock that is not exact cannot bind the runtime (V808-R5).
    """

    path = (root or project_root()).resolve() / EVALUATOR_LOCK
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ProvenanceRefused(
            f"the evaluator lock is missing or unreadable: {EVALUATOR_LOCK}"
        ) from exc

    pins: dict[str, str] = {}
    current: str | None = None
    hashes = 0
    continued = False
    for number, line in enumerate(lines, start=1):
        if continued:
            if not _LOCK_HASH.match(line):
                raise ProvenanceRefused(f"{EVALUATOR_LOCK}:{number}: expected a sha256 hash line")
            hashes += 1
            continued = line.endswith("\\")
            continue
        if current is not None and hashes == 0:
            raise ProvenanceRefused(f"{EVALUATOR_LOCK}: {current} has no hash")
        if not line.strip() or line.startswith("#"):
            continue
        match = _LOCK_PIN.match(line)
        if match is None:
            raise ProvenanceRefused(
                f"{EVALUATOR_LOCK}:{number}: not an exact, hashed pin: {line.strip()!r}"
            )
        current = canonical_distribution_name(match.group(1))
        if current in pins:
            raise ProvenanceRefused(f"{EVALUATOR_LOCK}: {current} is pinned twice")
        pins[current] = match.group(2)
        hashes = 0
        continued = True
    if continued or (current is not None and hashes == 0):
        raise ProvenanceRefused(f"{EVALUATOR_LOCK}: the last requirement is incomplete")
    if not pins:
        raise ProvenanceRefused(f"{EVALUATOR_LOCK}: the lock pins nothing")
    return pins


# --------------------------------------------------------------------------- the interpreter


def interpreter_flags(flags: Any = None) -> str:
    """The isolation flags actually in force, in :data:`REQUIRED_INTERPRETER_FLAGS` order."""

    flags = sys.flags if flags is None else flags
    return ",".join(name for name in REQUIRED_INTERPRETER_FLAGS if getattr(flags, name, 0))


def verify_interpreter_isolation(flags: Any = None) -> str:
    actual = interpreter_flags(flags)
    if actual != REQUIRED_FLAGS_TEXT:
        raise IsolationRefused(
            f"the evaluator must start as `{ISOLATED_STARTUP}`; flags in force are "
            f"[{actual}], required [{REQUIRED_FLAGS_TEXT}]"
        )
    return actual


def stdlib_roots() -> tuple[Path, ...]:
    paths = sysconfig.get_paths()
    return tuple(sorted({Path(paths["stdlib"]).resolve(), Path(paths["platstdlib"]).resolve()}))


def site_directories() -> tuple[Path, ...]:
    """The interpreter's OWN site-packages, independent of anything ``site`` would have added."""

    paths = sysconfig.get_paths()
    return tuple(sorted({Path(paths["purelib"]).resolve(), Path(paths["platlib"]).resolve()}))


def verify_initial_sys_path(
    entries: Iterable[str],
    *,
    prefixes: Iterable[str] = (),
    sites: Iterable[Path] = (),
) -> None:
    """Under ``-I -S`` the path is the interpreter's own library: its zip, stdlib, lib-dynload."""

    prefixes = tuple(prefixes) or (sys.base_prefix, sys.base_exec_prefix)
    allowed = [Path(prefix).resolve() for prefix in prefixes]
    site_paths = [Path(site).resolve() for site in (tuple(sites) or site_directories())]
    failures = []
    for entry in entries:
        if not entry:
            failures.append("the current directory is on sys.path")
            continue
        path = Path(entry).resolve()
        if not any(_is_within(path, prefix) for prefix in allowed):
            failures.append(f"{entry} is outside the interpreter's own library")
        elif any(_is_within(path, site) for site in site_paths):
            failures.append(f"{entry} is site-packages, importable before the audit")
    _refuse(failures, "sys.path at start-up is not the interpreter's own library")


# --------------------------------------------------------------------------- site-packages


@dataclass(frozen=True)
class _Distribution:
    name: str
    version: str
    site: Path
    dist_info: Path
    record: tuple[tuple[str, str | None, int | None], ...]


def _read_distribution(site: Path, dist_info: Path) -> _Distribution:
    headers = HeaderParser().parsestr((dist_info / "METADATA").read_text(encoding="utf-8"))
    name, version = headers.get("Name"), headers.get("Version")
    if not name or not version:
        raise ValueError("METADATA has no Name or Version")
    rows: list[tuple[str, str | None, int | None]] = []
    record_text = (dist_info / "RECORD").read_text(encoding="utf-8")
    for row in csv.reader(io.StringIO(record_text)):
        if not row:
            continue
        if len(row) != 3:
            raise ValueError(f"malformed RECORD row {row!r}")
        relative, digest, size = row
        if digest and not digest.startswith("sha256="):
            raise ValueError(f"RECORD row {relative!r} is not hashed with sha256")
        hashed = digest[len("sha256=") :] if digest else None
        rows.append((relative, hashed, int(size) if size else None))
    return _Distribution(canonical_distribution_name(name), version, site, dist_info, tuple(rows))


def _record_digest(data: bytes) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")


def audit_site_packages(
    site_dirs: Iterable[Path], lock_pins: Mapping[str, str]
) -> tuple[dict[str, str], str, frozenset[str]]:
    """Refuse unless site-packages is exactly the verified set. Returns what was verified.

    Returns ``(installed, installed_files_sha256, locked_files)``. The digest identifies the exact
    bytes of every locked file; ``locked_files`` are the resolved paths a module may come from.
    """

    sites = [Path(site).resolve() for site in site_dirs]
    failures: list[str] = []
    distributions: list[_Distribution] = []

    for site in sites:
        if not site.is_dir():
            failures.append(f"site-packages directory is missing: {site}")
            continue
        for entry in sorted(site.iterdir()):
            name = entry.name
            if name.endswith(".pth"):
                failures.append(f"path configuration file in site-packages: {name}")
            elif name.split(".")[0] in {"sitecustomize", "usercustomize"}:
                failures.append(f"start-up customization in site-packages: {name}")
            elif name.endswith((".egg-info", ".egg-link", ".egg")):
                failures.append(f"legacy distribution metadata is not verifiable: {name}")
            elif name.endswith(".dist-info") and entry.is_dir():
                try:
                    distributions.append(_read_distribution(site, entry))
                except (OSError, UnicodeError, ValueError, csv.Error) as exc:
                    failures.append(f"unreadable distribution {name}: {exc}")

    by_name: dict[str, list[_Distribution]] = {}
    for distribution in distributions:
        by_name.setdefault(distribution.name, []).append(distribution)
    for name, copies in sorted(by_name.items()):
        if len(copies) > 1:
            failures.append(
                f"distribution {name} is installed {len(copies)} times "
                f"({', '.join(sorted(copy.dist_info.name for copy in copies))})"
            )
    installed = {name: copies[0].version for name, copies in sorted(by_name.items())}
    for name, version in sorted(lock_pins.items()):
        if name not in installed:
            failures.append(f"locked distribution {name}=={version} is not installed")
        elif installed[name] != version:
            failures.append(f"{name} is {installed[name]}, the lock pins {version}")
    for name in sorted(set(installed) - set(lock_pins) - INSTALLER_DISTRIBUTIONS):
        failures.append(f"distribution outside the lock is installed: {name}=={installed[name]}")

    owned: set[Path] = set()
    locked_files: set[str] = set()
    digest_lines: list[str] = []
    for distribution in distributions:
        locked = distribution.name in lock_pins
        record_file = (distribution.dist_info / "RECORD").resolve()
        for relative, digest, size in distribution.record:
            path = (distribution.site / relative).resolve()
            if not _is_within(path, distribution.site):
                continue  # console scripts are written to bin/; they are not importable
            if path in owned:
                failures.append(f"{relative} is claimed by more than one distribution")
            owned.add(path)
            if not locked or path == record_file:
                continue
            if path.suffix in {".pyc", ".pyo"}:
                failures.append(f"locked {distribution.name} carries bytecode {relative}")
                continue
            if digest is None:
                failures.append(f"locked {distribution.name} records {relative} unhashed")
                continue
            try:
                data = path.read_bytes()
            except OSError:
                failures.append(f"locked file is missing: {relative}")
                continue
            if _record_digest(data) != digest or (size is not None and len(data) != size):
                failures.append(f"locked file differs from its record: {relative}")
                continue
            locked_files.add(path.as_posix())
            digest_lines.append(f"{path.relative_to(distribution.site).as_posix()}\0{digest}\n")

    for site in sites:
        if not site.is_dir():
            continue
        for directory, _, filenames in os.walk(site):
            for filename in filenames:
                path = (Path(directory) / filename).resolve()
                if path in owned:
                    continue
                if Path(directory).resolve() == site and filename in UNOWNED_SITE_FILES:
                    continue
                failures.append(
                    "a file no distribution owns could shadow a verified module: "
                    f"{path.relative_to(site) if _is_within(path, site) else path}"
                )

    _refuse(failures, "site-packages is not exactly the hash-locked set")
    digest = hashlib.sha256("".join(sorted(digest_lines)).encode("utf-8")).hexdigest()
    return installed, digest, frozenset(locked_files)


# --------------------------------------------------------------------------- the checkout


def audit_checkout(root: Path) -> None:
    """Refuse untracked or ignored code, any bytecode cache, and anything else in src/."""

    root = Path(root).resolve()
    listed = _git(root, "ls-files", "-z")
    if listed is None:
        raise IsolationRefused("the checkout's tracked files cannot be listed; not a git checkout?")
    tracked = {item for item in listed.split("\0") if item}
    failures: list[str] = []
    for relative in sorted(tracked):
        if relative.endswith(COMPILED_SUFFIXES):
            failures.append(f"a compiled or path-configuration file is tracked: {relative}")
    for directory, dirnames, filenames in os.walk(root):
        current = Path(directory)
        relative_dir = current.relative_to(root)
        if current == root:
            dirnames[:] = [name for name in dirnames if name != ".git"]
        if "__pycache__" in relative_dir.parts:
            failures.append(f"a bytecode cache is in the checkout: {relative_dir.as_posix()}")
            dirnames[:] = []
            continue
        for filename in filenames:
            relative = (relative_dir / filename).as_posix()
            if relative not in tracked and filename.endswith(CODE_SUFFIXES):
                failures.append(f"untracked or ignored code is in the checkout: {relative}")
    source = root / SOURCE_ROOT
    if source.is_dir():
        for entry in sorted(source.iterdir()):
            if entry.name != FIRST_PARTY_PACKAGE:
                failures.append(f"{SOURCE_ROOT}/ may hold only {FIRST_PARTY_PACKAGE}: {entry.name}")
    _refuse(failures, "the checkout carries code outside the reviewed commit")


# --------------------------------------------------------------------------- entering


def enter(
    root: Path | None = None, *, lock_pins: Mapping[str, str] | None = None
) -> IsolationReport:
    """Verify the isolated process and its import surface, then set the ONLY import path.

    Called with the first-party source root already appended (so this module could be imported)
    and nothing else added. On success ``sys.path`` becomes the interpreter's library, then its
    verified site-packages, then the source root, in that order.
    """

    root = (root or project_root()).resolve()
    source = str(root / SOURCE_ROOT)
    flags = verify_interpreter_isolation()
    initial = [entry for entry in sys.path if entry != source]
    sites = site_directories()
    verify_initial_sys_path(initial, sites=sites)
    installed, digest, locked_files = audit_site_packages(sites, lock_pins or read_lock(root))
    audit_checkout(root)
    sys.path[:] = [*initial, *(str(site) for site in sites), source]
    return IsolationReport(
        interpreter_flags=flags,
        stdlib_roots=tuple(str(path) for path in stdlib_roots()),
        site_dirs=tuple(str(site) for site in sites),
        source_root=source,
        installed=installed,
        installed_files_sha256=digest,
        locked_files=locked_files,
    )


# --------------------------------------------------------------------------- loaded modules


def attest_loaded_modules(
    report: IsolationReport,
    *,
    pinned: Iterable[str],
    root: Path,
    modules: Mapping[str, Any] | None = None,
) -> int:
    """Refuse unless every loaded module came from the stdlib, a locked file or the pin.

    Returns the number of modules verified. Built-in and frozen modules carry no file and are part
    of the interpreter itself.
    """

    root = Path(root).resolve()
    pinned_paths = {(root / relative).resolve() for relative in pinned}
    stdlib = [Path(path) for path in report.stdlib_roots]
    sites = [Path(path) for path in report.site_dirs]
    locked = {Path(path) for path in report.locked_files}
    source_package = Path(report.source_root) / FIRST_PARTY_PACKAGE

    def standard_library(path: Path) -> bool:
        return any(_is_within(path, lib) for lib in stdlib) and not any(
            _is_within(path, site) for site in sites
        )

    failures: list[str] = []
    verified = 0
    for name, module in sorted(dict(modules if modules is not None else sys.modules).items()):
        if module is None:
            continue
        spec = getattr(module, "__spec__", None)
        origin = getattr(spec, "origin", None) if spec is not None else None
        if origin in {"built-in", "frozen"}:
            verified += 1
            continue
        if origin is None:
            origin = getattr(module, "__file__", None)
        if origin is None:
            locations = list(getattr(spec, "submodule_search_locations", None) or [])
            if locations and all(
                standard_library(Path(location).resolve())
                or _is_within(Path(location).resolve(), source_package)
                for location in locations
            ):
                verified += 1
                continue
            failures.append(f"module {name} has no verifiable origin")
            continue
        path = Path(origin).resolve()
        if path in pinned_paths or path in locked or standard_library(path):
            verified += 1
            continue
        failures.append(
            f"module {name} was loaded from {origin}, outside the standard library, the verified "
            "locked files and the reviewed pin"
        )
    _refuse(failures, "a loaded module is not verified code")
    return verified


# --------------------------------------------------------------------------- helpers


def _refuse(failures: list[str], headline: str) -> None:
    if not failures:
        return
    shown = failures[:_MAX_LISTED_FAILURES]
    more = len(failures) - len(shown)
    suffix = f"; and {more} more" if more else ""
    raise IsolationRefused(
        f"section 5A run refused before the one look could be claimed: {headline}: "
        + "; ".join(shown)
        + suffix
    )


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _git(root: Path, *arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout
