"""Regenerate ops/a4_card04_companion/MANIFEST.json, the package seal, after any package file
changes.

Run: python -B ops/a4_card04_companion/build_manifest.py. It loads the runner from its source and
writes no bytecode, because the package folder must hold exactly its five files.
tests/automation/test_a4_card04_companion.py fails until the manifest matches the files, and
tests/automation/test_handoff_manifest.py until docs/automation/UOR_HANDOFF.md section 15 carries
their digests.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "ops" / "a4_card04_companion"
SEALED_FILES = ("a4_card04_companion.sql", "a4_card04_companion.py", "CARD.md", "build_manifest.py")
SCHEMA_SOURCES = (
    "migrations/0003_prediction_ledger.sql",
    "migrations/0013_automation_radar_ledger.sql",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runner() -> Any:
    """The runner, executed from its source: no bytecode is written into the package folder."""

    path = PACKAGE / "a4_card04_companion.py"
    spec = importlib.util.spec_from_file_location("a4c_runner", path)
    assert spec
    runner = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = runner
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), runner.__dict__)  # noqa: S102
    return runner


def manifest() -> dict:
    runner = _runner()
    return {
        "artifact": runner.ARTIFACT,
        "purpose": (
            "Prove the five durable facts UOR Card 04 needs for one qualification request: its"
            " deadline_ms and its run's analysis_hash from its public.automation_radar_ledger row,"
            " the count of public.predictions rows carrying its run_id, the count of its"
            " credential's ledger rows since the qualification's activation, and the count of"
            " ledger rows carrying its client_request_id under any credential. Read-only. Prepared,"
            " not run against production."
        ),
        "companion_of": {
            "artifact": "ucpe.a4_ledger_audit.v1",
            "artifact_sha256": "2007fa28a52048e13c1cadbc8e7d5c67fd317dcb9d3bb9e57d1a581a728b6577",
            "source_commit": "e468f1f118870f904d90505a3cdbb74446d5a495",
        },
        "files": {
            f"ops/a4_card04_companion/{name}": _sha256(PACKAGE / name) for name in SEALED_FILES
        },
        "package_files": sorted(runner.PACKAGE_FILES),
        "invocation": runner.INVOCATION,
        "reads": {
            "public.automation_radar_ledger": [
                "analysis_hash",
                "client_request_id",
                "credential_id",
                "deadline_ms",
                "evidence_origin",
                "http_status",
                "outcome_code",
                "received_at_utc",
                "run_id",
                "state",
            ],
            "public.predictions": ["run_id"],
            "pg_catalog": [
                "pg_attribute",
                "pg_class",
                "pg_constraint",
                "pg_inherits",
                "pg_namespace",
            ],
        },
        "schema_sources": {path: _sha256(ROOT / path) for path in SCHEMA_SOURCES},
        "input_binding": {
            "primary_key": ["credential_id", "client_request_id"],
            "from_the_response": ["run_id", "analysis_hash"],
            "from_the_request": ["deadline_ms"],
            "count_window_from": "qualification_activation_utc (inclusive)",
        },
        "counts": {
            "predictions_rows_for_run_id": "public.predictions rows carrying the bound run_id",
            "credential_ledger_rows_since_activation": (
                "ledger rows of the bound credential received at or after"
                " qualification_activation_utc, whatever their client_request_id"
            ),
            "ledger_rows_for_client_request_id_across_all_credentials": (
                "ledger rows carrying the bound client_request_id, under any credential and"
                " whenever received; no credential is named"
            ),
        },
        "output_keys": sorted(
            {
                *runner.SQL_COLUMNS,
                "artifact_sha256",
                "bound_qualification_activation_utc",
                "row_security_off",
                "sql_sha256",
                "transaction_read_only",
            }
        ),
        "reasons": list(runner.REASONS),
        "upstream_release_identity": {
            "serving_release_id": "UCPE-PROD-E2-20261004-A",
            "serving_commit": "1caa8b08ebfc45b79a9b14d8217dad3b112cda8d",
            "route_introduced_by": "UCPE-PROD-F1-AUTOMATION-20261001-A",
            "route_introduced_at": "5a3ef022db10462675361e8d15aa8f4f572dc1aa",
            "route_unchanged_since": (
                "src/crypto_probability_engine/automation/,"
                " src/crypto_probability_engine/api/automation_endpoint.py, migration 0013 and both"
                " radar schemas are byte-identical from 5a3ef022 to 1caa8b08"
            ),
            "per_request": (
                "the ledger row's release_id and the response's build_info.release_id name the"
                " release that served each request; the accepted A4 audit proves them"
            ),
        },
    }


def main() -> None:
    path = PACKAGE / "MANIFEST.json"
    path.write_text(json.dumps(manifest(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
