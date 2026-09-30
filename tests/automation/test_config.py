"""Fail-closed parsing of the synthetic automation registry and quotas."""

import json
from dataclasses import asdict

import pytest

from crypto_probability_engine.automation.config import (
    ENV_CREDENTIALS,
    ENV_ENABLED,
    ENV_QUOTA_PER_5MIN,
    ENV_QUOTA_PER_DAY,
    load_config,
)
from crypto_probability_engine.automation.credentials import secret_digest
from tests.automation.conftest import SYNTHETIC_SECRET, credential_env, token


def test_default_disabled_and_default_quotas():
    config = load_config({})
    assert not config.enabled and not config.usable
    assert config.problems == ()
    assert config.credentials == ()
    assert (config.quota_per_5min, config.quota_per_day) == (6, 120)


@pytest.mark.parametrize("enabled", ["1", "true"])
def test_explicit_enable(enabled):
    config = load_config(credential_env(enabled=enabled))
    assert config.enabled and config.usable and not config.problems


@pytest.mark.parametrize("enabled", ["", "0", "false"])
def test_explicit_disable(enabled):
    config = load_config(credential_env(enabled=enabled))
    assert not config.enabled and not config.usable and not config.problems


@pytest.mark.parametrize("enabled", ["yes", "2", "on", "null"])
def test_invalid_enable_value_fails_closed(enabled):
    config = load_config(credential_env(enabled=enabled))
    assert not config.enabled and not config.usable and config.problems


@pytest.mark.parametrize(
    "records",
    [
        [],
        [
            {
                "credential_id": "test-radar",
                "secret_sha256": secret_digest(SYNTHETIC_SECRET),
                "status": "REVOKED",
            }
        ],
    ],
)
def test_enabled_requires_an_active_credential(records):
    config = load_config(credential_env(records=records))
    assert config.enabled and not config.usable
    assert "no ACTIVE credential is configured" in config.problems


@pytest.mark.parametrize("raw", ["{", "{}", '"registry"', "null", "[NaN]", "[1]"])
def test_registry_requires_an_array_of_objects(raw):
    config = load_config({ENV_ENABLED: "1", ENV_CREDENTIALS: raw})
    assert config.problems and not config.usable


@pytest.mark.parametrize(
    "change",
    [
        {"credential_id": "BAD ID"},
        {"credential_id": "ab"},
        {"credential_id": "a" * 33},
        {"secret_sha256": "a" * 63},
        {"secret_sha256": "A" * 64},
        {"secret_sha256": SYNTHETIC_SECRET},
        {"status": "DISABLED"},
        {"unexpected": "synthetic"},
        {"not_after_utc": "not-a-date"},
        {"not_after_utc": "2026-01-01T00:00:00+00:00"},
        {"not_after_utc": None},
    ],
)
def test_invalid_credential_record(change):
    env = credential_env()
    records = json.loads(env[ENV_CREDENTIALS])
    records[0].update(change)
    config = load_config(credential_env(records=records))
    assert config.problems and not config.usable
    assert SYNTHETIC_SECRET not in repr(config)


@pytest.mark.parametrize("key", ["credential_id", "secret_sha256", "status"])
def test_missing_registry_key(key):
    records = json.loads(credential_env()[ENV_CREDENTIALS])
    del records[0][key]
    assert load_config(credential_env(records=records)).problems


def test_duplicate_id_is_refused():
    records = json.loads(credential_env()[ENV_CREDENTIALS])
    config = load_config(credential_env(records=records * 2))
    assert not config.usable
    assert any("duplicate credential_id" in problem for problem in config.problems)


@pytest.mark.parametrize(("five", "day"), [(1, 1), (60, 2000), (6, 120)])
def test_quota_inclusive_bounds(five, day):
    config = load_config(
        credential_env(
            **{
                ENV_QUOTA_PER_5MIN: str(five),
                ENV_QUOTA_PER_DAY: str(day),
            }
        )
    )
    assert config.usable
    assert (config.quota_per_5min, config.quota_per_day) == (five, day)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        (ENV_QUOTA_PER_5MIN, "0"),
        (ENV_QUOTA_PER_5MIN, "61"),
        (ENV_QUOTA_PER_DAY, "0"),
        (ENV_QUOTA_PER_DAY, "2001"),
        (ENV_QUOTA_PER_5MIN, "1.5"),
        (ENV_QUOTA_PER_DAY, "1.0"),
        (ENV_QUOTA_PER_5MIN, "true"),
        (ENV_QUOTA_PER_DAY, "-1"),
    ],
)
def test_invalid_quota_is_refused(name, value):
    config = load_config(credential_env(**{name: value}))
    assert config.problems and not config.usable


def test_short_quota_cannot_exceed_daily_quota():
    config = load_config(credential_env(**{ENV_QUOTA_PER_5MIN: "6", ENV_QUOTA_PER_DAY: "5"}))
    assert not config.usable
    assert "the 5-minute quota cannot exceed the daily quota" in config.problems


def test_records_only_hold_digests_and_parse_utc_expiry():
    records = json.loads(credential_env()[ENV_CREDENTIALS])
    records[0]["not_after_utc"] = "2026-10-01T00:00:00Z"
    config = load_config(credential_env(records=records))
    assert config.usable
    [record] = config.credentials
    assert set(asdict(record)) == {"credential_id", "secret_sha256", "status", "not_after_utc"}
    assert record.secret_sha256 == secret_digest(SYNTHETIC_SECRET)
    assert record.not_after_utc.isoformat() == "2026-10-01T00:00:00+00:00"
    assert SYNTHETIC_SECRET not in repr(config) and token() not in repr(config)
