"""A PostgREST stand-in for the PERS-0 rehearsal (B9, migration 0015), against scratch PostgreSQL.

The REST writer (SupabaseRestRepository) talks to it through an httpx.MockTransport, so the
writer's own code runs unchanged. Only the bundle RPC touches the database, and exactly as
PostgREST executes an RPC:
- one transaction per request, as the role the service-role key maps to (SET LOCAL ROLE
  service_role);
- the arguments taken from the raw request body by jsonb_to_record with the function's own
  parameter types, which is PostgREST's own json_to_record call, so JSON numbers keep their
  digits;
- a database error answers HTTP 400 with its SQLSTATE, and the transaction rolls back.
The writer's other requests (run summary, timeframe result, provider and news rows) lie outside
the bundle: they are acknowledged (201) and not stored.

Faults, each for the next RPC request only:
- "feature_snapshot": the scratch-only trigger pers0_fault.fail_feature_snapshot raises inside the
  RPC's transaction, after the prediction row was written;
- "lost_response": the transaction commits, then the response is lost (httpx.ReadError).
"""

from __future__ import annotations

from typing import Any

import httpx

RPC_PATH = "/rest/v1/rpc/save_prediction_bundle"
RPC_SQL = (
    "SELECT public.save_prediction_bundle(p_prediction => b.p_prediction, "
    "p_feature_snapshot => b.p_feature_snapshot, "
    "p_derivatives_snapshot => b.p_derivatives_snapshot) "
    "FROM pg_catalog.jsonb_to_record(%s::jsonb) "
    "AS b(p_prediction jsonb, p_feature_snapshot jsonb, p_derivatives_snapshot jsonb)"
)
# Installed by the rehearsal, never by a migration: scratch databases only.
FAULT_SETUP_SQL = (
    "CREATE SCHEMA IF NOT EXISTS pers0_fault",
    "CREATE OR REPLACE FUNCTION pers0_fault.fail_feature_snapshot() RETURNS trigger "
    "LANGUAGE plpgsql AS $$ BEGIN "
    "IF pg_catalog.current_setting('pers0.fail_feature_snapshot', true) = 'on' THEN "
    "RAISE EXCEPTION 'PERS-0 injected fault: the feature snapshot write fails in the bundle'; "
    "END IF; RETURN NEW; END $$",
    "DROP TRIGGER IF EXISTS pers0_fault_fail_feature_snapshot "
    "ON public.prediction_feature_snapshots",
    "CREATE TRIGGER pers0_fault_fail_feature_snapshot BEFORE INSERT "
    "ON public.prediction_feature_snapshots FOR EACH ROW "
    "EXECUTE FUNCTION pers0_fault.fail_feature_snapshot()",
    "GRANT USAGE ON SCHEMA pers0_fault TO service_role",
)
FAULTS = ("feature_snapshot", "lost_response")
FAULT_ON_SQL = "SELECT pg_catalog.set_config('pers0.fail_feature_snapshot', 'on', true)"


def install_faults(url: str) -> None:
    """The scratch-only fault trigger; inert unless a request switches it on."""

    import psycopg

    with psycopg.connect(url) as connection, connection.cursor() as cursor:
        for statement in FAULT_SETUP_SQL:
            cursor.execute(statement)


class PostgrestEmulator:
    """An httpx.MockTransport handler answering the REST writer as PostgREST would."""

    def __init__(self, url: str, *, fault: str | None = None) -> None:
        if fault is not None and fault not in FAULTS:
            raise ValueError(f"unknown fault {fault!r}")
        self.url = url
        self.fault = fault
        self.rpc_requests = 0
        self.answers: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path != RPC_PATH:
            return httpx.Response(201 if request.method == "POST" else 404)
        import psycopg

        self.rpc_requests += 1
        fault, self.fault = self.fault, None
        with psycopg.connect(self.url) as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL ROLE service_role")
                    if fault == "feature_snapshot":
                        cursor.execute(FAULT_ON_SQL)
                    cursor.execute(RPC_SQL, (request.content.decode("utf-8"),))
                    answer = cursor.fetchone()[0]
            except psycopg.Error as exc:
                connection.rollback()
                self.answers.append({"status": 400, "sqlstate": exc.sqlstate})
                return httpx.Response(400, json={"code": exc.sqlstate, "message": "RPC failed"})
            connection.commit()
        self.answers.append({"status": 200, "answer": answer})
        if fault == "lost_response":
            raise httpx.ReadError("the response was lost after the commit", request=request)
        return httpx.Response(200, json=answer)
