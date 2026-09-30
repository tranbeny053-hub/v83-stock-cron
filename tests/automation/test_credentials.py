"""Machine credentials are synthetic, route-scoped, and compared by digest."""

from dataclasses import replace
from datetime import timedelta

import pytest

from crypto_probability_engine.automation import credentials
from crypto_probability_engine.automation.config import load_config
from crypto_probability_engine.automation.credentials import (
    CredentialRefusal,
    MachinePrincipal,
    authenticate,
    secret_digest,
)
from tests.automation.conftest import (
    CREDENTIAL_ID,
    SYNTHETIC_SECRET,
    credential_env,
    token,
    utc,
)

NOW = utc(2026, 9, 30)


@pytest.fixture
def records():
    return load_config(credential_env()).credentials


def test_valid_machine_principal(records):
    principal = authenticate(token(), records, now=NOW)
    assert principal == MachinePrincipal(CREDENTIAL_ID)
    assert principal.evidence_origin == "AUTOMATED_RADAR"
    assert SYNTHETIC_SECRET not in repr(principal)


@pytest.mark.parametrize("presented", [None, ""])
def test_missing_credential(records, presented):
    assert authenticate(presented, records, now=NOW) is CredentialRefusal.MISSING


@pytest.mark.parametrize(
    "presented",
    [
        token().replace("ucpea.", "other.", 1),
        token(CREDENTIAL_ID, "A" * 42),
        token(CREDENTIAL_ID, "A" * 44),
        token(CREDENTIAL_ID, "!" + "A" * 42),
        "A" * 129,
    ],
)
def test_malformed_credential(records, presented):
    assert authenticate(presented, records, now=NOW) is CredentialRefusal.MALFORMED


def test_unknown_credential_id(records):
    assert authenticate(token("unknown-id"), records, now=NOW) is CredentialRefusal.UNKNOWN


def test_wrong_secret(records):
    assert (
        authenticate(token(CREDENTIAL_ID, "A" * 43), records, now=NOW) is CredentialRefusal.MISMATCH
    )


def test_revoked(records):
    revoked = [replace(records[0], status="REVOKED")]
    assert authenticate(token(), revoked, now=NOW) is CredentialRefusal.REVOKED


@pytest.mark.parametrize("offset", [0, 1])
def test_expiry_is_inclusive(records, offset):
    expiring = [replace(records[0], not_after_utc=NOW)]
    assert authenticate(token(), expiring, now=NOW + timedelta(microseconds=offset)) is (
        CredentialRefusal.EXPIRED
    )


def test_just_before_expiry_is_valid(records):
    expiring = [replace(records[0], not_after_utc=NOW)]
    assert isinstance(
        authenticate(token(), expiring, now=NOW - timedelta(microseconds=1)), MachinePrincipal
    )


@pytest.mark.parametrize(
    ("presented", "expected"),
    [
        (token(), MachinePrincipal(CREDENTIAL_ID)),
        (token(CREDENTIAL_ID, "A" * 43), CredentialRefusal.MISMATCH),
        (token("unknown-id"), CredentialRefusal.UNKNOWN),
    ],
)
def test_constant_time_digest_comparison_is_used(monkeypatch, records, presented, expected):
    calls = []
    original = credentials.hmac.compare_digest

    def spy(left, right):
        calls.append((left, right))
        return original(left, right)

    monkeypatch.setattr(credentials.hmac, "compare_digest", spy)
    assert authenticate(presented, records, now=NOW) == expected
    assert len(calls) == 1
    left, right = calls[0]
    assert left == secret_digest(presented.rsplit(".", 1)[1])
    assert len(left) == len(right) == 64
    if expected != CredentialRefusal.UNKNOWN:
        assert right == records[0].secret_sha256
