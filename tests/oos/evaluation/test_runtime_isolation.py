"""Isolated start-up and authenticated import surface (rulings G1=A, J1=B). No DB, no network.

Every refusal is proven against a synthetic layout, so each check is exercised on data it cannot
pass by accident:
- wheels built here and authenticated by a lock written here;
- site-packages installed from them exactly as pip installs;
- a real git checkout;
- a synthetic module table.

The whole mechanism running end to end in a `python -I -S -B` process is proven in
``tests/scripts/test_evaluate_section_5a.py``.
"""

from __future__ import annotations

import ast
import base64
import csv
import hashlib
import importlib.machinery
import io
import json
import subprocess
import sys
import types
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from crypto_probability_engine import runtime_isolation as iso
from crypto_probability_engine.oos.evaluation import provenance

ROOT = Path(__file__).resolve().parents[3]


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
    entries = iso.read_lock_entries(ROOT)
    assert {name: entry.version for name, entry in entries.items()} == iso.read_lock(ROOT)
    assert all(entry.hashes for entry in entries.values())


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


def test_this_test_process_is_not_isolated_and_is_refused(tmp_path: Path) -> None:
    with pytest.raises(iso.IsolationRefused):
        iso.verify_interpreter_isolation()
    with pytest.raises(iso.IsolationRefused):
        iso.enter(ROOT, wheelhouse=tmp_path)


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




# --------------------------------------------------------------------------- wheels and the lock


def _digest(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def _build_wheel(
    directory: Path,
    name: str,
    version: str,
    files: dict[str, bytes],
    *,
    tag: str = "py3-none-any",
    extra_record: tuple[tuple[str, str, str], ...] = (),
) -> Path:
    """A real wheel: payload, METADATA, WHEEL, and a RECORD of every member's digest."""

    stem = f"{name.replace('-', '_')}-{version}"
    dist_info = f"{stem}.dist-info"
    members = {
        **files,
        f"{dist_info}/METADATA": (
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n".encode()
        ),
        f"{dist_info}/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\n",
    }
    rows = [(path, _digest(data), str(len(data))) for path, data in members.items()]
    rows.append((f"{dist_info}/RECORD", "", ""))
    rows.extend(extra_record)
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    directory.mkdir(parents=True, exist_ok=True)
    wheel = directory / f"{stem}-{tag}.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for path, data in members.items():
            archive.writestr(path, data)
        archive.writestr(f"{dist_info}/RECORD", buffer.getvalue())
    return wheel


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pip_install(site: Path, wheel: Path) -> None:
    """Install as pip does: extract the payload, map .data/purelib, add installer metadata."""

    with zipfile.ZipFile(wheel) as archive:
        dist_info = next(
            n.split("/")[0] for n in archive.namelist() if n.endswith(".dist-info/RECORD")
        )
        data_prefix = dist_info[: -len(".dist-info")] + ".data/"
        for member in archive.namelist():
            target = member
            if member.startswith(data_prefix):
                kind, _, rest = member[len(data_prefix) :].partition("/")
                if kind not in {"purelib", "platlib"}:
                    continue
                target = rest
            path = site / target
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(member))
    (site / dist_info / "INSTALLER").write_text("pip\n")
    (site / dist_info / "REQUESTED").write_text("")


@pytest.fixture
def world(tmp_path: Path) -> SimpleNamespace:
    """A wheelhouse of two authenticated wheels, the lock that pins them, and a site from them."""

    wheelhouse = tmp_path / "wheels"
    alpha = _build_wheel(wheelhouse, "alpha", "1.0", {"alpha/__init__.py": b"VALUE = 1\n"})
    beta = _build_wheel(
        wheelhouse,
        "beta-core",
        "2.0",
        {
            "beta_core/__init__.py": b"",
            "beta_core/_ext.so": b"\x7fELF",
            "beta_core-2.0.data/purelib/beta_extra.py": b"EXTRA = 1\n",
            "beta_core-2.0.data/scripts/beta-tool": b"#!python\n",
        },
        tag="cp313-cp313-manylinux_2_28_x86_64",
    )
    lock = {
        "alpha": iso.LockEntry("1.0", frozenset({_sha256(alpha), "0" * 64})),
        "beta-core": iso.LockEntry("2.0", frozenset({_sha256(beta)})),
    }
    site = tmp_path / "lib/python3.13/site-packages"
    site.mkdir(parents=True)
    (site / "README.txt").write_text("CPython's own placeholder\n")
    for wheel in (alpha, beta):
        _pip_install(site, wheel)
    return SimpleNamespace(tmp=tmp_path, wheelhouse=wheelhouse, lock=lock, site=site)


def _authenticated(world) -> dict:
    return iso.authenticate_wheelhouse(world.wheelhouse, world.lock)


def test_the_lock_authenticates_exactly_its_wheels(world) -> None:
    wheels = _authenticated(world)
    assert sorted(wheels) == ["alpha", "beta-core"]
    beta = wheels["beta-core"]
    assert "beta_extra.py" in beta.payload, ".data/purelib installs at the site root"
    assert not any("beta-tool" in path for path in beta.payload), "scripts never enter site"
    assert "beta_core-2.0.dist-info/RECORD" not in beta.payload


def _wheelhouse_refusal(world, fragment: str) -> None:
    refusal = "not exactly the lock-authenticated wheels"
    with pytest.raises(iso.IsolationRefused, match=refusal) as exc:
        _authenticated(world)
    assert fragment in str(exc.value), str(exc.value)


def test_a_wheel_the_lock_does_not_authenticate_refuses(world) -> None:
    wheel = next(world.wheelhouse.glob("alpha-*.whl"))
    wheel.write_bytes(wheel.read_bytes() + b"\0")
    _wheelhouse_refusal(world, "is not a wheel the lock authenticates")


def test_a_wheel_at_another_version_refuses(world) -> None:
    _build_wheel(world.tmp / "other", "alpha", "1.1", {"alpha/__init__.py": b""})
    next((world.wheelhouse).glob("alpha-*.whl")).unlink()
    moved = world.tmp / "other/alpha-1.1-py3-none-any.whl"
    moved.rename(world.wheelhouse / moved.name)
    _wheelhouse_refusal(world, "is version 1.1; the lock pins 1.0")


def test_a_wheel_outside_the_lock_refuses(world) -> None:
    _build_wheel(world.wheelhouse, "gamma", "3.0", {"gamma.py": b""})
    _wheelhouse_refusal(world, "a wheel for a distribution outside the lock")


def test_a_missing_wheel_refuses(world) -> None:
    next(world.wheelhouse.glob("beta_core-*.whl")).unlink()
    _wheelhouse_refusal(world, "no authenticated wheel for locked beta-core==2.0")


def test_two_authenticated_wheels_for_one_pin_refuse(world) -> None:
    second = _build_wheel(
        world.tmp / "more",
        "alpha",
        "1.0",
        {"alpha/__init__.py": b"VALUE = 1\n"},
        tag="py2.py3-none-any",
    )
    world.lock["alpha"] = iso.LockEntry("1.0", world.lock["alpha"].hashes | {_sha256(second)})
    second.rename(world.wheelhouse / second.name)
    _wheelhouse_refusal(world, "more than one authenticated wheel for alpha")


def test_anything_but_regular_wheel_files_refuses(world) -> None:
    (world.wheelhouse / "notes.txt").write_text("not a wheel")
    _wheelhouse_refusal(world, "something but a regular wheel: notes.txt")


def test_a_symlinked_wheel_refuses(world) -> None:
    wheel = next(world.wheelhouse.glob("alpha-*.whl"))
    real = world.tmp / "elsewhere.whl"
    wheel.rename(real)
    wheel.symlink_to(real)
    _wheelhouse_refusal(world, "something but a regular wheel")


def test_a_wheel_record_with_an_unsafe_path_refuses(world) -> None:
    unsafe = _build_wheel(
        world.tmp / "unsafe",
        "alpha",
        "1.0",
        {"alpha/__init__.py": b""},
        extra_record=(("../escape.py", _digest(b""), "0"),),
    )
    next(world.wheelhouse.glob("alpha-*.whl")).unlink()
    unsafe.rename(world.wheelhouse / unsafe.name)
    world.lock["alpha"] = iso.LockEntry("1.0", frozenset({_sha256(world.wheelhouse / unsafe.name)}))
    _wheelhouse_refusal(world, "unsafe RECORD path")


def test_a_symlinked_wheelhouse_refuses(world) -> None:
    link = world.tmp / "link-wheels"
    link.symlink_to(world.wheelhouse)
    with pytest.raises(iso.IsolationRefused, match="not a real directory"):
        iso.authenticate_wheelhouse(link, world.lock)


# --------------------------------------------------------------------------- site-packages


def _audit(world):
    return iso.audit_site_packages(world.site, _authenticated(world))


def test_a_site_installed_from_the_authenticated_wheels_passes(world) -> None:
    installed, digest, locked_files = _audit(world)
    assert installed == {"alpha": "1.0", "beta-core": "2.0"}
    assert len(digest) == 64
    for relative in ("alpha/__init__.py", "beta_core/_ext.so", "beta_extra.py"):
        assert str((world.site / relative).resolve()) in locked_files


def test_the_installed_files_digest_is_a_function_of_the_wheels_alone(
    world, tmp_path: Path
) -> None:
    _, first, _ = _audit(world)
    again = tmp_path / "again/site-packages"
    again.mkdir(parents=True)
    for wheel in sorted(world.wheelhouse.glob("*.whl")):
        _pip_install(again, wheel)
    _, second, _ = iso.audit_site_packages(again, _authenticated(world))
    assert first == second


def _site_refusal(world, fragment: str) -> None:
    with pytest.raises(iso.IsolationRefused, match="not exactly the authenticated wheels") as exc:
        _audit(world)
    assert fragment in str(exc.value), str(exc.value)


def test_a_tampered_file_with_a_rewritten_installed_record_refuses(world) -> None:
    """V810-F1, reproduced: the installed RECORD is rewritten to bless the tampered bytes."""

    path = world.site / "alpha/__init__.py"
    path.write_bytes(b"VALUE = 1  # not in the authenticated wheel\n")
    record = world.site / "alpha-1.0.dist-info/RECORD"
    record.write_text(f"alpha/__init__.py,{_digest(path.read_bytes())},{path.stat().st_size}\n")
    _site_refusal(world, "differs from its authenticated wheel: alpha/__init__.py")


def test_a_symlinked_package_directory_refuses(world) -> None:
    """V810-F3, reproduced: a package directory replaced by a link to an outside copy."""

    outside = world.tmp / "outside-alpha"
    (world.site / "alpha").rename(outside)
    (world.site / "alpha").symlink_to(outside)
    _site_refusal(world, "a symlink in site-packages: alpha")


def test_a_symlinked_file_refuses(world) -> None:
    target = world.tmp / "real_init.py"
    target.write_bytes((world.site / "alpha/__init__.py").read_bytes())
    (world.site / "alpha/__init__.py").unlink()
    (world.site / "alpha/__init__.py").symlink_to(target)
    _site_refusal(world, "a symlink in site-packages: alpha/__init__.py")


def test_the_floating_installer_left_in_site_packages_refuses(world) -> None:
    (world.site / "pip").mkdir()
    (world.site / "pip/__init__.py").write_text("")
    (world.site / "pip-26.1.2.dist-info").mkdir()
    (world.site / "pip-26.1.2.dist-info/METADATA").write_text("Name: pip\nVersion: 26.1.2\n")
    _site_refusal(world, "a distribution outside the authenticated wheels is installed: pip")


@pytest.mark.parametrize(
    ("relative", "fragment"),
    [
        ("certifi.py", "no authenticated wheel declares could shadow verified code: certifi.py"),
        ("zz.pth", "path configuration file in site-packages: zz.pth"),
        ("sitecustomize.py", "start-up customization in site-packages: sitecustomize.py"),
        ("alpha/__pycache__/__init__.cpython-313.pyc", "an unexpected directory in site-packages"),
        ("alpha-1.0.dist-info/entry_points.txt", "could shadow verified code: alpha-1.0.dist-info"),
    ],
)
def test_an_unexpected_file_refuses(world, relative: str, fragment: str) -> None:
    path = world.site / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"unexpected")
    _site_refusal(world, fragment)


def test_an_unexpected_empty_directory_refuses(world) -> None:
    (world.site / "namespace_surprise").mkdir()
    _site_refusal(world, "an unexpected directory in site-packages: namespace_surprise")


def test_a_missing_authenticated_file_refuses(world) -> None:
    (world.site / "beta_core/_ext.so").unlink()
    _site_refusal(world, "an authenticated file is not installed: beta_core/_ext.so")


def test_a_duplicate_distribution_refuses(world) -> None:
    copy = world.site / "alpha_copy-1.0.dist-info"
    copy.mkdir()
    (copy / "METADATA").write_text("Metadata-Version: 2.1\nName: alpha\nVersion: 1.0\n")
    _site_refusal(world, "distribution alpha is installed more than once")


def test_a_split_purelib_platlib_layout_refuses(tmp_path: Path) -> None:
    with pytest.raises(iso.IsolationRefused, match="must be one directory"):
        iso.single_site_directory((tmp_path / "lib", tmp_path / "lib64"))


# --------------------------------------------------------------------------- the trusted installer


def test_the_only_trusted_installer_is_the_pip_cpython_bundles(tmp_path: Path) -> None:
    bundled = tmp_path / "ensurepip/_bundled"
    bundled.mkdir(parents=True)
    with pytest.raises(iso.IsolationRefused, match="exactly one regular bundled pip wheel"):
        iso.bundled_pip_wheel(tmp_path)
    (bundled / "pip-26.1.2-py3-none-any.whl").write_bytes(b"wheel")
    assert iso.bundled_pip_wheel(tmp_path).name == "pip-26.1.2-py3-none-any.whl"
    (bundled / "pip-25.0-py3-none-any.whl").write_bytes(b"wheel")
    with pytest.raises(iso.IsolationRefused, match="exactly one"):
        iso.bundled_pip_wheel(tmp_path)


def test_this_interpreter_bundles_exactly_one_pip() -> None:
    assert iso.bundled_pip_wheel().name.startswith("pip-")


def test_the_floating_installer_is_removed_without_being_run(tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    for name in ("pip", "pip-26.2.1.dist-info", "other"):
        (site / name).mkdir(parents=True)
    (site / "pip/__init__.py").write_text("raise SystemExit('pip must never run')\n")
    (site / "README.txt").write_text("kept")
    assert iso.remove_floating_installer(site) == ["pip", "pip-26.2.1.dist-info"]
    assert sorted(entry.name for entry in site.iterdir()) == ["README.txt", "other"]


def test_a_symlinked_floating_installer_is_refused_not_followed(tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    site.mkdir()
    target = tmp_path / "somewhere"
    target.mkdir()
    (site / "pip").symlink_to(target)
    with pytest.raises(iso.IsolationRefused, match="not a real directory"):
        iso.remove_floating_installer(site)
    assert target.exists()

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


def test_a_tracked_modification_refuses(checkout: Path) -> None:
    (checkout / "scripts/evaluate.py").write_text("print('changed after checkout')\n")
    with pytest.raises(iso.IsolationRefused, match="tracked files differ from the commit"):
        iso.audit_checkout(checkout)


def test_an_untracked_symlink_in_the_checkout_refuses(checkout: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside-src"
    outside.mkdir()
    (checkout / "scripts/linked").symlink_to(outside)
    with pytest.raises(iso.IsolationRefused, match="a symlink is in the checkout: scripts/linked"):
        iso.audit_checkout(checkout)


def test_a_tracked_symlink_refuses(checkout: Path) -> None:
    (checkout / "scripts/alias.py").symlink_to("evaluate.py")
    subprocess.run(["git", "add", "-A"], cwd=checkout, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "x"],
        cwd=checkout,
        check=True,
    )
    with pytest.raises(iso.IsolationRefused, match="a tracked symlink: scripts/alias.py"):
        iso.audit_checkout(checkout)



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
        ("certifi", "site/certifi.py", "outside the standard library, the authenticated files"),
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


# --------------------------------------------------------------------------- dynamic helpers


def _driver_layout(layout, *, authenticated: bool = True):
    """The locked Postgres driver's compiled extensions, installed and optionally authenticated."""

    import dataclasses

    suffix = importlib.machinery.EXTENSION_SUFFIXES[0]
    extensions = {}
    for name in iso.DYNAMIC_HELPER_DRIVER_EXTENSIONS:
        path = layout.site / (name.replace(".", "/") + suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x7fELF compiled")
        extensions[name] = _module(name, origin=str(path))
    locked = set(layout.report.locked_files)
    if authenticated:
        locked |= {str(Path(module.__spec__.origin).resolve()) for module in extensions.values()}
    report = dataclasses.replace(layout.report, locked_files=frozenset(locked))
    return report, extensions


def _cython_runtime() -> types.ModuleType:
    """Exactly the module Cython's runtime creates: a bare module, nothing in it."""

    return _module("cython_runtime")


def test_exactly_two_helpers_are_pinned_each_by_a_sha256_fingerprint() -> None:
    assert set(iso.DYNAMIC_HELPER_FINGERPRINTS) == {"_cython_3_2_4", "cython_runtime"}
    assert all(
        len(v) == 64 and set(v) <= set("0123456789abcdef")
        for v in iso.DYNAMIC_HELPER_FINGERPRINTS.values()
    )
    assert iso.DYNAMIC_HELPER_DRIVER_EXTENSIONS == ("psycopg_binary._psycopg", "psycopg_binary.pq")
    with pytest.raises(TypeError):
        iso.DYNAMIC_HELPER_FINGERPRINTS["_cython_9_9_9"] = "0" * 64  # type: ignore[index]


def test_a_pinned_helper_passes_only_while_the_authenticated_driver_is_loaded(layout) -> None:
    report, extensions = _driver_layout(layout)
    modules = {**extensions, "cython_runtime": _cython_runtime()}
    verified = iso.attest_loaded_modules(
        report, pinned=layout.pinned, root=layout.root, modules=modules
    )
    assert verified == 3

    with pytest.raises(iso.IsolationRefused, match="driver is not loaded"):
        iso.attest_loaded_modules(
            report,
            pinned=layout.pinned,
            root=layout.root,
            modules={"cython_runtime": _cython_runtime()},
        )


def test_driver_extensions_outside_the_authenticated_files_do_not_count(layout) -> None:
    report, extensions = _driver_layout(layout, authenticated=False)
    with pytest.raises(iso.IsolationRefused) as exc:
        iso.attest_loaded_modules(
            report,
            pinned=layout.pinned,
            root=layout.root,
            modules={**extensions, "cython_runtime": _cython_runtime()},
        )
    assert "driver is not loaded" in str(exc.value)
    assert "psycopg_binary._psycopg was loaded from" in str(exc.value)


def test_one_driver_extension_is_not_the_driver(layout) -> None:
    report, extensions = _driver_layout(layout)
    extensions.pop("psycopg_binary.pq")
    with pytest.raises(iso.IsolationRefused, match="driver is not loaded"):
        iso.attest_loaded_modules(
            report,
            pinned=layout.pinned,
            root=layout.root,
            modules={**extensions, "cython_runtime": _cython_runtime()},
        )


@pytest.mark.parametrize("name", ["_cython_3_2_5", "_cython_3_2_4x", "cython_runtime2", "_cython"])
def test_no_other_file_less_name_is_ever_a_helper(layout, name: str) -> None:
    report, extensions = _driver_layout(layout)
    with pytest.raises(iso.IsolationRefused) as exc:
        iso.attest_loaded_modules(
            report,
            pinned=layout.pinned,
            root=layout.root,
            modules={**extensions, name: _module(name)},
        )
    assert f"module {name} has no verifiable origin" in str(exc.value)
    assert "pinned dynamic helper" not in str(exc.value)


class _ModuleSubclass(types.ModuleType):
    pass


def _shape(variant: str) -> types.ModuleType:
    module = _cython_runtime()
    if variant == "python-function":
        module.hook = lambda: None
    elif variant == "extra-string":
        module.note = "text"
    elif variant == "subclass":
        module = _ModuleSubclass("cython_runtime")
        module.__spec__ = None
    elif variant == "loader":
        module.__loader__ = object()
    elif variant == "path":
        module.__path__ = []
    elif variant == "renamed":
        module.__name__ = "something_else"
    elif variant == "python-class":
        module.generator = type("generator", (), {"send": lambda self, value: value})
    return module


@pytest.mark.parametrize(
    ("variant", "fragment"),
    [
        ("python-function", "structural fingerprint"),
        ("extra-string", "structural fingerprint"),
        ("python-class", "structural fingerprint"),
        ("subclass", "not a plain module"),
        ("loader", "spec, loader, file or path"),
        ("path", "spec, loader, file or path"),
        ("renamed", "its own name is not the one it is loaded under"),
    ],
)
def test_a_pinned_helper_name_with_any_other_shape_refuses(
    layout, variant: str, fragment: str
) -> None:
    report, extensions = _driver_layout(layout)
    with pytest.raises(iso.IsolationRefused) as exc:
        iso.attest_loaded_modules(
            report,
            pinned=layout.pinned,
            root=layout.root,
            modules={**extensions, "cython_runtime": _shape(variant)},
        )
    assert fragment in str(exc.value)


def test_a_refused_fingerprint_names_the_digest_it_saw() -> None:
    """A platform whose helper differs must be diagnosable from the refusal alone."""

    shaped = _shape("extra-string")
    refusal = iso._dynamic_helper_refusal("cython_runtime", shaped, driver_loaded=True)
    assert iso.dynamic_helper_fingerprint(shaped) in refusal
    assert iso.DYNAMIC_HELPER_FINGERPRINTS["cython_runtime"] in refusal


def test_the_fingerprint_ignores_insertion_order_and_sees_python_code() -> None:
    first, second = types.ModuleType("probe"), types.ModuleType("probe")
    first.a, first.b = 1, "x"
    second.b, second.a = "x", 1
    assert iso.dynamic_helper_fingerprint(first) == iso.dynamic_helper_fingerprint(second)

    carrier = types.ModuleType("probe")
    carrier.kind = type("kind", (), {"run": lambda self: None})
    described = iso.describe_dynamic_helper(carrier)["namespace"]["kind"]
    assert described["attributes"]["run"] == "function"
    assert described["metatype"] == "type" and described["bases"] == ["object"]


def test_the_installed_driver_s_helpers_are_judged_by_the_pinned_rule() -> None:
    """The REAL driver, imported in a fresh process, never skipped (tests/test_no_silent_skips.py).

    Every file-less module its import creates is judged by the pinned rule. On the pinned
    interpreter with the locked driver build, both helpers must be accepted with exactly the pinned
    fingerprints. On any other build, a helper is accepted only with the pinned fingerprint, and
    otherwise refused with both digests named. The Section 5A jobs prove the pinned case on the real
    runner in their secret-free attest step.
    """

    probe = (
        "import json, platform, sys\n"
        "from importlib import metadata\n"
        f"sys.path.append({str(ROOT / 'src')!r})\n"
        "from crypto_probability_engine import runtime_isolation as iso\n"
        "before = set(sys.modules)\n"
        "import psycopg\n"
        "judged = {}\n"
        "for name in sorted(set(sys.modules) - before):\n"
        "    module = sys.modules[name]\n"
        "    spec = getattr(module, '__spec__', None)\n"
        "    if spec is not None or getattr(module, '__file__', None) is not None:\n"
        "        continue\n"
        "    judged[name] = {'fingerprint': iso.dynamic_helper_fingerprint(module),\n"
        "        'refusal': iso._dynamic_helper_refusal(name, module, driver_loaded=True)}\n"
        "print(json.dumps({'python': platform.python_version(),\n"
        "    'driver': metadata.version('psycopg-binary'), 'judged': judged}))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-c", probe],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    seen = json.loads(completed.stdout.strip().splitlines()[-1])
    pinned = iso.DYNAMIC_HELPER_FINGERPRINTS
    for name, verdict in seen["judged"].items():
        if verdict["refusal"] is None:
            assert verdict["fingerprint"] == pinned[name], name
        elif verdict["refusal"]:
            assert verdict["fingerprint"] in verdict["refusal"], name
            assert pinned[name] in verdict["refusal"], name
    locked_driver = provenance.read_lock(ROOT)["psycopg-binary"]
    if seen["python"] == provenance.PINNED_PYTHON_VERSION and seen["driver"] == locked_driver:
        assert {name: v["fingerprint"] for name, v in seen["judged"].items()} == dict(pinned)
        assert all(v["refusal"] is None for v in seen["judged"].values())
