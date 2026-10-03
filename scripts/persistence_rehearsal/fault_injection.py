"""PERS-0: the persistence writers under injected faults (B9 adds the REST bundle route).

Plan references: §22 item 7, and the §23 Persistence criteria.

Two routes, each measured on the same scenarios:
- "postgres": the direct-Postgres writer (SupabasePersistenceRepository), unchanged by B9 and not
  production's writer (M1 = REST, CONFIG_PROVEN). Its verdicts are data;
- "rest_rpc": production's REST writer (SupabaseRestRepository) and its B9 bundle, migration 0015's
  public.save_prediction_bundle, called exactly as PostgREST calls it (postgrest_emulator.py). With
  --require-route rest_rpc every one of its criteria must PASS, or the run fails.

Each scenario persists bundles built exactly as the real pipeline builds them: the writer's own
prediction row and feature snapshot, as in the 0014 writer probe. It persists them through the
app's own confirmation path (_persist_work_confirmed), with one fault injected, then reads the
scratch database. A fresh repository is used per scenario unless the scenario is about the
circuit breaker.

The scenarios:
- S1 baseline, no fault.
- S2 the feature snapshot write fails after the prediction write (postgres: save_feature_snapshot
  raises after the prediction committed; rest_rpc: a scratch-only trigger raises inside the
  bundle's transaction).
- S3 a same-content retry of S2's bundle, no fault.
- S4 a same-content retry of S1's complete bundle.
- S5 a conflicting prediction: S1's prediction_id with different content.
- S6 a conflicting feature snapshot: S1's prediction_id with a different snapshot.
- S7 a response lost after commit (postgres: save_prediction commits, then raises; rest_rpc: the
  RPC commits, then the HTTP response is lost); then a same-content retry.
- S8 the circuit after a failure: a new bundle on the repository that just failed.

The §23 criteria are derived from what is observed:
- C1a an acknowledged result (overall OK) always has its complete bundle in the database;
- C1b no partial bundle is ever persisted (atomicity);
- C2 a same-content retry is idempotent and leaves exactly one complete bundle;
- C3 a conflicting retry is refused (not reported OK) and leaves the stored row unchanged;
- C4 a response lost after commit is reconciled by a same-content retry, with no duplicate;
- C5 the receipt (plan §8.1) never lies: SAVED only when the complete bundle is stored (and never
  for a conflicting submission); NOT_SAVED only when the submission stored no complete bundle;
  COMMIT_UNKNOWN is always truthful.

The script exits 0 when every scenario ran and the report was written, 1 if the harness itself
failed, and 3 when a route named by --require-route has a criterion that is not PASS.

Runs ONLY against a scratch local PostgreSQL on a CI runner, reached through its unix socket
(PERSISTENCE_REHEARSAL_URL). It refuses any other database.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
# First on the path, so this repository's packages (and tests/fixtures) win over anything installed.
for _path in (ROOT, ROOT / "src"):
    if str(_path) in sys.path:
        sys.path.remove(str(_path))
    sys.path.insert(0, str(_path))

SCHEMA_VERSION = "persistence-fault-rehearsal.v2"
ROUTES = ("postgres", "rest_rpc")
REST_BASE = "https://rehearsal.invalid"
REST_KEY = "rehearsal-service-role-key"
BUNDLE_FUNCTION = "public.save_prediction_bundle(jsonb,jsonb,jsonb)"
CRITERIA = ("C1a", "C1b", "C2", "C3", "C4", "C5")


class InjectedFault(RuntimeError):
    """A deliberately injected failure."""


def require_scratch(url: str) -> None:
    if not url.startswith("postgresql:///") or "host=/var/run/postgresql" not in url:
        raise SystemExit("only a scratch local PostgreSQL over its unix socket is accepted")


def verdicts(observations: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The §23 criteria from the scenario observations. Pure: unit-tested without a database."""

    def complete(obs: dict[str, Any]) -> bool:
        return obs["db"]["predictions"] == 1 and obs["db"]["snapshots"] == 1

    def partial(obs: dict[str, Any]) -> bool:
        return obs["db"]["predictions"] == 1 and obs["db"]["snapshots"] == 0

    acknowledged = [
        name for name, obs in observations.items() if obs["result"].get("overall") == "OK"
    ]
    c1a_bad = [name for name in acknowledged if not complete(observations[name])]
    c1b_bad = [name for name, obs in observations.items() if partial(obs)]
    retries = [name for name in ("S3", "S4", "S7b") if name in observations]
    c2_bad = [
        name
        for name in retries
        if not (
            complete(observations[name]) and observations[name]["result"].get("overall") == "OK"
        )
    ]
    conflicts = [name for name in ("S5", "S6") if name in observations]
    c3_bad = [
        name
        for name in conflicts
        if observations[name]["conflict_reported_ok"] or not observations[name]["stored_unchanged"]
    ]
    s7b = observations.get("S7b")
    c4_ok = bool(s7b) and complete(s7b) and s7b["result"].get("overall") == "OK"
    c5_bad = []
    for name, obs in observations.items():
        receipt = obs.get("receipt")
        before = obs.get("db_before") or {"predictions": 0, "snapshots": 0}
        was_complete = before["predictions"] == 1 and before["snapshots"] == 1
        if receipt not in {"SAVED", "NOT_SAVED", "COMMIT_UNKNOWN"}:
            c5_bad.append(name)
        elif receipt == "SAVED" and (not complete(obs) or name in conflicts):
            c5_bad.append(name)
        elif receipt == "NOT_SAVED" and complete(obs) and not was_complete:
            c5_bad.append(name)
    return {
        "C1a": {
            "verdict": "PASS" if not c1a_bad else "FAIL",
            "acknowledged": acknowledged,
            "acknowledged_but_incomplete": c1a_bad,
        },
        "C1b": {"verdict": "PASS" if not c1b_bad else "FAIL", "partial_bundles_persisted": c1b_bad},
        "C2": {
            "verdict": "PASS" if retries and not c2_bad else "FAIL",
            "retries": retries,
            "not_idempotent": c2_bad,
        },
        "C3": {
            "verdict": "PASS" if conflicts and not c3_bad else "FAIL",
            "conflicts": conflicts,
            "not_refused": c3_bad,
        },
        "C4": {"verdict": "PASS" if c4_ok else "FAIL", "scenario": "S7b"},
        "C5": {
            "verdict": "PASS" if observations and not c5_bad else "FAIL",
            "receipts": {name: obs.get("receipt") for name, obs in observations.items()},
            "false_receipts": c5_bad,
        },
    }


class Faulty:
    """A real repository with one injected fault; every other call goes straight through."""

    def __init__(
        self, real: Any, *, snapshot_raises: bool = False, prediction_lost: bool = False
    ) -> None:
        self._real = real
        self._snapshot_raises = snapshot_raises
        self._prediction_lost = prediction_lost

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    def save_feature_snapshot(self, row: Any) -> Any:
        if self._snapshot_raises:
            raise InjectedFault("crash after the prediction committed")
        return self._real.save_feature_snapshot(row)

    def save_prediction(self, row: Any) -> Any:
        status = self._real.save_prediction(row)
        if self._prediction_lost:
            raise InjectedFault("the response was lost after the commit")
        return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument(
        "--require-route",
        action="append",
        default=[],
        choices=ROUTES,
        help="fail (exit 3) unless every criterion of this route is PASS",
    )
    args = parser.parse_args(argv)
    url = os.environ.get("PERSISTENCE_REHEARSAL_URL", "")
    require_scratch(url)

    import httpx
    import psycopg

    from crypto_probability_engine.api.analysis_service import (
        _persist_work_confirmed,
        _persistence_work,
        _prediction_row,
        analyze_request,
    )
    from crypto_probability_engine.api.schemas import AnalysisRequest
    from crypto_probability_engine.config.settings import Settings
    from crypto_probability_engine.persistence.feature_snapshot import build_feature_snapshot
    from crypto_probability_engine.persistence.repository import (
        SupabasePersistenceRepository,
        SupabaseRestRepository,
    )
    from crypto_probability_engine.persistence.run_store import InMemoryRunStore
    from crypto_probability_engine.quant.pipeline import run_quant_pipeline
    from crypto_probability_engine.quant_v2.contract import build_quant_v2_shadow
    from scripts.persistence_rehearsal.postgrest_emulator import PostgrestEmulator, install_faults
    from tests.fixtures.market_data import make_high_volatility_snapshot, make_snapshot

    live = {
        "is_live_data": True,
        "data_source": "BINANCE_PUBLIC",
        "cross_provider_state": "UNAVAILABLE",
    }
    provider = {"status": "OK", "active_provider": "binance"}

    def snapshot_row(row: dict, shape: Any) -> dict:
        snapshot = shape(provider="binance", timeframe="4H")
        quant = run_quant_pipeline(snapshot, provider)
        block = build_quant_v2_shadow(
            quant_result=quant,
            snapshot=snapshot,
            provider_state=provider,
            symbol="BTC",
            normalized_symbol="BTC/USDT",
            timeframe="4H",
        )
        return build_feature_snapshot(row, block)

    def bundle() -> Any:
        payload = analyze_request(
            AnalysisRequest(symbol="BTC/USDT", timeframe="4H"),
            settings=Settings(data_mode="fixture"),
            run_store=InMemoryRunStore(limit=50),
        )
        payload["run_id"] = f"pers0_{uuid.uuid4().hex}"
        snapshot = make_snapshot(provider="binance", timeframe="4H")
        quant = run_quant_pipeline(snapshot, provider)
        row = _prediction_row(
            run_id=payload["run_id"],
            request_symbol="BTC",
            normalized_symbol="BTC/USDT",
            timeframe="4H",
            snapshot=snapshot,
            quant_result=quant,
            data_quality=live,
            provider_state=provider,
        )
        if row is None:
            raise SystemExit("the writer built no prediction row")
        work = _persistence_work(payload, "OK", consume_pending=False)
        return dataclasses.replace(
            work, prediction_rows=(row,), feature_snapshot_rows=(snapshot_row(row, make_snapshot),)
        )

    def db(prediction_id: str) -> dict[str, Any]:
        with psycopg.connect(url) as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM public.predictions WHERE prediction_id = %s", (prediction_id,)
            )
            predictions = int(cursor.fetchone()[0])
            cursor.execute(
                "SELECT count(*) FROM public.prediction_feature_snapshots WHERE prediction_id = %s",
                (prediction_id,),
            )
            snapshots = int(cursor.fetchone()[0])
            cursor.execute(
                "SELECT reference_price::text FROM public.predictions WHERE prediction_id = %s",
                (prediction_id,),
            )
            stored = cursor.fetchone()
            cursor.execute(
                "SELECT snapshot_hash FROM public.prediction_feature_snapshots "
                "WHERE prediction_id = %s",
                (prediction_id,),
            )
            snapshot_hash = cursor.fetchone()
        return {
            "predictions": predictions,
            "snapshots": snapshots,
            "reference_price": stored[0] if stored else None,
            "snapshot_hash": snapshot_hash[0] if snapshot_hash else None,
        }

    def run(work: Any, repository: Any) -> tuple[dict[str, Any], tuple[Any, Any]]:
        try:
            confirmation = _persist_work_confirmed(work, repository)
        except Exception as exc:  # recorded, never hidden; the telemetry calls it unknown
            return {"raised": type(exc).__name__}, ("COMMIT_UNKNOWN", "UNCONFIRMED_EXCEPTION")
        return confirmation.public_result(), (confirmation.receipt, confirmation.receipt_reason)

    def scenarios(fresh: Callable[..., Any], faulted: Callable[[str, Any], Any],
                  reuse: Callable[[Any], Any]) -> dict[str, dict[str, Any]]:
        """The same scenarios on one route.

        ``fresh()`` is a new repository; ``faulted(fault, repository)`` is one that injects
        ``fault``; ``reuse(faulted)`` is the repository S8 reuses after S2's failure.
        """

        observations: dict[str, dict[str, Any]] = {}

        def observe(name: str, fault: str, work: Any, repository: Any,
                    **extra: Any) -> dict[str, Any]:
            before = db(work.prediction_rows[0]["prediction_id"])
            result, (receipt, reason) = run(work, repository)
            obs = {
                "fault": fault,
                "result": result,
                "receipt": receipt,
                "receipt_reason": reason,
                "db_before": before,
                "db": db(work.prediction_rows[0]["prediction_id"]),
                **extra,
            }
            observations[name] = obs
            return obs

        s1 = bundle()
        observe("S1", "none", s1, fresh())
        s2 = bundle()
        failing = faulted("feature_snapshot", fresh())
        observe("S2", "the feature snapshot write fails after the prediction write", s2, failing)
        s8 = bundle()
        observe("S8", "a new bundle on the repository that just failed (circuit)", s8,
                reuse(failing))
        observe("S3", "none (a same-content retry of S2)", s2, fresh())
        observe("S4", "none (a same-content retry of S1)", s1, fresh())

        before = db(s1.prediction_rows[0]["prediction_id"])
        changed = dict(s1.prediction_rows[0])
        changed["reference_price"] = float(changed["reference_price"]) * 1.01
        conflict = dataclasses.replace(s1, prediction_rows=(changed,))
        obs = observe(
            "S5", "a conflicting prediction (same id, reference_price x 1.01)", conflict, fresh()
        )
        obs["conflict_reported_ok"] = obs["result"].get("prediction") in {"OK", "STATELESS"}
        obs["stored_unchanged"] = obs["db"]["reference_price"] == before["reference_price"]

        other = snapshot_row(s1.prediction_rows[0], make_high_volatility_snapshot)
        conflict_snapshot = dataclasses.replace(s1, feature_snapshot_rows=(other,))
        obs = observe(
            "S6",
            "a conflicting feature snapshot (same id, another market shape)",
            conflict_snapshot,
            fresh(),
        )
        obs["conflict_reported_ok"] = obs["result"].get("feature_snapshot") in {
            "INSERTED",
            "IDENTICAL_DUPLICATE",
        }
        obs["stored_unchanged"] = obs["db"]["snapshot_hash"] == before["snapshot_hash"]

        s7 = bundle()
        observe("S7a", "the write commits, then the response is lost", s7,
                faulted("lost_response", fresh()))
        observe("S7b", "none (a same-content retry after the lost response)", s7, fresh())
        return observations

    # Route "postgres": the direct-Postgres writer, faults through the Faulty wrapper.
    def postgres_faulted(fault: str, repository: Any) -> Any:
        return Faulty(repository, snapshot_raises=fault == "feature_snapshot",
                      prediction_lost=fault == "lost_response")

    # Route "rest_rpc": the REST writer through a PostgREST-compatible endpoint on scratch PG.
    emulators: list[PostgrestEmulator] = []

    def rest(fault: str | None = None) -> Any:
        emulator = PostgrestEmulator(url, fault=fault)
        emulators.append(emulator)
        client = httpx.Client(transport=httpx.MockTransport(emulator))
        return SupabaseRestRepository(REST_BASE, REST_KEY, client=client)

    report_routes: dict[str, dict[str, Any]] = {}
    try:
        install_faults(url)
        postgres = scenarios(
            lambda: SupabasePersistenceRepository(url), postgres_faulted, lambda f: f._real
        )
        report_routes["postgres"] = {"scenarios": postgres, "criteria": verdicts(postgres)}
        rest_obs = scenarios(rest, lambda fault, _unused: rest(fault), lambda f: f)
        report_routes["rest_rpc"] = {
            "scenarios": rest_obs,
            "criteria": verdicts(rest_obs),
            "rpc_requests": sum(emulator.rpc_requests for emulator in emulators),
            "privileges": rest_privileges(url),
            "refusals": rest_refusals(url, rest),
        }
    except SystemExit:
        raise
    except Exception as exc:
        print(f"PERS0_HARNESS_FAIL: {type(exc).__name__}: {exc}")
        return 1

    report = {
        "schema_version": SCHEMA_VERSION,
        "routes": report_routes,
        "scope": (
            "postgres: the direct-Postgres writer, not production's; rest_rpc: production's REST "
            "writer and migration 0015's bundle RPC, called as PostgREST calls it, on scratch "
            "PostgreSQL built from migrations 0001-0015"
        ),
    }
    Path(args.report).write_text(
        json.dumps(report, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    lines = [
        f"{route}: " + " ".join(
            f"{name}={report_routes[route]['criteria'][name]['verdict']}" for name in CRITERIA
        )
        for route in ROUTES
    ]
    print("PERS0_REHEARSAL=RAN " + " | ".join(lines))
    unmet = unmet_requirements(report_routes, args.require_route)
    if unmet:
        print("PERS0_REQUIRED_ROUTE=FAIL " + " ".join(unmet))
        return 3
    if args.require_route:
        print("PERS0_REQUIRED_ROUTE=PASS " + " ".join(args.require_route))
    return 0


def unmet_requirements(
    routes: dict[str, dict[str, Any]], required: list[str]
) -> list[str]:
    """Pure: every criterion, privilege or refusal of a required route that does not hold."""

    unmet: list[str] = []
    for route in required:
        report = routes[route]
        unmet += [
            f"{route}.{name}" for name in CRITERIA if report["criteria"][name]["verdict"] != "PASS"
        ]
        for section in ("privileges", "refusals"):
            unmet += [
                f"{route}.{section}.{name}"
                for name, held in report.get(section, {}).get("expected", {}).items()
                if held is not True
            ]
    return unmet


PRIVILEGES_SQL = (
    "SELECT pg_catalog.has_function_privilege('public', p.oid, 'EXECUTE'),"
    " pg_catalog.has_function_privilege('anon', p.oid, 'EXECUTE'),"
    " pg_catalog.has_function_privilege('authenticated', p.oid, 'EXECUTE'),"
    " pg_catalog.has_function_privilege('service_role', p.oid, 'EXECUTE'),"
    " p.prosecdef, COALESCE(p.proconfig, ARRAY[]::text[]),"
    " pg_catalog.pg_get_userbyid(p.proowner),"
    " pg_catalog.has_function_privilege('ucpe_api_writer', p.oid, 'EXECUTE')"
    " FROM pg_catalog.pg_proc AS p"
    f" WHERE p.oid = '{BUNDLE_FUNCTION}'::regprocedure"
)


def rest_privileges(url: str) -> dict[str, Any]:
    """The catalog facts of the bundle RPC: who may execute it, how it runs.

    Since migration 0016 (W2) it runs SECURITY DEFINER as its narrow owner, ucpe_bundle_owner, and
    the writer role may execute it beside service_role (the live writer's).
    """

    import psycopg

    with psycopg.connect(url) as connection, connection.cursor() as cursor:
        cursor.execute(PRIVILEGES_SQL)
        public, anon, authenticated, service_role, definer, config, owner, writer = (
            cursor.fetchone()
        )
    observed = {
        "execute_public": public,
        "execute_anon": anon,
        "execute_authenticated": authenticated,
        "execute_service_role": service_role,
        "execute_writer": writer,
        "security_definer": definer,
        "owner": owner,
        "config": list(config),
    }
    return {
        "observed": observed,
        "expected": {
            "no_execute_for_public_anon_authenticated": not (public or anon or authenticated),
            "execute_for_service_role": service_role is True,
            "execute_for_the_writer": writer is True,
            "security_definer_of_ucpe_bundle_owner": (
                definer is True and owner == "ucpe_bundle_owner"
            ),
            "fixed_search_path": list(config) == ["search_path=pg_catalog, pg_temp"],
        },
    }


def rest_refusals(url: str, rest: Callable[..., Any]) -> dict[str, Any]:
    """The RPC refuses the API roles and malformed bundles, and writes nothing when it does."""

    import psycopg

    observed: dict[str, Any] = {}
    for role in ("anon", "authenticated"):
        with psycopg.connect(url) as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"SET LOCAL ROLE {role}")
                    cursor.execute(
                        f"SELECT {BUNDLE_FUNCTION.split('(')[0]}"
                        "('{\"prediction_id\": \"pers0_refused\"}'::jsonb)"
                    )
                observed[f"{role}_sqlstate"] = None
            except psycopg.Error as exc:
                observed[f"{role}_sqlstate"] = exc.sqlstate
                connection.rollback()
    malformed = {
        "unknown_key": ({"prediction_id": "pers0_malformed_1", "not_a_column": 1}, None),
        "oos_identity": ({"prediction_id": "oosb-" + "0" * 32 + ":4H:BASELINE",
                          "prediction_origin": "SCHEDULED_SHADOW_EVIDENCE"}, None),
        "snapshot_of_another_prediction": (
            {"prediction_id": "pers0_malformed_2"},
            {"prediction_id": "pers0_malformed_other", "snapshot_payload": {"k": 1},
             "snapshot_hash": "a" * 64},
        ),
    }
    statuses = {}
    for name, (row, feature) in malformed.items():
        repository = rest()
        try:
            written = repository.save_prediction_bundle(row, feature)
            statuses[name] = str(written.prediction)
        except ValueError:
            statuses[name] = "REFUSED_BY_CLIENT"
    observed["malformed"] = statuses
    with psycopg.connect(url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM public.predictions WHERE prediction_id LIKE 'pers0_malformed%'"
            " OR prediction_id = 'pers0_refused'"
        )
        observed["rows_written_by_refusals"] = int(cursor.fetchone()[0])
    return {
        "observed": observed,
        "expected": {
            "anon_refused_42501": observed["anon_sqlstate"] == "42501",
            "authenticated_refused_42501": observed["authenticated_sqlstate"] == "42501",
            "malformed_bundles_unavailable": all(
                status in {"UNAVAILABLE", "REFUSED_BY_CLIENT"} for status in statuses.values()
            ),
            "refusals_write_nothing": observed["rows_written_by_refusals"] == 0,
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
