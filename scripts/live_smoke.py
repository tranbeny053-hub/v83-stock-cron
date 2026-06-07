"""Manual live public-provider smoke, gated by UCPE_LIVE_SMOKE_ENABLED=true."""

from __future__ import annotations

import json
import os

from fastapi.testclient import TestClient

from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import hash_code
from crypto_probability_engine.api.schemas import validate_analysis_response
from crypto_probability_engine.config.env_flags import parse_bool
from crypto_probability_engine.config.settings import Settings

LIVE_SOURCES = {"BINANCE_PUBLIC", "OKX_PUBLIC", "CROSS_PROVIDER"}
SMOKE_SYMBOLS = ("BTC", "ETH")
SMOKE_MODES = ("METRICS_ONLY", "NEWS_ADDON")


def main() -> int:
    if not parse_bool(os.environ.get("UCPE_LIVE_SMOKE_ENABLED"), default=False):
        print("SKIP: UCPE_LIVE_SMOKE_ENABLED is not true; live smoke was not run.")
        return 0

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
