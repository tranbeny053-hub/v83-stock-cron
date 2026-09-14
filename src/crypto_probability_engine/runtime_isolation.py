"""Isolated start-up and authenticated import surface for the section 5A evaluation.

OWNER RULINGS G1=A (strengthened) and J1=B (2026-09-14; pre-registration Addenda 6 and 7).

THE TRUST BOUNDARY (J1=B). Trusted, and nothing else: the exact CPython 3.13.14 installed by the
pinned setup-python Action; the pinned Actions; and the pip wheel CPython itself bundles in
``ensurepip/_bundled``. Everything the evaluator imports beyond the standard library is
AUTHENTICATED, never merely inventoried:

- each downloaded wheel's SHA-256 must be one the hash lock pins for that exact version;
- each installed importable file must match the digest and size recorded INSIDE its authenticated
  wheel. V810-F1 showed the RECORD written next to installed files can be rewritten to bless
  tampered code, so it is never the authority;
- site-packages must hold exactly those files, their installer metadata and CPython's README: no
  other file, directory, distribution, symlink, ``.pth`` or start-up customization. The runner's
  floating pip, which setup-python reinstalls from the index unverified, is removed without ever
  being executed;
- the checkout must equal its commit: no tracked modification, no symlink, no untracked or ignored
  code or bytecode, nothing in ``src/`` but the first-party package.

The process runs as ``python -I -S -B``:
- ``-I``: no ``PYTHON*`` variables, no script directory on the path, no user site-packages;
- ``-S``: no ``site``, so no ``.pth`` or ``sitecustomize`` executes before these checks;
- ``-B``: nothing a run compiles can later stand in for a verified source.

:func:`enter` audits before any non-stdlib module can load, then sets the ONLY import path:
stdlib, then the authenticated site-packages, then ``src/``. :func:`attest_loaded_modules`
cross-checks what actually loaded, and the CLI repeats it immediately before the claim.

STANDARD LIBRARY IMPORTS ONLY, by contract and by test. ``crypto_probability_engine.oos`` imports
pydantic when it loads, so nothing here may import from it.

RESIDUAL, stated rather than hidden (Addendum 7). The trusted base above is trusted, and so, with
it, are the runner image beneath the interpreter (kernel, filesystem, bash, git). Because no
unverified code runs after attestation, a file swapped between audit and load, or a module origin
rewritten in memory, requires code from inside that trusted base. The verify-at-load import hook
was considered and not adopted by owner ruling. A compromised owner credential remains out of
reach, as Addendum 5 §30 records.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import os
import re
import shutil
import stat
import subprocess
import sys
import sysconfig
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from email.parser import HeaderParser
from pathlib import Path, PurePosixPath
from typing import Any

EVALUATOR_LOCK = "ops/section_5a_evaluator_requirements.lock"
SOURCE_ROOT = "src"
FIRST_PARTY_PACKAGE = "crypto_probability_engine"
ISOLATED_STARTUP = "python -I -S -B"
WHEELHOUSE_NAME = "section-5a-wheels"

# The installer the runner image floats: removed before installation, never executed, never allowed
# to remain as an import surface.
FLOATING_INSTALLER = "pip"

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
# What pip writes into an installed .dist-info beyond the wheel's own files. Not importable.
INSTALLER_METADATA = frozenset({"INSTALLER", "REQUESTED", "RECORD", "direct_url.json"})

# Code, bytecode and path-configuration files: never untracked or ignored in the checkout.
CODE_SUFFIXES = (".py", ".pyc", ".pyo", ".pyd", ".so", ".dylib", ".pth")
COMPILED_SUFFIXES = (".pyc", ".pyo", ".pyd", ".so", ".dylib", ".pth")

_LOCK_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9.+!_-]+) \\$")
_LOCK_HASH = re.compile(r"^    --hash=sha256:([0-9a-f]{64})( \\)?$")
_MAX_LISTED_FAILURES = 25


class ProvenanceRefused(RuntimeError):
    """The run is not a verified, isolated dispatch under the pinned runtime; nothing was read."""


class IsolationRefused(ProvenanceRefused):
    """The process did not start isolated, or what it can import is not exactly the verified set."""


@dataclass(frozen=True)
class LockEntry:
    version: str
    hashes: frozenset[str]


@dataclass(frozen=True)
class AuthenticatedWheel:
    """A wheel whose bytes the lock authenticates, and the importable payload it declares."""

    name: str
    version: str
    sha256: str
    dist_info: str
    payload: Mapping[str, tuple[str, int | None]]


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


def read_lock_entries(root: Path | None = None) -> dict[str, LockEntry]:
    """Exact pins AND their hashes from the evaluator lock, fail-closed.

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

    versions: dict[str, str] = {}
    hashes: dict[str, set[str]] = {}
    current: str | None = None
    continued = False
    for number, line in enumerate(lines, start=1):
        if continued:
            match = _LOCK_HASH.match(line)
            if match is None:
                raise ProvenanceRefused(f"{EVALUATOR_LOCK}:{number}: expected a sha256 hash line")
            hashes[current].add(match.group(1))
            continued = line.endswith("\\")
            continue
        if not line.strip() or line.startswith("#"):
            continue
        match = _LOCK_PIN.match(line)
        if match is None:
            raise ProvenanceRefused(
                f"{EVALUATOR_LOCK}:{number}: not an exact, hashed pin: {line.strip()!r}"
            )
        current = canonical_distribution_name(match.group(1))
        if current in versions:
            raise ProvenanceRefused(f"{EVALUATOR_LOCK}: {current} is pinned twice")
        versions[current] = match.group(2)
        hashes[current] = set()
        continued = True
    if continued:
        raise ProvenanceRefused(f"{EVALUATOR_LOCK}: the last requirement is incomplete")
    if not versions:
        raise ProvenanceRefused(f"{EVALUATOR_LOCK}: the lock pins nothing")
    for name, digests in hashes.items():
        if not digests:
            raise ProvenanceRefused(f"{EVALUATOR_LOCK}: {name} has no hash")
    return {name: LockEntry(versions[name], frozenset(hashes[name])) for name in versions}


def read_lock(root: Path | None = None) -> dict[str, str]:
    """Exact pins from the evaluator lock: name -> version. See :func:`read_lock_entries`."""

    return {name: entry.version for name, entry in read_lock_entries(root).items()}


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


def single_site_directory(sites: Iterable[Path] | None = None) -> Path:
    """The one directory wheels install into. Split purelib/platlib layouts are refused."""

    found = tuple(sites if sites is not None else site_directories())
    if len(found) != 1:
        headline = "site-packages must be one directory (purelib == platlib)"
        _refuse([f"found {list(found)}"], headline)
    return Path(found[0]).resolve()


def bundled_pip_wheel(stdlib: Path | None = None) -> Path:
    """The pip wheel CPython itself ships in ``ensurepip/_bundled``: the only trusted installer."""

    root = Path(stdlib or sysconfig.get_paths()["stdlib"]) / "ensurepip" / "_bundled"
    wheels = sorted(root.glob("pip-*.whl")) if root.is_dir() else []
    if len(wheels) != 1 or wheels[0].is_symlink() or not wheels[0].is_file():
        raise IsolationRefused(
            f"expected exactly one regular bundled pip wheel in {root}; found {wheels}"
        )
    return wheels[0]


def remove_floating_installer(site: Path) -> list[str]:
    """Delete the runner's floating pip from site-packages WITHOUT running it.

    setup-python reinstalls pip from the package index at job time, unverified. It is outside the
    trusted base, so it may neither install anything nor remain importable. Only real directories
    named for it are removed; anything else in site-packages is left for the audit to refuse.
    """

    site = Path(site)
    removed: list[str] = []
    for entry in sorted(site.iterdir()):
        name = entry.name
        is_installer = name == FLOATING_INSTALLER or (
            name.startswith(f"{FLOATING_INSTALLER}-") and name.endswith(".dist-info")
        )
        if not is_installer:
            continue
        if entry.is_symlink() or not entry.is_dir():
            raise IsolationRefused(f"refusing to remove {entry}: not a real directory")
        shutil.rmtree(entry)
        removed.append(name)
    return removed


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


# --------------------------------------------------------------------------- the wheelhouse


def _sha256_hex(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _record_digest(data: bytes) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")


def _safe_relative(raw: str) -> PurePosixPath | None:
    path = PurePosixPath(raw)
    if not raw or "\\" in raw or path.is_absolute() or ".." in path.parts or "" in path.parts:
        return None
    return path


def _wheel_payload(archive: zipfile.ZipFile, wheel_name: str) -> tuple[str, dict]:
    """The importable payload a wheel declares in its own RECORD, mapped to install paths."""

    records = [
        name
        for name in archive.namelist()
        if name.count("/") == 1 and name.endswith(".dist-info/RECORD")
    ]
    if len(records) != 1:
        raise ValueError(f"{wheel_name} has {len(records)} top-level .dist-info/RECORD files")
    dist_info = records[0].split("/", 1)[0]
    data_prefix = dist_info[: -len(".dist-info")] + ".data"
    payload: dict[str, tuple[str, int | None]] = {}
    for row in csv.reader(io.StringIO(archive.read(records[0]).decode("utf-8"))):
        if not row:
            continue
        if len(row) != 3:
            raise ValueError(f"{wheel_name}: malformed RECORD row {row!r}")
        raw, digest, size = row
        path = _safe_relative(raw)
        if path is None:
            raise ValueError(f"{wheel_name}: unsafe RECORD path {raw!r}")
        if raw == records[0] or raw.endswith((".dist-info/RECORD.jws", ".dist-info/RECORD.p7s")):
            continue
        if path.parts[0] == data_prefix:
            if len(path.parts) < 3:
                raise ValueError(f"{wheel_name}: malformed .data path {raw!r}")
            if path.parts[1] not in {"purelib", "platlib"}:
                continue  # scripts, headers and data never install into site-packages
            path = PurePosixPath(*path.parts[2:])
        if not digest.startswith("sha256="):
            raise ValueError(f"{wheel_name}: {raw} is not recorded with a sha256 digest")
        payload[path.as_posix()] = (digest[len("sha256=") :], int(size) if size else None)
    return dist_info, payload


def authenticate_wheelhouse(
    wheelhouse: Path, lock_entries: Mapping[str, LockEntry]
) -> dict[str, AuthenticatedWheel]:
    """Refuse unless the wheelhouse holds exactly one lock-authenticated wheel per locked pin."""

    wheelhouse = Path(wheelhouse)
    if wheelhouse.is_symlink() or not wheelhouse.is_dir():
        _refuse([f"not a real directory: {wheelhouse}"], "the wheelhouse is not usable")
    failures: list[str] = []
    wheels: dict[str, AuthenticatedWheel] = {}
    attempted: set[str] = set()
    for entry in sorted(wheelhouse.iterdir()):
        if entry.is_symlink() or not entry.is_file() or entry.suffix != ".whl":
            failures.append(f"the wheelhouse holds something but a regular wheel: {entry.name}")
            continue
        parts = entry.name[: -len(".whl")].split("-")
        if len(parts) not in {5, 6}:
            failures.append(f"not a wheel file name: {entry.name}")
            continue
        name, version = canonical_distribution_name(parts[0]), parts[1]
        attempted.add(name)
        pin = lock_entries.get(name)
        if pin is None:
            failures.append(f"a wheel for a distribution outside the lock: {entry.name}")
            continue
        if version != pin.version:
            failures.append(f"{entry.name} is version {version}; the lock pins {pin.version}")
            continue
        sha256 = _sha256_hex(entry)
        if sha256 not in pin.hashes:
            failures.append(f"{entry.name} is not a wheel the lock authenticates (sha256 {sha256})")
            continue
        if name in wheels:
            failures.append(f"more than one authenticated wheel for {name}")
            continue
        try:
            with zipfile.ZipFile(entry) as archive:
                dist_info, payload = _wheel_payload(archive, entry.name)
        except (OSError, UnicodeError, ValueError, zipfile.BadZipFile, csv.Error) as exc:
            failures.append(f"authenticated wheel {entry.name} cannot be read: {exc}")
            continue
        wheels[name] = AuthenticatedWheel(name, version, sha256, dist_info, payload)
    for name, pin in sorted(lock_entries.items()):
        if name not in attempted:
            failures.append(f"no authenticated wheel for locked {name}=={pin.version}")
    _refuse(failures, "the wheelhouse is not exactly the lock-authenticated wheels")
    return wheels


# --------------------------------------------------------------------------- site-packages


def audit_site_packages(
    site: Path, wheels: Mapping[str, AuthenticatedWheel]
) -> tuple[dict[str, str], str, frozenset[str]]:
    """Refuse unless site-packages is exactly the authenticated wheels' installed payload.

    Every importable byte is compared with the digest recorded INSIDE its authenticated wheel.
    Returns ``(installed, installed_files_sha256, locked_files)``: the digest identifies the exact
    authenticated payload, and ``locked_files`` are the resolved paths a module may come from.
    """

    site = Path(site)
    failures: list[str] = []
    if site.is_symlink() or not site.is_dir():
        _refuse([f"not a real directory: {site}"], "site-packages is not usable")
    site = site.resolve()

    expected_files: dict[str, tuple[str, int | None]] = {}
    metadata_files: set[str] = set()
    for wheel in wheels.values():
        for relative, digest in wheel.payload.items():
            if relative in expected_files:
                failures.append(f"{relative} is declared by more than one authenticated wheel")
            expected_files[relative] = digest
        metadata_files.update(f"{wheel.dist_info}/{name}" for name in INSTALLER_METADATA)
    expected_dirs = {
        parent.as_posix()
        for relative in (*expected_files, *metadata_files)
        for parent in PurePosixPath(relative).parents
        if parent.as_posix() != "."
    }

    installed: dict[str, str] = {}
    for entry in sorted(site.iterdir()):
        name = entry.name
        if name.endswith(".pth"):
            failures.append(f"path configuration file in site-packages: {name}")
        elif name.split(".")[0] in {"sitecustomize", "usercustomize"}:
            failures.append(f"start-up customization in site-packages: {name}")
        elif name.endswith((".egg-info", ".egg-link", ".egg")):
            failures.append(f"legacy distribution metadata is not verifiable: {name}")
        elif name.endswith(".dist-info") and entry.is_dir() and not entry.is_symlink():
            try:
                headers = HeaderParser().parsestr((entry / "METADATA").read_text(encoding="utf-8"))
            except (OSError, UnicodeError) as exc:
                failures.append(f"unreadable distribution {name}: {exc}")
                continue
            key = canonical_distribution_name(headers.get("Name") or "")
            if key in installed:
                failures.append(f"distribution {key} is installed more than once")
            installed[key] = headers.get("Version") or ""
    for name, wheel in sorted(wheels.items()):
        if installed.get(name) != wheel.version:
            failures.append(
                f"{name} must be installed at {wheel.version}; found {installed.get(name)!r}"
            )
    for name in sorted(set(installed) - set(wheels)):
        failures.append(f"a distribution outside the authenticated wheels is installed: {name}")

    locked_files: set[str] = set()
    digest_lines: list[str] = []
    for relative, (digest, size) in sorted(expected_files.items()):
        path = site / relative
        try:
            info = path.lstat()
        except OSError:
            failures.append(f"an authenticated file is not installed: {relative}")
            continue
        if not stat.S_ISREG(info.st_mode):
            failures.append(f"an authenticated file is not a regular file: {relative}")
            continue
        data = path.read_bytes()
        if _record_digest(data) != digest or (size is not None and len(data) != size):
            failures.append(f"an installed file differs from its authenticated wheel: {relative}")
            continue
        locked_files.add(path.as_posix())
        digest_lines.append(f"{relative}\0{digest}\n")

    for directory, dirnames, filenames in os.walk(site):
        current = Path(directory)
        relative_dir = current.relative_to(site)
        for dirname in dirnames:
            relative = (relative_dir / dirname).as_posix()
            if (current / dirname).is_symlink():
                failures.append(f"a symlink in site-packages: {relative}")
            elif relative not in expected_dirs:
                failures.append(f"an unexpected directory in site-packages: {relative}")
        for filename in filenames:
            relative = (relative_dir / filename).as_posix()
            if (current / filename).is_symlink():
                failures.append(f"a symlink in site-packages: {relative}")
            elif relative in expected_files or relative in metadata_files:
                continue
            elif relative_dir == Path(".") and filename in UNOWNED_SITE_FILES:
                continue
            else:
                failures.append(
                    f"a file no authenticated wheel declares could shadow verified code: {relative}"
                )
        dirnames[:] = [name for name in dirnames if not (current / name).is_symlink()]

    _refuse(failures, "site-packages is not exactly the authenticated wheels")
    digest = hashlib.sha256("".join(digest_lines).encode("utf-8")).hexdigest()
    return installed, digest, frozenset(locked_files)


# --------------------------------------------------------------------------- the checkout


def audit_checkout(root: Path) -> None:
    """Refuse a checkout that is not exactly its commit, or that carries code beside it.

    Refused: tracked modifications, tracked or untracked symlinks, untracked or ignored code,
    bytecode caches, tracked compiled or path files, and anything in ``src/`` but the package.
    """

    root = Path(root).resolve()
    listed = _git(root, "ls-files", "-s", "-z")
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=no")
    if listed is None or status is None:
        _refuse(["tracked files cannot be listed; not a git checkout?"], "the checkout is unusable")
    failures: list[str] = []
    if status.strip():
        failures.append(f"tracked files differ from the commit: {status.split()[-1]}")
    tracked: set[str] = set()
    for record in filter(None, listed.split("\0")):
        mode, _, remainder = record.partition(" ")
        relative = remainder.split("\t", 1)[-1]
        tracked.add(relative)
        if mode == "120000":
            failures.append(f"a tracked symlink: {relative}")
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
        for name in [*dirnames, *filenames]:
            if (current / name).is_symlink():
                relative = (relative_dir / name).as_posix()
                if relative not in tracked:
                    failures.append(f"a symlink is in the checkout: {relative}")
        dirnames[:] = [name for name in dirnames if not (current / name).is_symlink()]
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
    root: Path | None = None,
    *,
    wheelhouse: Path,
    lock_entries: Mapping[str, LockEntry] | None = None,
) -> IsolationReport:
    """Verify the isolated process and its import surface, then set the ONLY import path.

    Called with the first-party source root already appended (so this module could be imported)
    and nothing else added. On success ``sys.path`` becomes the interpreter's library, then the
    authenticated site-packages, then the source root, in that order.
    """

    root = (root or project_root()).resolve()
    source = str(root / SOURCE_ROOT)
    flags = verify_interpreter_isolation()
    initial = [entry for entry in sys.path if entry != source]
    site = single_site_directory()
    verify_initial_sys_path(initial, sites=(site,))
    wheels = authenticate_wheelhouse(Path(wheelhouse), lock_entries or read_lock_entries(root))
    installed, digest, locked_files = audit_site_packages(site, wheels)
    audit_checkout(root)
    sys.path[:] = [*initial, str(site), source]
    return IsolationReport(
        interpreter_flags=flags,
        stdlib_roots=tuple(str(path) for path in stdlib_roots()),
        site_dirs=(str(site),),
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
    """Refuse unless every loaded module came from the stdlib, an authenticated file or the pin.

    Returns the number of modules verified. Built-in and frozen modules carry no file and are part
    of the interpreter itself. Under J1=B this is a cross-check: no unverified code runs after
    attestation, so origins can only be rewritten from inside the trusted base (Addendum 7).
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
            f"module {name} was loaded from {origin}, outside the standard library, the "
            "authenticated files and the reviewed pin"
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
