"""Isolated start-up and code-origin attestation (owner ruling G1=A). No database, no network.

Every refusal is proven against a synthetic interpreter layout — site-packages with real RECORD
hashes, a real git checkout, a synthetic module table — so each check is exercised on data it
cannot pass by accident. The whole mechanism running end to end in a `python -I -S -B` process is
proven in ``tests/scripts/test_evaluate_section_5a.py``.
"""

from __future__ import annotations

import ast
import base64
import csv
import hashlib
import importlib.machinery
import io
import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from crypto_probability_engine import runtime_isolation as iso
from crypto_probability_engine.oos.evaluation import provenance

LOCK = {"alpha": "1.0", "beta-core": "2.0"}
BETA_FILES = {"beta_core/__init__.py": b"", "beta_core/_ext.so": b"\x7fELF"}
ROOT = Path(__file__).resolve().parents[3]


def _digest(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def _install(
    site: Path,
    name: str,
    version: str,
    files: dict[str, bytes],
    *,
    hashed: bool = True,
    extra_rows: tuple[tuple[str, str, str], ...] = (),
    dist_dir: str | None = None,
) -> Path:
    """Write a distribution exactly as an installer would: files, METADATA and a RECORD."""

    dist_info = site / (dist_dir or f"{name.replace('-', '_')}-{version}.dist-info")
    dist_info.mkdir(parents=True)
    metadata = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n".encode()
    (dist_info / "METADATA").write_bytes(metadata)
    rows = []
    for relative, data in files.items():
        path = site / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        rows.append((relative, _digest(data) if hashed else "", str(len(data)) if hashed else ""))
    rows.append((f"{dist_info.name}/METADATA", _digest(metadata), str(len(metadata))))
    rows.append((f"{dist_info.name}/RECORD", "", ""))
    rows.extend(extra_rows)
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    (dist_info / "RECORD").write_text(buffer.getvalue(), encoding="utf-8")
    return dist_info


@pytest.fixture
def site(tmp_path: Path) -> Path:
    """A site-packages holding exactly LOCK plus the installer, as a real image would."""

    site = tmp_path / "lib/python3.13/site-packages"
    site.mkdir(parents=True)
    (site / "README.txt").write_text("CPython's own placeholder\n")
    _install(site, "alpha", "1.0", {"alpha/__init__.py": b"VALUE = 1\n"})
    _install(site, "beta-core", "2.0", BETA_FILES)
    _install(
        site,
        "pip",
        "26.1.2",
        {"pip/__init__.py": b""},
        extra_rows=(("pip/__pycache__/__init__.cpython-313.pyc", "", ""),),
    )
    (site / "pip/__pycache__").mkdir()
    (site / "pip/__pycache__/__init__.cpython-313.pyc").write_bytes(b"compiled")
    return site


# --------------------------------------------------------------------------- contract


def test_the_isolation_module_imports_only_the_standard_library() -> None:
    tree = ast.parse(Path(iso.__file__).read_text(encoding="utf-8"))
    imported = {
        (node.module if isinstance(node, ast.ImportFrom) else alias.name).split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else [None])
    }
    assert imported and all(
        name == "__future__" or name in sys.stdlib_module_names for name in imported
    ), imported


def test_importing_it_in_an_isolated_process_loads_nothing_else() -> None:
    probe = (
        "import json, sys, sysconfig\n"
        "from pathlib import Path\n"
        f"sys.path.append({str(ROOT / 'src')!r})\n"
        "import crypto_probability_engine.runtime_isolation\n"
        "lib = Path(sysconfig.get_paths()['stdlib']).resolve()\n"
        "site = Path(sysconfig.get_paths()['purelib']).resolve()\n"
        "def stdlib(p):\n"
        "    p = Path(p).resolve()\n"
        "    return p.is_relative_to(lib) and not p.is_relative_to(site)\n"
        "print(json.dumps(sorted(n for n, m in list(sys.modules.items())\n"
        "    if getattr(m, '__file__', None) and not stdlib(m.__file__))))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert completed.stdout.strip() == (
        '["crypto_probability_engine", "crypto_probability_engine.runtime_isolation"]'
    )


def test_one_refusal_type_is_shared_with_provenance() -> None:
    assert provenance.ProvenanceRefused is iso.ProvenanceRefused
    assert issubclass(iso.IsolationRefused, iso.ProvenanceRefused)
    assert provenance.read_lock() == iso.read_lock(ROOT)


# --------------------------------------------------------------------------- the interpreter


def _flags(**unset: int) -> SimpleNamespace:
    values = {name: 1 for name in iso.REQUIRED_INTERPRETER_FLAGS}
    values.update(unset)
    return SimpleNamespace(**values)


def test_the_required_flags_are_exactly_python_i_s_b() -> None:
    assert iso.verify_interpreter_isolation(_flags()) == iso.REQUIRED_FLAGS_TEXT
    assert iso.REQUIRED_FLAGS_TEXT == (
        "isolated,ignore_environment,no_user_site,safe_path,no_site,dont_write_bytecode"
    )


@pytest.mark.parametrize("missing", iso.REQUIRED_INTERPRETER_FLAGS)
def test_any_missing_isolation_flag_refuses(missing: str) -> None:
    with pytest.raises(iso.IsolationRefused, match="must start as `python -I -S -B`"):
        iso.verify_interpreter_isolation(_flags(**{missing: 0}))


def test_this_test_process_is_not_isolated_and_is_refused() -> None:
    with pytest.raises(iso.IsolationRefused):
        iso.verify_interpreter_isolation()
    with pytest.raises(iso.IsolationRefused):
        iso.enter(ROOT)


def test_the_start_up_path_must_be_the_interpreter_s_own_library(tmp_path: Path) -> None:
    base = tmp_path / "base"
    lib = base / "lib/python3.13"
    for directory in (lib / "lib-dynload", lib / "site-packages"):
        directory.mkdir(parents=True)
    own = [str(base / "lib/python313.zip"), str(lib), str(lib / "lib-dynload")]
    sites = [lib / "site-packages"]
    iso.verify_initial_sys_path(own, prefixes=[str(base)], sites=sites)
    for intruder, fragment in (
        ("", "current directory"),
        (str(tmp_path / "checkout/scripts"), "outside the interpreter's own library"),
        (str(lib / "site-packages"), "importable before the audit"),
    ):
        with pytest.raises(iso.IsolationRefused, match=fragment):
            iso.verify_initial_sys_path([*own, intruder], prefixes=[str(base)], sites=sites)


# --------------------------------------------------------------------------- site-packages


def test_a_site_holding_exactly_the_lock_passes(site: Path) -> None:
    installed, digest, locked_files = iso.audit_site_packages([site], LOCK)
    assert installed == {"alpha": "1.0", "beta-core": "2.0", "pip": "26.1.2"}
    assert len(digest) == 64
    assert str((site / "alpha/__init__.py").resolve()) in locked_files
    assert str((site / "beta_core/_ext.so").resolve()) in locked_files
    assert not any("/pip/" in path for path in locked_files), "the installer is never an origin"


def test_the_installed_files_digest_identifies_the_exact_bytes(site: Path, tmp_path: Path) -> None:
    _, first, _ = iso.audit_site_packages([site], LOCK)
    other = tmp_path / "other/site-packages"
    other.mkdir(parents=True)
    _install(other, "alpha", "1.0", {"alpha/__init__.py": b"VALUE = 2\n"})
    _install(other, "beta-core", "2.0", BETA_FILES)
    _, second, _ = iso.audit_site_packages([other], LOCK)
    assert first != second


def _refusal(site: Path, fragment: str) -> None:
    with pytest.raises(iso.IsolationRefused, match="not exactly the hash-locked set") as exc:
        iso.audit_site_packages([site], LOCK)
    assert fragment in str(exc.value), str(exc.value)


def test_a_path_configuration_file_refuses(site: Path) -> None:
    (site / "distutils-precedence.pth").write_text("import os\n")
    _refusal(site, "path configuration file in site-packages: distutils-precedence.pth")


@pytest.mark.parametrize("name", ["sitecustomize.py", "usercustomize.py"])
def test_start_up_customization_refuses(site: Path, name: str) -> None:
    (site / name).write_text("print('ran at start-up')\n")
    _refusal(site, f"start-up customization in site-packages: {name}")


def test_a_legacy_egg_refuses(site: Path) -> None:
    (site / "gamma-1.0.egg-info").mkdir()
    _refusal(site, "legacy distribution metadata is not verifiable")


def test_a_distribution_installed_twice_refuses_even_at_one_version(site: Path) -> None:
    # Same normalized name and version under another directory, as a second install would leave.
    _install(site, "Alpha", "1.0", {"alpha_copy.py": b""}, dist_dir="alpha_copy-1.0.dist-info")
    _refusal(site, "distribution alpha is installed 2 times")


def test_a_missing_locked_distribution_refuses(site: Path) -> None:
    refusal = "locked distribution gamma==3.0 is not installed"
    with pytest.raises(iso.IsolationRefused, match=refusal):
        iso.audit_site_packages([site], {**LOCK, "gamma": "3.0"})


def test_a_version_other_than_the_lock_refuses(site: Path) -> None:
    with pytest.raises(iso.IsolationRefused, match="alpha is 1.0, the lock pins 1.1"):
        iso.audit_site_packages([site], {**LOCK, "alpha": "1.1"})


def test_a_distribution_outside_the_lock_refuses(site: Path) -> None:
    _install(site, "gamma", "3.0", {"gamma.py": b""})
    _refusal(site, "distribution outside the lock is installed: gamma==3.0")


def test_a_shadow_module_no_distribution_owns_refuses(site: Path) -> None:
    """Codex's V809-F1 probe: a shadow certifi.py under unchanged package metadata."""

    (site / "certifi.py").write_text("def where(): return '/attacker/ca.pem'\n")
    _refusal(site, "a file no distribution owns could shadow a verified module: certifi.py")


def test_a_stray_bytecode_file_inside_a_locked_package_refuses(site: Path) -> None:
    (site / "alpha/__pycache__").mkdir()
    (site / "alpha/__pycache__/__init__.cpython-313.pyc").write_bytes(b"stale")
    _refusal(site, "alpha/__pycache__/__init__.cpython-313.pyc")


def test_a_locked_file_changed_after_install_refuses(site: Path) -> None:
    (site / "alpha/__init__.py").write_bytes(b"VALUE = 1  # patched\n")
    _refusal(site, "locked file differs from its record: alpha/__init__.py")


def test_a_deleted_locked_file_refuses(site: Path) -> None:
    (site / "beta_core/_ext.so").unlink()
    _refusal(site, "locked file is missing: beta_core/_ext.so")


def test_a_locked_distribution_recording_an_unhashed_file_refuses(tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    site.mkdir()
    _install(site, "alpha", "1.0", {"alpha/__init__.py": b""}, hashed=False)
    _install(site, "beta-core", "2.0", {"beta_core/__init__.py": b""})
    _refusal(site, "locked alpha records alpha/__init__.py unhashed")


def test_a_locked_distribution_carrying_bytecode_refuses(tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    site.mkdir()
    _install(site, "alpha", "1.0", {"alpha/__init__.py": b"", "alpha/__pycache__/m.pyc": b"x"})
    _install(site, "beta-core", "2.0", {"beta_core/__init__.py": b""})
    _refusal(site, "locked alpha carries bytecode alpha/__pycache__/m.pyc")


def test_an_unreadable_distribution_refuses(site: Path) -> None:
    broken = site / "delta-1.0.dist-info"
    broken.mkdir()
    (broken / "METADATA").write_text("Metadata-Version: 2.1\n")
    (broken / "RECORD").write_text("")
    _refusal(site, "unreadable distribution delta-1.0.dist-info")


def test_a_record_hashed_with_anything_but_sha256_refuses(site: Path) -> None:
    record = site / "alpha-1.0.dist-info/RECORD"
    record.write_text(record.read_text().replace("sha256=", "md5=", 1))
    _refusal(site, "unreadable distribution alpha-1.0.dist-info")


# --------------------------------------------------------------------------- the checkout


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    package = root / "src/crypto_probability_engine"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (root / "scripts").mkdir()
    (root / "scripts/evaluate.py").write_text("print('entrypoint')\n")
    (root / ".gitignore").write_text("__pycache__/\n.work/\n")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q"], cwd=root, check=True)
    subprocess.run([*git, "add", "-A"], cwd=root, check=True)
    subprocess.run([*git, "commit", "-qm", "reviewed"], cwd=root, check=True)
    return root


def test_a_clean_checkout_passes_and_plain_untracked_data_is_allowed(checkout: Path) -> None:
    (checkout / ".work").mkdir()
    (checkout / ".work/section-5a-report.json").write_text("{}")
    (checkout / "notes.txt").write_text("not code")
    iso.audit_checkout(checkout)


@pytest.mark.parametrize(
    ("relative", "fragment"),
    [
        ("scripts/platform.py", "code is in the checkout: scripts/platform.py"),
        ("src/crypto_probability_engine/json.py", "untracked or ignored code"),
        ("tests_helper.pth", "untracked or ignored code is in the checkout: tests_helper.pth"),
        (".work/hook.py", "untracked or ignored code is in the checkout: .work/hook.py"),
        ("src/crypto_probability_engine/_speedups.so", "untracked or ignored code"),
    ],
)
def test_untracked_or_ignored_code_refuses(checkout: Path, relative: str, fragment: str) -> None:
    path = checkout / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"code")
    refusal = "carries code outside the reviewed commit"
    with pytest.raises(iso.IsolationRefused, match=refusal) as exc:
        iso.audit_checkout(checkout)
    assert fragment in str(exc.value)


def test_a_bytecode_cache_in_the_checkout_refuses(checkout: Path) -> None:
    cache = checkout / "src/crypto_probability_engine/__pycache__"
    cache.mkdir()
    (cache / "__init__.cpython-313.pyc").write_bytes(b"compiled")
    with pytest.raises(iso.IsolationRefused, match="a bytecode cache is in the checkout"):
        iso.audit_checkout(checkout)


def test_a_committed_shadow_in_the_source_root_refuses(checkout: Path) -> None:
    """Opus's O809-1 probe, at the source root: only the first-party package may live in src/."""

    (checkout / "src/platform.py").write_text("SHADOW = True\n")
    subprocess.run(["git", "add", "-A"], cwd=checkout, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "x"],
        cwd=checkout,
        check=True,
    )
    with pytest.raises(iso.IsolationRefused, match="src/ may hold only crypto_probability_engine"):
        iso.audit_checkout(checkout)


def test_a_tracked_compiled_file_refuses(checkout: Path) -> None:
    (checkout / "scripts/helper.pth").write_text("import os\n")
    subprocess.run(["git", "add", "-A"], cwd=checkout, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "x"],
        cwd=checkout,
        check=True,
    )
    refusal = "compiled or path-configuration file is tracked"
    with pytest.raises(iso.IsolationRefused, match=refusal):
        iso.audit_checkout(checkout)


def test_a_directory_that_is_not_a_checkout_refuses(tmp_path: Path) -> None:
    with pytest.raises(iso.IsolationRefused, match="not a git checkout"):
        iso.audit_checkout(tmp_path)


# --------------------------------------------------------------------------- loaded modules


@pytest.fixture
def layout(tmp_path: Path):
    lib = tmp_path / "base/lib/python3.13"
    site = lib / "site-packages"
    root = tmp_path / "checkout"
    for path, text in (
        (lib / "json/__init__.py", ""),
        (site / "alpha/__init__.py", ""),
        (site / "certifi.py", ""),
        (root / "src/crypto_probability_engine/__init__.py", ""),
        (root / "src/crypto_probability_engine/pinned.py", ""),
        (root / "src/crypto_probability_engine/unpinned.py", ""),
        (root / "scripts/evaluate.py", ""),
        (tmp_path / "elsewhere/evil.py", ""),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    report = iso.IsolationReport(
        interpreter_flags=iso.REQUIRED_FLAGS_TEXT,
        stdlib_roots=(str(lib.resolve()),),
        site_dirs=(str(site.resolve()),),
        source_root=str((root / "src").resolve()),
        installed={},
        installed_files_sha256="e" * 64,
        locked_files=frozenset({str((site / "alpha/__init__.py").resolve())}),
    )
    pinned = [
        "scripts/evaluate.py",
        "src/crypto_probability_engine/__init__.py",
        "src/crypto_probability_engine/pinned.py",
    ]
    return SimpleNamespace(
        lib=lib, site=site, root=root, tmp=tmp_path, report=report, pinned=pinned
    )


def _module(name: str, *, origin=None, file=None, locations=None):
    module = types.ModuleType(name)
    if origin is not None or locations is not None:
        spec = importlib.machinery.ModuleSpec(name, loader=None, origin=origin)
        if locations is not None:
            spec.submodule_search_locations = locations
        module.__spec__ = spec
    else:
        module.__spec__ = None
    if file is not None:
        module.__file__ = file
    return module


def test_verified_origins_pass(layout) -> None:
    modules = {
        "sys": _module("sys", origin="built-in"),
        "_frozen_importlib": _module("_frozen_importlib", origin="frozen"),
        "json": _module("json", origin=str(layout.lib / "json/__init__.py")),
        "alpha": _module("alpha", origin=str(layout.site / "alpha/__init__.py")),
        "crypto_probability_engine.pinned": _module(
            "crypto_probability_engine.pinned",
            origin=str(layout.root / "src/crypto_probability_engine/pinned.py"),
        ),
        "__main__": _module("__main__", file=str(layout.root / "scripts/evaluate.py")),
        "email.namespace": _module("email.namespace", locations=[str(layout.lib / "json")]),
        "placeholder": None,
    }
    verified = iso.attest_loaded_modules(
        layout.report, pinned=layout.pinned, root=layout.root, modules=modules
    )
    assert verified == 7


@pytest.mark.parametrize(
    ("name", "where", "fragment"),
    [
        ("certifi", "site/certifi.py", "outside the standard library, the verified locked files"),
        (
            "crypto_probability_engine.unpinned",
            "src/crypto_probability_engine/unpinned.py",
            "outside",
        ),
        ("evil", "elsewhere/evil.py", "outside"),
    ],
)
def test_an_unverified_origin_refuses(layout, name: str, where: str, fragment: str) -> None:
    base = {
        "site": layout.site,
        "src": layout.root / "src",
        "elsewhere": layout.tmp / "elsewhere",
    }[where.split("/", 1)[0]]
    origin = str(base / where.split("/", 1)[1])
    with pytest.raises(iso.IsolationRefused, match="a loaded module is not verified code") as exc:
        iso.attest_loaded_modules(
            layout.report,
            pinned=layout.pinned,
            root=layout.root,
            modules={name: _module(name, origin=origin)},
        )
    assert fragment in str(exc.value)


def test_a_module_without_any_origin_refuses(layout) -> None:
    with pytest.raises(iso.IsolationRefused, match="has no verifiable origin"):
        iso.attest_loaded_modules(
            layout.report,
            pinned=layout.pinned,
            root=layout.root,
            modules={"ghost": _module("ghost")},
        )


def test_a_namespace_package_outside_verified_roots_refuses(layout) -> None:
    outside = _module("stray", locations=[str(layout.tmp / "elsewhere")])
    with pytest.raises(iso.IsolationRefused, match="has no verifiable origin"):
        iso.attest_loaded_modules(
            layout.report, pinned=layout.pinned, root=layout.root, modules={"stray": outside}
        )


def test_site_packages_inside_the_stdlib_tree_is_not_standard_library(layout) -> None:
    """site-packages lives under lib/python3.13; being below the stdlib root is not enough."""

    assert iso._is_within(layout.site.resolve(), layout.lib.resolve())
    with pytest.raises(iso.IsolationRefused):
        iso.attest_loaded_modules(
            layout.report,
            pinned=layout.pinned,
            root=layout.root,
            modules={"certifi": _module("certifi", origin=str(layout.site / "certifi.py"))},
        )
