"""Content pin for the section 5A evaluator, derived MECHANICALLY.

OWNER RULING D1 (2026-09-13). The pinned set is no longer a hand-maintained list. It is:

  1. the FULL first-party import closure of the evaluator's production entrypoint — every
     ``crypto_probability_engine`` module reachable through any import statement, at module level
     or inside a function, together with every parent package ``__init__.py``, because Python
     executes those on import; plus
  2. the explicitly declared surfaces that no import reaches but that govern the answer: the rules
     it implements and the runtime that executes it.

WHY. A declared list was incomplete in three consecutive verification rounds (F6, G4, V807-F7):
each repair added exactly the files the verifier named, and nothing checked the list was whole.
The pre-registration had rejected closure derivation expecting it to "sweep in most of the
application"; measured, the closure is a bounded set that does not reach the Hugging Face
application surface.

The digest mechanism mirrors ``oos/freeze_guard.py``: SHA-256 over canonical JSON of the sorted
file list, then per file a NUL-delimited path marker, the UTF-8 relative path, a NUL-delimited
content marker and the raw bytes; compared by exact equality, failing closed.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

PIN_SCHEMA_VERSION = "section-5a-evaluator-pin.v2"
DEFAULT_PIN = Path("ops/section_5a_evaluator_pin.json")
FIRST_PARTY_PACKAGE = "crypto_probability_engine"
SOURCE_ROOT = "src"

# The production entrypoint. Everything the evaluator executes is reachable from here.
ENTRYPOINTS: tuple[str, ...] = ("scripts/evaluate_section_5a.py",)

# Surfaces that govern the answer but are never imported. Each is named with its reason.
DECLARED_SURFACES: tuple[str, ...] = (
    "V1_QUANT_CONTRACT.md",  # the rules: §5A defines what the evaluator computes
    "docs/SECTION_5A_EVALUATION_PREREGISTRATION.md",  # the rules as resolved before the look
    "migrations/0009_section_5a_evaluation_seal.sql",  # the durable seal lifecycle, DB-enforced
    ".github/workflows/section-5a-evaluation.yml",  # where and how the evaluation executes
    # Which third-party runtime is installed: exact versions, every hash (owner ruling E3=A). It
    # replaces requirements.txt, whose version ranges bound nothing (V808-R5).
    "ops/section_5a_evaluator_requirements.lock",
)


class EvaluatorPinMismatch(RuntimeError):
    """The reviewed evaluator pin does not match the evaluator on disk."""


def project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def import_closure(root: Path | None = None) -> tuple[str, ...]:
    """Return the full first-party import closure of the entrypoints, fail-closed.

    Static and deterministic: it parses source rather than executing it, so it is identical in
    every environment, and it includes imports inside functions, which a runtime ``sys.modules``
    snapshot would miss until they execute. A first-party module that is imported but cannot be
    resolved to a file is an error, never a silent omission.
    """

    repository_root = (root or project_root()).resolve()
    pending: list[Path] = []
    for entry in ENTRYPOINTS:
        path = repository_root / entry
        if not path.is_file():
            raise EvaluatorPinMismatch(f"evaluator entrypoint is missing: {entry}")
        pending.append(path)

    seen: set[Path] = set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        try:
            tree = ast.parse(current.read_text(encoding="utf-8"), filename=str(current))
        except (OSError, UnicodeError, SyntaxError) as exc:
            raise EvaluatorPinMismatch(f"cannot parse pinned source: {current}") from exc
        for module, required in _imported_modules(tree):
            for name in _with_parent_packages(module):
                resolved = _module_file(repository_root, name)
                if resolved is None:
                    # The imported MODULE itself must exist; `from x import Name` also probes
                    # x.Name, which is legitimately absent when Name is an attribute.
                    if required and name == module:
                        raise EvaluatorPinMismatch(
                            f"first-party import cannot be resolved to a file: {module}"
                        )
                    continue
                if resolved not in seen:
                    pending.append(resolved)

    return tuple(sorted(path.relative_to(repository_root).as_posix() for path in seen))


def pinned_files(root: Path | None = None) -> tuple[str, ...]:
    repository_root = (root or project_root()).resolve()
    files = set(import_closure(repository_root))
    for surface in DECLARED_SURFACES:
        if not (repository_root / surface).is_file():
            raise EvaluatorPinMismatch(f"declared pinned surface is missing: {surface}")
        files.add(surface)
    return tuple(sorted(files))


def closure_digest(root: Path | None = None) -> tuple[tuple[str, ...], str]:
    repository_root = (root or project_root()).resolve()
    files = pinned_files(repository_root)
    digest = hashlib.sha256()
    digest.update(_canonical_json(list(files)))
    for relative in files:
        content = (repository_root / relative).read_bytes()
        digest.update(b"\0path\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0content\0")
        digest.update(content)
    return files, digest.hexdigest()


def current_pin_artifacts(root: Path | None = None) -> dict[str, Any]:
    files, digest = closure_digest(root)
    return {
        "schema_version": PIN_SCHEMA_VERSION,
        "entrypoints": list(ENTRYPOINTS),
        "declared_surfaces": list(DECLARED_SURFACES),
        "pinned_files": list(files),
        "closure_digest": digest,
    }


def assert_evaluator_pin(
    *, pin_path: Path | None = None, root: Path | None = None
) -> dict[str, Any]:
    """Fail closed unless the evaluator on disk is byte-identical to the reviewed pin."""

    repository_root = (root or project_root()).resolve()
    resolved = pin_path or (repository_root / DEFAULT_PIN)
    try:
        pinned = json.loads(Path(resolved).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluatorPinMismatch("evaluator pin is missing or invalid") from exc
    current = current_pin_artifacts(repository_root)
    if pinned != current:
        raise EvaluatorPinMismatch(
            "evaluator does not match its reviewed pin; a change after the first live "
            "readiness run requires owner authorization (pre-registration §2)"
        )
    return current


def write_pin(*, pin_path: Path | None = None, root: Path | None = None) -> Path:
    repository_root = (root or project_root()).resolve()
    resolved = Path(pin_path or (repository_root / DEFAULT_PIN))
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_bytes(_canonical_json(current_pin_artifacts(repository_root)) + b"\n")
    return resolved


def _imported_modules(tree: ast.AST) -> list[tuple[str, bool]]:
    """(module name, must-resolve) for every first-party import anywhere in the tree."""

    found: list[tuple[str, bool]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == FIRST_PARTY_PACKAGE:
                    found.append((alias.name, True))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise EvaluatorPinMismatch(
                    "relative imports are not supported by the pin derivation; use absolute "
                    "first-party imports"
                )
            if node.module and node.module.split(".")[0] == FIRST_PARTY_PACKAGE:
                found.append((node.module, True))
                for alias in node.names:
                    if alias.name != "*":
                        found.append((f"{node.module}.{alias.name}", False))
    return found


def _with_parent_packages(module: str) -> list[str]:
    parts = module.split(".")
    return [".".join(parts[:index]) for index in range(1, len(parts) + 1)]


def _module_file(root: Path, module: str) -> Path | None:
    base = root / SOURCE_ROOT / Path(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate.resolve()
    return None


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
