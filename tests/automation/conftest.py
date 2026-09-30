"""Shared fixtures for the automation route (F1). Synthetic only: no holdout, no network, no secret.

Market data is the repository's deterministic fixture snapshot, served through the real analysis
pipeline with ``select_market_data`` replaced. Credentials live in an in-memory registry holding the
digest of a fixed, obviously synthetic value; no real credential exists anywhere in the tests.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from crypto_probability_engine.adapters.provider_selection import ProviderSelectionResult
from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.automation import config as automation_config
from crypto_probability_engine.automation.credentials import (
    CREDENTIAL_HEADER,
    CredentialRecord,
    InMemoryCredentialRegistry,
    secret_digest,
)
from crypto_probability_engine.automation.ledger import InMemoryAutomationLedger
from crypto_probability_engine.automation.service import RadarEvidenceService
from crypto_probability_engine.config.settings import Settings
from tests.fixtures.market_data import make_snapshot

AUTOMATION_PATH = "/v1/automation/radar-evidence"
# 43 URL-safe characters, as the token format requires; obviously not a real secret.
SYNTHETIC_SECRET = "SYNTHETIC-test-secret-not-a-credential-0000"
CREDENTIAL_ID = "test-radar"
SKILL_EVIDENCE = {"verdict": "INSUFFICIENT_EVIDENCE", "n": 0, "observed_directional_rate": None}


def token(credential_id: str = CREDENTIAL_ID, secret: str = SYNTHETIC_SECRET) -> str:
    return f"ucpea.{credential_id}.{secret}"


def credential_env(*, enabled: str = "1", **extra: str) -> dict[str, str]:
    """The route's environment: the kill switch and quotas only, never a credential."""

    return {automation_config.ENV_ENABLED: enabled, **extra}


def active_record(
    credential_id: str = CREDENTIAL_ID, secret: str = SYNTHETIC_SECRET, **changes: object
) -> CredentialRecord:
    fields = {
        "credential_id": credential_id,
        "secret_sha256": secret_digest(secret),
        "status": "ACTIVE",
        "not_after_utc": None,
        **changes,
    }
    return CredentialRecord(**fields)


def registry(*records: CredentialRecord) -> InMemoryCredentialRegistry:
    """The synthetic registry; with no argument it holds the one ACTIVE test credential."""

    return InMemoryCredentialRegistry(records or (active_record(),))


def request_body(**overrides: object) -> dict:
    body = {
        "symbol": "BTC",
        "primary_timeframe": "4H",
        "client_request_id": "3f9d2c1e-8a4b-4c2d-9e6f-1a2b3c4d5e6f",
        "deadline_ms": 30000,
    }
    body.update(overrides)
    return body


def fixture_selection(provider: str = "okx", data_source: str = "OKX_PUBLIC"):
    def select(symbol, timeframe, *, settings):
        del settings
        return ProviderSelectionResult(
            snapshot=make_snapshot(provider=provider, symbol=symbol.display, timeframe=timeframe),
            provider_state={
                "status": "OK",
                "active_provider": provider,
                "cross_provider_state": "UNAVAILABLE",
                "providers": {provider: {"status": "OK"}},
            },
            data_quality={
                "status": "OK",
                "warnings": [],
                "freshness_budget": "DEFAULT_PHASE1A",
                "is_live_data": True,
                "data_source": data_source,
                "latest_candle_age_seconds": 0,
                "provider_failures": {},
                "cross_provider_state": "UNAVAILABLE",
            },
        )

    return select


@pytest.fixture
def fixture_market(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real pipeline on the deterministic fixture snapshot; no network, no skill cache."""

    monkeypatch.setattr(analysis_service, "select_market_data", fixture_selection())
    monkeypatch.setattr(
        analysis_service, "get_cached_skill_evidence", lambda _timeframe: dict(SKILL_EVIDENCE)
    )


@dataclass
class AutomationHarness:
    client: TestClient
    ledger: InMemoryAutomationLedger
    app: object
    env: dict[str, str]
    registry: InMemoryCredentialRegistry

    def post(self, body: object = None, *, headers: dict | None = None, raw: bytes | None = None):
        send = {CREDENTIAL_HEADER: token()} if headers is None else headers
        if raw is not None:
            return self.client.post(AUTOMATION_PATH, content=raw, headers=send)
        payload = request_body() if body is None else body
        return self.client.post(AUTOMATION_PATH, json=payload, headers=send)


@pytest.fixture
def harness_factory(fixture_market) -> Callable[..., AutomationHarness]:
    del fixture_market

    def build(
        *,
        env: dict[str, str] | None = None,
        analyzer=None,
        clock=None,
        monotonic=None,
        ledger: InMemoryAutomationLedger | None = None,
        credential_registry: InMemoryCredentialRegistry | None = None,
    ) -> AutomationHarness:
        settings = Settings(data_mode="fixture")
        app = create_app(settings)
        chosen_env = credential_env() if env is None else env
        chosen_ledger = ledger or InMemoryAutomationLedger()
        chosen_registry = registry() if credential_registry is None else credential_registry
        kwargs = {}
        if analyzer is not None:
            kwargs["analyzer"] = analyzer
        if clock is not None:
            kwargs["clock"] = clock
        if monotonic is not None:
            kwargs["monotonic"] = monotonic
        app.state.automation_service = RadarEvidenceService(
            settings=settings,
            ledger=chosen_ledger,
            registry=chosen_registry,
            config_loader=lambda: automation_config.load_config(chosen_env),
            **kwargs,
        )
        return AutomationHarness(TestClient(app), chosen_ledger, app, chosen_env, chosen_registry)

    return build


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)
