"""Scratch-PostgreSQL rehearsal of ucpe.a4_card04_companion.v1 (no secret, no real database).

Runs ONLY against the scratch local PostgreSQL 17.6 that run_scratch.sh builds from every applied
migration, locally or on a CI runner. It inserts synthetic ledger and prediction rows and alters the
scratch tables to rehearse schema drift, so it refuses any URL that is not a local socket database
named a4_companion_rehearsal.

What it proves, each as a case with expected and actual results:
- the sealed companion, through its real command line and psycopg, PASSES each qualifying row
  with the exact facts: the row's deadline_ms and analysis_hash, the count of prediction rows
  carrying the run id (0, or 2 for a run that synthetic rows carry), and the credential's ledger
  rows from the activation instant on (inclusive: a row received at that instant counts);
- it fails closed with the right reason on every other shape: no row, another credential, in
  progress, a refusal, a run, deadline or analysis hash that differs, an activation after the row;
- the binding is the PAIR: the same client_request_id under another credential is another row, and
  a variant bound on client_request_id alone finds two rows (AMBIGUOUS);
- the cross-credential count (owner ruling A4-CRID-UNIQUENESS) is 0 for an unsent id, 1 for an id
  one row carries and 2 for an id two credentials carry, whatever the pair binds; when a third
  credential reuses a bound row's id, that count alone moves, and when the activation moves, the
  credential count alone moves: the two ledger counts are separate facts;
- the card's exact command, python -I -B, PASSES with the same line as the in-process run and
  leaves the package folder exactly as sealed; any other start is refused; a copy of the folder with
  one more module is refused, and that module never runs under -I (without -I it would: shown with a
  harmless marker);
- least privilege: as a role that can read only the eleven columns (and bypasses row security), the
  companion PASSES with the owner's facts, and that role is refused every other column and table;
- row security: a reader that row-level security applies to is refused (with or without a permissive
  policy), never counted; a variant without the runner's row-security preamble shows the silent zero
  this prevents;
- read-only: under the runner's own preamble every write kind is refused (INSERT, UPDATE, DELETE,
  MERGE, CREATE, ALTER, DROP, TRUNCATE) and the database is unchanged, rows and catalog;
- schema drift fails closed: a changed type, a nullable run_id, a view in place of predictions, an
  inheritance child of either table, a missing primary key; a renamed table is a database error;
  an extra column the companion does not read is not drift.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import psycopg

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "ops" / "a4_card04_companion"
EXAMPLE = ROOT / "docs/automation/examples/radar_evidence.v1.synthetic-btc-4h-gate-blocked.json"
ERROR_EXAMPLE = (
    ROOT / "docs/automation/examples/radar_evidence_error.v1.synthetic-quota-exceeded.json"
)
DATABASE = "a4_companion_rehearsal"
CRED_A = "a4c-rehearsal-uor"
CRED_B = "a4c-rehearsal-other"
CRED_C = "a4c-rehearsal-third"
CROSS = "ledger_rows_for_client_request_id_across_all_credentials"
PROBE, POLICY_READER, HIDDEN_READER = "a4c_probe", "a4c_policy_reader", "a4c_hidden_reader"
NAMESPACE = uuid.UUID("2b0b1c9e-7d61-4c3e-9a55-4c2f0e6d8a17")
ACTIVATION = "2026-10-05T00:00:00Z"
LEDGER_READ = (
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
)
SENTINEL = "public.a4c_rehearsal_sentinel"


def load_runner() -> Any:
    """The runner, executed from its source: no bytecode is written into the package folder, which
    must hold exactly its five files."""

    path = PACKAGE / "a4_card04_companion.py"
    spec = importlib.util.spec_from_file_location("a4c_companion_runner", path)
    assert spec
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), module.__dict__)  # noqa: S102
    return module


runner = load_runner()


def refuse_non_scratch(url: str) -> None:
    parsed = urlparse(url)
    host = parse_qs(parsed.query).get("host", [""])[0]
    if parsed.hostname or not host.startswith("/") or parsed.path.lstrip("/") != DATABASE:
        raise SystemExit(f"REFUSED: only the local scratch database {DATABASE}")


def rid(name: str) -> str:
    return str(uuid.uuid5(NAMESPACE, name))


def hexed(char: str, prefix: str, size: int) -> str:
    return prefix + char * size


class Rehearsal:
    def __init__(self, url: str) -> None:
        self.url = url
        self.cases: list[dict[str, Any]] = []
        self.example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        self.release = self.example["build_info"]["release_id"]
        self.rows: dict[str, dict[str, Any]] = {}

    # ---------------------------------------------------------------- fixtures
    def owner(self) -> psycopg.Connection:
        return psycopg.connect(self.url, autocommit=True)

    def success(
        self,
        name: str,
        *,
        credential_id: str,
        received: str,
        char: str,
        deadline_ms: int = 30000,
        client_request_id: str | None = None,
    ) -> None:
        crid = client_request_id or rid(name)
        body = copy.deepcopy(self.example)
        body.update(
            client_request_id=crid,
            run_id=hexed(char, "run_", 32),
            analysis_hash=hexed(char, "sha256:", 64),
            evidence_hash=hexed(char, "sha256:", 63) + "0",
        )
        self._insert(
            credential_id=credential_id,
            client_request_id=crid,
            received=received,
            state="COMPLETED",
            outcome="SUCCEEDED",
            status=200,
            body=body,
            deadline_ms=deadline_ms,
        )
        self.rows[name] = {
            "credential_id": credential_id,
            "client_request_id": crid,
            "run_id": body["run_id"],
            "deadline_ms": str(deadline_ms),
            "analysis_hash": body["analysis_hash"],
            "received": received,
        }

    def _insert(
        self,
        *,
        credential_id: str,
        client_request_id: str,
        received: str,
        state: str,
        outcome: str | None,
        status: int | None,
        body: dict[str, Any] | None,
        deadline_ms: int = 30000,
    ) -> None:
        succeeded = outcome == "SUCCEEDED"
        with self.owner() as conn:
            conn.execute(
                """
                INSERT INTO public.automation_radar_ledger
                       (credential_id, client_request_id, request_fingerprint, state,
                        outcome_code, http_status, response_body, run_id, analysis_hash,
                        evidence_hash, release_id, deadline_ms, received_at_utc,
                        completed_at_utc)
                VALUES (%s, %s::uuid, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s,
                        %s::timestamptz,
                        CASE WHEN %s = 'COMPLETED'
                             THEN %s::timestamptz + interval '1 minute' END)
                """,
                (
                    credential_id,
                    client_request_id,
                    hexed("1", "sha256:", 64),
                    state,
                    outcome,
                    status,
                    json.dumps(body) if body is not None else None,
                    body["run_id"] if succeeded and body else None,
                    body["analysis_hash"] if succeeded and body else None,
                    body["evidence_hash"] if succeeded and body else None,
                    self.release,
                    deadline_ms,
                    received,
                    state,
                    received,
                ),
            )

    def prediction(self, prediction_id: str, run_id: str) -> None:
        """A synthetic predictions row (scratch only), outside any protected window."""

        with self.owner() as conn:
            conn.execute(
                """
                INSERT INTO public.predictions
                       (prediction_id, run_id, symbol, normalized_symbol, timeframe,
                        horizon_bars, predicted_at_utc, reference_close_utc, reference_price,
                        horizon_end_utc, p_up_frac, p_down_frac, p_timeout_frac, model_version,
                        methodology_version, calibration_status, reliability_status)
                VALUES (%s, %s, 'BTCUSDT', 'BTCUSDT', '4H', 6, '2026-10-04T00:00:05Z',
                        '2026-10-04T00:00:00Z', 100, '2026-10-05T00:00:00Z', 0.3, 0.3, 0.4,
                        'a4c-rehearsal', 'a4c-rehearsal', 'UNCALIBRATED', 'UNKNOWN')
                """,
                (prediction_id, run_id),
            )

    def seed(self) -> None:
        self.success(
            "before activation", credential_id=CRED_A, received="2026-10-04T23:00:00Z", char="b"
        )
        self.success("at activation", credential_id=CRED_A, received=ACTIVATION, char="c")
        self.success(
            "qualifying",
            credential_id=CRED_A,
            received="2026-10-05T00:10:00Z",
            char="a",
            deadline_ms=45000,
        )
        self._insert(
            credential_id=CRED_A,
            client_request_id=rid("in progress"),
            received="2026-10-05T00:20:00Z",
            state="IN_PROGRESS",
            outcome=None,
            status=None,
            body=None,
        )
        self._insert(
            credential_id=CRED_A,
            client_request_id=rid("refused"),
            received="2026-10-05T00:30:00Z",
            state="COMPLETED",
            outcome="QUOTA_EXCEEDED",
            status=429,
            body=json.loads(ERROR_EXAMPLE.read_text(encoding="utf-8")),
        )
        self.success("leaked run", credential_id=CRED_A, received="2026-10-05T00:40:00Z", char="e")
        self.success(
            "other credential",
            credential_id=CRED_B,
            received="2026-10-05T00:15:00Z",
            char="f",
            client_request_id=self.rows["qualifying"]["client_request_id"],
        )
        self.success(
            "other credential later",
            credential_id=CRED_B,
            received="2026-10-05T00:50:00Z",
            char="9",
        )
        for number in (1, 2):
            self.prediction(f"a4c-leak-{number}", self.rows["leaked run"]["run_id"])
        self.prediction("a4c-unrelated", hexed("7", "run_", 32))
        with self.owner() as conn:
            conn.execute(f"CREATE TABLE {SENTINEL} (x integer)")
            conn.execute(f"INSERT INTO {SENTINEL} VALUES (1)")

    def digest(self) -> str:
        """The scratch database's state: every row of the two tables and the sentinel, and the
        public catalog's relations and columns. MISSING while a drift stage renames a table."""

        with self.owner() as conn:
            try:
                rows = conn.execute(
                    "SELECT md5(concat_ws('|',"
                    " (SELECT string_agg(row_to_json(l)::text, '/' ORDER BY l.credential_id,"
                    "  l.client_request_id) FROM public.automation_radar_ledger AS l),"
                    " (SELECT string_agg(row_to_json(p)::text, '/' ORDER BY p.prediction_id)"
                    "  FROM public.predictions AS p),"
                    f" (SELECT string_agg(s.x::text, '/' ORDER BY s.x) FROM {SENTINEL} AS s),"
                    " (SELECT string_agg(c.relname::text || '.' || a.attname::text || ':'"
                    "  || pg_catalog.format_type(a.atttypid, a.atttypmod)"
                    "  || ':' || c.relkind::text,"
                    "  '/' ORDER BY c.relname, a.attnum)"
                    "  FROM pg_catalog.pg_class AS c"
                    "  JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace"
                    "  JOIN pg_catalog.pg_attribute AS a ON a.attrelid = c.oid"
                    "  WHERE n.nspname = 'public' AND a.attnum > 0 AND NOT a.attisdropped)))"
                ).fetchone()
            except psycopg.errors.UndefinedTable:
                return "MISSING"
        return rows[0]

    # ---------------------------------------------------------------- one audit
    def audit(
        self, binding: dict[str, str], connect: Callable[..., Any] | None = None
    ) -> tuple[int, dict[str, Any]]:
        out = io.StringIO()
        code = runner.main(
            [
                "--credential-id",
                binding["credential_id"],
                "--client-request-id",
                binding["client_request_id"],
                "--run-id",
                binding["run_id"],
                "--deadline-ms",
                binding["deadline_ms"],
                "--analysis-hash",
                binding["analysis_hash"],
                "--qualification-activation-utc",
                binding["activation"],
            ],
            environ={runner.DATABASE_URL_ENV: self.url},
            connect=connect,
            stdout=out,
        )
        return code, json.loads(out.getvalue())

    def binding(self, name: str, **changes: str) -> dict[str, str]:
        row = self.rows[name]
        binding = {
            key: row[key]
            for key in (
                "credential_id",
                "client_request_id",
                "run_id",
                "deadline_ms",
                "analysis_hash",
            )
        }
        binding["activation"] = ACTIVATION
        binding.update(changes)
        return binding

    def case(
        self,
        name: str,
        binding: dict[str, str],
        expected_reason: str,
        expected_exit: int,
        facts: dict[str, Any] | None = None,
        connect: Callable[..., Any] | None = None,
    ) -> dict[str, Any]:
        before = self.digest()
        code, payload = self.audit(binding, connect)
        after = self.digest()
        wrong = {
            key: payload.get(key)
            for key, value in (facts or {}).items()
            if payload.get(key) != value
        }
        result = {
            "case": name,
            "expected_reason": expected_reason,
            "reason": payload.get("reason"),
            "expected_exit": expected_exit,
            "exit": code,
            "error_class": payload.get("error_class"),
            "facts_ok": not wrong,
            "wrong_facts": wrong,
            "database_unchanged": before == after,
            "ok": payload.get("reason") == expected_reason
            and code == expected_exit
            and not wrong
            and before == after,
        }
        self.cases.append(result)
        return payload

    def variant_case(
        self, name: str, sql: str, binding: dict[str, str], expected_reason: str
    ) -> None:
        facts = runner.run_sealed_audit(
            self.url,
            runner.validate(
                binding["credential_id"],
                binding["client_request_id"],
                binding["run_id"],
                binding["deadline_ms"],
                binding["analysis_hash"],
                binding["activation"],
            ),
            sql,
            connect=psycopg.connect,
        )
        self.cases.append(
            {
                "case": name,
                "expected_reason": expected_reason,
                "reason": facts["reason"],
                "ok": facts["reason"] == expected_reason,
            }
        )

    def variant(self, old: str, new: str) -> str:
        sealed = runner.SQL_PATH.read_text(encoding="utf-8")
        assert sealed.count(old) == 1, old
        return sealed.replace(old, new)

    @staticmethod
    def as_role(role: str) -> Callable[..., Any]:
        def connect(url: str, **kwargs: Any) -> psycopg.Connection:
            conn = psycopg.connect(url, **{**kwargs, "autocommit": True})
            conn.execute(f"SET ROLE {role}")
            conn.autocommit = False
            return conn

        return connect

    # ---------------------------------------------------------------- the cases
    def run(self) -> dict[str, Any]:
        self.seed()
        self.reused_request_id()
        start = self.digest()
        qualifying = {
            "deadline_ms": 45000,
            "analysis_hash": self.rows["qualifying"]["analysis_hash"],
            "deadline_ms_matches": True,
            "analysis_hash_matches": True,
            "predictions_rows_for_run_id": 0,
            "credential_ledger_rows_since_activation": 5,
            CROSS: 2,  # the other credential's row carries the same client_request_id
        }
        owner_pass = self.case("qualifying row", self.binding("qualifying"), "OK", 0, qualifying)
        at_receipt = self.case(
            "activation at the request's own receipt: the window is inclusive",
            self.binding("qualifying", activation="2026-10-05T00:10:00Z"),
            "OK",
            0,
            {**qualifying, "credential_ledger_rows_since_activation": 4},
        )
        moved = sorted(key for key in owner_pass if owner_pass.get(key) != at_receipt.get(key))
        self.cases.append(
            {
                "case": "the activation moves only the credential count and its own echo",
                "expected_reason": [
                    "bound_qualification_activation_utc",
                    "credential_ledger_rows_since_activation",
                ],
                "reason": moved,
                "ok": moved
                == [
                    "bound_qualification_activation_utc",
                    "credential_ledger_rows_since_activation",
                ],
            }
        )
        self.case(
            "an earlier activation counts the earlier row too",
            self.binding("qualifying", activation="2026-10-04T22:00:00Z"),
            "OK",
            0,
            {**qualifying, "credential_ledger_rows_since_activation": 6},
        )
        self.case(
            "a row received exactly at the activation instant",
            self.binding("at activation"),
            "OK",
            0,
            {"deadline_ms": 30000, "credential_ledger_rows_since_activation": 5, CROSS: 1},
        )
        self.case(
            "an activation one microsecond after the request",
            self.binding("at activation", activation="2026-10-05T00:00:00.000001Z"),
            "ACTIVATION_AFTER_REQUEST",
            1,
        )
        self.case(
            "activation after the request",
            self.binding("qualifying", activation="2026-10-05T00:10:00.000001Z"),
            "ACTIVATION_AFTER_REQUEST",
            1,
        )
        self.case(
            "a run that synthetic prediction rows carry is counted, not judged",
            self.binding("leaked run"),
            "OK",
            0,
            {"predictions_rows_for_run_id": 2, CROSS: 2},
        )
        self.case(
            "same request id, other credential: its own row and its own count",
            self.binding("other credential"),
            "OK",
            0,
            {
                "predictions_rows_for_run_id": 0,
                "credential_ledger_rows_since_activation": 2,
                CROSS: 2,
            },
        )
        self.case(
            "the other credential's run is not this row's",
            self.binding("qualifying", run_id=self.rows["other credential"]["run_id"]),
            "RUN_MISMATCH",
            1,
        )
        self.case(
            "unknown request id",
            self.binding("qualifying", client_request_id=rid("never sent")),
            "NO_ROW",
            1,
            {"deadline_ms": None, "analysis_hash": None, CROSS: 0},
        )
        self.case(
            "unknown credential",
            self.binding("qualifying", credential_id="a4c-never-issued"),
            "NO_ROW",
            1,
            # No row for the pair, yet two rows carry the id: the count does not follow the pair.
            {"credential_ledger_rows_since_activation": 0, CROSS: 2},
        )
        self.case(
            "in progress",
            self.binding("qualifying", client_request_id=rid("in progress")),
            "NOT_COMPLETED",
            1,
            {"analysis_hash": None, CROSS: 1},
        )
        self.case(
            "a refusal",
            self.binding("qualifying", client_request_id=rid("refused")),
            "NOT_SUCCEEDED",
            1,
            {"analysis_hash": None},
        )
        self.case(
            "deadline differs",
            self.binding("qualifying", deadline_ms="30000"),
            "DEADLINE_MISMATCH",
            1,
            {"deadline_ms": 45000, "deadline_ms_matches": False},
        )
        self.case(
            "analysis hash differs",
            self.binding("qualifying", analysis_hash=hexed("d", "sha256:", 64)),
            "ANALYSIS_HASH_MISMATCH",
            1,
            {"analysis_hash_matches": False},
        )
        self.variant_case(
            "client_request_id alone is ambiguous",
            self.variant(
                "        ON l.credential_id = b.credential_id\n       AND l.client_request_id",
                "        ON l.client_request_id",
            ),
            self.binding("qualifying"),
            "AMBIGUOUS",
        )
        least_privilege = self.least_privilege(owner_pass)
        command_line = self.isolated_command_line(owner_pass)
        row_security = self.row_security()
        read_only = self.read_only()
        end = self.drift()
        with self.owner() as conn:
            server_version = conn.execute("SHOW server_version").fetchone()[0]
        report = {
            "artifact": runner.ARTIFACT,
            "sql_sha256": runner.SQL_SHA256,
            "artifact_sha256": owner_pass.get("artifact_sha256"),
            "server_version": server_version,
            "cases": self.cases,
            "least_privilege": least_privilege,
            "isolated_command_line": command_line,
            "row_security": row_security,
            "read_only": read_only,
            "database_restored": start == end,
        }
        report["all_ok"] = (
            all(case["ok"] for case in self.cases)
            and least_privilege["ok"]
            and command_line["ok"]
            and row_security["ok"]
            and read_only["ok"]
            and report["database_restored"]
            and server_version.split()[0] == "17.6"
        )
        return report

    def reused_request_id(self) -> None:
        """A third credential reuses a bound row's client_request_id: the bound row stays unique
        under the pair, every fact stays as it was, and only the cross-credential count moves."""

        binding = self.binding("leaked run")
        before = self.case("one row carries the request id", binding, "OK", 0, {CROSS: 1})
        self.success(
            "leaked run, reused by a third credential",
            credential_id=CRED_C,
            received="2026-10-05T00:41:00Z",
            char="8",
            client_request_id=self.rows["leaked run"]["client_request_id"],
        )
        after = self.case(
            "a third credential reuses the request id: the same bound row, two rows carry it",
            binding,
            "OK",
            0,
            {CROSS: 2},
        )
        changed = sorted(key for key in before if before.get(key) != after.get(key))
        self.cases.append(
            {
                "case": "the reuse changes only the cross-credential count",
                "expected_reason": [CROSS],
                "reason": changed,
                "ok": changed == [CROSS],
            }
        )

    def least_privilege(self, owner_pass: dict[str, Any]) -> dict[str, Any]:
        """The probe reads exactly the eleven columns: the companion passes as it, with the owner's
        facts, and every other column and table is refused."""

        with self.owner() as conn:
            columns = {
                (table, name): granted
                for table, name, granted in conn.execute(
                    "SELECT c.relname, a.attname,"
                    " pg_catalog.has_column_privilege(%s, c.oid, a.attnum, 'SELECT')"
                    " FROM pg_catalog.pg_class AS c"
                    " JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace"
                    " JOIN pg_catalog.pg_attribute AS a ON a.attrelid = c.oid"
                    " WHERE n.nspname = 'public'"
                    " AND c.relname IN ('automation_radar_ledger', 'predictions')"
                    " AND a.attnum > 0 AND NOT a.attisdropped",
                    (PROBE,),
                ).fetchall()
            }
            readable_relations = [
                row[0]
                for row in conn.execute(
                    "SELECT c.relname FROM pg_catalog.pg_class AS c"
                    " JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace"
                    " WHERE n.nspname = 'public' AND c.relkind IN ('r', 'v', 'm', 'p', 'f')"
                    " AND pg_catalog.has_any_column_privilege(%s, c.oid, 'SELECT') ORDER BY 1",
                    (PROBE,),
                ).fetchall()
            ]
        granted = sorted(key for key, value in columns.items() if value)
        wanted = sorted(
            [("automation_radar_ledger", name) for name in LEDGER_READ]
            + [("predictions", "run_id")]
        )
        refused_reads = {}
        for table, name in sorted(key for key, value in columns.items() if not value):
            refused_reads[f"{table}.{name}"] = self._probe_read(
                f"SELECT {name} FROM public.{table} LIMIT 1"
            )
        for table in (
            "prediction_outcomes",
            "analysis_runs",
            "automation_credential",
            "prediction_feature_snapshots",
            "analysis_run_details",
        ):
            refused_reads[table] = self._probe_read(f"SELECT 1 FROM public.{table} LIMIT 1")
        probe_pass = self.case(
            "least privilege: the companion as the eleven-column probe",
            self.binding("qualifying"),
            "OK",
            0,
            connect=self.as_role(PROBE),
        )
        same = all(probe_pass.get(key) == owner_pass.get(key) for key in owner_pass)
        return {
            "granted_columns": [f"{table}.{name}" for table, name in granted],
            "readable_public_relations": readable_relations,
            "refused_reads": refused_reads,
            "same_output_as_the_owner": same,
            "ok": granted == wanted
            and readable_relations == ["automation_radar_ledger", "predictions"]
            and set(refused_reads.values()) == {"REFUSED"}
            and same,
        }

    def isolated_command_line(self, owner_pass: dict[str, Any]) -> dict[str, Any]:
        """The card's exact command, python -I -B, in a child process against this server: it
        PASSES with the in-process run's line and leaves the package folder exactly as sealed. Any
        other start is refused. A copy of the folder with one more module is refused, and the module
        never runs under -I; without -I it would, which a harmless marker shows."""

        binding = self.binding("qualifying")
        args = [
            "--credential-id",
            binding["credential_id"],
            "--client-request-id",
            binding["client_request_id"],
            "--run-id",
            binding["run_id"],
            "--deadline-ms",
            binding["deadline_ms"],
            "--analysis-hash",
            binding["analysis_hash"],
            "--qualification-activation-utc",
            binding["activation"],
        ]
        environment = {"PATH": os.environ.get("PATH", ""), runner.DATABASE_URL_ENV: self.url}

        def start(script: Path, *flags: str) -> tuple[int, dict[str, Any]]:
            done = subprocess.run(  # noqa: S603 - this interpreter, a sealed file, fixed arguments
                [sys.executable, *flags, str(script), *args],
                env=environment,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            line = done.stdout.strip()
            return done.returncode, json.loads(line) if line.startswith("{") else {}

        before = sorted(os.listdir(PACKAGE))
        state = self.digest()
        isolated_code, isolated = start(PACKAGE / "a4_card04_companion.py", "-I", "-B")
        refused = {
            " ".join(flags): start(PACKAGE / "a4_card04_companion.py", *flags)
            for flags in (("-B",), ("-I",), ())
        }
        after = sorted(os.listdir(PACKAGE))
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "ops" / "a4_card04_companion"
            shutil.copytree(PACKAGE, folder)
            marker = Path(root) / "planted-module-ran"
            (folder / "json.py").write_text(
                f"open({str(marker)!r}, 'w').close()\nraise SystemExit(99)\n", encoding="utf-8"
            )
            planted_code, planted = start(folder / "a4_card04_companion.py", "-I", "-B")
            ran_under_isolation = marker.exists()
            unisolated_code, _ = start(folder / "a4_card04_companion.py", "-B")
            ran_without_isolation = marker.exists()
        result = {
            "isolated_exit": isolated_code,
            "isolated_line_equals_in_process": isolated == owner_pass,
            "other_starts": {
                flags or "(none)": [code, payload.get("reason")]
                for flags, (code, payload) in refused.items()
            },
            "package_folder_before": before,
            "package_folder_after": after,
            "database_unchanged": state == self.digest(),
            "planted_module": {
                "isolated_exit": planted_code,
                "isolated_reason": planted.get("reason"),
                "ran_under_isolation": ran_under_isolation,
                "exit_without_isolation": unisolated_code,
                "ran_without_isolation": ran_without_isolation,
            },
        }
        result["ok"] = (
            isolated_code == 0
            and isolated.get("verdict") == "PASS"
            and result["isolated_line_equals_in_process"]
            and all(
                code == 2 and reason == "NOT_ISOLATED"
                for code, reason in result["other_starts"].values()
            )
            and before == after == sorted(runner.PACKAGE_FILES)
            and result["database_unchanged"]
            and planted_code == 3
            and planted.get("reason") == "SEAL_MISMATCH"
            and not ran_under_isolation
            and ran_without_isolation
        )
        return result

    def _probe_read(self, statement: str) -> str:
        with self.owner() as conn:
            conn.execute(f"SET ROLE {PROBE}")
            try:
                conn.execute(statement)
                return "READ"
            except psycopg.errors.InsufficientPrivilege:
                return "REFUSED"

    def row_security(self) -> dict[str, Any]:
        """A reader row-level security applies to is refused, with or without a permissive policy:
        never a count through a policy. Without the runner's preamble the hidden reader would see a
        silent zero."""

        binding = self.binding("leaked run")
        refused = {}
        for role in (POLICY_READER, HIDDEN_READER):
            payload = self.case(
                f"row security applies to {role}: refused, never counted",
                binding,
                "DATABASE_ERROR",
                4,
                {"error_class": "InsufficientPrivilege"},
                connect=self.as_role(role),
            )
            refused[role] = payload.get("error_class")
        conn = self.as_role(HIDDEN_READER)(self.url)
        try:
            with conn.cursor() as cur:
                for statement in runner.READ_ONLY_PREAMBLE:
                    if "row_security" not in statement:
                        cur.execute(statement)
                cur.execute(
                    runner.verified_package()[0],
                    runner.validate(
                        binding["credential_id"],
                        binding["client_request_id"],
                        binding["run_id"],
                        binding["deadline_ms"],
                        binding["analysis_hash"],
                        binding["activation"],
                    ).parameters(),
                )
                silent = dict(zip(runner.SQL_COLUMNS, cur.fetchone(), strict=True))
        finally:
            conn.rollback()
            conn.close()
        return {
            "refused": refused,
            "without_the_preamble": {
                key: silent[key]
                for key in (
                    "reason",
                    "predictions_rows_for_run_id",
                    "credential_ledger_rows_since_activation",
                    CROSS,
                )
            },
            "ok": set(refused.values()) == {"InsufficientPrivilege"}
            and silent["reason"] == "NO_ROW"
            and silent["predictions_rows_for_run_id"] == 0
            and silent["credential_ledger_rows_since_activation"] == 0
            and silent[CROSS] == 0,
        }

    def read_only(self) -> dict[str, Any]:
        """Every write kind is refused under the runner's own preamble, and nothing changes.
        Statements that remove rows target the scratch sentinel table (nothing in this repository
        names a deletion on the ledger); READ ONLY covers every table alike."""

        writes = {
            "INSERT (ledger)": "INSERT INTO public.automation_radar_ledger (credential_id,"
            " client_request_id, request_fingerprint, state, release_id,"
            " deadline_ms, received_at_utc) VALUES ('a4c-rehearsal-uor',"
            " gen_random_uuid(), 'sha256:" + "9" * 64 + "', 'IN_PROGRESS',"
            " 'UCPE-X-Y', 30000, now())",
            "INSERT (predictions)": (
                "INSERT INTO public.predictions SELECT * FROM public.predictions LIMIT 1"
            ),
            "UPDATE (ledger)": "UPDATE public.automation_radar_ledger SET state = state",
            "UPDATE (predictions)": "UPDATE public.predictions SET run_id = run_id",
            "DELETE (sentinel)": f"DELETE FROM {SENTINEL}",
            "MERGE (sentinel)": f"MERGE INTO {SENTINEL} AS s USING (SELECT 1 AS x) AS v"
            " ON s.x = v.x WHEN MATCHED THEN DELETE",
            "CREATE": "CREATE TABLE public.a4c_must_not_exist (x integer)",
            "ALTER (ledger)": (
                "ALTER TABLE public.automation_radar_ledger ADD COLUMN a4c_probe text"
            ),
            "DROP (sentinel)": f"DROP TABLE {SENTINEL}",
            "TRUNCATE (sentinel)": f"TRUNCATE {SENTINEL}",
        }
        outcomes = {}
        before = self.digest()
        for name, statement in writes.items():
            with psycopg.connect(self.url, autocommit=False) as conn, conn.cursor() as cur:
                runner.begin_read_only(cur)
                try:
                    cur.execute(statement)
                    outcomes[name] = "EXECUTED"
                except psycopg.errors.ReadOnlySqlTransaction:
                    outcomes[name] = "REFUSED_READ_ONLY"
                conn.rollback()
        unchanged = before == self.digest()
        return {
            "writes": outcomes,
            "database_unchanged": unchanged,
            "ok": set(outcomes.values()) == {"REFUSED_READ_ONLY"} and unchanged,
        }

    def drift(self) -> str:
        """Schema drift fails closed. Returns the digest after every reversible stage; the last
        stage (no primary key, a duplicate row) is left as it is: the scratch database is discarded
        with its cluster, and nothing here names a deletion on the ledger."""

        def ddl(*statements: str) -> None:
            with self.owner() as conn:
                for statement in statements:
                    conn.execute(statement)

        ledger, ok = "public.automation_radar_ledger", self.binding("qualifying")
        ddl(f"ALTER TABLE {ledger} ADD COLUMN a4c_unread text")
        self.case("an extra column the companion does not read is not drift", ok, "OK", 0)
        ddl(f"ALTER TABLE {ledger} DROP COLUMN a4c_unread")
        ddl(f"ALTER TABLE {ledger} ALTER COLUMN deadline_ms TYPE bigint")
        self.case("drift: a changed type", ok, "SCHEMA_DRIFT", 1)
        ddl(f"ALTER TABLE {ledger} ALTER COLUMN deadline_ms TYPE integer")
        self.case("drift reverted: the type restored", ok, "OK", 0)
        ddl("ALTER TABLE public.predictions ALTER COLUMN run_id DROP NOT NULL")
        self.case("drift: predictions.run_id nullable", ok, "SCHEMA_DRIFT", 1)
        ddl("ALTER TABLE public.predictions ALTER COLUMN run_id SET NOT NULL")
        self.case("drift reverted: predictions.run_id required again", ok, "OK", 0)
        ddl(
            "ALTER TABLE public.predictions RENAME TO a4c_predictions_moved",
            "CREATE VIEW public.predictions AS SELECT * FROM public.a4c_predictions_moved",
        )
        self.case("drift: a view in place of predictions", ok, "SCHEMA_DRIFT", 1)
        ddl(
            "DROP VIEW public.predictions",
            "ALTER TABLE public.a4c_predictions_moved RENAME TO predictions",
        )
        self.case("drift reverted: predictions is a table again", ok, "OK", 0)
        ddl("ALTER TABLE public.predictions RENAME TO a4c_predictions_moved")
        self.case("drift: predictions is gone", ok, "DATABASE_ERROR", 4)
        ddl("ALTER TABLE public.a4c_predictions_moved RENAME TO predictions")
        ddl(f"ALTER TABLE {ledger} RENAME TO a4c_ledger_moved")
        self.case("drift: the ledger is gone", ok, "DATABASE_ERROR", 4)
        ddl("ALTER TABLE public.a4c_ledger_moved RENAME TO automation_radar_ledger")
        self.case("drift reverted: both tables back", ok, "OK", 0)
        ddl("CREATE TABLE public.a4c_ledger_child () INHERITS (public.automation_radar_ledger)")
        self.case("drift: an inheritance child of the ledger", ok, "SCHEMA_DRIFT", 1)
        ddl("DROP TABLE public.a4c_ledger_child")
        ddl("CREATE TABLE public.a4c_predictions_child () INHERITS (public.predictions)")
        self.case("drift: an inheritance child of predictions", ok, "SCHEMA_DRIFT", 1)
        ddl("DROP TABLE public.a4c_predictions_child")
        self.case("drift reverted: no inheritance child", ok, "OK", 0)
        restored = self.digest()
        ddl(f"ALTER TABLE {ledger} DROP CONSTRAINT automation_radar_ledger_pkey")
        self.case("drift: no primary key", ok, "SCHEMA_DRIFT", 1)
        row = self.rows["qualifying"]
        body = copy.deepcopy(self.example)
        body.update(
            client_request_id=row["client_request_id"],
            run_id=row["run_id"],
            analysis_hash=row["analysis_hash"],
            evidence_hash=hexed("a", "sha256:", 63) + "0",
        )
        self._insert(
            credential_id=CRED_A,
            client_request_id=row["client_request_id"],
            received=row["received"],
            state="COMPLETED",
            outcome="SUCCEEDED",
            status=200,
            body=body,
            deadline_ms=45000,
        )
        self.case("drift: a duplicate without a primary key", ok, "SCHEMA_DRIFT", 1)
        self.variant_case(
            "a duplicate with the drift check removed is still AMBIGUOUS",
            self.variant("               WHEN k.schema_ok IS NOT TRUE THEN 'SCHEMA_DRIFT'\n", ""),
            ok,
            "AMBIGUOUS",
        )
        return restored


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    url = os.environ["A4C_REHEARSAL_URL"]
    refuse_non_scratch(url)
    report = Rehearsal(url).run()
    Path(args.report).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for case in report["cases"]:
        print(("PASS " if case["ok"] else "FAIL ") + case["case"] + f" -> {case['reason']}")
    print(
        f"least_privilege ok={report['least_privilege']['ok']}"
        f" isolated_command_line ok={report['isolated_command_line']['ok']}"
        f" row_security ok={report['row_security']['ok']}"
        f" read_only ok={report['read_only']['ok']}"
        f" database_restored={report['database_restored']}"
        f" server_version={report['server_version']}"
    )
    print("A4C_REHEARSAL=" + ("PASS" if report["all_ok"] else "FAIL"))
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
