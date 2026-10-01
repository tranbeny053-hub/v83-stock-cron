"""Migration 0014 rehearsal, step 1: the PRODUCTION writer's own SQL against the new checks.

It drives SupabasePersistenceRepository (the Postgres transport) with the rows the real pipeline
builds (the writer's own _prediction_row output) across 3 market shapes and every timeframe, plus a
feature snapshot and a resolver-shaped outcome: every one must be accepted. The tc-v1 stamp is not
applied here: only the writer and the resolver may import the target contract (its own guard test),
and the stamp's four columns are 0011's to check, not 0014's. Then, with fresh repositories, rows
the checks refuse must not be persisted: a refused prediction is reported as not OK, and a refused
outcome raises, which the resolver records as error_save_exception.

Runs ONLY against a scratch local PostgreSQL on a CI runner, reached through its unix socket
(MIGRATION_0014_REHEARSAL_URL). It refuses any other database.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# First on the path, so this repository's packages (and tests/fixtures) win over anything installed.
for _path in (ROOT, ROOT / "src"):
    if str(_path) in sys.path:
        sys.path.remove(str(_path))
    sys.path.insert(0, str(_path))

import psycopg  # noqa: E402

from crypto_probability_engine.api.analysis_service import _prediction_row  # noqa: E402
from crypto_probability_engine.config.defaults import TIMEFRAME_SECONDS  # noqa: E402
from crypto_probability_engine.persistence.feature_snapshot import (  # noqa: E402
    build_feature_snapshot,
)
from crypto_probability_engine.persistence.repository import (  # noqa: E402
    SupabasePersistenceRepository,
)
from crypto_probability_engine.quant.pipeline import run_quant_pipeline  # noqa: E402
from crypto_probability_engine.quant_v2.contract import build_quant_v2_shadow  # noqa: E402
from tests.fixtures.market_data import (  # noqa: E402
    make_downtrend_snapshot,
    make_high_volatility_snapshot,
    make_snapshot,
)

LIVE = {
    "is_live_data": True,
    "data_source": "BINANCE_PUBLIC",
    "cross_provider_state": "UNAVAILABLE",
}
PROVIDER = {"status": "OK", "active_provider": "binance"}
SHAPES = {
    "up": make_snapshot,
    "down": make_downtrend_snapshot,
    "vol": make_high_volatility_snapshot,
}


def fail(message: str) -> None:
    print(f"REHEARSAL_FAIL: {message}")
    raise SystemExit(1)


def count(url: str, sql: str, *params: object) -> int:
    with psycopg.connect(url) as conn, conn.cursor() as cursor:
        cursor.execute(sql, params)
        return int(cursor.fetchone()[0])


def writer_row(shape: str, timeframe: str) -> tuple[dict, dict | None]:
    snapshot = SHAPES[shape](provider="binance", timeframe=timeframe)
    quant = run_quant_pipeline(snapshot, PROVIDER)
    row = _prediction_row(run_id=f"rehearsal_{shape}_{timeframe}", request_symbol="BTC",
                          normalized_symbol="BTC/USDT", timeframe=timeframe, snapshot=snapshot,
                          quant_result=quant, data_quality=LIVE, provider_state=PROVIDER)
    if row is None:
        fail(f"the writer built no row for {shape} {timeframe}")
    block = build_quant_v2_shadow(quant_result=quant, snapshot=snapshot, provider_state=PROVIDER,
                                  symbol="BTC", normalized_symbol="BTC/USDT", timeframe=timeframe)
    return row, build_feature_snapshot(row, block)


def main() -> int:
    url = os.environ.get("MIGRATION_0014_REHEARSAL_URL", "")
    if not url.startswith("postgresql:///") or "host=/var/run/postgresql" not in url:
        fail("only a scratch local PostgreSQL over its unix socket is accepted")
    repository = SupabasePersistenceRepository(url)
    saved: list[dict] = []
    for shape in sorted(SHAPES):
        for timeframe in sorted(TIMEFRAME_SECONDS):
            row, snapshot_row = writer_row(shape, timeframe)
            status = repository.save_prediction(row)
            if status != "OK":
                fail(f"the writer's {shape} {timeframe} row was not accepted ({status})")
            saved.append(row)
            if shape == "up" and timeframe == "4H":
                if snapshot_row is None:
                    fail("no feature snapshot was built")
                snapshot_status = repository.save_feature_snapshot(snapshot_row)
                if str(snapshot_status) not in {"INSERTED", "IDENTICAL_DUPLICATE"}:
                    fail(f"the feature snapshot was not accepted ({snapshot_status})")
    ids = [row["prediction_id"] for row in saved]
    stored = count(url, "SELECT count(*) FROM public.predictions WHERE prediction_id = ANY(%s)",
                   ids)
    if stored != len(ids):
        fail(f"stored {stored} of {len(ids)} writer rows")
    first = saved[0]
    outcome = {
        "prediction_id": first["prediction_id"], "resolved_at_utc": first["horizon_end_utc"],
        "outcome_close_utc": first["horizon_end_utc"], "outcome_reference_price": 121.5,
        "terminal_return_frac": 0.0045, "realized_label": "TIMEOUT",
        "decision_band_frac": first["decision_band_frac"], "max_favorable_frac": 0.01,
        "max_adverse_frac": -0.01, "candles_observed": 6, "resolver_version": "rehearsal",
        "data_source": "BINANCE_PUBLIC", "is_live_data": True,
    }
    repository.save_prediction_outcome(outcome)
    # Refusals use fresh repositories: a refused write opens the circuit of the one that saw it.
    refusing = SupabasePersistenceRepository(url)
    bad_prediction = {**saved[1], "prediction_id": "rehearsal:refused", "p_up_frac": 0.9}
    if refusing.save_prediction(bad_prediction) == "OK":
        fail("a probability sum above 1 was reported OK")
    bad_outcome = {**outcome, "prediction_id": saved[1]["prediction_id"],
                   "outcome_reference_price": 0.0}
    try:
        SupabasePersistenceRepository(url).save_prediction_outcome(bad_outcome)
    except RuntimeError:
        pass
    else:
        fail("a zero outcome price did not raise")
    refused = count(url, "SELECT count(*) FROM public.predictions WHERE prediction_id = %s",
                    "rehearsal:refused")
    refused += count(url, "SELECT count(*) FROM public.prediction_outcomes "
                          "WHERE prediction_id = %s", saved[1]["prediction_id"])
    if refused:
        fail("a refused row was persisted")
    print(f"WRITER_PROBE=PASS {len(saved)} writer rows, 1 feature snapshot and 1 outcome "
          "accepted; a refused prediction and a refused outcome were not persisted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
