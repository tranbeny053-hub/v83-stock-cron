"""The structure-first restore proof (governing plan §12.1 and §23 "Backup"; owner ruling DP-D=2).

    python scripts/restore_proof/prove.py --pg-bin <PostgreSQL 17.6 bin> --export <folder> \\
        --work <fresh folder> --report <report.json> \\
        --expect-sha256 schema.sql=<hex> --expect-sha256 roles.sql=<hex>

It takes the owner's two export files (docs/runbooks/RESTORE_PROOF_EXPORT.md), and:
1. refuses them unless they are the very files the owner exported (their two sha256 digests) and a
   schema-only, password-free export made by the card's commands (gate.py): nothing is restored
   from a refused export;
2. builds a scratch reference cluster from the migrations, exactly as every migration rehearsal
   does, and a second scratch cluster into which it restores the export as it is;
3. compares the two catalogs item by item (catalog.py) and writes one report: the export's manifest
   (names, sha256, bytes, versions), every restore error and every difference, classified;
4. stops both clusters and deletes their data. It reads no table row, takes no database URL and
   reaches no server but the two it made.

RESTORE_PROOF=PASS needs: the export passed the gate, the restore raised no error but the two
every such restore raises (the bootstrap superuser and the public schema already exist) and a
platform role's own setting, and no app difference. Operational and platform differences are
reported, not failing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import psycopg

if __package__ in {None, ""}:  # run as a script: make the repository root importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.restore_proof import catalog, gate, scratch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "ucpe.restore_proof.v1"
REFERENCE_DATABASE = "reference"
RESTORED_DATABASE = "restored"
_ALTER_ROLE = re.compile(r"^ALTER ROLE (\S+) WITH (.*);$")


def run(
    pg_bin: Path,
    export: Path,
    work: Path,
    *,
    restored_owner: str = scratch.MIGRATION_OWNER,
    bootstrap: str = scratch.BOOTSTRAP_SUPERUSER,
    root: Path = ROOT,
    reference: dict[str, Any] | None = None,
    expected_sha256: dict[str, str] | None = None,
) -> dict[str, Any]:
    """The whole proof for one export, as a report (a dict); nothing outside ``work`` is written.
    ``reference`` is the migrations' fingerprint, when the caller has already built it, and
    ``expected_sha256`` the owner's digests of the two files, which must match exactly."""

    checked = gate.check_export(export)
    actual_sha256 = {item.name: item.sha256 for item in checked.files}
    for name in ("schema.sql", "roles.sql"):
        if expected_sha256 is not None and expected_sha256.get(name) != actual_sha256.get(name):
            checked.refusals.append(gate.Refusal(name, None, "DIGEST_MISMATCH"))
    if checked.passed and not keeps_superuser(export / "roles.sql", bootstrap):
        checked.refusals.append(gate.Refusal("roles.sql", None, "BOOTSTRAP_SUPERUSER_NOT_KEPT"))
    if checked.passed and bootstrap == restored_owner:
        checked.refusals.append(gate.Refusal("roles.sql", None, "BOOTSTRAP_IS_THE_OWNER"))
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "digests_checked": expected_sha256 is not None,
        "bootstrap_superuser": bootstrap,
        "restored_owner": restored_owner,
        "export": [asdict(item) for item in checked.files],
        "gate_refusals": [asdict(item) for item in checked.refusals],
    }
    if not checked.passed:
        return {**report, "verdict": "REFUSED_EXPORT"}
    roles = catalog.migration_roles(root / "migrations")
    expected_errors = {
        ("roles.sql", f'role "{bootstrap}" already exists'),
        ("schema.sql", 'schema "public" already exists'),
    }
    work.mkdir(parents=True, exist_ok=False)
    expected = reference
    if expected is None:
        expected = reference_fingerprint(pg_bin, work, bootstrap=bootstrap, root=root)
    restored = scratch.start(pg_bin, work, "restored", superuser=bootstrap)
    try:
        errors = scratch.restore(restored, export, RESTORED_DATABASE)
        actual = _fingerprint(restored, RESTORED_DATABASE, restored_owner, roles)
    finally:
        scratch.stop(restored)
    statements = _role_statements(export / "roles.sql")
    classified = [_classify_error(error, statements, roles, expected_errors) for error in errors]
    differences = catalog.compare(expected, actual)
    failing = [item for item in classified if item["category"] == "fail"]
    app = [item for item in differences if item.category == "app"]
    return {
        **report,
        "migration_roles": sorted(roles),
        "restore_errors": classified,
        "differences": [asdict(item) for item in differences],
        "function_text_differences": catalog.function_diff(expected, actual),
        "counts": {
            "relations": len(actual["relations"]),
            "functions": len(actual["functions"]),
            "triggers": sum(len(items) for items in actual["triggers"].values()),
            "policies": sum(len(items) for items in actual["policies"].values()),
            "differences": {
                category: sum(item.category == category for item in differences)
                for category in ("app", "operational", "platform")
            },
        },
        "verdict": "PASS" if not failing and not app else "FAIL",
    }


def reference_fingerprint(
    pg_bin: Path, work: Path, *, bootstrap: str = scratch.BOOTSTRAP_SUPERUSER, root: Path = ROOT
) -> dict[str, Any]:
    """The structure the migrations declare, read from a scratch cluster built from them."""

    roles = catalog.migration_roles(root / "migrations")
    reference = scratch.start(pg_bin, work, "reference", superuser=bootstrap)
    try:
        scratch.build_from_migrations(reference, root, REFERENCE_DATABASE)
        return _fingerprint(reference, REFERENCE_DATABASE, scratch.MIGRATION_OWNER, roles)
    finally:
        scratch.stop(reference)


def _fingerprint(
    cluster: scratch.Cluster, database: str, owner: str, roles: frozenset[str]
) -> dict[str, Any]:
    with psycopg.connect(cluster.url(database), autocommit=True) as conn:
        return catalog.fingerprint(conn, owner=owner, roles=roles)


def keeps_superuser(roles_dump: Path, name: str) -> bool:
    """The export's own ALTER ROLE for the bootstrap name keeps it SUPERUSER (and nothing else
    alters it), so restoring the dump cannot take superuser from the role running the restore."""

    attributes = [
        match.group(2).split()
        for line in roles_dump.read_text(encoding="utf-8").split("\n")
        if (match := _ALTER_ROLE.match(line)) and match.group(1).strip('"') == name
    ]
    return len(attributes) == 1 and "SUPERUSER" in attributes[0]


def _role_statements(path: Path) -> dict[int, tuple[str, ...]]:
    statements, _ = gate.scan(path.read_text(encoding="utf-8"))
    return dict(statements)


def _classify_error(
    error: scratch.RestoreError,
    role_statements: dict[int, tuple[str, ...]],
    roles: frozenset[str],
    expected: set[tuple[str, str]],
) -> dict[str, Any]:
    item = asdict(error)
    if (error.file, error.message) in expected:
        return {**item, "category": "expected"}
    lead = role_statements.get(error.line, ()) if error.file == "roles.sql" else ()
    # A platform role's own setting (ALTER ROLE r SET / IN DATABASE): never a migration role's.
    if (
        lead[:2] == ("ALTER", "ROLE")
        and len(lead) == 4
        and lead[3] in {"SET", "IN"}
        and lead[2].lower() not in roles
    ):
        return {**item, "category": "platform"}
    return {**item, "category": "fail"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--pg-bin", type=Path, required=True)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--restored-owner", default=scratch.MIGRATION_OWNER)
    parser.add_argument("--bootstrap-superuser", default=scratch.BOOTSTRAP_SUPERUSER)
    parser.add_argument(
        "--expect-sha256",
        action="append",
        required=True,
        metavar="NAME=HEX",
        help="the owner's digest of schema.sql and of roles.sql (step 5 of the card)",
    )
    args = parser.parse_args(argv)
    expected = dict(item.split("=", 1) for item in args.expect_sha256 if "=" in item)
    if set(expected) != {"schema.sql", "roles.sql"}:
        print("REFUSED: give --expect-sha256 for schema.sql and roles.sql", file=sys.stderr)
        return 2
    if args.work.exists():
        print(f"REFUSED: {args.work} exists; give a fresh work folder", file=sys.stderr)
        return 2
    report = run(
        args.pg_bin,
        args.export,
        args.work,
        restored_owner=args.restored_owner,
        bootstrap=args.bootstrap_superuser,
        expected_sha256=expected,
    )
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
    counts = report.get("counts", {}).get("differences", {})
    print(
        f"RESTORE_PROOF={report['verdict']} refusals={len(report['gate_refusals'])} "
        f"restore_errors={len(report.get('restore_errors', []))} "
        f"app={counts.get('app', 0)} operational={counts.get('operational', 0)} "
        f"platform={counts.get('platform', 0)}"
    )
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
