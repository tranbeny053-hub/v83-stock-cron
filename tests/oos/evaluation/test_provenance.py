"""Dispatch provenance and runtime binding (owner rulings E2=A, E3=A). No dispatch, no database."""

from __future__ import annotations

import hashlib
import platform
import subprocess
from pathlib import Path

import pytest

from crypto_probability_engine.oos.evaluation import evaluator_pin, provenance
from crypto_probability_engine.utils import canonical_json
from tests.oos.evaluation.conftest import (
    SYNTHETIC_INSTALLED_FILES_SHA256,
    SYNTHETIC_SHA,
    synthetic_dispatch,
    synthetic_isolation,
    synthetic_runtime,
    verified_provenance,
)

LOCK_PINS = provenance.read_lock()


def _verify(dispatch=None, runtime=None, *, expected_sha=SYNTHETIC_SHA):
    return provenance.verify_run_provenance(
        dispatch if dispatch is not None else synthetic_dispatch(),
        runtime if runtime is not None else synthetic_runtime(),
        expected_sha=expected_sha,
        lock_pins=LOCK_PINS,
    )


# --------------------------------------------------------------------------- verification


def test_a_verified_dispatch_under_the_pinned_runtime_verifies() -> None:
    record = _verify()
    assert record["dispatch_verified"] is True
    assert record["expected_sha"] == record["sha"] == record["git_head"] == SYNTHETIC_SHA
    assert record["python_version"] == provenance.PINNED_PYTHON_VERSION
    assert record["lock_path"] == provenance.EVALUATOR_LOCK
    assert set(record["installed"]) >= set(LOCK_PINS)


@pytest.mark.parametrize(
    ("dispatch", "runtime", "expected_sha", "fragment"),
    [
        ({"github_actions": ""}, {}, SYNTHETIC_SHA, "not running inside GitHub Actions"),
        ({"event_name": "push"}, {}, SYNTHETIC_SHA, "not a manual workflow_dispatch"),
        ({"event_name": "schedule"}, {}, SYNTHETIC_SHA, "not a manual workflow_dispatch"),
        ({"ref": "refs/heads/feature"}, {}, SYNTHETIC_SHA, "not refs/heads/main"),
        ({"ref": "refs/tags/v1"}, {}, SYNTHETIC_SHA, "not refs/heads/main"),
        (
            {"workflow_ref": "synthetic/ucpe/.github/workflows/ci.yml@refs/heads/main"},
            {},
            SYNTHETIC_SHA,
            "not .github/workflows/section-5a-evaluation.yml",
        ),
        (
            {
                "workflow_ref": "synthetic/ucpe/.github/workflows/section-5a-evaluation.yml"
                "@refs/heads/feature"
            },
            {},
            SYNTHETIC_SHA,
            "not .github/workflows/section-5a-evaluation.yml",
        ),
        ({"repository": ""}, {}, SYNTHETIC_SHA, "section-5a-evaluation.yml"),
        ({}, {}, SYNTHETIC_SHA.upper(), "full 40-character lowercase"),
        ({}, {}, SYNTHETIC_SHA[:12], "full 40-character lowercase"),
        ({}, {}, "", "full 40-character lowercase"),
        ({"sha": "b" * 40}, {}, SYNTHETIC_SHA, "dispatched commit"),
        ({}, {"git_head": "b" * 40}, SYNTHETIC_SHA, "checked-out commit"),
        ({}, {"git_head": ""}, SYNTHETIC_SHA, "checked-out commit"),
        ({}, {"tracked_tree_clean": False}, SYNTHETIC_SHA, "tracked files differ"),
        ({}, {"tracked_tree_clean": None}, SYNTHETIC_SHA, "tracked files differ"),
        ({}, {"python_version": "3.13.13"}, SYNTHETIC_SHA, "interpreter"),
        ({}, {"python_version": "3.12.11"}, SYNTHETIC_SHA, "interpreter"),
        ({}, {"python_implementation": "PyPy"}, SYNTHETIC_SHA, "interpreter"),
        ({}, {"lock_sha256": ""}, SYNTHETIC_SHA, "lock digest"),
        ({}, {"pin_digest": ""}, SYNTHETIC_SHA, "pin digest"),
        ({"run_id": "abc"}, {}, SYNTHETIC_SHA, "run_id"),
        ({"run_attempt": ""}, {}, SYNTHETIC_SHA, "run_attempt"),
        # G1=A: an evaluator that did not start isolated, or whose installed files went unverified
        ({}, {"interpreter_flags": ""}, SYNTHETIC_SHA, "did not start as `python -I -S -B`"),
        (
            {},
            {"interpreter_flags": "isolated,ignore_environment,no_user_site,safe_path"},
            SYNTHETIC_SHA,
            "did not start as `python -I -S -B`",
        ),
        ({}, {"installed_files_sha256": ""}, SYNTHETIC_SHA, "not verified against their records"),
    ],
)
def test_every_unverified_fact_refuses(dispatch, runtime, expected_sha, fragment) -> None:
    refusal = "refused before any database access"
    with pytest.raises(provenance.ProvenanceRefused, match=refusal) as exc:
        _verify(
            synthetic_dispatch(**dispatch), synthetic_runtime(**runtime), expected_sha=expected_sha
        )
    assert fragment in str(exc.value)


@pytest.mark.parametrize(
    ("installed", "fragment"),
    [
        ({k: v for k, v in LOCK_PINS.items() if k != "psycopg-binary"}, "differ from the lock"),
        ({**LOCK_PINS, "pydantic": "2.12.0"}, "differ from the lock"),
        ({**LOCK_PINS, "pydantic": f"{LOCK_PINS['pydantic']}|2.12.0"}, "differ from the lock"),
        ({**LOCK_PINS, "numpy": "2.3.0"}, "outside the lock"),
        ({**LOCK_PINS, "crypto-probability-engine": "0.1"}, "outside the lock"),
    ],
)
def test_the_runtime_must_be_exactly_the_lock(installed, fragment) -> None:
    with pytest.raises(provenance.ProvenanceRefused) as exc:
        _verify(runtime=synthetic_runtime(installed=installed))
    assert fragment in str(exc.value)


def test_not_even_the_installer_may_sit_beside_the_lock() -> None:
    """J1=B: the runner's floating pip is deleted unrun; any installer left behind refuses."""

    for installer in ("pip", "setuptools", "wheel"):
        with pytest.raises(provenance.ProvenanceRefused, match="outside the lock"):
            _verify(runtime=synthetic_runtime(installed={**LOCK_PINS, installer: "1.0"}))


def test_every_failed_check_is_named_not_only_the_first() -> None:
    with pytest.raises(provenance.ProvenanceRefused) as exc:
        _verify(
            synthetic_dispatch(github_actions="", ref="refs/heads/feature"),
            synthetic_runtime(python_version="3.11.9", tracked_tree_clean=False),
            expected_sha="nope",
        )
    message = str(exc.value)
    for fragment in (
        "GitHub Actions",
        "refs/heads/main",
        "40-character",
        "interpreter",
        "tracked files",
    ):
        assert fragment in message, fragment


def test_the_record_is_plain_strings_so_the_sql_check_can_read_it() -> None:
    """Migration 0009 reads the record with ->>; a number tag would make that comparison fail."""

    record = _verify()
    for key, value in record.items():
        if key == "dispatch_verified":
            assert value is True
        elif key == "installed":
            assert all(isinstance(v, str) for v in value.values())
        else:
            assert isinstance(value, str), key
    assert b"$decimal" not in canonical_json.dumps(record)


# --------------------------------------------------------------------------- the lock


def _lock_root(tmp_path: Path, body: str) -> Path:
    (tmp_path / "ops").mkdir()
    (tmp_path / provenance.EVALUATOR_LOCK).write_text(body, encoding="utf-8")
    return tmp_path


HASH = "    --hash=sha256:" + "a" * 64


def test_the_committed_lock_pins_exact_versions_with_hashes() -> None:
    assert len(LOCK_PINS) == 19
    text = (evaluator_pin.project_root() / provenance.EVALUATOR_LOCK).read_text(encoding="utf-8")
    assert text.count("--hash=sha256:") >= len(LOCK_PINS)
    assert ">=" not in text and "~=" not in text and "<" not in text


@pytest.mark.parametrize(
    "body",
    [
        "pydantic>=2,<3 \\\n" + HASH + "\n",  # a range bounds nothing (V808-R5)
        "pydantic==2.13.4\n",  # unhashed
        "pydantic==2.13.4 \\\n" + HASH + "\npydantic==2.13.4 \\\n" + HASH + "\n",  # twice
        "pydantic==2.13.4 \\\n",  # incomplete
        "psycopg[binary]==3.3.4 \\\n" + HASH + "\n",  # extras are not a single distribution
        "pydantic==2.13.4 \\\n    --hash=md5:abc\n",  # not sha256
        "# only comments\n",  # pins nothing
        "-e .\n",  # anything unrecognized
    ],
)
def test_a_lock_that_is_not_exact_refuses(tmp_path: Path, body: str) -> None:
    with pytest.raises(provenance.ProvenanceRefused):
        provenance.read_lock(_lock_root(tmp_path, body))


def test_a_missing_lock_refuses(tmp_path: Path) -> None:
    with pytest.raises(provenance.ProvenanceRefused, match="missing"):
        provenance.read_lock(tmp_path)


def test_distribution_names_are_normalized() -> None:
    assert provenance.canonical_distribution_name("Pygments") == "pygments"
    assert provenance.canonical_distribution_name("typing_extensions") == "typing-extensions"
    assert provenance.canonical_distribution_name("zope.interface") == "zope-interface"


# --------------------------------------------------------------------------- observation


def test_dispatch_facts_come_from_the_variables_github_sets() -> None:
    facts = provenance.observe_dispatch(
        {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": SYNTHETIC_SHA,
            "GITHUB_RUN_ID": "42",
        }
    )
    assert facts["github_actions"] == "true" and facts["sha"] == SYNTHETIC_SHA
    assert facts["run_id"] == "42"
    assert facts["workflow_ref"] == "", "absent is empty, never assumed"
    assert facts["run_attempt"] == ""


def test_runtime_facts_are_this_process_and_this_checkout() -> None:
    root = evaluator_pin.project_root()
    facts = provenance.observe_runtime(root)
    assert facts["python_version"] == platform.python_version()
    assert facts["python_implementation"] == platform.python_implementation()
    lock_bytes = (root / provenance.EVALUATOR_LOCK).read_bytes()
    assert facts["lock_sha256"] == hashlib.sha256(lock_bytes).hexdigest()
    assert facts["pin_digest"] == evaluator_pin.current_pin_artifacts(root)["closure_digest"]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
    )
    if head.returncode == 0:
        assert facts["git_head"] == head.stdout.strip()
        assert isinstance(facts["tracked_tree_clean"], bool)


def test_runtime_facts_fail_closed_outside_a_checkout(tmp_path: Path) -> None:
    for relative in evaluator_pin.pinned_files():
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((evaluator_pin.project_root() / relative).read_bytes())
    facts = provenance.observe_runtime(tmp_path)
    assert facts["git_head"] == "" or facts["tracked_tree_clean"] is not True


# --------------------------------------------------------------------------- attest


def test_nothing_is_attested_outside_the_isolated_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """G1=A. Without runtime_isolation.enter's report, attestation refuses before anything else."""

    def _never(**_):
        raise AssertionError("the pin was checked before isolation was established")

    monkeypatch.setattr(provenance, "assert_evaluator_pin", _never)
    refusal = "not entered through the isolated runtime"
    with pytest.raises(provenance.IsolationRefused, match=refusal):
        provenance.attest(SYNTHETIC_SHA, environ={})


def test_attest_outside_github_actions_refuses(tmp_path: Path) -> None:
    with pytest.raises(provenance.ProvenanceRefused) as exc:
        provenance.attest(SYNTHETIC_SHA, environ={}, isolation=synthetic_isolation())
    assert "not running inside GitHub Actions" in str(exc.value)


def test_attest_verifies_the_pin_before_the_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    def _drift(**_):
        raise evaluator_pin.EvaluatorPinMismatch("simulated drift")

    monkeypatch.setattr(provenance, "assert_evaluator_pin", _drift)
    with pytest.raises(evaluator_pin.EvaluatorPinMismatch):
        provenance.attest(SYNTHETIC_SHA, environ={}, isolation=synthetic_isolation())


def test_attest_returns_the_verified_record_for_a_verified_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provenance, "observe_dispatch", lambda environ: synthetic_dispatch())
    monkeypatch.setattr(
        provenance, "observe_runtime", lambda root, isolation=None: synthetic_runtime()
    )
    record = provenance.attest(SYNTHETIC_SHA, environ={}, isolation=synthetic_isolation())
    assert record == verified_provenance()
    assert record["interpreter_flags"] == provenance.REQUIRED_FLAGS_TEXT


def test_runtime_facts_carry_the_live_flags_and_the_isolation_digest() -> None:
    facts = provenance.observe_runtime(evaluator_pin.project_root(), synthetic_isolation())
    from crypto_probability_engine import runtime_isolation

    assert facts["interpreter_flags"] == runtime_isolation.interpreter_flags()
    assert facts["installed_files_sha256"] == SYNTHETIC_INSTALLED_FILES_SHA256
    assert provenance.observe_runtime(evaluator_pin.project_root())["installed_files_sha256"] == ""


# --------------------------------------------------------------------------- consumed records


def test_a_verifier_record_is_accepted_where_records_are_consumed() -> None:
    record = verified_provenance()
    assert provenance.require_verified_provenance(record) == record


@pytest.mark.parametrize("record", [None, "verified", 1, ["dispatch_verified"]])
def test_no_record_is_refusal(record) -> None:
    with pytest.raises(provenance.ProvenanceRefused, match="no verified run provenance"):
        provenance.require_verified_provenance(record)


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"dispatch_verified": False}, "not verified"),
        ({"dispatch_verified": "true"}, "not verified"),
        ({"schema_version": "v0"}, "schema"),
        ({"event_name": "push"}, "manual dispatch"),
        ({"ref": "refs/heads/feature"}, "refs/heads/main"),
        ({"workflow_ref": "x/y/.github/workflows/ci.yml@refs/heads/main"}, "evaluation workflow"),
        ({"expected_sha": "A" * 40}, "full commit SHA"),
        ({"git_head": "b" * 40}, "disagree"),
        ({"sha": "b" * 40}, "disagree"),
        ({"python_version": "3.12.11"}, "pinned interpreter"),
        ({"lock_path": "requirements.txt"}, "evaluator lock"),
        ({"lock_sha256": "0" * 64}, "not the lock"),
        ({"pin_digest": "0" * 64}, "evaluator pin"),
        ({"installed": {"pydantic": "2.13.4"}}, "locked dependency set"),
        ({"run_id": "12a"}, "run_id"),
        ({"interpreter_flags": "isolated"}, "not an isolated start-up"),
        ({"installed_files_sha256": "not-a-digest"}, "installed files were not verified"),
    ],
)
def test_a_rewritten_record_is_refused(change, fragment) -> None:
    with pytest.raises(provenance.ProvenanceRefused) as exc:
        provenance.require_verified_provenance({**verified_provenance(), **change})
    assert fragment in str(exc.value)


# --------------------------------------------------------------------------- the seal migration run


def _seal_migration_dispatch() -> dict[str, str]:
    repository = synthetic_dispatch()["repository"]
    return synthetic_dispatch(
        workflow_ref=(
            f"{repository}/{provenance.SEAL_MIGRATION_WORKFLOW}@{provenance.REQUIRED_REF}"
        )
    )


def test_the_seal_migration_run_attests_only_as_its_own_workflow() -> None:
    """K2=A. The apply of 0009 runs under the same attestation, bound to its own workflow."""

    record = provenance.verify_run_provenance(
        _seal_migration_dispatch(),
        synthetic_runtime(),
        expected_sha=SYNTHETIC_SHA,
        lock_pins=LOCK_PINS,
        workflow=provenance.SEAL_MIGRATION_WORKFLOW,
    )
    assert record["workflow_ref"].endswith(
        f"/{provenance.SEAL_MIGRATION_WORKFLOW}@{provenance.REQUIRED_REF}"
    )
    with pytest.raises(provenance.ProvenanceRefused, match="section-5a-evaluation.yml on"):
        _verify(_seal_migration_dispatch())
    with pytest.raises(provenance.ProvenanceRefused, match="apply-seal-migration.yml on"):
        provenance.verify_run_provenance(
            synthetic_dispatch(),
            synthetic_runtime(),
            expected_sha=SYNTHETIC_SHA,
            lock_pins=LOCK_PINS,
            workflow=provenance.SEAL_MIGRATION_WORKFLOW,
        )


@pytest.mark.parametrize(
    "workflow", [".github/workflows/ci.yml", "", provenance.EVALUATION_WORKFLOW + " "]
)
def test_no_other_workflow_can_be_named_attestable(workflow: str) -> None:
    repository = synthetic_dispatch()["repository"]
    dispatch = synthetic_dispatch(workflow_ref=f"{repository}/{workflow}@{provenance.REQUIRED_REF}")
    with pytest.raises(provenance.ProvenanceRefused, match="is not an attestable workflow"):
        provenance.verify_run_provenance(
            dispatch,
            synthetic_runtime(),
            expected_sha=SYNTHETIC_SHA,
            lock_pins=LOCK_PINS,
            workflow=workflow,
        )


def test_a_seal_migration_record_can_never_claim_or_recover_the_look() -> None:
    """Where records are consumed, only the evaluation workflow is accepted."""

    record = provenance.verify_run_provenance(
        _seal_migration_dispatch(),
        synthetic_runtime(),
        expected_sha=SYNTHETIC_SHA,
        lock_pins=LOCK_PINS,
        workflow=provenance.SEAL_MIGRATION_WORKFLOW,
    )
    with pytest.raises(provenance.ProvenanceRefused, match="not the evaluation workflow on main"):
        provenance.require_verified_provenance(record)


def test_attest_passes_the_named_workflow_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provenance, "assert_evaluator_pin", lambda **_: None)
    monkeypatch.setattr(provenance, "observe_dispatch", lambda environ: _seal_migration_dispatch())
    monkeypatch.setattr(
        provenance, "observe_runtime", lambda root, isolation=None: synthetic_runtime()
    )
    record = provenance.attest(
        SYNTHETIC_SHA,
        environ={},
        isolation=synthetic_isolation(),
        workflow=provenance.SEAL_MIGRATION_WORKFLOW,
    )
    assert provenance.SEAL_MIGRATION_WORKFLOW in record["workflow_ref"]
    with pytest.raises(provenance.ProvenanceRefused, match="section-5a-evaluation.yml on"):
        provenance.attest(SYNTHETIC_SHA, environ={}, isolation=synthetic_isolation())


def test_a_record_of_the_wrong_shape_is_refused() -> None:
    record = verified_provenance()
    missing = {k: v for k, v in record.items() if k != "run_attempt"}
    with pytest.raises(provenance.ProvenanceRefused, match="wrong shape"):
        provenance.require_verified_provenance(missing)
    with pytest.raises(provenance.ProvenanceRefused, match="wrong shape"):
        provenance.require_verified_provenance({**record, "note": "extra"})
    with pytest.raises(provenance.ProvenanceRefused, match="not a string"):
        provenance.require_verified_provenance({**record, "run_id": 42})
    with pytest.raises(provenance.ProvenanceRefused, match="name->version"):
        provenance.require_verified_provenance({**record, "installed": ["pydantic"]})
