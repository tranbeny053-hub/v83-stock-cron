#!/usr/bin/env python
"""P3-PRIV-R: the least-privilege roles, rehearsed on scratch PostgreSQL behind a real PostgREST.

The design is .work/roadmap/phase3/PRIVILEGE_AUDIT_AND_DESIGN.md (C1-C3, option W2) with its
Correction 01.

Migration 0016 (migrations/0016_least_privilege_roles.sql, its reviewed bytes; owner ruling E1 =
YES, W2) is applied here as the tables' owner, which holds CREATEROLE without SUPERUSER, as
Supabase's postgres does. Production's OWN code then runs under
each narrow role:
- **the REST runtime** (the analysis service's persistence and SupabaseRestRepository) runs as
  ucpe_api_writer, through a real PostgREST with a scratch writer JWT. That is how the live Space
  would run after the writer cutover;
- **the Space's direct Postgres** runs as ucpe_space_db: the calibration query, plus migration
  0013's F1 registry, ledger and capacity probes, unchanged;
- **the resolver** runs as ucpe_resolver: its repository and its status store.

The REST client falls back to an in-memory copy when a request fails, so no read is believed on its
own. After every call the circuit must still be CLOSED, reads go through a fresh repository, and
every effect is verified in the database as the owner.

Criteria, each PASS or FAIL in the report (--require-all makes every one a gate):
- P1 MATRIX: every new role's table, sequence, function, schema and policy grants equal the design
  exactly, and so do its attributes, memberships and ownership.
- P2 WRITER: as ucpe_api_writer, the REST runtime:
  - persists a full analysis (receipt SAVED) and its detail;
  - reads them back;
  - replays the analysis (SAVED);
  - refuses a conflicting one (NOT_SAVED CONFLICT);
  - round-trips the watchlist.
- P3 WRITER_REFUSALS: every request outside the writer's list is refused and writes nothing. So is
  a JWT naming any other role, and so is anon.
- P4 SPACE_DB: calibration and the F1 registry, ledger and capacity probes pass as ucpe_space_db,
  and every statement outside its list is refused.
- P5 RESOLVER: as ucpe_resolver, the due scans, the outcome insert, the read-back and the status
  upsert all work, and every statement outside its list is refused.
- P6 UNCHANGED:
  - anon, authenticated and service_role hold exactly what they held;
  - anon and authenticated are still denied;
  - the live service_role writer still persists through PostgREST (SAVED).
- P7 ONE_SHOT: a second application of migration 0016 is refused and changes nothing.
- P8 ROLLBACK: the rollback restores the pre-draft catalog exactly, and the service_role writer
  still persists (SAVED).

W-A (migration 0017, migrations/0017_forecast_bundle_rpc.sql, its reviewed bytes; owner ruling
WB1 = YES, after 0016), on top of the applied 0016, before P8: plan §8.1's whole core bundle (the
run identity, the detail, the prediction and its snapshots) in one transaction, called through
PostgREST as ucpe_api_writer with production-built rows:
- W1 CATALOG: the definer function, its EXECUTE list, its owner's exact matrix (insert and read,
  never update) and policies.
- W2 SAVED: a new bundle stores all four parts. W3 REPLAY: identical, and nothing changes.
- W4 and W5: a different run or detail under a stored run is refused, and nothing is written.
- W6 ATOMIC: a failure inside, or a refusal inside 0015's function, keeps none of it, the run and
  the detail included.
- W7 MALFORMED: an unknown key, or another run's prediction, fails with 22023 and writes nothing.
- W8 CALLERS: anon, and every role but the writer, are refused.
- W9 ONE_SHOT and ROLLBACK: a second application is refused (UP017), and the rollback restores the
  post-0016 catalog exactly.
- W10 PRODUCTION_WRITER: production's REST writer as released with W-A and E4, on the applied 0017:
  - the least-privilege writer sends the API key in `apikey` and its JWT in `Authorization`;
  - each forecast bundle is ONE call to the forecast RPC, and the run and the detail are never sent
    beside it;
  - a new analysis is SAVED whole, and an identical replay is SAVED;
  - a conflicting run identity and a conflicting prediction are NOT_SAVED (CONFLICT), with nothing
    changed;
  - service_role (until D6) still saves through the same RPC.

P2, P6 and P8 run the writer as it was live when 0016 was applied, and as an H2-safe rollback
target runs it: the W-B path, B9's bundle with the run and the detail written beside it.

J1 SIGNING_KEY (E3, the supported Supabase path for a custom-role JWT). A second PostgREST trusts
only a scratch ES256 key with a kid (scripts/privilege_rehearsal/es256.py), as a project trusts its
imported, rotated-in signing key. On it:
- a token signed by that key, claiming ucpe_api_writer with a short expiry, runs as the writer. It
  reads runs, is refused outcomes, and production's two-header writer SAVES through the forecast
  RPC;
- an unknown kid, a tampered signature, another key under the same kid, an expired token and a
  token signed with the HS256 secret are each refused (401);
- the same key also signs a service_role token that is accepted. That is why the signing key stays
  with the owner and never goes into the Space: only a short-lived writer token does.

Runs ONLY against a CI runner's scratch PostgreSQL and the PostgREST started there. It refuses to
run beside any production variable, and it names no secret: its passwords and its JWT key are
scratch values that live for one run.
"""

from __future__ import annotations

import argparse
import base64
import dataclasses
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "src"):
    if str(_path) in sys.path:
        sys.path.remove(str(_path))
    sys.path.insert(0, str(_path))

HERE = Path(__file__).resolve().parent
# Migration 0016 itself (the bytes its one-shot route pins), and its rollback.
DRAFT = ROOT / "migrations" / "0016_least_privilege_roles.sql"
ROLLBACK = HERE / "rollback_0016.sql"
# Migration 0017 itself (the bytes its one-shot route pins), and its rollback.
DRAFT_0017 = ROOT / "migrations" / "0017_forecast_bundle_rpc.sql"
ROLLBACK_0017 = HERE / "rollback_0017.sql"
SCHEMA_VERSION = "privilege-rehearsal.v1"
# P1-P8: the roles (migration 0016). W1-W9: the whole core bundle in one transaction (migration
# 0017).
CRITERIA = (
    "P1",
    "P2",
    "P3",
    "P4",
    "P5",
    "P6",
    "P7",
    "P8",
    "W1",
    "W2",
    "W3",
    "W4",
    "W5",
    "W6",
    "W7",
    "W8",
    "W9",
    "W10",
    "J1",
)
WIDE_CRITERIA = tuple(name for name in CRITERIA if name.startswith("W"))
REST_BASE = "https://rehearsal.invalid"
OPERATOR = "privrehearsal"
# E3 (J1): the second PostgREST, which trusts only the scratch ES256 key, and that key's file.
ES256_ENVIRONMENT = (
    "PRIVILEGE_REHEARSAL_ES256_POSTGREST_URL",
    "PRIVILEGE_REHEARSAL_ES256_POSTGREST_ADMIN_URL",
    "PRIVILEGE_REHEARSAL_ES256_KEY_FILE",
)
FORBIDDEN_ENVIRONMENT = (
    "SUPABASE_DB_URL",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_PUBLISHABLE_KEY",
    "SUPABASE_WRITER_JWT",
)
_LOCAL_SOCKET_URL = re.compile(r"postgresql:///[a-z_][a-z0-9_]*\?host=/var/run/postgresql")
_LOCAL_HTTP = re.compile(r"http://127\.0\.0\.1:[0-9]{2,5}")

NEW_ROLES = ("ucpe_api_writer", "ucpe_bundle_owner", "ucpe_space_db", "ucpe_resolver")
LOGIN_ROLES = ("ucpe_space_db", "ucpe_resolver")
API_ROLES = ("anon", "authenticated", "service_role")
TABLES = (
    "analysis_run_details",
    "analysis_runs",
    "analysis_timeframe_results",
    "app_events",
    "automation_credential",
    "automation_radar_ledger",
    "news_clusters",
    "news_evidence_links",
    "news_items",
    "prediction_derivatives_snapshots",
    "prediction_feature_snapshots",
    "prediction_outcomes",
    "prediction_resolution_status",
    "predictions",
    "provider_observations",
    "section_5a_evaluation_seal",
    "watchlist",
)
SEQUENCES = (
    "analysis_timeframe_results_id_seq",
    "app_events_id_seq",
    "provider_observations_id_seq",
)
BUNDLE = "public.save_prediction_bundle(jsonb, jsonb, jsonb)"
BASE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
POLICY_COMMANDS = ("SELECT", "INSERT", "UPDATE", "DELETE")
SEARCH_PATH = ["search_path=pg_catalog, pg_temp"]

_UPSERTED = frozenset({"SELECT", "INSERT", "UPDATE"})
# The design, and nothing else (migration 0016's comments give each line's reason).
EXPECTED_TABLES: dict[str, dict[str, frozenset[str]]] = {
    "ucpe_api_writer": {
        "analysis_runs": _UPSERTED,
        "analysis_run_details": _UPSERTED,
        "news_items": _UPSERTED,
        "news_clusters": _UPSERTED,
        "news_evidence_links": _UPSERTED,
        "analysis_timeframe_results": frozenset({"INSERT"}),
        "provider_observations": frozenset({"INSERT"}),
        "watchlist": frozenset({"SELECT", "INSERT", "UPDATE", "DELETE"}),
        "predictions": frozenset({"SELECT"}),
    },
    "ucpe_bundle_owner": {
        "predictions": frozenset({"SELECT", "INSERT"}),
        "prediction_feature_snapshots": frozenset({"SELECT", "INSERT"}),
        "prediction_derivatives_snapshots": frozenset({"SELECT", "INSERT"}),
    },
    "ucpe_space_db": {
        "predictions": frozenset({"SELECT"}),
        "prediction_outcomes": frozenset({"SELECT"}),
        "automation_credential": frozenset({"SELECT"}),
        "automation_radar_ledger": frozenset({"SELECT", "INSERT", "UPDATE"}),
    },
    "ucpe_resolver": {
        "predictions": frozenset({"SELECT"}),
        "prediction_outcomes": frozenset({"SELECT", "INSERT"}),
        "prediction_resolution_status": frozenset({"SELECT", "INSERT", "UPDATE"}),
    },
}
EXPECTED_SEQUENCES: dict[str, dict[str, frozenset[str]]] = {
    "ucpe_api_writer": {
        "analysis_timeframe_results_id_seq": frozenset({"USAGE"}),
        "provider_observations_id_seq": frozenset({"USAGE"}),
    },
}
EXPECTED_EXECUTE = {
    "ucpe_api_writer": True,
    "service_role": True,
    "anon": False,
    "authenticated": False,
    "public": False,
    "ucpe_space_db": False,
    "ucpe_resolver": False,
}


# ------------------------------------------------------------------------- pure verdict helpers


def table_privileges(server_version_num: int) -> tuple[str, ...]:
    """MAINTAIN exists from PostgreSQL 17 (production runs 17)."""

    return BASE_PRIVILEGES + (("MAINTAIN",) if server_version_num >= 170000 else ())


def expected_policies() -> set[tuple[str, str, str]]:
    """One permissive policy per (table, role, command) the design grants, for row commands only."""

    return {
        (table, role, command)
        for role, tables in EXPECTED_TABLES.items()
        for table, privileges in tables.items()
        for command in POLICY_COMMANDS
        if command in privileges
    }


def matrix_differences(
    observed: dict[str, dict[str, set[str]]],
    expected: dict[str, dict[str, frozenset[str]]],
    roles: tuple[str, ...],
    objects: tuple[str, ...],
) -> list[str]:
    """Every (role, object) whose held privileges differ from the design, missing or extra."""

    differences = []
    for role in roles:
        for name in objects:
            held = set(observed.get(role, {}).get(name, set()))
            wanted = set(expected.get(role, {}).get(name, frozenset()))
            if held != wanted:
                differences.append(
                    f"{role} on {name}: missing {sorted(wanted - held)},"
                    f" extra {sorted(held - wanted)}"
                )
    return differences


def refused(outcomes: dict[str, str | None]) -> list[str]:
    """The probes NOT refused for privilege (SQLSTATE 42501): an empty list means every one was.

    Any other answer, success or another error, fails it: a typo never passes as a refusal.
    """

    return sorted(name for name, sqlstate in outcomes.items() if sqlstate != "42501")


def verdict(failures: list[str], **details: Any) -> dict[str, Any]:
    return {"verdict": "PASS" if not failures else "FAIL", "failures": failures, **details}


def unmet(criteria: dict[str, dict[str, Any]]) -> list[str]:
    return [name for name in CRITERIA if criteria.get(name, {}).get("verdict") != "PASS"]


def mint_jwt(role: str, key: str, *, now: int | None = None) -> str:
    """An HS256 JWT naming a role, signed with this run's scratch key, as PostgREST verifies it."""

    issued = int(time.time()) if now is None else now

    def b64(raw: bytes) -> bytes:
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims = b64(
        json.dumps(
            {"role": role, "iat": issued, "exp": issued + 900}, separators=(",", ":")
        ).encode()
    )
    signing_input = header + b"." + claims
    signature = b64(hmac.new(key.encode(), signing_input, hashlib.sha256).digest())
    return (signing_input + b"." + signature).decode()


# ------------------------------------------------------------------------- the database


class Database:
    """The scratch database: the owner over the unix socket, the login roles over local TCP."""

    def __init__(self, owner_url: str, name: str, port: int) -> None:
        self.owner_url = owner_url
        self.name = name
        self.port = port
        self.logins: dict[str, str] = {}

    def owner(self, statement: Any, params: Any = None) -> list[tuple] | None:
        import psycopg

        with psycopg.connect(self.owner_url, autocommit=False) as conn, conn.cursor() as cur:
            cur.execute(statement, params)
            rows = cur.fetchall() if cur.description else None
            conn.commit()
            return rows

    def apply(self, path: Path) -> str | None:
        """One file in one transaction as the owner. The SQLSTATE of a refusal, else None."""

        import psycopg

        try:
            with psycopg.connect(self.owner_url, autocommit=False) as conn:
                conn.execute(path.read_text(encoding="utf-8"))
                conn.commit()
        except psycopg.Error as exc:
            return exc.sqlstate or "ERROR"
        return None

    def grant_login(self, role: str) -> None:
        """The owner's credential step, rehearsed: LOGIN and a scratch password for one run."""

        from psycopg import sql

        value = secrets.token_hex(24)
        self.owner(
            sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(value)
            )
        )
        self.logins[role] = value

    def login_url(self, role: str) -> str:
        return f"postgresql://{role}:{self.logins[role]}@127.0.0.1:{self.port}/{self.name}"

    def attempt(self, url: str, statement: str, params: Any = None) -> str | None:
        """One statement in its own transaction, rolled back. The SQLSTATE if refused, else None."""

        import psycopg

        try:
            with psycopg.connect(url, autocommit=False) as conn:
                conn.execute(statement, params)
                conn.rollback()
        except psycopg.Error as exc:
            return exc.sqlstate or "ERROR"
        return None

    def count(self, table: str, **where: Any) -> int:
        """Rows of one table matching every column = value given, read as the owner."""

        from psycopg import sql

        condition = sql.SQL(" AND ").join(
            sql.SQL("{} = {}").format(sql.Identifier(column), sql.Placeholder(column))
            for column in where
        )
        statement = sql.SQL("SELECT count(*) FROM {}.{} WHERE {}").format(
            sql.Identifier("public"), sql.Identifier(table), condition
        )
        return int(self.owner(statement, where)[0][0])

    def counts(self) -> dict[str, int]:
        return {
            table: int(self.owner(f"SELECT count(*) FROM public.{table}")[0][0])  # noqa: S608
            for table in TABLES
        }


SNAPSHOT_SQL = {
    "roles": (
        "SELECT rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb, rolcanlogin,"
        " rolreplication,"
        " rolbypassrls FROM pg_catalog.pg_roles WHERE rolname LIKE 'ucpe\\_%' ORDER BY 1"
    ),
    "memberships": (
        "SELECT r.rolname, m.rolname, a.admin_option, a.inherit_option, a.set_option"
        " FROM pg_catalog.pg_auth_members a"
        " JOIN pg_catalog.pg_roles r ON r.oid = a.roleid"
        " JOIN pg_catalog.pg_roles m ON m.oid = a.member"
        " WHERE r.rolname LIKE 'ucpe\\_%' OR m.rolname LIKE 'ucpe\\_%'"
        " OR m.rolname = 'authenticator'"
        " ORDER BY 1, 2, 3, 4, 5"
    ),
    "relation_acl": (
        "SELECT c.relname, coalesce(g.rolname, 'PUBLIC'), x.privilege_type, x.is_grantable"
        " FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace"
        " CROSS JOIN LATERAL pg_catalog.aclexplode(coalesce(c.relacl, pg_catalog.acldefault("
        "   CASE WHEN c.relkind = 'S' THEN 's'::\"char\" ELSE 'r'::\"char\" END, c.relowner))) x"
        " LEFT JOIN pg_catalog.pg_roles g ON g.oid = x.grantee"
        " WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'S') ORDER BY 1, 2, 3"
    ),
    "relation_owners": (
        "SELECT c.relname, o.rolname FROM pg_catalog.pg_class c"
        " JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace"
        " JOIN pg_catalog.pg_roles o ON o.oid = c.relowner"
        " WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'S', 'v', 'm') ORDER BY 1"
    ),
    "function": (
        "SELECT o.rolname, p.prosecdef, p.proconfig, pg_catalog.md5(p.prosrc)"
        " FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_roles o ON o.oid = p.proowner"
        f" WHERE p.oid = '{BUNDLE}'::pg_catalog.regprocedure"
    ),
    "function_acl": (
        "SELECT coalesce(g.rolname, 'PUBLIC'), gr.rolname, x.privilege_type"
        " FROM pg_catalog.pg_proc p"
        " CROSS JOIN LATERAL pg_catalog.aclexplode("
        "   coalesce(p.proacl, pg_catalog.acldefault('f', p.proowner))) x"
        " LEFT JOIN pg_catalog.pg_roles g ON g.oid = x.grantee"
        " JOIN pg_catalog.pg_roles gr ON gr.oid = x.grantor"
        f" WHERE p.oid = '{BUNDLE}'::pg_catalog.regprocedure ORDER BY 1, 2, 3"
    ),
    "functions_owned_by_new_roles": (
        "SELECT p.oid::pg_catalog.regprocedure::text, o.rolname FROM pg_catalog.pg_proc p"
        " JOIN pg_catalog.pg_roles o ON o.oid = p.proowner"
        " WHERE o.rolname LIKE 'ucpe\\_%' ORDER BY 1"
    ),
    "schema_acl": (
        "SELECT coalesce(g.rolname, 'PUBLIC'), x.privilege_type FROM pg_catalog.pg_namespace n"
        " CROSS JOIN LATERAL pg_catalog.aclexplode("
        "   coalesce(n.nspacl, pg_catalog.acldefault('n', n.nspowner))) x"
        " LEFT JOIN pg_catalog.pg_roles g ON g.oid = x.grantee"
        " WHERE n.nspname = 'public' ORDER BY 1, 2"
    ),
    "policies": (
        "SELECT tablename, policyname, permissive, roles::text, cmd, qual, with_check"
        " FROM pg_catalog.pg_policies WHERE schemaname = 'public' ORDER BY 1, 2"
    ),
}


def _plain(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value if value is None or isinstance(value, (bool, int, str)) else str(value)


def sizes(state: dict[str, list]) -> dict[str, int]:
    """How many catalog rows each comparison holds: an empty comparison would prove nothing."""

    return {name: len(rows) for name, rows in state.items()}


def snapshot(db: Database) -> dict[str, list]:
    return {name: _plain(db.owner(statement) or []) for name, statement in SNAPSHOT_SQL.items()}


def held(
    db: Database, roles: tuple[str, ...], privileges: tuple[str, ...]
) -> dict[str, dict[str, set[str]]]:
    rows = db.owner(
        "SELECT r, t, p, pg_catalog.has_table_privilege(r, 'public.' || t, p)"
        " FROM unnest(%s::text[]) r, unnest(%s::text[]) t, unnest(%s::text[]) p",
        (list(roles), list(TABLES), list(privileges)),
    )
    matrix: dict[str, dict[str, set[str]]] = {}
    for role, table, privilege, has in rows or []:
        if has:
            matrix.setdefault(role, {}).setdefault(table, set()).add(privilege)
    return matrix


def held_sequences(db: Database, roles: tuple[str, ...]) -> dict[str, dict[str, set[str]]]:
    rows = db.owner(
        "SELECT r, s, p, pg_catalog.has_sequence_privilege(r, 'public.' || s, p)"
        " FROM unnest(%s::text[]) r, unnest(%s::text[]) s, unnest(%s::text[]) p",
        (list(roles), list(SEQUENCES), ["USAGE", "SELECT", "UPDATE"]),
    )
    matrix: dict[str, dict[str, set[str]]] = {}
    for role, sequence, privilege, has in rows or []:
        if has:
            matrix.setdefault(role, {}).setdefault(sequence, set()).add(privilege)
    return matrix


def server_version_num(db: Database) -> int:
    return int(db.owner("SHOW server_version_num")[0][0])


def owner_role(db: Database) -> str:
    return str(db.owner("SELECT current_user")[0][0])


# ------------------------------------------------------------------------- PostgREST


def gateway_client(postgrest_url: str):
    """Strips Supabase's /rest/v1 prefix, as its gateway does, and forwards to local PostgREST."""

    import httpx

    upstream = httpx.URL(postgrest_url)

    class Gateway(httpx.BaseTransport):
        def __init__(self) -> None:
            self._transport = httpx.HTTPTransport()

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            raw = request.url.raw_path
            if not raw.startswith(b"/rest/v1/"):
                return httpx.Response(404)
            url = request.url.copy_with(
                scheme=upstream.scheme,
                host=upstream.host,
                port=upstream.port,
                raw_path=raw[len(b"/rest/v1") :],
            )
            headers = [(k, v) for k, v in request.headers.raw if k.lower() != b"host"]
            return self._transport.handle_request(
                httpx.Request(request.method, url, headers=headers, content=request.read())
            )

        def close(self) -> None:
            self._transport.close()

    return httpx.Client(transport=Gateway(), timeout=10.0)


def wait_for_reload(postgrest_url: str, admin_url: str | None) -> None:
    """PostgREST reloads its schema cache on NOTIFY; give it a moment and require it ready again."""

    import httpx

    time.sleep(1.0)
    if not admin_url:
        return
    for _ in range(40):
        try:
            if httpx.get(f"{admin_url}/ready", timeout=2.0).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise RuntimeError("PostgREST did not become ready again after a schema reload")


# ------------------------------------------------------------------ production's own analysis


LIVE = {
    "is_live_data": True,
    "data_source": "BINANCE_PUBLIC",
    "cross_provider_state": "UNAVAILABLE",
}
PROVIDER = {"status": "OK", "active_provider": "binance"}


def analysis_work() -> tuple[Any, dict]:
    """One full analysis as the live service persists it: PERS-0's construction and code."""

    from crypto_probability_engine.api.analysis_service import (
        _persistence_work,
        _prediction_row,
        analyze_request,
    )
    from crypto_probability_engine.api.schemas import AnalysisRequest
    from crypto_probability_engine.config.settings import Settings
    from crypto_probability_engine.persistence.feature_snapshot import build_feature_snapshot
    from crypto_probability_engine.persistence.run_store import InMemoryRunStore
    from crypto_probability_engine.quant.pipeline import run_quant_pipeline
    from crypto_probability_engine.quant_v2.contract import build_quant_v2_shadow
    from tests.fixtures.market_data import make_snapshot

    payload = analyze_request(
        AnalysisRequest(symbol="BTC/USDT", timeframe="4H"),
        settings=Settings(data_mode="fixture"),
        run_store=InMemoryRunStore(limit=50),
    )
    payload["run_id"] = f"privrehearsal_{uuid.uuid4().hex}"
    snapshot_data = make_snapshot(provider="binance", timeframe="4H")
    quant = run_quant_pipeline(snapshot_data, PROVIDER)
    row = _prediction_row(
        run_id=payload["run_id"],
        request_symbol="BTC",
        normalized_symbol="BTC/USDT",
        timeframe="4H",
        snapshot=snapshot_data,
        quant_result=quant,
        data_quality=LIVE,
        provider_state=PROVIDER,
    )
    if row is None:
        raise RuntimeError("the writer built no prediction row")
    block = build_quant_v2_shadow(
        quant_result=quant,
        snapshot=snapshot_data,
        provider_state=PROVIDER,
        symbol="BTC",
        normalized_symbol="BTC/USDT",
        timeframe="4H",
    )
    work = _persistence_work(payload, "OK", consume_pending=False)
    # As the live service schedules a USER_REQUESTED analysis: the detail inside the core bundle.
    work = dataclasses.replace(
        work,
        prediction_rows=(row,),
        feature_snapshot_rows=(build_feature_snapshot(row, block),),
        run_detail_row=detail_row(payload),
    )
    return work, payload


def detail_row(payload: dict) -> dict:
    from crypto_probability_engine.utils.sanitize import sanitize_for_export

    return {
        "run_id": payload["run_id"],
        "analysis_hash": payload.get("analysis_hash"),
        "detail_payload": sanitize_for_export(payload["detail_view"]),
    }


def outcome_for(prediction: dict) -> dict:
    """A resolver-shaped outcome (migration 0014's rehearsal shape)."""

    return {
        "prediction_id": prediction["prediction_id"],
        "resolved_at_utc": prediction["horizon_end_utc"],
        "outcome_close_utc": prediction["horizon_end_utc"],
        "outcome_reference_price": 121.5,
        "terminal_return_frac": 0.0045,
        "realized_label": "TIMEOUT",
        "decision_band_frac": prediction["decision_band_frac"],
        "max_favorable_frac": 0.01,
        "max_adverse_frac": -0.01,
        "candles_observed": 6,
        "resolver_version": "rehearsal",
        "data_source": "BINANCE_PUBLIC",
        "is_live_data": True,
    }


class B9Writer:
    """The REST writer without W-A's save_forecast_bundle: the W-B path, as the app live when 0016
    was applied, and any H2-safe rollback target, persists."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        if name == "save_forecast_bundle":
            raise AttributeError(name)
        return getattr(self._inner, name)


def persist_through_rest(repository: Any, work: Any) -> tuple[Any, str]:
    """The W-B path (P2, P6, P8)."""

    from crypto_probability_engine.api.analysis_service import _persist_work_confirmed

    confirmation = _persist_work_confirmed(work, B9Writer(repository))
    return confirmation, repository.circuit_state()


def persist_through_forecast(repository: Any, work: Any) -> tuple[Any, str]:
    """The W-A path, as released (W10)."""

    from crypto_probability_engine.api.analysis_service import _persist_work_confirmed

    confirmation = _persist_work_confirmed(work, repository)
    return confirmation, repository.circuit_state()


# ------------------------------------------------------------------------- the criteria


def criterion_matrix(db: Database, version: int, owner: str) -> dict[str, Any]:
    failures: list[str] = []
    privileges = table_privileges(version)
    failures += matrix_differences(
        held(db, NEW_ROLES, privileges), EXPECTED_TABLES, NEW_ROLES, TABLES
    )
    failures += matrix_differences(
        held_sequences(db, NEW_ROLES), EXPECTED_SEQUENCES, NEW_ROLES, SEQUENCES
    )
    execute = {
        role: bool(
            db.owner("SELECT pg_catalog.has_function_privilege(%s, %s, 'EXECUTE')", (role, BUNDLE))[
                0
            ][0]
        )
        for role in EXPECTED_EXECUTE
    }
    failures += [
        f"EXECUTE for {role} is {execute[role]}"
        for role in EXPECTED_EXECUTE
        if execute[role] != EXPECTED_EXECUTE[role]
    ]
    function = db.owner(SNAPSHOT_SQL["function"])[0]
    if (
        function[0] != "ucpe_bundle_owner"
        or function[1] is not True
        or list(function[2] or []) != SEARCH_PATH
    ):
        failures.append(
            f"the bundle RPC is {function[:3]}, not SECURITY DEFINER owned by ucpe_bundle_owner"
        )
    schema = {
        (role, privilege): bool(
            db.owner("SELECT pg_catalog.has_schema_privilege(%s, 'public', %s)", (role, privilege))[
                0
            ][0]
        )
        for role in NEW_ROLES
        for privilege in ("USAGE", "CREATE")
    }
    failures += [
        f"schema public {privilege} for {role} is {value}"
        for (role, privilege), value in schema.items()
        if value != (privilege == "USAGE")
    ]
    attributes = {row[0]: row[1:] for row in db.owner(SNAPSHOT_SQL["roles"]) or []}
    for role in NEW_ROLES:
        found = attributes.get(role)
        wanted = (False, False, False, False, role in LOGIN_ROLES, False, False)
        if found is None or tuple(found) != wanted:
            failures.append(f"role {role} attributes {found} != {wanted}")
    memberships = {tuple(row) for row in db.owner(SNAPSHOT_SQL["memberships"]) or []}
    allowed = {("ucpe_api_writer", "authenticator", False, False, True)}
    allowed |= {(api, "authenticator", False, False, True) for api in API_ROLES}
    # PostgreSQL 16+: a CREATEROLE creator keeps ADMIN OPTION (no SET, no INHERIT) on its roles.
    allowed |= {(role, owner, True, False, False) for role in NEW_ROLES}
    failures += [f"unexpected membership {row}" for row in sorted(memberships - allowed)]
    if ("ucpe_api_writer", "authenticator", False, False, True) not in memberships:
        failures.append("authenticator cannot switch to ucpe_api_writer")
    owned = [row for row in db.owner(SNAPSHOT_SQL["relation_owners"]) or [] if row[1] in NEW_ROLES]
    failures += [f"relation {name} owned by {role}" for name, role in owned]
    functions = [tuple(row) for row in db.owner(SNAPSHOT_SQL["functions_owned_by_new_roles"]) or []]
    if functions != [("save_prediction_bundle(jsonb,jsonb,jsonb)", "ucpe_bundle_owner")]:
        failures.append(f"functions owned by the new roles: {functions}")
    policies = db.owner(SNAPSHOT_SQL["policies"]) or []
    found_policies: set[tuple[str, str, str]] = set()
    for table, _name, permissive, roles, command, qual, with_check in policies:
        names = roles.strip("{}").split(",")
        new = [name for name in names if name in NEW_ROLES]
        if not new:
            continue
        if len(names) != 1 or permissive != "PERMISSIVE":
            failures.append(f"policy on {table} for {roles} is not one permissive role")
        expected_qual = "true" if command in ("SELECT", "UPDATE", "DELETE") else None
        expected_check = "true" if command in ("INSERT", "UPDATE") else None
        if qual != expected_qual or with_check != expected_check:
            failures.append(f"policy on {table} for {roles} {command} is ({qual}, {with_check})")
        found_policies.add((table, new[0], command))
    wanted_policies = expected_policies()
    failures += [f"missing policy {item}" for item in sorted(wanted_policies - found_policies)]
    failures += [f"extra policy {item}" for item in sorted(found_policies - wanted_policies)]
    return verdict(
        failures, execute=execute, policies=len(found_policies), memberships=sorted(memberships)
    )


def criterion_writer(db: Database, rest: Callable[[str], Any]) -> tuple[dict[str, Any], dict]:
    """P2. Returns the verdict and the saved prediction (for P4 and P5)."""

    from crypto_probability_engine.api.analysis_service import RECEIPT_NOT_SAVED, RECEIPT_SAVED

    failures: list[str] = []
    steps: dict[str, Any] = {}
    work, payload = analysis_work()
    prediction = work.prediction_rows[0]
    run_id = payload["run_id"]
    writer = rest("ucpe_api_writer")
    confirmation, circuit = persist_through_rest(writer, work)
    steps["first"] = [
        confirmation.receipt,
        confirmation.receipt_reason,
        confirmation.overall,
        circuit,
    ]
    if (confirmation.receipt, confirmation.overall, circuit) != (RECEIPT_SAVED, "OK", "CLOSED"):
        failures.append(f"the analysis was not SAVED: {steps['first']}")
    steps["detail_in_the_core_bundle"] = work.run_detail_row is not None
    if work.run_detail_row is None:
        failures.append("the analysis carries no detail row")
    run_tables = (
        "analysis_runs",
        "analysis_run_details",
        "analysis_timeframe_results",
        "provider_observations",
        "predictions",
    )
    rows = {table: db.count(table, run_id=run_id) for table in run_tables}
    rows["prediction_feature_snapshots"] = db.count(
        "prediction_feature_snapshots", prediction_id=prediction["prediction_id"]
    )
    steps["rows"] = rows
    expected_rows = {
        "analysis_runs",
        "analysis_run_details",
        "predictions",
        "prediction_feature_snapshots",
    }
    if work.timeframe_result is not None:
        expected_rows.add("analysis_timeframe_results")
    if work.provider_observations:
        expected_rows.add("provider_observations")
    failures += [f"no {table} row stored" for table in sorted(expected_rows) if rows[table] < 1]

    reader = rest("ucpe_api_writer")  # a fresh repository: its in-memory fallback is empty
    origin = prediction.get("prediction_origin") or "USER_REQUESTED"
    read_back = {
        "get_run": reader.get_run(run_id) is not None,
        "get_run_detail": reader.get_run_detail(run_id, prediction_origin=origin) is not None,
        "recent_runs": any(run.get("run_id") == run_id for run in reader.recent_runs(50)),
        "run_ids_with_detail": run_id
        in reader.run_ids_with_detail([run_id], prediction_origin=origin),
        "circuit": reader.circuit_state(),
    }
    steps["read_back"] = read_back
    failures += [
        f"read-back {name} failed"
        for name, ok in read_back.items()
        if ok is not True and name != "circuit"
    ]
    if read_back["circuit"] != "CLOSED":
        failures.append("a read opened the writer's circuit")

    symbol = f"PR{uuid.uuid4().hex[:6].upper()}/USDT"
    watch = rest("ucpe_api_writer")
    added = watch.add_watchlist(symbol, operator_id=OPERATOR)
    stored_watch = db.count("watchlist", operator_id=OPERATOR, normalized_symbol=symbol)
    listed = symbol in rest("ucpe_api_writer").list_watchlist(operator_id=OPERATOR)
    removed = watch.remove_watchlist(symbol, operator_id=OPERATOR)
    left = db.count("watchlist", operator_id=OPERATOR, normalized_symbol=symbol)
    steps["watchlist"] = [added, stored_watch, listed, removed, left, watch.circuit_state()]
    if steps["watchlist"] != ["OK", 1, True, "OK", 0, "CLOSED"]:
        failures.append(f"the watchlist did not round-trip: {steps['watchlist']}")

    replay, circuit = persist_through_rest(rest("ucpe_api_writer"), work)
    steps["replay"] = [replay.receipt, replay.receipt_reason, circuit]
    if (replay.receipt, circuit) != (RECEIPT_SAVED, "CLOSED"):
        failures.append(f"the identical replay was not SAVED: {steps['replay']}")
    changed = {**prediction, "reference_price": float(prediction["reference_price"]) * 1.01}
    conflict, _ = persist_through_rest(
        rest("ucpe_api_writer"), dataclasses.replace(work, prediction_rows=(changed,))
    )
    kept = db.owner(
        "SELECT reference_price::float8 FROM public.predictions WHERE prediction_id = %s",
        (prediction["prediction_id"],),
    )[0][0]
    steps["conflict"] = [conflict.receipt, conflict.receipt_reason]
    if (conflict.receipt, conflict.receipt_reason) != (RECEIPT_NOT_SAVED, "CONFLICT"):
        failures.append(f"the conflicting analysis was not refused: {steps['conflict']}")
    if abs(float(kept) - float(prediction["reference_price"])) > 1e-9 * max(1.0, abs(float(kept))):
        failures.append("the conflicting analysis changed the stored prediction")
    return verdict(failures, steps=steps), prediction


def criterion_writer_refusals(
    db: Database, raw: Callable[..., Any], prediction: dict, owner: str
) -> dict[str, Any]:
    """P3: requests the writer's list does not contain, each refused, writing nothing."""

    before = db.counts()
    fresh = {
        **prediction,
        "prediction_id": f"{prediction['prediction_id']}:direct",
        "run_id": "privrehearsal_direct",
    }
    pid = prediction["prediction_id"]
    probes = {
        "POST predictions (around the RPC)": ("POST", "predictions", {}, fresh),
        "POST prediction_feature_snapshots": (
            "POST",
            "prediction_feature_snapshots",
            {},
            {"prediction_id": fresh["prediction_id"]},
        ),
        "POST prediction_derivatives_snapshots": (
            "POST",
            "prediction_derivatives_snapshots",
            {},
            {"prediction_id": fresh["prediction_id"]},
        ),
        "POST prediction_outcomes (labels)": (
            "POST",
            "prediction_outcomes",
            {},
            outcome_for(prediction),
        ),
        "GET prediction_outcomes": (
            "GET",
            "prediction_outcomes",
            {"select": "prediction_id", "limit": "1"},
            None,
        ),
        "PATCH predictions": (
            "PATCH",
            "predictions",
            {"prediction_id": f"eq.{pid}"},
            {"reference_price": 1},
        ),
        "DELETE predictions": ("DELETE", "predictions", {"prediction_id": f"eq.{pid}"}, None),
        "DELETE analysis_runs": (
            "DELETE",
            "analysis_runs",
            {"run_id": f"eq.{prediction['run_id']}"},
            None,
        ),
        "PATCH analysis_timeframe_results": (
            "PATCH",
            "analysis_timeframe_results",
            {"run_id": f"eq.{prediction['run_id']}"},
            {"timeframe": "1D"},
        ),
        "GET analysis_timeframe_results": (
            "GET",
            "analysis_timeframe_results",
            {"limit": "1"},
            None,
        ),
        "GET provider_observations": ("GET", "provider_observations", {"limit": "1"}, None),
        "GET automation_credential": ("GET", "automation_credential", {"limit": "1"}, None),
        "GET automation_radar_ledger": ("GET", "automation_radar_ledger", {"limit": "1"}, None),
        "GET section_5a_evaluation_seal": (
            "GET",
            "section_5a_evaluation_seal",
            {"limit": "1"},
            None,
        ),
        "GET prediction_resolution_status": (
            "GET",
            "prediction_resolution_status",
            {"limit": "1"},
            None,
        ),
        "GET app_events": ("GET", "app_events", {"limit": "1"}, None),
        "POST app_events": ("POST", "app_events", {}, {"event_type": "privrehearsal"}),
        "GET prediction_feature_snapshots": (
            "GET",
            "prediction_feature_snapshots",
            {"limit": "1"},
            None,
        ),
    }
    outcomes: dict[str, Any] = {}
    failures: list[str] = []
    for name, (method, path, params, body) in probes.items():
        status, code = raw("ucpe_api_writer", method, path, params, body)
        outcomes[name] = [status, code]
        if not (status in (401, 403) and code == "42501"):
            failures.append(f"{name} was not refused for privilege: {status} {code}")
    for role in ("ucpe_space_db", "ucpe_resolver", "ucpe_bundle_owner", owner, "postgres"):
        status, code = raw(
            role, "GET", "predictions", {"select": "prediction_id", "limit": "1"}, None
        )
        outcomes[f"a JWT naming {role}"] = [status, code]
        if 200 <= status < 300:
            failures.append(f"a JWT naming {role} was served ({status})")
    for method, path, body in (
        ("GET", "predictions", None),
        ("POST", "rpc/save_prediction_bundle", {"p_prediction": prediction}),
    ):
        status, code = raw(None, method, path, {}, body)
        outcomes[f"anon {method} {path}"] = [status, code]
        if 200 <= status < 300:
            failures.append(f"anon {method} {path} was served ({status})")
    after = db.counts()
    if after != before:
        failures.append(f"a refused request changed rows: {before} -> {after}")
    return verdict(failures, outcomes=outcomes)


def criterion_space_db(db: Database, prediction: dict) -> dict[str, Any]:
    """P4: the Space's direct Postgres, production's code, as ucpe_space_db."""

    from crypto_probability_engine.calibration.service import build_calibration_report
    from crypto_probability_engine.persistence.repository import SupabasePersistenceRepository
    from scripts.migration_0013_rehearsal import probe_app_sql as f1

    failures: list[str] = []
    details: dict[str, Any] = {}
    SupabasePersistenceRepository(db.owner_url).save_prediction_outcome(outcome_for(prediction))
    url = db.login_url("ucpe_space_db")
    rows = SupabasePersistenceRepository(url).fetch_resolved_prediction_outcomes_for_calibration(
        timeframe="4H"
    )
    details["calibration_rows"] = len(rows)
    if not any(row.get("prediction_id") == prediction["prediction_id"] for row in rows):
        failures.append("the calibration read did not return the resolved prediction")
    report = build_calibration_report(SupabasePersistenceRepository(url), timeframe="4H")
    details["calibration_report_repository"] = report.get("repository")
    if "metrics" not in report:
        failures.append("the calibration report has no metrics")

    def owner_sql(statement: str, params: dict | None = None):
        return db.owner(statement, params or {})

    f1.checks_passed.clear()
    try:
        f1.probe_registry(url, owner_sql)
        f1.probe_ledger(url, owner_sql)
        f1.probe_capacity(url, owner_sql)
    except SystemExit as exc:
        failures.append(f"F1 probe: {exc}")
    details["f1_checks_passed"] = len(f1.checks_passed)
    statements = {
        "INSERT predictions": (
            "INSERT INTO public.predictions (prediction_id) VALUES ('privrehearsal:x')"
        ),
        "INSERT prediction_outcomes": (
            "INSERT INTO public.prediction_outcomes (prediction_id) VALUES ('x')"
        ),
        "UPDATE prediction_outcomes": "UPDATE public.prediction_outcomes SET candles_observed = 1",
        "INSERT automation_credential": (
            "INSERT INTO public.automation_credential (credential_id, secret_sha256, status)"
            " VALUES ('privrehearsal-x', repeat('a', 64), 'ACTIVE')"
        ),
        "UPDATE automation_credential (revoke)": (
            "UPDATE public.automation_credential SET status = 'REVOKED', revoked_at_utc = now()"
        ),
        # The ledger's own DELETE and TRUNCATE are absent from P1's exact matrix. Its retention test
        # forbids naming them anywhere else, so the functional probes target core evidence.
        "DELETE predictions": "DELETE FROM public.predictions",
        "TRUNCATE prediction_outcomes": "TRUNCATE public.prediction_outcomes",
        "SELECT section_5a_evaluation_seal": (
            "SELECT 1 FROM public.section_5a_evaluation_seal LIMIT 1"
        ),
        "SELECT prediction_resolution_status": (
            "SELECT 1 FROM public.prediction_resolution_status LIMIT 1"
        ),
        "SELECT analysis_runs": "SELECT 1 FROM public.analysis_runs LIMIT 1",
        "SELECT prediction_feature_snapshots": (
            "SELECT 1 FROM public.prediction_feature_snapshots LIMIT 1"
        ),
        "CREATE TABLE in public": "CREATE TABLE public.privrehearsal_x (id int)",
        "DISABLE the append-only triggers": "ALTER TABLE public.predictions DISABLE TRIGGER ALL",
        "SET ROLE service_role": "SET ROLE service_role",
        "SET ROLE ucpe_api_writer": "SET ROLE ucpe_api_writer",
        "SET ROLE authenticator": "SET ROLE authenticator",
        "EXECUTE the bundle RPC": "SELECT public.save_prediction_bundle('{}'::jsonb, NULL, NULL)",
    }
    outcomes = {name: db.attempt(url, statement) for name, statement in statements.items()}
    details["refusals"] = outcomes
    failures += [f"{name} was not refused" for name in refused(outcomes)]
    return verdict(failures, **details)


def criterion_resolver(db: Database) -> dict[str, Any]:
    """P5: the resolver's repository and status store, production's code, as ucpe_resolver."""

    from crypto_probability_engine.api.analysis_service import _prediction_row
    from crypto_probability_engine.persistence.repository import SupabasePersistenceRepository
    from crypto_probability_engine.quant.pipeline import run_quant_pipeline
    from crypto_probability_engine.resolution.rq_v1 import StatusWrite
    from crypto_probability_engine.resolution.status_store import PgStatusStore
    from scripts.resolve_outcomes import EXACT_SOURCE_PROVIDERS, RESOLVER_VERSION
    from tests.fixtures.market_data import make_downtrend_snapshot

    failures: list[str] = []
    details: dict[str, Any] = {}
    snapshot_data = make_downtrend_snapshot(provider="binance", timeframe="4H")
    due = _prediction_row(
        run_id=f"privrehearsal_due_{uuid.uuid4().hex}",
        request_symbol="BTC",
        normalized_symbol="BTC/USDT",
        timeframe="4H",
        snapshot=snapshot_data,
        quant_result=run_quant_pipeline(snapshot_data, PROVIDER),
        data_quality=LIVE,
        provider_state=PROVIDER,
    )
    if due is None or SupabasePersistenceRepository(db.owner_url).save_prediction(due) != "OK":
        return verdict(["the due prediction could not be seeded as the owner"])
    url = db.login_url("ucpe_resolver")
    later = datetime(2100, 1, 1, tzinfo=UTC)
    repository = SupabasePersistenceRepository(url)
    scanned = repository.fetch_due_unresolved_predictions(later, 500)
    details["due_scan"] = len(scanned)
    if not any(row.get("prediction_id") == due["prediction_id"] for row in scanned):
        failures.append("the due scan did not return the due prediction")
    store = PgStatusStore(url)
    details["preflight"] = store.preflight()
    if details["preflight"] is not True:
        failures.append("the status store preflight failed")
    scan = store.fetch_due(
        later,
        500,
        venues=tuple(EXACT_SOURCE_PROVIDERS),
        timeframes=("4H",),
        prediction_origins=("USER_REQUESTED",),
    )
    details["status_due_scan"] = type(scan).__name__
    status = repository.save_prediction_outcome(
        {**outcome_for(due), "resolver_version": RESOLVER_VERSION}
    )
    details["outcome_insert"] = str(status)
    stored = store.read_outcome(due["prediction_id"])
    if stored is None:
        failures.append("the inserted outcome did not read back")
    now = datetime.now(UTC).replace(microsecond=0)
    first = StatusWrite(
        prediction_id=due["prediction_id"],
        resolution_status="RETRYABLE",
        attempt_count=1,
        first_attempt_utc=now,
        last_attempt_utc=now,
        first_reason="skip_terminal_bar_missing",
        last_reason="skip_terminal_bar_missing",
        next_eligible_utc=now + timedelta(hours=2),
        quarantined_at_utc=None,
        resolved_at_utc=None,
        policy_version="rq-v1",
        resolver_version=RESOLVER_VERSION,
    )
    second = dataclasses.replace(
        first,
        attempt_count=2,
        last_attempt_utc=now + timedelta(hours=2),
        last_reason="error_provider_unavailable",
        next_eligible_utc=now + timedelta(hours=4),
    )
    applied = [len(store.write_batch([first])), len(store.write_batch([second]))]
    details["status_upserts_applied"] = applied
    if applied != [1, 1]:
        failures.append(f"the status insert and update applied {applied}")
    statements = {
        "UPDATE prediction_outcomes": "UPDATE public.prediction_outcomes SET candles_observed = 1",
        "DELETE prediction_outcomes": "DELETE FROM public.prediction_outcomes",
        "TRUNCATE prediction_outcomes": "TRUNCATE public.prediction_outcomes",
        "INSERT predictions": (
            "INSERT INTO public.predictions (prediction_id) VALUES ('privrehearsal:y')"
        ),
        "DELETE prediction_resolution_status": "DELETE FROM public.prediction_resolution_status",
        "SELECT automation_credential": "SELECT 1 FROM public.automation_credential LIMIT 1",
        "SELECT automation_radar_ledger": "SELECT 1 FROM public.automation_radar_ledger LIMIT 1",
        "SELECT analysis_runs": "SELECT 1 FROM public.analysis_runs LIMIT 1",
        "SELECT section_5a_evaluation_seal": (
            "SELECT 1 FROM public.section_5a_evaluation_seal LIMIT 1"
        ),
        "CREATE TABLE in public": "CREATE TABLE public.privrehearsal_y (id int)",
        "SET ROLE service_role": "SET ROLE service_role",
        "EXECUTE the bundle RPC": "SELECT public.save_prediction_bundle('{}'::jsonb, NULL, NULL)",
    }
    outcomes = {name: db.attempt(url, statement) for name, statement in statements.items()}
    details["refusals"] = outcomes
    failures += [f"{name} was not refused" for name in refused(outcomes)]
    return verdict(failures, **details)


def criterion_unchanged(
    db: Database, version: int, before: dict[str, dict[str, set[str]]], rest: Callable[[str], Any]
) -> dict[str, Any]:
    from crypto_probability_engine.api.analysis_service import RECEIPT_SAVED

    failures: list[str] = []
    after = held(db, API_ROLES, table_privileges(version))
    if {role: {t: sorted(p) for t, p in tables.items()} for role, tables in after.items()} != {
        role: {t: sorted(p) for t, p in tables.items()} for role, tables in before.items()
    }:
        failures.append("an API role's table privileges changed")
    denied = {}
    for role in ("anon", "authenticated"):
        denied[role] = db.attempt(
            db.owner_url, f"SET LOCAL ROLE {role}; SELECT 1 FROM public.predictions LIMIT 1"
        )
    failures += [f"{role} read predictions" for role in refused(denied)]
    confirmation, circuit = persist_through_rest(rest("service_role"), analysis_work()[0])
    if (confirmation.receipt, circuit) != (RECEIPT_SAVED, "CLOSED"):
        failures.append(
            f"the live service_role writer did not persist: {confirmation.receipt} {circuit}"
        )
    return verdict(failures, denied=denied, service_role_receipt=confirmation.receipt)


# ------------------------------------------------------------------------- W-A, migration 0017


WIDE_FUNCTION = "public.save_forecast_bundle(jsonb, jsonb, jsonb, jsonb, jsonb)"
# W2: what the wider function's body writes, for its narrow owner: insert and read, never update.
WIDE_OWNER_TABLES = {
    **EXPECTED_TABLES["ucpe_bundle_owner"],
    "analysis_runs": frozenset({"SELECT", "INSERT"}),
    "analysis_run_details": frozenset({"SELECT", "INSERT"}),
}
WIDE_EXECUTE = {
    "ucpe_api_writer": True,
    "service_role": True,
    "anon": False,
    "authenticated": False,
    "public": False,
    "ucpe_space_db": False,
    "ucpe_resolver": False,
}
CORE_TABLES = (
    "analysis_runs",
    "analysis_run_details",
    "predictions",
    "prediction_feature_snapshots",
)


def wide_expected_policies() -> set[tuple[str, str, str]]:
    return expected_policies() | {
        (table, "ucpe_bundle_owner", command)
        for table in ("analysis_runs", "analysis_run_details")
        for command in ("SELECT", "INSERT")
    }


def wide_bundle_body() -> dict:
    """One full analysis's core bundle, as the client after W-A would send it: production's rows."""

    from crypto_probability_engine.persistence.repository import _prediction_row_with_origin

    work, _ = analysis_work()
    return {
        "p_run": dict(work.run_summary),
        "p_prediction": _prediction_row_with_origin(work.prediction_rows[0]),
        "p_feature_snapshot": dict(work.feature_snapshot_rows[0]),
        "p_derivatives_snapshot": None,
        "p_run_detail": dict(work.run_detail_row),
    }


def renamed(body: dict, suffix: str, *, new_run: bool) -> dict:
    """The same bundle under a fresh prediction id (and, with new_run, a fresh run id)."""

    run_id = f"{body['p_run']['run_id']}_{suffix}" if new_run else body["p_run"]["run_id"]
    prediction_id = f"{run_id}:{suffix}"
    return {
        "p_run": {**body["p_run"], "run_id": run_id},
        "p_prediction": {**body["p_prediction"], "run_id": run_id, "prediction_id": prediction_id},
        "p_feature_snapshot": {
            **body["p_feature_snapshot"],
            "run_id": run_id,
            "prediction_id": prediction_id,
        },
        "p_derivatives_snapshot": None,
        "p_run_detail": {**body["p_run_detail"], "run_id": run_id},
    }


def answer_of(**parts: str | None) -> dict:
    keys = ("run", "run_detail", "prediction", "feature_snapshot", "derivatives_snapshot")
    return {**{key: parts.get(key) for key in keys}, "refused": parts.get("refused", False)}


def criteria_wide_bundle(
    db: Database, version: int, call: Callable[..., Any], raw: Callable[..., Any]
) -> dict[str, dict[str, Any]]:
    """W1-W8 on the applied migration 0017. W9 (its rollback) is judged by the caller."""

    out: dict[str, dict[str, Any]] = {}

    def guarded(name: str, phase: Callable[[], dict[str, Any]]) -> None:
        out[name] = _guarded(phase)

    def w1() -> dict[str, Any]:
        failures: list[str] = []
        expected = {**EXPECTED_TABLES, "ucpe_bundle_owner": WIDE_OWNER_TABLES}
        failures += matrix_differences(
            held(db, NEW_ROLES, table_privileges(version)), expected, NEW_ROLES, TABLES
        )
        row = db.owner(
            "SELECT o.rolname, p.prosecdef, p.proconfig FROM pg_catalog.pg_proc p"
            " JOIN pg_catalog.pg_roles o ON o.oid = p.proowner"
            f" WHERE p.oid = '{WIDE_FUNCTION}'::pg_catalog.regprocedure"
        )[0]
        if row[0] != "ucpe_bundle_owner" or row[1] is not True or list(row[2] or []) != SEARCH_PATH:
            failures.append(
                f"the wider RPC is {row}, not SECURITY DEFINER owned by ucpe_bundle_owner"
            )
        execute = {
            role: bool(
                db.owner(
                    "SELECT pg_catalog.has_function_privilege(%s, %s, 'EXECUTE')",
                    (role, WIDE_FUNCTION),
                )[0][0]
            )
            for role in WIDE_EXECUTE
        }
        failures += [
            f"EXECUTE for {role} is {execute[role]}"
            for role in WIDE_EXECUTE
            if execute[role] != WIDE_EXECUTE[role]
        ]
        update = bool(
            db.owner(
                "SELECT pg_catalog.has_column_privilege('ucpe_bundle_owner',"
                " 'public.analysis_runs',"
                " 'persistence_status', 'UPDATE')"
            )[0][0]
        )
        if update:
            failures.append("ucpe_bundle_owner may update analysis_runs")
        found: set[tuple[str, str, str]] = set()
        for table, _name, _permissive, roles, command, _qual, _check in (
            db.owner(SNAPSHOT_SQL["policies"]) or []
        ):
            names = [n for n in roles.strip("{}").split(",") if n in NEW_ROLES]
            if names:
                found.add((table, names[0], command))
        wanted = wide_expected_policies()
        failures += [f"missing policy {item}" for item in sorted(wanted - found)]
        failures += [f"extra policy {item}" for item in sorted(found - wanted)]
        owned = sorted(
            row[0] for row in db.owner(SNAPSHOT_SQL["functions_owned_by_new_roles"]) or []
        )
        if owned != [
            "save_forecast_bundle(jsonb,jsonb,jsonb,jsonb,jsonb)",
            "save_prediction_bundle(jsonb,jsonb,jsonb)",
        ]:
            failures.append(f"functions owned by the new roles: {owned}")
        return verdict(failures, execute=execute, policies=len(found))

    guarded("W1", w1)
    body = wide_bundle_body()

    def core_rows(bundle: dict) -> dict[str, int]:
        run_id = bundle["p_run"]["run_id"]
        prediction_id = bundle["p_prediction"]["prediction_id"]
        return {
            "analysis_runs": db.count("analysis_runs", run_id=run_id),
            "analysis_run_details": db.count("analysis_run_details", run_id=run_id),
            "predictions": db.count("predictions", prediction_id=prediction_id),
            "prediction_feature_snapshots": db.count(
                "prediction_feature_snapshots", prediction_id=prediction_id
            ),
        }

    def w2() -> dict[str, Any]:
        status, answer = call("ucpe_api_writer", body)
        rows = core_rows(body)
        expected = answer_of(
            run="INSERTED",
            run_detail="INSERTED",
            prediction="INSERTED",
            feature_snapshot="INSERTED",
        )
        failures = [] if (status, answer) == (200, expected) else [f"answered {status} {answer}"]
        failures += [f"{table} not stored" for table, count in rows.items() if count != 1]
        return verdict(failures, status=status, answer=answer, rows=rows)

    def w3() -> dict[str, Any]:
        before = db.counts()
        status, answer = call("ucpe_api_writer", body)
        expected = answer_of(
            run="IDENTICAL_DUPLICATE",
            run_detail="IDENTICAL_DUPLICATE",
            prediction="IDENTICAL_DUPLICATE",
            feature_snapshot="IDENTICAL_DUPLICATE",
        )
        failures = [] if (status, answer) == (200, expected) else [f"answered {status} {answer}"]
        if db.counts() != before:
            failures.append("the identical replay changed rows")
        return verdict(failures, status=status, answer=answer)

    def refusal(bundle: dict, expected: dict) -> dict[str, Any]:
        before = db.counts()
        status, answer = call("ucpe_api_writer", bundle)
        failures = [] if (status, answer) == (200, expected) else [f"answered {status} {answer}"]
        if db.counts() != before:
            failures.append("a refused bundle changed rows")
        return verdict(failures, status=status, answer=answer)

    def w4() -> dict[str, Any]:
        conflicting = renamed(body, "w4", new_run=False)
        conflicting["p_run"]["analysis_hash"] = "sha256:" + "f" * 64
        return refusal(conflicting, answer_of(run="CONFLICT", refused=True))

    def w5() -> dict[str, Any]:
        conflicting = renamed(body, "w5", new_run=False)
        conflicting["p_run_detail"]["detail_payload"] = {
            **body["p_run_detail"]["detail_payload"],
            "privrehearsal": "a different detail",
        }
        return refusal(
            conflicting,
            answer_of(run="IDENTICAL_DUPLICATE", run_detail="CONFLICT", refused=True),
        )

    def w6() -> dict[str, Any]:
        failures: list[str] = []
        before = db.counts()
        # A failure inside the transaction: the feature snapshot breaks CHECK (feature_count >= 0).
        broken = renamed(body, "w6", new_run=True)
        broken["p_feature_snapshot"]["feature_count"] = -1
        status, answer = call("ucpe_api_writer", broken)
        if 200 <= status < 300:
            failures.append(f"a failing bundle was answered {status} {answer}")
        # A refusal inside 0015's function: a new run whose prediction id is stored, other content.
        refused_inside = renamed(body, "w6b", new_run=True)
        refused_inside["p_prediction"] = {
            **body["p_prediction"],
            "run_id": refused_inside["p_run"]["run_id"],
        }
        refused_inside["p_feature_snapshot"] = {
            **body["p_feature_snapshot"],
            "run_id": refused_inside["p_run"]["run_id"],
        }
        inner_status, inner_answer = call("ucpe_api_writer", refused_inside)
        expected = answer_of(
            run="NOT_KEPT", run_detail="NOT_KEPT", prediction="CONFLICT", refused=True
        )
        if (inner_status, inner_answer) != (200, expected):
            failures.append(f"the inner refusal answered {inner_status} {inner_answer}")
        for bundle in (broken, refused_inside):
            run_id = bundle["p_run"]["run_id"]
            for table in ("analysis_runs", "analysis_run_details"):
                if db.count(table, run_id=run_id):
                    failures.append(f"{table} kept a row of the failed bundle {run_id[-8:]}")
        if db.counts() != before:
            failures.append("a failed bundle changed rows")
        return verdict(failures, failure_status=status, inner=[inner_status, inner_answer])

    def w7() -> dict[str, Any]:
        failures: list[str] = []
        before = db.counts()
        unknown = renamed(body, "w7a", new_run=True)
        unknown["p_run"]["not_a_column"] = 1
        stray = renamed(body, "w7b", new_run=True)
        stray["p_prediction"]["run_id"] = "privrehearsal_another_run"
        outcomes = {}
        for name, bundle in (("unknown key", unknown), ("another run's prediction", stray)):
            status, answer = call("ucpe_api_writer", bundle)
            outcomes[name] = [
                status,
                (answer or {}).get("code") if isinstance(answer, dict) else None,
            ]
            if not (400 <= status < 500 and outcomes[name][1] == "22023"):
                failures.append(f"{name} answered {status} {answer}")
        if db.counts() != before:
            failures.append("a malformed bundle changed rows")
        return verdict(failures, outcomes=outcomes)

    def w8() -> dict[str, Any]:
        failures: list[str] = []
        before = db.counts()
        outcomes: dict[str, Any] = {}
        for role in (None, "ucpe_space_db", "ucpe_resolver"):
            status, code = raw(
                role, "POST", "rpc/save_forecast_bundle", {}, renamed(body, "w8", new_run=True)
            )
            outcomes[f"REST as {role or 'anon'}"] = [status, code]
            if 200 <= status < 300:
                failures.append(f"REST as {role or 'anon'} was served ({status})")
        for role in ("ucpe_space_db", "ucpe_resolver"):
            sqlstate = db.attempt(
                db.login_url(role), "SELECT public.save_forecast_bundle('{}'::jsonb, '{}'::jsonb)"
            )
            outcomes[f"SQL as {role}"] = sqlstate
            if sqlstate != "42501":
                failures.append(f"SQL as {role} answered {sqlstate}")
        if db.counts() != before:
            failures.append("a refused caller changed rows")
        return verdict(failures, outcomes=outcomes)

    for name, phase in (
        ("W2", w2),
        ("W3", w3),
        ("W4", w4),
        ("W5", w5),
        ("W6", w6),
        ("W7", w7),
        ("W8", w8),
    ):
        guarded(name, phase)
    return out


# ------------------------------------------------------------------------- the run


def criterion_production_writer(
    db: Database, writer: Callable[[], tuple[Any, list]], rest: Callable[[str], Any]
) -> dict[str, Any]:
    """W10. Production's REST writer as released (W-A and E4) on the applied 0017."""

    from crypto_probability_engine.api.analysis_service import RECEIPT_NOT_SAVED, RECEIPT_SAVED

    failures: list[str] = []
    steps: dict[str, Any] = {}
    work, payload = analysis_work()
    run_id = payload["run_id"]
    prediction = work.prediction_rows[0]
    repository, seen = writer()
    first, circuit = persist_through_forecast(repository, work)
    steps["first"] = [first.receipt, first.receipt_reason, first.overall, circuit]
    if (first.receipt, first.overall, circuit) != (RECEIPT_SAVED, "OK", "CLOSED"):
        failures.append(f"the analysis was not SAVED: {steps['first']}")
    paths = [path for path, _headers in seen]
    steps["requests"] = sorted(set(paths))
    if paths.count("rpc/save_forecast_bundle") != 1:
        failures.append("the forecast bundle was not exactly one RPC call")
    for beside in ("analysis_runs", "analysis_run_details", "rpc/save_prediction_bundle"):
        if beside in paths:
            failures.append(f"{beside} was sent beside the forecast bundle")
    # Booleans only: the report never carries a credential.
    steps["two_headers"] = sorted({headers for _path, headers in seen})
    if steps["two_headers"] != [(True, True)]:
        failures.append("a request did not carry the API key and the writer's JWT apart")
    stored = {table: db.count(table, run_id=run_id)
              for table in ("analysis_runs", "analysis_run_details", "predictions")}
    stored["prediction_feature_snapshots"] = db.count(
        "prediction_feature_snapshots", prediction_id=prediction["prediction_id"]
    )
    steps["stored"] = stored
    failures += [f"{table} holds {count} rows, not 1" for table, count in stored.items()
                 if count != 1]

    replay, circuit = persist_through_forecast(writer()[0], work)
    steps["replay"] = [replay.receipt, replay.receipt_reason, circuit]
    if (replay.receipt, circuit) != (RECEIPT_SAVED, "CLOSED"):
        failures.append(f"the identical replay was not SAVED: {steps['replay']}")

    def score() -> str:
        return db.owner(
            "SELECT total_score::text FROM public.analysis_runs WHERE run_id = %s", (run_id,)
        )[0][0]

    kept_score = score()
    total = work.run_summary.get("total_score")
    other_run = {**work.run_summary, "total_score": round(float(total or 0) + 1.5, 6)}
    run_conflict, _ = persist_through_forecast(
        writer()[0], dataclasses.replace(work, run_summary=other_run)
    )
    steps["run_conflict"] = [run_conflict.receipt, run_conflict.receipt_reason]
    if steps["run_conflict"] != [RECEIPT_NOT_SAVED, "CONFLICT"]:
        failures.append(f"the conflicting run identity was not refused: {steps['run_conflict']}")
    if score() != kept_score:
        failures.append("the conflicting run identity changed the stored run")

    changed = {**prediction, "reference_price": float(prediction["reference_price"]) * 1.01}
    conflict, _ = persist_through_forecast(
        writer()[0], dataclasses.replace(work, prediction_rows=(changed,))
    )
    kept = db.owner(
        "SELECT reference_price::float8 FROM public.predictions WHERE prediction_id = %s",
        (prediction["prediction_id"],),
    )[0][0]
    steps["prediction_conflict"] = [conflict.receipt, conflict.receipt_reason]
    if steps["prediction_conflict"] != [RECEIPT_NOT_SAVED, "CONFLICT"]:
        failures.append(f"the conflicting prediction was not refused: {conflict.receipt}")
    if abs(float(kept) - float(prediction["reference_price"])) > 1e-9 * max(1.0, abs(float(kept))):
        failures.append("the conflicting prediction changed the stored prediction")

    legacy_work, legacy_payload = analysis_work()
    legacy, circuit = persist_through_forecast(rest("service_role"), legacy_work)
    steps["service_role"] = [legacy.receipt, circuit,
                             db.count("analysis_runs", run_id=legacy_payload["run_id"])]
    if steps["service_role"] != [RECEIPT_SAVED, "CLOSED", 1]:
        failures.append(
            f"service_role did not save through the forecast RPC: {steps['service_role']}"
        )
    return verdict(failures, steps=steps)


def criterion_signing_key(
    db: Database,
    es256_url: str,
    key_file: str,
    writer: Callable[[str], Any],
    hs256_token: str,
) -> dict[str, Any]:
    """J1 (E3). Behind a PostgREST that trusts only a scratch ES256 key with a kid."""

    import subprocess
    import tempfile

    from crypto_probability_engine.api.analysis_service import RECEIPT_SAVED
    from scripts.privilege_rehearsal import es256

    failures: list[str] = []
    steps: dict[str, Any] = {}

    def status(token: str, table: str) -> int:
        with gateway_client(es256_url) as client:
            return client.get(
                f"{REST_BASE}/rest/v1/{table}",
                params={"limit": "0"},
                headers={"Authorization": f"Bearer {token}"},
            ).status_code

    token = es256.mint(key_file, "ucpe_api_writer")
    steps["writer_reads_runs"] = status(token, "analysis_runs")
    steps["writer_reads_outcomes"] = status(token, "prediction_outcomes")
    if (steps["writer_reads_runs"], steps["writer_reads_outcomes"]) != (200, 403):
        failures.append(
            "the ES256 writer token did not run as ucpe_api_writer: "
            f"{steps['writer_reads_runs']} {steps['writer_reads_outcomes']}"
        )
    work, payload = analysis_work()
    confirmation, circuit = persist_through_forecast(writer(token), work)
    steps["writer_saves"] = [confirmation.receipt, confirmation.overall, circuit,
                             db.count("analysis_runs", run_id=payload["run_id"])]
    if steps["writer_saves"] != [RECEIPT_SAVED, "OK", "CLOSED", 1]:
        failures.append(f"the ES256 writer did not save: {steps['writer_saves']}")

    header, claims, signature = token.split(".")
    middle = len(signature) // 2
    swapped = "A" if signature[middle] != "A" else "B"
    tampered = f"{header}.{claims}.{signature[:middle]}{swapped}{signature[middle + 1:]}"
    with tempfile.TemporaryDirectory() as scratch:
        other = f"{scratch}/other-es256.pem"
        subprocess.run(
            ["openssl", "ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", other],
            check=True, capture_output=True,
        )
        another_key = es256.mint(other, "ucpe_api_writer")
    refused = {
        "unknown_kid": es256.mint(key_file, "ucpe_api_writer", kid="ucpe-unknown-kid"),
        "tampered_signature": tampered,
        "another_key_same_kid": another_key,
        "expired": es256.mint(key_file, "ucpe_api_writer", now=int(time.time()) - 3600,
                              lifetime=60),
        "hs256_secret": hs256_token,
    }
    steps["refused"] = {name: status(value, "analysis_runs") for name, value in refused.items()}
    failures += [f"{name} answered {code}, not 401" for name, code in steps["refused"].items()
                 if code != 401]

    steps["signing_key_claims_service_role"] = status(
        es256.mint(key_file, "service_role"), "prediction_outcomes"
    )
    if steps["signing_key_claims_service_role"] != 200:
        failures.append(
            "a service_role token signed by the trusted key was not accepted: "
            f"{steps['signing_key_claims_service_role']}"
        )
    return verdict(failures, steps=steps)


def _require_scratch(owner_url: str, postgrest_url: str) -> None:
    present = [name for name in FORBIDDEN_ENVIRONMENT if os.environ.get(name)]
    if present:
        raise SystemExit(f"REFUSED: never beside a production variable ({', '.join(present)})")
    if not _LOCAL_SOCKET_URL.fullmatch(owner_url):
        raise SystemExit("REFUSED: the owner URL must be a scratch local unix-socket URL")
    if not _LOCAL_HTTP.fullmatch(postgrest_url):
        raise SystemExit("REFUSED: PostgREST must be the local scratch one")
    for name in ES256_ENVIRONMENT[:2]:
        value = os.environ.get(name)
        if value and not _LOCAL_HTTP.fullmatch(value):
            raise SystemExit(f"REFUSED: {name} must be the local scratch PostgREST")


def run(
    db: Database,
    postgrest_url: str,
    admin_url: str | None,
    jwt_key: str,
    es256: tuple[str, str | None, str] | None = None,
) -> dict[str, Any]:
    import httpx

    from crypto_probability_engine.persistence.repository import SupabaseRestRepository

    def rest(role: str) -> SupabaseRestRepository:
        return SupabaseRestRepository(
            REST_BASE, mint_jwt(role, jwt_key), client=gateway_client(postgrest_url)
        )

    def writer() -> tuple[SupabaseRestRepository, list]:
        """E4's least-privilege writer: a publishable-key stand-in in `apikey` (local PostgREST,
        without Supabase's gateway, ignores it) and the writer's JWT in `Authorization`. Each
        request is recorded as its path and whether each header held its expected value."""

        jwt = mint_jwt("ucpe_api_writer", jwt_key)
        publishable = f"sb_publishable_scratch_{secrets.token_hex(8)}"
        seen: list = []
        client = gateway_client(postgrest_url)

        def record(request: Any) -> None:
            seen.append((
                request.url.path.removeprefix("/rest/v1/"),
                (request.headers.get("apikey") == publishable,
                 request.headers.get("Authorization") == f"Bearer {jwt}"),
            ))

        client.event_hooks["request"].append(record)
        repository = SupabaseRestRepository(
            REST_BASE, "", publishable_key=publishable, writer_jwt=jwt, client=client
        )
        return repository, seen

    def raw(
        role: str | None, method: str, path: str, params: dict, body: Any
    ) -> tuple[int, str | None]:
        headers = {"Content-Type": "application/json", "Prefer": "return=minimal"}
        if role is not None:
            headers["Authorization"] = f"Bearer {mint_jwt(role, jwt_key)}"
        with gateway_client(postgrest_url) as client:
            response = client.request(
                method, f"{REST_BASE}/rest/v1/{path}", params=params, headers=headers, json=body
            )
        try:
            code = response.json().get("code") if response.content else None
        except (ValueError, AttributeError):
            code = None
        return response.status_code, code

    def call(role: str, body: dict) -> tuple[int, Any]:
        """The wider RPC, called as PostgREST serves it, with a JWT naming the role."""

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {mint_jwt(role, jwt_key)}",
        }
        with gateway_client(postgrest_url) as client:
            response = client.post(
                f"{REST_BASE}/rest/v1/rpc/save_forecast_bundle", headers=headers, json=body
            )
        try:
            return response.status_code, response.json() if response.content else None
        except ValueError:
            return response.status_code, None

    version = server_version_num(db)
    owner = owner_role(db)
    criteria: dict[str, dict[str, Any]] = {}
    pre = snapshot(db)
    api_before = held(db, API_ROLES, table_privileges(version))

    applied = db.apply(DRAFT)
    if applied is not None:
        return {
            "criteria": {
                name: verdict([f"migration 0016 did not apply: {applied}"]) for name in CRITERIA
            },
            "server_version_num": version,
            "owner": owner,
        }
    wait_for_reload(postgrest_url, admin_url)
    for role in LOGIN_ROLES:
        db.grant_login(role)

    applied_state = snapshot(db)
    second = db.apply(DRAFT)
    criteria["P7"] = verdict(
        ([] if second == "UP016" else [f"the second application answered {second}"])
        + (
            []
            if snapshot(db) == applied_state
            else ["the refused second application changed the catalog"]
        ),
        second_application_sqlstate=second,
        snapshot_sizes=sizes(applied_state),
    )
    criteria["P1"] = _guarded(lambda: criterion_matrix(db, version, owner))
    prediction: dict | None = None
    try:
        criteria["P2"], prediction = criterion_writer(db, rest)
    except Exception as exc:  # noqa: BLE001 - the report records the first failure, never a secret
        criteria["P2"] = verdict([f"{type(exc).__name__}: {exc}"])
    if prediction is None:
        criteria["P3"] = verdict(["P2 saved no prediction to refuse around"])
        criteria["P4"] = verdict(["P2 saved no prediction to resolve"])
    else:
        criteria["P3"] = _guarded(lambda: criterion_writer_refusals(db, raw, prediction, owner))
        criteria["P4"] = _guarded(lambda: criterion_space_db(db, prediction))
    criteria["P5"] = _guarded(lambda: criterion_resolver(db))
    criteria["P6"] = _guarded(lambda: criterion_unchanged(db, version, api_before, rest))

    # W-A: migration 0017 on top of the applied 0016, then its own rollback.
    before_0017 = snapshot(db)
    applied_0017 = db.apply(DRAFT_0017)
    if applied_0017 is not None:
        for name in (*WIDE_CRITERIA, "J1"):
            criteria[name] = verdict([f"migration 0017 did not apply: {applied_0017}"])
    else:
        wait_for_reload(postgrest_url, admin_url)
        criteria.update(criteria_wide_bundle(db, version, call, raw))
        criteria["W10"] = _guarded(lambda: criterion_production_writer(db, writer, rest))
        if es256 is None:
            criteria["J1"] = verdict(["the ES256 PostgREST of E3 is not configured"])
        else:
            es256_url, es256_admin_url, key_file = es256
            wait_for_reload(es256_url, es256_admin_url)

            def es256_writer(token: str) -> SupabaseRestRepository:
                return SupabaseRestRepository(
                    REST_BASE,
                    "",
                    publishable_key=f"sb_publishable_scratch_{secrets.token_hex(8)}",
                    writer_jwt=token,
                    client=gateway_client(es256_url),
                )

            criteria["J1"] = _guarded(lambda: criterion_signing_key(
                db, es256_url, key_file, es256_writer, mint_jwt("ucpe_api_writer", jwt_key)
            ))
        second_0017 = db.apply(DRAFT_0017)
        rolled_0017 = db.apply(ROLLBACK_0017)
        try:
            wait_for_reload(postgrest_url, admin_url)
        except (RuntimeError, httpx.HTTPError) as exc:
            rolled_0017 = rolled_0017 or f"reload: {exc}"
        after_0017 = snapshot(db)
        w9_differences = sorted(
            name for name in SNAPSHOT_SQL if after_0017[name] != before_0017[name]
        )
        criteria["W9"] = verdict(
            ([] if second_0017 == "UP017" else [f"the second application answered {second_0017}"])
            + ([f"the rollback of 0017 failed: {rolled_0017}"] if rolled_0017 else [])
            + [f"the catalog differs after the rollback of 0017: {n}" for n in w9_differences],
            second_application_sqlstate=second_0017,
            catalog_differences=w9_differences,
            snapshot_sizes=sizes(before_0017),
        )

    rolled = db.apply(ROLLBACK)
    try:
        wait_for_reload(postgrest_url, admin_url)
    except (RuntimeError, httpx.HTTPError) as exc:
        rolled = rolled or f"reload: {exc}"
    post = snapshot(db)
    differences = sorted(name for name in SNAPSHOT_SQL if post[name] != pre[name])
    p8_failures = ([f"the rollback failed: {rolled}"] if rolled else []) + [
        f"the catalog differs after the rollback: {name}" for name in differences
    ]
    if not rolled:
        from crypto_probability_engine.api.analysis_service import RECEIPT_SAVED

        try:
            confirmation, circuit = persist_through_rest(rest("service_role"), analysis_work()[0])
            if (confirmation.receipt, circuit) != (RECEIPT_SAVED, "CLOSED"):
                p8_failures.append(
                    f"after the rollback the writer did not persist: {confirmation.receipt}"
                )
        except Exception as exc:  # noqa: BLE001
            p8_failures.append(f"{type(exc).__name__}: {exc}")
    criteria["P8"] = verdict(
        p8_failures, catalog_differences=differences, snapshot_sizes=sizes(pre), after=sizes(post)
    )
    return {
        "criteria": {name: criteria[name] for name in CRITERIA},
        "server_version_num": version,
        "owner": owner,
    }


def _guarded(phase: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return phase()
    except Exception as exc:  # noqa: BLE001 - the report records the first failure, never a secret
        return verdict([f"{type(exc).__name__}: {exc}"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument(
        "--require-all", action="store_true", help="exit 3 unless every criterion is PASS"
    )
    args = parser.parse_args(argv)
    owner_url = os.environ.get("PRIVILEGE_REHEARSAL_OWNER_URL", "")
    postgrest_url = os.environ.get("PRIVILEGE_REHEARSAL_POSTGREST_URL", "")
    admin_url = os.environ.get("PRIVILEGE_REHEARSAL_POSTGREST_ADMIN_URL") or None
    jwt_key = os.environ.get("PGRST_JWT_SECRET", "")
    _require_scratch(owner_url, postgrest_url)
    if len(jwt_key) < 32:
        raise SystemExit("REFUSED: the scratch JWT key must be at least 32 characters")
    database = owner_url.split("///", 1)[1].split("?", 1)[0]
    db = Database(owner_url, database, int(os.environ.get("PRIVILEGE_REHEARSAL_PORT", "5432")))
    es256_url, es256_admin_url, key_file = (os.environ.get(name) for name in ES256_ENVIRONMENT)
    es256 = (es256_url, es256_admin_url or None, key_file) if es256_url and key_file else None
    result = run(db, postgrest_url, admin_url, jwt_key, es256)
    report = {
        "schema_version": SCHEMA_VERSION,
        "scope": (
            "migration 0016 (Phase 3's least-privilege roles: design C1-C3 with W2 and"
            " Correction 01) and migration 0017 (W-A, owner ruling WB1 = YES), on scratch"
            " PostgreSQL built from migrations 0001-0015, behind a real PostgREST"
        ),
        "postgrest_version": os.environ.get("PRIVILEGE_REHEARSAL_POSTGREST_VERSION"),
        "migration_0016_sha256": hashlib.sha256(DRAFT.read_bytes()).hexdigest(),
        "rollback_sha256": hashlib.sha256(ROLLBACK.read_bytes()).hexdigest(),
        "migration_0017_sha256": hashlib.sha256(DRAFT_0017.read_bytes()).hexdigest(),
        "rollback_0017_sha256": hashlib.sha256(ROLLBACK_0017.read_bytes()).hexdigest(),
        **result,
    }
    Path(args.report).write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    missing = unmet(report["criteria"])
    for name in CRITERIA:
        entry = report["criteria"][name]
        print(
            f"{name} {entry['verdict']}"
            + (f": {entry['failures'][:3]}" if entry["failures"] else "")
        )
    if args.require_all and missing:
        print(f"PRIVILEGE_REHEARSAL=FAIL {missing}")
        return 3
    print("PRIVILEGE_REHEARSAL=" + ("PASS" if not missing else f"FAIL {missing}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
