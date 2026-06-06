"""Runtime settings sourced from environment variables."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, Field

from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A
from crypto_probability_engine.config.env_flags import parse_bool


class Settings(BaseModel):
    app_name: str = "Ultimate Crypto Probability Engine"
    app_version: str = "0.1.0"
    schema_version: str = "1.1-crypto-probability"
    host: str = "0.0.0.0"
    port: int = 7860
    session_ttl_seconds: int = 3600
    session_cookie_secure: bool = True
    dev_mode_enabled: bool = False
    enable_derivatives: bool = False
    strict_cors_origins: tuple[str, ...] = ()
    provider_mode: str = "public"
    recent_run_limit: int = 100
    default_asset_class: str = DEFAULT_PHASE1A.asset_class_default
    default_analysis_mode: str = DEFAULT_PHASE1A.analysis_mode_default
    default_timeframe: str = DEFAULT_PHASE1A.primary_timeframe
    access_code_hash: str | None = Field(default=None, repr=False)
    dev_mode_code_hash: str | None = Field(default=None, repr=False)
    access_code_salt: str = Field(default=DEFAULT_PHASE1A.access_code_local_salt, repr=False)
    access_code_pbkdf2_iterations: int = DEFAULT_PHASE1A.access_code_pbkdf2_iterations
    session_signing_key: str | None = Field(default=None, repr=False)
    external_store_configured: bool = False

    @classmethod
    def from_env(cls) -> Settings:
        origins_raw = os.environ.get("UCPE_CORS_ORIGINS", "")
        origins = tuple(item.strip() for item in origins_raw.split(",") if item.strip())
        return cls(
            app_version=os.environ.get("UCPE_APP_VERSION", "0.1.0"),
            schema_version=os.environ.get("UCPE_SCHEMA_VERSION", "1.1-crypto-probability"),
            port=int(os.environ.get("PORT", os.environ.get("UCPE_PORT", "7860"))),
            session_ttl_seconds=int(os.environ.get("UCPE_SESSION_TTL_SECONDS", "3600")),
            session_cookie_secure=parse_bool(os.environ.get("UCPE_COOKIE_SECURE"), default=True),
            dev_mode_enabled=parse_bool(os.environ.get("UCPE_DEV_MODE_ENABLED"), default=False),
            enable_derivatives=parse_bool(os.environ.get("UCPE_ENABLE_DERIVATIVES"), default=False),
            strict_cors_origins=origins,
            provider_mode=os.environ.get("UCPE_PROVIDER_MODE", "public"),
            recent_run_limit=int(os.environ.get("UCPE_RECENT_RUN_LIMIT", "100")),
            access_code_hash=os.environ.get("APP_ACCESS_CODE_HASH"),
            dev_mode_code_hash=os.environ.get("DEV_MODE_CODE_HASH"),
            access_code_salt=os.environ.get(
                "UCPE_ACCESS_CODE_SALT",
                DEFAULT_PHASE1A.access_code_local_salt,
            ),
            access_code_pbkdf2_iterations=int(
                os.environ.get(
                    "UCPE_ACCESS_CODE_PBKDF2_ITERATIONS",
                    str(DEFAULT_PHASE1A.access_code_pbkdf2_iterations),
                )
            ),
            session_signing_key=os.environ.get("SESSION_SIGNING_KEY"),
            external_store_configured=bool(os.environ.get("SUPABASE_URL")),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()
