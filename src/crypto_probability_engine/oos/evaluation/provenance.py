"""Dispatch provenance and runtime binding for the section 5A evaluation.

OWNER RULINGS E2=A and E3=A (2026-09-14; pre-registration Addendum 5).

V808-F1 showed the evaluation workflow could run arbitrary commands after its pin check had
passed. The workflow no longer puts any input into shell source, and this module makes the facts
that govern a live run POSITIVELY VERIFIED rather than assumed:

  E2  the run is a manual dispatch of THE evaluation workflow, on ``main``, at exactly the commit
      the owner named (``expected_sha``), with no tracked file modified since checkout;
  E3  it executes under exactly the pinned interpreter and exactly the hash-locked dependency
      set, with nothing else installed — not even the installer (owner ruling J1=B).

:func:`attest` observes and verifies. Its record is written durably into the one-look claim, so
the run that spent the look stays identified: commit, run, interpreter, lock and pin.

ISOLATION (owner ruling G1=A). Nothing is attested unless the process was started as
``python -I -S -B`` and :func:`runtime_isolation.enter` verified its import surface first; the
record carries the interpreter flags and the digest of every verified installed file.

ENFORCEMENT LAYERS. The CLI attests before any repository exists, for every live mode. The
durable Postgres authority refuses a claim whose record does not verify (in Python, and in SQL
by migration 0009). Seal recovery refuses a seal whose record does not verify. The library
passes a record through and verifies it when one is given; declared test doubles may omit it,
exactly as they may declare the durable authority (owner ruling D3).

RESIDUAL, stated rather than hidden. Every fact here is observed by code from the dispatcher's own
tree. The one account with write access, or anything holding its credentials, can dispatch a
branch whose evaluator skips this module entirely. These guards stop accidents, drift,
mis-dispatch and the public. They do not stop a compromised owner credential.
"""

from __future__ import annotations

import hashlib
import platform
import re
import subprocess
from collections.abc import Mapping
from importlib import metadata
from pathlib import Path
from typing import Any

from crypto_probability_engine import runtime_isolation
from crypto_probability_engine.oos.evaluation.evaluator_pin import (
    assert_evaluator_pin,
    current_pin_artifacts,
    project_root,
)
from crypto_probability_engine.runtime_isolation import (
    EVALUATOR_LOCK,
    REQUIRED_FLAGS_TEXT,
    IsolationRefused,
    ProvenanceRefused,
    canonical_distribution_name,
)

PROVENANCE_SCHEMA_VERSION = "section-5a-run-provenance.v1"
EVALUATION_WORKFLOW = ".github/workflows/section-5a-evaluation.yml"
# Owner ruling K2=A (pre-registration Addendum 8). Migration 0009 is applied once, by its own
# dispatch-only workflow, under this same attestation. A record that workflow produces verifies ONLY
# as that workflow, and it can never claim or recover the look: require_verified_provenance, the
# durable authority and the 0009 CHECK all accept the evaluation workflow alone.
SEAL_MIGRATION_WORKFLOW = ".github/workflows/section-5a-apply-seal-migration.yml"
ATTESTABLE_WORKFLOWS = (EVALUATION_WORKFLOW, SEAL_MIGRATION_WORKFLOW)
REQUIRED_EVENT = "workflow_dispatch"
REQUIRED_REF = "refs/heads/main"

# E3=A. The exact runtime the evaluation executes under. The workflow installs exactly these; the
# run refuses anything else. Both are pinned: this constant by the import closure, the lock
# (runtime_isolation.EVALUATOR_LOCK) as a declared surface.
PINNED_PYTHON_IMPLEMENTATION = "CPython"
PINNED_PYTHON_VERSION = "3.13.14"

__all__ = [
    "EVALUATOR_LOCK",
    "IsolationRefused",
    "ProvenanceRefused",
    "canonical_distribution_name",
]

_DISPATCH_VARIABLES = (
    ("github_actions", "GITHUB_ACTIONS"),
    ("event_name", "GITHUB_EVENT_NAME"),
    ("repository", "GITHUB_REPOSITORY"),
    ("workflow_ref", "GITHUB_WORKFLOW_REF"),
    ("ref", "GITHUB_REF"),
    ("sha", "GITHUB_SHA"),
    ("run_id", "GITHUB_RUN_ID"),
    ("run_attempt", "GITHUB_RUN_ATTEMPT"),
    ("runner_os", "RUNNER_OS"),
    ("runner_arch", "RUNNER_ARCH"),
    ("image_os", "ImageOS"),
    ("image_version", "ImageVersion"),
)

# The record's exact shape. Every value is a string except the two named here, so the SQL CHECK in
# migration 0009 can read it without number tags.
_RECORD_STRING_FIELDS = (
    "schema_version",
    "event_name",
    "repository",
    "workflow_ref",
    "ref",
    "sha",
    "expected_sha",
    "git_head",
    "run_id",
    "run_attempt",
    "runner_os",
    "runner_arch",
    "image_os",
    "image_version",
    "python_implementation",
    "python_version",
    "lock_path",
    "lock_sha256",
    "pin_digest",
    "interpreter_flags",
    "installed_files_sha256",
)
_RECORD_FIELDS = frozenset({*_RECORD_STRING_FIELDS, "dispatch_verified", "installed"})

_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DIGITS = re.compile(r"^[0-9]+$")


# --------------------------------------------------------------------------- the lock


def read_lock(root: Path | None = None) -> dict[str, str]:
    """Exact, hashed pins from the evaluator lock. See :func:`runtime_isolation.read_lock`."""

    return runtime_isolation.read_lock((root or project_root()).resolve())


def lock_sha256(root: Path | None = None) -> str:
    path = (root or project_root()).resolve() / EVALUATOR_LOCK
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


# --------------------------------------------------------------------------- observation


def observe_dispatch(environ: Mapping[str, str]) -> dict[str, str]:
    """The dispatch facts GitHub sets for every job step. Observation only; nothing is judged."""

    return {field: str(environ.get(variable, "")) for field, variable in _DISPATCH_VARIABLES}


def installed_distributions() -> dict[str, str]:
    """Every distribution importable by this interpreter, by normalized name.

    Two different versions of one name visible on the path are recorded as both, so they can never
    satisfy a lock that pins one of them.
    """

    found: dict[str, str] = {}
    for distribution in metadata.distributions():
        name = distribution.metadata["Name"]
        if not name:
            continue
        key = canonical_distribution_name(name)
        version = distribution.version
        if key in found and found[key] != version:
            version = "|".join(sorted({*found[key].split("|"), version}))
        found[key] = version
    return dict(sorted(found.items()))


def observe_runtime(
    root: Path | None = None, isolation: runtime_isolation.IsolationReport | None = None
) -> dict[str, Any]:
    """The facts of the process and checkout that will execute the evaluation."""

    repository_root = (root or project_root()).resolve()
    status = _git(repository_root, "status", "--porcelain=v1", "--untracked-files=no")
    return {
        "interpreter_flags": runtime_isolation.interpreter_flags(),
        "installed_files_sha256": "" if isolation is None else isolation.installed_files_sha256,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "git_head": _git(repository_root, "rev-parse", "HEAD") or "",
        "tracked_tree_clean": status == "" if status is not None else None,
        "lock_sha256": lock_sha256(repository_root),
        "installed": installed_distributions(),
        "pin_digest": str(current_pin_artifacts(repository_root)["closure_digest"]),
    }


# --------------------------------------------------------------------------- verification


def verify_run_provenance(
    dispatch: Mapping[str, str],
    runtime: Mapping[str, Any],
    *,
    expected_sha: str,
    lock_pins: Mapping[str, str],
    workflow: str = EVALUATION_WORKFLOW,
) -> dict[str, Any]:
    """Pure: observed facts in, a verified record out, or a refusal naming EVERY failed check.

    ``workflow`` names the one workflow this run must be; it is never inferred from the dispatch.
    """

    failures: list[str] = []

    def need(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    repository = str(dispatch.get("repository", ""))
    need(workflow in ATTESTABLE_WORKFLOWS, f"{workflow!r} is not an attestable workflow")
    need(dispatch.get("github_actions") == "true", "not running inside GitHub Actions")
    need(
        dispatch.get("event_name") == REQUIRED_EVENT,
        f"event is {dispatch.get('event_name')!r}, not a manual {REQUIRED_EVENT}",
    )
    need(dispatch.get("ref") == REQUIRED_REF, f"ref is {dispatch.get('ref')!r}, not {REQUIRED_REF}")
    need(
        bool(repository)
        and workflow in ATTESTABLE_WORKFLOWS
        and dispatch.get("workflow_ref") == f"{repository}/{workflow}@{REQUIRED_REF}",
        f"workflow is {dispatch.get('workflow_ref')!r}, not {workflow} on {REQUIRED_REF}",
    )
    sha_is_canonical = isinstance(expected_sha, str) and bool(_COMMIT_SHA.match(expected_sha))
    need(
        sha_is_canonical,
        "expected_sha must be the full 40-character lowercase commit SHA of the reviewed commit",
    )
    need(
        sha_is_canonical and dispatch.get("sha") == expected_sha,
        f"the dispatched commit {dispatch.get('sha')!r} is not expected_sha",
    )
    need(
        sha_is_canonical and runtime.get("git_head") == expected_sha,
        f"the checked-out commit {runtime.get('git_head')!r} is not expected_sha",
    )
    need(
        runtime.get("tracked_tree_clean") is True,
        "tracked files differ from the checked-out commit",
    )
    need(
        runtime.get("python_implementation") == PINNED_PYTHON_IMPLEMENTATION
        and runtime.get("python_version") == PINNED_PYTHON_VERSION,
        f"interpreter is {runtime.get('python_implementation')} {runtime.get('python_version')}, "
        f"not {PINNED_PYTHON_IMPLEMENTATION} {PINNED_PYTHON_VERSION}",
    )
    installed = runtime.get("installed")
    installed = dict(installed) if isinstance(installed, Mapping) else {}
    mismatched = sorted(
        name for name, version in lock_pins.items() if installed.get(name) != version
    )
    # J1=B: not even the installer may sit beside the lock; the floating pip is removed unrun.
    unexpected = sorted(set(installed) - set(lock_pins))
    need(not mismatched, f"installed versions differ from the lock for {mismatched}")
    need(not unexpected, f"distributions outside the lock are installed: {unexpected}")
    need(bool(_DIGITS.match(str(dispatch.get("run_id", "")))), "run_id is not a GitHub run id")
    need(bool(_DIGITS.match(str(dispatch.get("run_attempt", "")))), "run_attempt is not a number")
    need(bool(_SHA256.match(str(runtime.get("lock_sha256", "")))), "the lock digest is missing")
    need(bool(_SHA256.match(str(runtime.get("pin_digest", "")))), "the pin digest is missing")
    need(
        runtime.get("interpreter_flags") == REQUIRED_FLAGS_TEXT,
        f"the evaluator did not start as `{runtime_isolation.ISOLATED_STARTUP}` "
        f"(flags [{runtime.get('interpreter_flags')}])",
    )
    need(
        bool(_SHA256.match(str(runtime.get("installed_files_sha256", "")))),
        "the installed files were not verified against their records",
    )

    if failures:
        raise ProvenanceRefused(
            "section 5A run refused before any database access: " + "; ".join(failures)
        )
    return {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "dispatch_verified": True,
        "event_name": str(dispatch["event_name"]),
        "repository": repository,
        "workflow_ref": str(dispatch["workflow_ref"]),
        "ref": str(dispatch["ref"]),
        "sha": str(dispatch["sha"]),
        "expected_sha": expected_sha,
        "git_head": str(runtime["git_head"]),
        "run_id": str(dispatch["run_id"]),
        "run_attempt": str(dispatch["run_attempt"]),
        "runner_os": str(dispatch.get("runner_os", "")),
        "runner_arch": str(dispatch.get("runner_arch", "")),
        "image_os": str(dispatch.get("image_os", "")),
        "image_version": str(dispatch.get("image_version", "")),
        "python_implementation": str(runtime["python_implementation"]),
        "python_version": str(runtime["python_version"]),
        "lock_path": EVALUATOR_LOCK,
        "lock_sha256": str(runtime["lock_sha256"]),
        "installed": {str(name): str(version) for name, version in sorted(installed.items())},
        "pin_digest": str(runtime["pin_digest"]),
        "interpreter_flags": str(runtime["interpreter_flags"]),
        "installed_files_sha256": str(runtime["installed_files_sha256"]),
    }


def attest(
    expected_sha: str,
    *,
    environ: Mapping[str, str],
    root: Path | None = None,
    isolation: runtime_isolation.IsolationReport | None = None,
    workflow: str = EVALUATION_WORKFLOW,
) -> dict[str, Any]:
    """Verify the pin, the dispatch and the runtime of THIS process. Touches no repository.

    ``isolation`` is the report of :func:`runtime_isolation.enter`, which must already have run in
    this process (owner ruling G1=A). Without it nothing is attested. ``workflow`` is the one
    workflow the dispatch must be (:data:`ATTESTABLE_WORKFLOWS`).
    """

    if isolation is None:
        raise IsolationRefused(
            "section 5A run refused before any database access: the process was not entered "
            f"through the isolated runtime (`{runtime_isolation.ISOLATED_STARTUP}` and "
            "runtime_isolation.enter)"
        )
    repository_root = (root or project_root()).resolve()
    assert_evaluator_pin(root=repository_root)
    return verify_run_provenance(
        observe_dispatch(environ),
        observe_runtime(repository_root, isolation),
        expected_sha=expected_sha,
        lock_pins=read_lock(repository_root),
        workflow=workflow,
    )


def require_verified_provenance(record: Any, *, root: Path | None = None) -> dict[str, Any]:
    """Fail closed unless ``record`` is a verified record consistent with the pinned artifacts.

    Used wherever a record is consumed rather than produced: before a claim, by the durable
    authority, and before recovery. It cannot re-observe the dispatch, so it checks the record's
    exact shape, its internal agreements, and that it names the pin and the lock this process
    runs under.
    """

    if not isinstance(record, Mapping):
        raise ProvenanceRefused(
            "no verified run provenance: the one look may be claimed or recovered only by a "
            "verified dispatch (owner ruling E2)"
        )
    keys = set(record)
    if keys != _RECORD_FIELDS:
        raise ProvenanceRefused(
            "run provenance has the wrong shape: "
            f"missing {sorted(_RECORD_FIELDS - keys)}, unexpected {sorted(keys - _RECORD_FIELDS)}"
        )
    for field in _RECORD_STRING_FIELDS:
        if not isinstance(record[field], str):
            raise ProvenanceRefused(f"run provenance field {field} is not a string")
    installed = record["installed"]
    if not isinstance(installed, Mapping) or not all(
        isinstance(name, str) and isinstance(version, str) for name, version in installed.items()
    ):
        raise ProvenanceRefused("run provenance field installed is not a name->version mapping")

    repository_root = (root or project_root()).resolve()
    lock_pins = read_lock(repository_root)
    failures: list[str] = []

    def need(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    need(record["schema_version"] == PROVENANCE_SCHEMA_VERSION, "unknown provenance schema")
    need(record["dispatch_verified"] is True, "the dispatch was not verified")
    need(record["event_name"] == REQUIRED_EVENT, "not a manual dispatch")
    need(record["ref"] == REQUIRED_REF, f"ref is not {REQUIRED_REF}")
    need(
        bool(record["repository"])
        and record["workflow_ref"]
        == f"{record['repository']}/{EVALUATION_WORKFLOW}@{REQUIRED_REF}",
        "not the evaluation workflow on main",
    )
    need(bool(_COMMIT_SHA.match(record["expected_sha"])), "expected_sha is not a full commit SHA")
    need(
        record["sha"] == record["expected_sha"] == record["git_head"],
        "the dispatched, expected and checked-out commits disagree",
    )
    need(
        record["python_implementation"] == PINNED_PYTHON_IMPLEMENTATION
        and record["python_version"] == PINNED_PYTHON_VERSION,
        "not the pinned interpreter",
    )
    need(record["lock_path"] == EVALUATOR_LOCK, "not the evaluator lock")
    need(record["lock_sha256"] == lock_sha256(repository_root), "not the lock this evaluator pins")
    need(
        record["pin_digest"] == str(current_pin_artifacts(repository_root)["closure_digest"]),
        "not the evaluator pin this process runs under",
    )
    need(
        all(installed.get(name) == version for name, version in lock_pins.items())
        and not set(installed) - set(lock_pins),
        "the recorded runtime is not the locked dependency set",
    )
    need(bool(_DIGITS.match(record["run_id"])), "run_id is not a GitHub run id")
    need(bool(_DIGITS.match(record["run_attempt"])), "run_attempt is not a number")
    need(record["interpreter_flags"] == REQUIRED_FLAGS_TEXT, "not an isolated start-up")
    need(
        bool(_SHA256.match(record["installed_files_sha256"])),
        "the installed files were not verified",
    )
    if failures:
        raise ProvenanceRefused("run provenance does not verify: " + "; ".join(failures))
    return {**dict(record), "installed": dict(installed)}


def _git(root: Path, *arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()
