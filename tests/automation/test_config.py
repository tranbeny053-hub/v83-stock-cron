"""Fail-closed parsing of the automation kill switch and quotas; no credential lives here."""

from dataclasses import fields

import pytest

from crypto_probability_engine.automation import config as automation_config
from crypto_probability_engine.automation.config import (
    ENV_ENABLED,
    ENV_QUOTA_PER_5MIN,
    ENV_QUOTA_PER_DAY,
    load_config,
)
from tests.automation.conftest import credential_env


def test_default_disabled_and_default_quotas():
    config = load_config({})
    assert not config.enabled and not config.usable
    assert config.problems == ()
    assert (config.quota_per_5min, config.quota_per_day) == (6, 120)


@pytest.mark.parametrize("enabled", ["1", "true", "TRUE", " 1 "])
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


def test_no_credential_or_digest_is_read_from_the_environment():
    """Credentials live only in the database registry, so a rotation needs no restart."""

    assert [field.name for field in fields(automation_config.AutomationConfig)] == [
        "enabled",
        "quota_per_5min",
        "quota_per_day",
        "problems",
    ]
    assert not hasattr(automation_config, "ENV_CREDENTIALS")
    retired = {**credential_env(), "UCPE_AUTOMATION_CREDENTIALS": '[{"credential_id": "x"}]'}
    assert load_config(retired) == load_config(credential_env())


@pytest.mark.parametrize(("five", "day"), [(1, 1), (60, 2000), (6, 120)])
def test_quota_inclusive_bounds(five, day):
    config = load_config(
        credential_env(**{ENV_QUOTA_PER_5MIN: str(five), ENV_QUOTA_PER_DAY: str(day)})
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


def test_a_disabled_route_with_problems_is_reported_disabled_first():
    config = load_config({ENV_ENABLED: "0", ENV_QUOTA_PER_5MIN: "0"})
    assert not config.enabled and config.problems
