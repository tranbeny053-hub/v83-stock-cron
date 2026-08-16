"""Manual live public-provider smokes, gated by explicit operator opt-ins."""

from __future__ import annotations

import json
import os

from fastapi.testclient import TestClient

from crypto_probability_engine.api.analysis_service import (
    _peek_prediction_persistence,
    analyze_request,
)
from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import hash_code
from crypto_probability_engine.api.schemas import AnalysisRequest, validate_analysis_response
from crypto_probability_engine.config.env_flags import parse_bool
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.prediction_origin import PredictionOrigin
from crypto_probability_engine.persistence.run_store import InMemoryRunStore

LIVE_SOURCES = {"BINANCE_PUBLIC", "OKX_PUBLIC", "CROSS_PROVIDER"}
SMOKE_SYMBOLS = ("BTC", "ETH")
SMOKE_MODES = ("METRICS_ONLY", "NEWS_ADDON")
WAVE4B0_SMOKE_ENV = "UCPE_WAVE4B0_LIVE_SMOKE_ENABLED"
WAVE4B0_SYMBOLS = ("BTC", "SOL")
WAVE4B0_TIMEFRAMES = ("1D", "1W", "1M")
DATABASE_ENV_VARS = (
    "SUPABASE_DB_URL",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
)
PROBABILITY_SUM_TOLERANCE = 1e-9


class Wave4B0SmokeFailure(RuntimeError):
    """First causal failure in the Wave 4B0 smoke."""


def main() -> int:
    if not parse_bool(os.environ.get("UCPE_LIVE_SMOKE_ENABLED"), default=False):
        print("SKIP: UCPE_LIVE_SMOKE_ENABLED is not true; live smoke was not run.")
        return 0

    wave4b0_enabled = parse_bool(os.environ.get(WAVE4B0_SMOKE_ENV), default=False)
    if wave4b0_enabled:
        configured_database_var = _configured_database_var()
        if configured_database_var is not None:
            print(
                "FAIL: Wave 4B0 CONTROLLED_SMOKE refused because database variable "
                f"{configured_database_var} is configured."
            )
            return 1

    sprint2_status = run_sprint2_smoke()
    if sprint2_status != 0 or not wave4b0_enabled:
        return sprint2_status
    return run_wave4b0_smoke(database_guard_checked=True)


def run_sprint2_smoke() -> int:
    settings = Settings(
        access_code_hash=hash_code("operator-live-smoke-code"),
        session_signing_key="live-smoke-signing-key",
        session_cookie_secure=False,
        data_mode="live",
        live_smoke_enabled=True,
    )
    client = TestClient(create_app(settings))
    login = client.post("/v1/auth/login", json={"code": "operator-live-smoke-code"})
    if login.status_code != 200:
        print(f"FAIL: login failed with HTTP {login.status_code}")
        return 1

    symbols = _smoke_symbols()
    summaries: list[str] = []
    for symbol in symbols:
        for mode in SMOKE_MODES:
            payload = _analyze(client, symbol, mode)
            if payload is None:
                return 1
            data_source = payload["data_quality"]["data_source"]
            if data_source not in LIVE_SOURCES:
                print(f"FAIL: {symbol} {mode} did not return a live public data source.")
                return 1
            if mode == "NEWS_ADDON" and payload["news_addon_state"]["status"] != "UNAVAILABLE":
                print("FAIL: Sprint 2 live smoke expected NEWS_ADDON news state UNAVAILABLE.")
                return 1
            serialized = json.dumps(payload, sort_keys=True)
            if "operator-live-smoke-code" in serialized or "live-smoke-signing-key" in serialized:
                print(f"FAIL: {symbol} {mode} response leaked smoke auth material.")
                return 1
            if "full_article_body" in serialized or "article_body" in serialized:
                print(f"FAIL: {symbol} {mode} response included article body content.")
                return 1
            summaries.append(f"{symbol}:{mode}:{data_source}")
    print("PASS: live public-provider smoke returned schema-valid live payloads.")
    print("SUMMARY: " + ", ".join(summaries))
    return 0


def run_wave4b0_smoke(*, database_guard_checked: bool = False) -> int:
    """Run the stateless long-timeframe smoke directly against runtime primitives."""
    if not database_guard_checked:
        configured_database_var = _configured_database_var()
        if configured_database_var is not None:
            print(
                "FAIL: Wave 4B0 CONTROLLED_SMOKE refused because database variable "
                f"{configured_database_var} is configured."
            )
            return 1

    settings = Settings(data_mode="live", live_smoke_enabled=True)
    run_store = InMemoryRunStore()
    summaries: list[str] = []
    try:
        for symbol in WAVE4B0_SYMBOLS:
            for timeframe in WAVE4B0_TIMEFRAMES:
                payload = analyze_request(
                    AnalysisRequest(
                        symbol=symbol,
                        timeframe=timeframe,
                        analysis_mode="METRICS_ONLY",
                    ),
                    settings=settings,
                    run_store=run_store,
                    persistence_status="STATELESS",
                    prediction_origin=PredictionOrigin.CONTROLLED_SMOKE,
                )
                summaries.append(_validate_wave4b0_cell(payload, symbol, timeframe))
    except Exception as exc:
        print(f"FAIL: Wave 4B0 CONTROLLED_SMOKE: {exc}")
        return 1

    for summary in summaries:
        print(summary)
    print("PASS: Wave 4B0 CONTROLLED_SMOKE long-timeframe live smoke.")
    return 0


def _validate_wave4b0_cell(payload: dict, symbol: str, timeframe: str) -> str:
    validate_analysis_response(payload)
    data_quality = payload["data_quality"]
    if data_quality["is_live_data"] is not True:
        raise Wave4B0SmokeFailure(f"{symbol} {timeframe} did not report is_live_data=true.")
    data_source = data_quality["data_source"]
    if data_source not in LIVE_SOURCES:
        raise Wave4B0SmokeFailure(
            f"{symbol} {timeframe} did not return a live public data source."
        )

    horizons = payload["probability_state"]["horizons"]
    for horizon_name, horizon in horizons.items():
        total = sum(
            float(horizon[field])
            for field in ("p_up_frac", "p_down_frac", "p_timeout_frac")
        )
        if abs(total - 1.0) > PROBABILITY_SUM_TOLERANCE:
            raise Wave4B0SmokeFailure(
                f"{symbol} {timeframe} {horizon_name} probability sum was not 1.0 "
                f"within tolerance {PROBABILITY_SUM_TOLERANCE}."
            )
    if payload["calibration_state"]["profitability_claim"] is not False:
        raise Wave4B0SmokeFailure(f"{symbol} {timeframe} made a profitability claim.")
    if float(payload["score_stack"]["news_influence_frac"]) != 0.0:
        raise Wave4B0SmokeFailure(f"{symbol} {timeframe} had non-zero news influence.")

    sample_flag = payload["epistemic_sufficiency_state"]["sufficiency_level"]
    if timeframe == "1M" and sample_flag != "LOW_SAMPLE":
        raise Wave4B0SmokeFailure(
            f"{symbol} 1M expected sample flag LOW_SAMPLE, got {sample_flag}."
        )

    prediction_rows, _, build_failed, _, _ = _peek_prediction_persistence(payload)
    if build_failed or len(prediction_rows) != 1:
        raise Wave4B0SmokeFailure(
            f"{symbol} {timeframe} had no observable runtime-built prediction."
        )
    if prediction_rows[0].get("prediction_origin") != PredictionOrigin.CONTROLLED_SMOKE:
        raise Wave4B0SmokeFailure(
            f"{symbol} {timeframe} prediction was not classified CONTROLLED_SMOKE."
        )

    primary = horizons["H_primary"]
    labels = {
        "UP": float(primary["p_up_frac"]),
        "DOWN": float(primary["p_down_frac"]),
        "TIMEOUT": float(primary["p_timeout_frac"]),
    }
    top_label, top_probability = max(labels.items(), key=lambda item: item[1])
    return (
        f"SUMMARY: {symbol}:{timeframe}:{data_source}:"
        f"{top_label}={top_probability:.6f}:{sample_flag}"
    )


def _configured_database_var() -> str | None:
    return next((name for name in DATABASE_ENV_VARS if os.environ.get(name)), None)


def _analyze(client: TestClient, symbol: str, mode: str) -> dict | None:
    response = client.post("/v1/analyze", json={"symbol": symbol, "analysis_mode": mode})
    if response.status_code != 200:
        print(
            f"FAIL: {symbol} {mode} analyze returned HTTP "
            f"{response.status_code}: {response.text}"
        )
        return None
    payload = response.json()
    validate_analysis_response(payload)
    if payload["data_quality"]["is_live_data"] is not True:
        print(f"FAIL: {symbol} {mode} did not report is_live_data=true.")
        return None
    for path, value in _iter_frac_fields(payload):
        if not isinstance(value, int | float) or not 0.0 <= float(value) <= 1.0:
            print(f"FAIL: {symbol} {mode} emitted invalid fraction at {path}.")
            return None
    return payload


def _smoke_symbols() -> tuple[str, ...]:
    raw = os.environ.get("UCPE_LIVE_SMOKE_SYMBOLS")
    if not raw:
        return SMOKE_SYMBOLS
    symbols = tuple(item.strip() for item in raw.split(",") if item.strip())
    return symbols or SMOKE_SYMBOLS


def _iter_frac_fields(value, path: str = "payload"):
    if isinstance(value, dict):
        for key, item in value.items():
            item_path = f"{path}.{key}"
            if key.endswith("_frac"):
                yield item_path, item
            yield from _iter_frac_fields(item, item_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_frac_fields(item, f"{path}[{index}]")


if __name__ == "__main__":
    raise SystemExit(main())
