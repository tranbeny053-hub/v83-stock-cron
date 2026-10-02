"""PERS-0: the current Postgres writer under injected faults.

Plan references: §22 item 7, and the §23 Persistence criteria.

It measures and fixes nothing. B9 (the atomic, idempotent forecast bundle) needs M1 and a §2.6
crossing; this records today's behaviour so that decision rests on evidence.

Each scenario persists bundles built exactly as the real pipeline builds them: the writer's own
prediction row and feature snapshot, as in the 0014 writer probe. It persists them through the
app's own confirmation path (_persist_work_confirmed), with one fault injected, then reads the
scratch database. A fresh repository is used per scenario unless the scenario is about the
circuit breaker.

The scenarios:
- S1 baseline, no fault.
- S2 a crash after the prediction committed: save_feature_snapshot raises.
- S3 a same-content retry of S2's bundle, no fault.
- S4 a same-content retry of S1's complete bundle.
- S5 a conflicting prediction: S1's prediction_id with different content.
- S6 a conflicting feature snapshot: S1's prediction_id with a different snapshot.
- S7 a response lost after commit: save_prediction commits, then raises; then a same-content retry.
- S8 the circuit after a failure: a new bundle on the repository that just failed.

The §23 criteria are derived from what is observed:
- C1a an acknowledged result (overall OK) always has its complete bundle in the database;
- C1b no partial bundle is ever persisted (atomicity);
- C2 a same-content retry is idempotent and leaves exactly one complete bundle;
- C3 a conflicting retry is refused (not reported OK) and leaves the stored row unchanged;
- C4 a response lost after commit is reconciled by a same-content retry, with no duplicate.

The verdicts are data, never gates. The script exits 0 when every scenario ran and the report was
written, and 1 if the harness itself failed.

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
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
# First on the path, so this repository's packages (and tests/fixtures) win over anything installed.
for _path in (ROOT, ROOT / "src"):
    if str(_path) in sys.path:
        sys.path.remove(str(_path))
    sys.path.insert(0, str(_path))

SCHEMA_VERSION = "persistence-fault-rehearsal.v1"
CRITERIA = ("C1a", "C1b", "C2", "C3", "C4")


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
    args = parser.parse_args(argv)
    url = os.environ.get("PERSISTENCE_REHEARSAL_URL", "")
    require_scratch(url)

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
    from crypto_probability_engine.persistence.repository import SupabasePersistenceRepository
    from crypto_probability_engine.persistence.run_store import InMemoryRunStore
    from crypto_probability_engine.quant.pipeline import run_quant_pipeline
    from crypto_probability_engine.quant_v2.contract import build_quant_v2_shadow
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

    def run(work: Any, repository: Any) -> dict[str, Any]:
        try:
            result = _persist_work_confirmed(work, repository).public_result()
        except Exception as exc:  # recorded, never hidden
            result = {"raised": type(exc).__name__}
        return result

    def fresh() -> Any:
        return SupabasePersistenceRepository(url)

    observations: dict[str, dict[str, Any]] = {}

    def observe(name: str, fault: str, work: Any, repository: Any, **extra: Any) -> dict[str, Any]:
        result = run(work, repository)
        obs = {
            "fault": fault,
            "result": result,
            "db": db(work.prediction_rows[0]["prediction_id"]),
            **extra,
        }
        observations[name] = obs
        return obs

    try:
        s1 = bundle()
        observe("S1", "none", s1, fresh())
        s2 = bundle()
        failing = Faulty(fresh(), snapshot_raises=True)
        observe("S2", "save_feature_snapshot raises after the prediction committed", s2, failing)
        s8 = bundle()
        observe(
            "S8", "a new bundle on the repository that just failed (circuit)", s8, failing._real
        )
        observe("S3", "none (a same-content retry of S2)", s2, fresh())
        observe("S4", "none (a same-content retry of S1)", s1, fresh())

        before = db(s1.prediction_rows[0]["prediction_id"])
        changed = dict(s1.prediction_rows[0])
        changed["reference_price"] = float(changed["reference_price"]) * 1.01
        conflict = dataclasses.replace(s1, prediction_rows=(changed,))
        obs = observe(
            "S5", "a conflicting prediction (same id, reference_price x 1.01)", conflict, fresh()
        )
        after = obs["db"]
        obs["conflict_reported_ok"] = obs["result"].get("prediction") in {"OK", "STATELESS"}
        obs["stored_unchanged"] = after["reference_price"] == before["reference_price"]

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
        observe(
            "S7a",
            "save_prediction commits, then the response is lost",
            s7,
            Faulty(fresh(), prediction_lost=True),
        )
        observe("S7b", "none (a same-content retry after the lost response)", s7, fresh())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"PERS0_HARNESS_FAIL: {type(exc).__name__}: {exc}")
        return 1

    report = {
        "schema_version": SCHEMA_VERSION,
        "scenarios": observations,
        "criteria": verdicts(observations),
        "scope": (
            "the Postgres transport only; the REST transport is not measured; "
            "production's transport "
            "is UNKNOWN (M1)"
        ),
    }
    Path(args.report).write_text(
        json.dumps(report, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    line = " ".join(f"{name}={report['criteria'][name]['verdict']}" for name in CRITERIA)
    print(f"PERS0_REHEARSAL=RAN {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
