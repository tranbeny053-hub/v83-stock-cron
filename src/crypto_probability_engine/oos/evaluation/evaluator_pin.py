"""Content pin for the section 5A evaluator.

Mirrors ``oos/freeze_guard.py``: SHA-256 over canonical JSON of a sorted file list, then
per file a NUL-delimited path marker, the UTF-8 relative path, a NUL-delimited content
marker and the raw bytes; compared by exact equality and failing closed.

The pinned set is DECLARED EXPLICITLY rather than derived by import closure.  The
evaluator's transitive closure would sweep in most of the application and churn on
unrelated edits; the declared set is exactly what can change the answer
(``docs/SECTION_5A_EVALUATION_PREREGISTRATION.md`` §2).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PIN_SCHEMA_VERSION = "section-5a-evaluator-pin.v1"
DEFAULT_PIN = Path("ops/section_5a_evaluator_pin.json")

_EVALUATOR_PACKAGE = "src/crypto_probability_engine/oos/evaluation"
_REUSED_DEFINITIONS = (
    "src/crypto_probability_engine/calibration/metrics.py",
    "src/crypto_probability_engine/calibration/schemas.py",
    "src/crypto_probability_engine/utils/invariants.py",
)


class EvaluatorPinMismatch(RuntimeError):
    """The reviewed evaluator pin does not match the evaluator on disk."""


def project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def pinned_files(root: Path | None = None) -> tuple[str, ...]:
    repository_root = (root or project_root()).resolve()
    package = repository_root / _EVALUATOR_PACKAGE
    names = {
        f"{_EVALUATOR_PACKAGE}/{path.name}" for path in package.glob("*.py")
    }
    names.update(_REUSED_DEFINITIONS)
    for relative in sorted(names):
        if not (repository_root / relative).is_file():
            raise EvaluatorPinMismatch(f"pinned file is missing: {relative}")
    return tuple(sorted(names))


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


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
