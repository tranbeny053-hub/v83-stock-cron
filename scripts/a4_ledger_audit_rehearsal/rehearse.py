"""Scratch-PostgreSQL rehearsal of ucpe.a4_ledger_audit.v1 (CI only: no secret, no real database).

Runs ONLY against a scratch local PostgreSQL that a CI runner built from every applied migration
(.github/workflows/a4-ledger-audit-rehearsal.yml). It inserts synthetic ledger rows and alters the
scratch ledger to rehearse schema drift, so it refuses any URL that is not a local socket database
named a4_rehearsal.

What it proves, each as a case with an expected and an actual result:
- the sealed audit, through its real command line and psycopg, PASSES the one qualifying row and
  fails closed with the right reason on every other shape: no row, another credential, in progress,
  a refusal, a body whose origin, request id or release differs, and a run, release or evidence
  hash that differs from the response;
- the binding is the PAIR: the same client_request_id under another credential is another row, and
  a variant bound on client_request_id alone finds two rows (AMBIGUOUS);
- schema drift fails closed: an extra column, a changed type, a missing primary key (and, with the
  drift check removed from a variant, duplicates are still AMBIGUOUS), a renamed table;
- isolation: run as a role that can read only the ledger, the audit still PASSES, and that role is
  refused every other table;
- read-only: under the audit's own session preamble, every write is refused, and the ledger's
  content digest is identical before and after every audit run.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import io
import json
import os
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import psycopg

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "ops" / "a4_ledger_audit"
EXAMPLE = ROOT / "docs/automation/examples/radar_evidence.v1.synthetic-btc-4h-gate-blocked.json"
ERROR_EXAMPLE = (
    ROOT / "docs/automation/examples/radar_evidence_error.v1.synthetic-quota-exceeded.json"
)
CRED_A = "a4-rehearsal-uor"
CRED_B = "a4-rehearsal-other"
PROBE_ROLE = "a4_probe"
NAMESPACE = uuid.UUID("6a4d1f0e-5c3b-4a29-8f17-0e6d5c4b3a29")


def load_runner() -> Any:
    spec = importlib.util.spec_from_file_location(
        "a4_ledger_audit_runner", PACKAGE / "a4_ledger_audit.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = load_runner()


def refuse_non_scratch(url: str) -> None:
    parsed = urlparse(url)
    host = parse_qs(parsed.query).get("host", [""])[0]
    if parsed.hostname or not host.startswith("/") or parsed.path.lstrip("/") != "a4_rehearsal":
        raise SystemExit("REFUSED: only the local scratch database a4_rehearsal")


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

    # ---------------------------------------------------------------- fixtures
    def owner(self) -> psycopg.Connection:
        return psycopg.connect(self.url, autocommit=True)

    def insert(self, conn: psycopg.Connection, *, credential_id: str, client_request_id: str,
               state: str = "COMPLETED", outcome: str | None = "SUCCEEDED",
               status: int | None = 200, body: dict[str, Any] | None = None,
               fingerprint_char: str = "1") -> None:
        succeeded = outcome == "SUCCEEDED"
        conn.execute(
            """
            INSERT INTO public.automation_radar_ledger
                   (credential_id, client_request_id, request_fingerprint, state, outcome_code,
                    http_status, response_body, run_id, analysis_hash, evidence_hash, release_id,
                    deadline_ms, received_at_utc, completed_at_utc)
            VALUES (%s, %s::uuid, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, 30000,
                    now() - interval '1 minute',
                    CASE WHEN %s = 'COMPLETED' THEN now() END)
            """,
            (
                credential_id, client_request_id, hexed(fingerprint_char, "sha256:", 64), state,
                outcome if state == "COMPLETED" else None,
                status if state == "COMPLETED" else None,
                json.dumps(body) if body is not None else None,
                body["run_id"] if succeeded and body else None,
                body["analysis_hash"] if succeeded and body else None,
                body["evidence_hash"] if succeeded and body else None,
                self.release, state,
            ),
        )

    def body(self, client_request_id: str, run_char: str, **changes: Any) -> dict[str, Any]:
        body = copy.deepcopy(self.example)
        body.update(client_request_id=client_request_id, run_id=hexed(run_char, "run_", 32),
                    evidence_hash=hexed(run_char, "sha256:", 64))
        for key, value in changes.items():
            if key == "release_id":
                body["build_info"]["release_id"] = value
            else:
                body[key] = value
        return body

    def seed(self) -> None:
        with self.owner() as conn:
            self.ok = self.body(self.example["client_request_id"], "a")
            self.insert(conn, credential_id=CRED_A, client_request_id=self.ok["client_request_id"],
                        body=self.ok)
            self.other = self.body(self.example["client_request_id"], "b")
            self.insert(conn, credential_id=CRED_B,
                        client_request_id=self.other["client_request_id"], body=self.other)
            self.insert(conn, credential_id=CRED_A, client_request_id=rid("in-progress"),
                        state="IN_PROGRESS")
            refusal = json.loads(ERROR_EXAMPLE.read_text(encoding="utf-8"))
            self.insert(conn, credential_id=CRED_A, client_request_id=rid("refused"),
                        outcome="QUOTA_EXCEEDED", status=429, body=refusal)
            self.wrong = {
                "body-release": self.body(rid("body-release"), "c", release_id="UCPE-OTHER-REL"),
                "body-origin": self.body(rid("body-origin"), "d",
                                         evidence_origin="USER_REQUESTED"),
                "body-request": self.body(rid("body-request"), "e"),
            }
            self.wrong["body-request"]["client_request_id"] = self.example["client_request_id"]
            for name, body in self.wrong.items():
                self.insert(conn, credential_id=CRED_A, client_request_id=rid(name), body=body)

    def digest(self) -> str:
        """The ledger's full content digest, or MISSING while a drift case has renamed it."""

        with self.owner() as conn:
            try:
                row = conn.execute(
                    "SELECT md5(coalesce(string_agg(row_to_json(l)::text, '|' ORDER BY "
                    "l.credential_id, l.client_request_id, l.request_fingerprint), ''))"
                    " FROM public.automation_radar_ledger AS l"
                ).fetchone()
            except psycopg.errors.UndefinedTable:
                return "MISSING"
        return row[0]

    # ---------------------------------------------------------------- one audit
    def audit(self, *, credential_id: str, client_request_id: str, run_id: str, release_id: str,
              evidence_hash: str, connect: Callable[..., Any] | None = None) -> tuple[int, dict]:
        out = io.StringIO()
        code = runner.main(
            ["--credential-id", credential_id, "--client-request-id", client_request_id,
             "--run-id", run_id, "--release-id", release_id, "--evidence-hash", evidence_hash],
            environ={runner.DATABASE_URL_ENV: self.url}, connect=connect, stdout=out,
        )
        return code, json.loads(out.getvalue())

    def case(self, name: str, expected_reason: str, expected_code: int, **binding: Any) -> None:
        before = self.digest()
        code, payload = self.audit(**binding)
        after = self.digest()
        self.cases.append({
            "case": name, "expected_reason": expected_reason, "reason": payload.get("reason"),
            "expected_exit": expected_code, "exit": code,
            "error_class": payload.get("error_class"),
            "ledger_unchanged": before == after,
            "ok": payload.get("reason") == expected_reason and code == expected_code
                  and before == after,
        })

    def ok_binding(self, **changes: str) -> dict[str, str]:
        binding = {"credential_id": CRED_A, "client_request_id": self.ok["client_request_id"],
                   "run_id": self.ok["run_id"], "release_id": self.release,
                   "evidence_hash": self.ok["evidence_hash"]}
        binding.update(changes)
        return binding

    def wrong_binding(self, name: str) -> dict[str, str]:
        body = self.wrong[name]
        return {"credential_id": CRED_A, "client_request_id": rid(name), "run_id": body["run_id"],
                "release_id": self.release, "evidence_hash": body["evidence_hash"]}

    def variant(self, old: str, new: str) -> str:
        sealed = runner.SQL_PATH.read_text(encoding="utf-8")
        assert sealed.count(old) == 1, old
        return sealed.replace(old, new)

    def variant_case(self, name: str, sql: str, expected_reason: str, binding: dict) -> None:
        facts = runner.run_sealed_audit(self.url, runner.validate(**binding), sql,
                                        connect=psycopg.connect)
        self.cases.append({"case": name, "expected_reason": expected_reason,
                           "reason": facts["reason"], "matched_rows": facts["matched_rows"],
                           "ok": facts["reason"] == expected_reason})

    # ---------------------------------------------------------------- the cases
    def run(self) -> dict[str, Any]:
        self.seed()
        start = self.digest()
        self.case("qualifying row", "OK", 0, **self.ok_binding())
        self.case("same request id, other credential: its own row", "OK", 0,
                  credential_id=CRED_B, client_request_id=self.other["client_request_id"],
                  run_id=self.other["run_id"], release_id=self.release,
                  evidence_hash=self.other["evidence_hash"])
        self.case("the other credential's run is not this row's", "RUN_MISMATCH", 1,
                  **self.ok_binding(run_id=self.other["run_id"]))
        self.case("unknown request id", "NO_ROW", 1, **self.ok_binding(
            client_request_id=rid("never-sent")))
        self.case("unknown credential", "NO_ROW", 1, **self.ok_binding(
            credential_id="a4-never-issued"))
        self.case("in progress", "NOT_COMPLETED", 1, **self.ok_binding(
            client_request_id=rid("in-progress")))
        self.case("a refusal", "NOT_SUCCEEDED", 1, **self.ok_binding(
            client_request_id=rid("refused")))
        self.case("body release differs", "BODY_IDENTITY_MISMATCH", 1,
                  **self.wrong_binding("body-release"))
        self.case("body origin differs", "WRONG_ORIGIN", 1, **self.wrong_binding("body-origin"))
        self.case("body request id differs", "BODY_IDENTITY_MISMATCH", 1,
                  **self.wrong_binding("body-request"))
        self.case("run differs", "RUN_MISMATCH", 1,
                  **self.ok_binding(run_id=hexed("f", "run_", 32)))
        self.case("release differs", "RELEASE_MISMATCH", 1, **self.ok_binding(
            release_id="UCPE-PROD-NOT-THIS"))
        self.case("evidence hash differs", "EVIDENCE_MISMATCH", 1, **self.ok_binding(
            evidence_hash=hexed("f", "sha256:", 64)))
        self.variant_case(
            "client_request_id alone is ambiguous", self.variant(
                "        ON l.credential_id = b.credential_id\n       AND l.client_request_id",
                "        ON l.client_request_id"),
            "AMBIGUOUS", self.ok_binding())
        isolation = self.isolation()
        read_only = self.read_only()
        end = self.drift()
        report = {
            "artifact": runner.ARTIFACT, "sql_sha256": runner.SQL_SHA256, "cases": self.cases,
            "isolation": isolation, "read_only": read_only, "ledger_restored": start == end,
        }
        report["all_ok"] = (all(case["ok"] for case in self.cases) and isolation["ok"]
                            and read_only["ok"] and report["ledger_restored"])
        return report

    def isolation(self) -> dict[str, Any]:
        with self.owner() as conn:
            readable = [row[0] for row in conn.execute(
                "SELECT c.relname FROM pg_catalog.pg_class AS c"
                " JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace"
                " WHERE n.nspname = 'public' AND c.relkind IN ('r', 'v', 'm', 'p', 'f')"
                " AND pg_catalog.has_table_privilege(%s, c.oid, 'SELECT') ORDER BY 1",
                (PROBE_ROLE,)).fetchall()]
        refused = {}
        for table in ("predictions", "prediction_outcomes", "analysis_runs",
                      "automation_credential"):
            with self.owner() as conn:
                conn.execute(f"SET ROLE {PROBE_ROLE}")
                try:
                    conn.execute(f"SELECT 1 FROM public.{table} LIMIT 1")
                    refused[table] = "READ"
                except psycopg.errors.InsufficientPrivilege:
                    refused[table] = "REFUSED"

        def as_probe(url: str, **kwargs: Any) -> psycopg.Connection:
            conn = psycopg.connect(url, **{**kwargs, "autocommit": True})
            conn.execute(f"SET ROLE {PROBE_ROLE}")
            conn.autocommit = False
            return conn

        code, payload = self.audit(connect=as_probe, **self.ok_binding())
        return {
            "probe_readable_public_relations": readable, "probe_refused": refused,
            "probe_audit_reason": payload.get("reason"), "probe_audit_exit": code,
            "ok": readable == ["automation_radar_ledger"]
                  and set(refused.values()) == {"REFUSED"}
                  and payload.get("reason") == "OK" and code == 0,
        }

    def read_only(self) -> dict[str, Any]:
        """Every write is refused under the audit's own preamble: on the ledger itself (insert,
        update, alter), and on a scratch sentinel table for the statements that delete rows
        (nothing in this repository names a deletion on the ledger; READ ONLY covers every table).
        """

        with self.owner() as conn:
            conn.execute("CREATE TABLE public.a4_rehearsal_sentinel (x integer)")
            conn.execute("INSERT INTO public.a4_rehearsal_sentinel VALUES (1)")
        writes = {
            "insert": "INSERT INTO public.automation_radar_ledger (credential_id,"
                      " client_request_id,"
                      " request_fingerprint, state, release_id, deadline_ms, received_at_utc)"
                      " VALUES ('a4-rehearsal-uor', gen_random_uuid(),"
                      " 'sha256:" + "9" * 64 + "', 'IN_PROGRESS', 'UCPE-X-Y', 30000, now())",
            "update": "UPDATE public.automation_radar_ledger SET state = state",
            "alter": "ALTER TABLE public.automation_radar_ledger ADD COLUMN a4_ro_probe text",
            "create": "CREATE TABLE public.a4_must_not_exist (x integer)",
            "delete (sentinel)": "DELETE FROM public.a4_rehearsal_sentinel",
            "truncate (sentinel)": "TRUNCATE public.a4_rehearsal_sentinel",
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
        with self.owner() as conn:
            sentinel = conn.execute("SELECT count(*) FROM public.a4_rehearsal_sentinel").fetchone()
        unchanged = before == self.digest() and sentinel[0] == 1
        return {"writes": outcomes, "ledger_and_sentinel_unchanged": unchanged,
                "ok": set(outcomes.values()) == {"REFUSED_READ_ONLY"} and unchanged}

    def drift(self) -> str:
        """Schema drift fails closed. Returns the ledger digest after every reversible stage; the
        last stage (no primary key, a duplicate row) is left as it is: the scratch database is
        discarded with the runner, and nothing here names a deletion on the ledger."""

        def ddl(statement: str) -> None:
            with self.owner() as conn:
                conn.execute(statement)

        table = "public.automation_radar_ledger"
        ddl(f"ALTER TABLE {table} ADD COLUMN a4_drift_extra text")
        self.case("drift: an extra column", "SCHEMA_DRIFT", 1, **self.ok_binding())
        ddl(f"ALTER TABLE {table} DROP COLUMN a4_drift_extra")
        self.case("drift reverted: the extra column dropped", "OK", 0, **self.ok_binding())
        ddl(f"ALTER TABLE {table} ALTER COLUMN deadline_ms TYPE bigint")
        self.case("drift: a changed type", "SCHEMA_DRIFT", 1, **self.ok_binding())
        ddl(f"ALTER TABLE {table} ALTER COLUMN deadline_ms TYPE integer")
        self.case("drift reverted: the type restored", "OK", 0, **self.ok_binding())
        ddl(f"ALTER TABLE {table} RENAME TO automation_radar_ledger_moved")
        self.case("drift: the table is gone", "DATABASE_ERROR", 4, **self.ok_binding())
        ddl("ALTER TABLE public.automation_radar_ledger_moved RENAME TO automation_radar_ledger")
        self.case("drift reverted: the table is back", "OK", 0, **self.ok_binding())
        restored = self.digest()
        ddl(f"ALTER TABLE {table} DROP CONSTRAINT automation_radar_ledger_pkey")
        self.case("drift: no primary key", "SCHEMA_DRIFT", 1, **self.ok_binding())
        with self.owner() as conn:
            self.insert(conn, credential_id=CRED_A, client_request_id=self.ok["client_request_id"],
                        body=self.ok, fingerprint_char="d")
        self.case("drift: duplicates without a primary key", "SCHEMA_DRIFT", 1,
                  **self.ok_binding())
        self.variant_case(
            "duplicates with the drift check removed are still AMBIGUOUS", self.variant(
                "               WHEN k.schema_ok IS NOT TRUE THEN 'SCHEMA_DRIFT'\n", ""),
            "AMBIGUOUS", self.ok_binding())
        return restored


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    url = os.environ["A4_REHEARSAL_URL"]
    refuse_non_scratch(url)
    report = Rehearsal(url).run()
    Path(args.report).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
    for case in report["cases"]:
        print(("PASS " if case["ok"] else "FAIL ") + case["case"] + f" -> {case['reason']}")
    print(f"isolation ok={report['isolation']['ok']} read_only ok={report['read_only']['ok']}"
          f" ledger_restored={report['ledger_restored']}")
    print("A4_REHEARSAL=" + ("PASS" if report["all_ok"] else "FAIL"))
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
