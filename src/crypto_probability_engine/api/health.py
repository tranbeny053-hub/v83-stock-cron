"""Runtime and system health endpoints."""

from __future__ import annotations

from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.config.unit_discipline import utc_now

STARTED_AT = utc_now()


def runtime_health(settings: Settings) -> dict:
    now = utc_now()
    return {
        "status": "OK",
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "schema_version": settings.schema_version,
        "cache_ready": True,
        "cache_age_seconds": 0,
        "symbols_in_cache": 0,
        "uptime_seconds": int((now - STARTED_AT).total_seconds()),
        "as_of_utc": now.isoformat().replace("+00:00", "Z"),
    }


def system_status(settings: Settings) -> dict:
    return {
        "runtime": runtime_health(settings),
        "system": {
            "binance_status": "TO_VERIFY",
            "okx_status": "TO_VERIFY",
            "store_status": "CONFIGURED" if settings.external_store_configured else "STATELESS",
            "news_sources_status": "UNAVAILABLE",
            "last_calibration_utc": None,
            "shelter_mode": False,
            "kill_switch": False,
            "provider_mode": settings.provider_mode,
        },
    }

