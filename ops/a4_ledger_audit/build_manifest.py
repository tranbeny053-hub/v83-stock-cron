"""Regenerate ops/a4_ledger_audit/MANIFEST.json, the package seal, after any package file changes.

Run: python ops/a4_ledger_audit/build_manifest.py. tests/automation/test_a4_ledger_audit.py fails
until the manifest and docs/automation/UOR_HANDOFF.md section 14 match the files.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "ops" / "a4_ledger_audit"
SEALED_FILES = ("a4_ledger_audit.sql", "a4_ledger_audit.py", "CARD.md")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest() -> dict:
    spec = importlib.util.spec_from_file_location("a4_runner", PACKAGE / "a4_ledger_audit.py")
    assert spec and spec.loader
    runner = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = runner
    spec.loader.exec_module(runner)
    migration = ROOT / "migrations" / "0013_automation_radar_ledger.sql"
    return {
        "artifact": runner.ARTIFACT,
        "purpose": (
            "Prove the one public.automation_radar_ledger row that records one UOR qualification"
            " request, so UOR can adjudicate A4. Read-only. Prepared, not run against production."
        ),
        "files": {
            f"ops/a4_ledger_audit/{name}": _sha256(PACKAGE / name) for name in SEALED_FILES
        },
        "ledger_schema": {
            "migration": "migrations/0013_automation_radar_ledger.sql",
            "sha256": _sha256(migration),
            "table": "public.automation_radar_ledger",
            "primary_key": ["credential_id", "client_request_id"],
        },
        "input_binding": {
            "primary_key": ["credential_id", "client_request_id"],
            "cross_checked_against_the_response": [
                "run_id", "build_info.release_id", "evidence_hash"
            ],
        },
        "output_keys": sorted(
            {*runner.SQL_COLUMNS, "artifact", "sql_sha256", "transaction_read_only"}
        ),
        "reasons": list(runner.REASONS),
        "upstream_release_identity": {
            "serving_release_id": "UCPE-PROD-E2-20261004-A",
            "serving_commit": "1caa8b08ebfc45b79a9b14d8217dad3b112cda8d",
            "route_introduced_by": "UCPE-PROD-F1-AUTOMATION-20261001-A",
            "route_introduced_at": "5a3ef022db10462675361e8d15aa8f4f572dc1aa",
            "route_unchanged_since": (
                "src/crypto_probability_engine/automation/, api/automation_endpoint.py,"
                " migration 0013 and both radar schemas are byte-identical from 5a3ef022 to"
                " 1caa8b08"
            ),
            "per_request": (
                "the ledger row's release_id and the response's build_info.release_id name the"
                " release that served each request; the audit takes the expected value from the"
                " response"
            ),
        },
    }


def main() -> None:
    path = PACKAGE / "MANIFEST.json"
    path.write_text(json.dumps(manifest(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
