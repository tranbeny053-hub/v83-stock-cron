"""Machine credentials: synthetic, route-scoped, compared by digest, read from the registry.

The registry is read on EVERY authentication, with no cache: a rotation or a revocation applies to
the next request, and a registry that cannot be read authenticates nothing.
"""

import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from crypto_probability_engine.automation import credentials
from crypto_probability_engine.automation.credentials import (
    MAX_CONCURRENT_REGISTRY_LOOKUPS,
    REGISTRY_TIMEOUT_SECONDS,
    CredentialRecord,
    CredentialRefusal,
    InMemoryCredentialRegistry,
    MachinePrincipal,
    PostgresCredentialRegistry,
    RegistryUnavailable,
    authenticate,
    secret_digest,
    validated_record,
)
from tests.automation.conftest import (
    CREDENTIAL_ID,
    SYNTHETIC_SECRET,
    active_record,
    registry,
    token,
    utc,
)

NOW = utc(2026, 9, 30)
OTHER_SECRET = "SYNTHETIC-rotated-secret-not-a-credential-1"


def test_valid_machine_principal():
    principal = authenticate(token(), registry(), now=NOW)
    assert principal == MachinePrincipal(CREDENTIAL_ID)
    assert principal.evidence_origin == "AUTOMATED_RADAR"
    assert SYNTHETIC_SECRET not in repr(principal)


@pytest.mark.parametrize("presented", [None, ""])
def test_missing_credential_never_reads_the_registry(presented):
    source = registry()
    assert authenticate(presented, source, now=NOW) is CredentialRefusal.MISSING
    assert source.lookups == 0


@pytest.mark.parametrize(
    "presented",
    [
        token().replace("ucpea.", "other.", 1),
        token(CREDENTIAL_ID, "A" * 42),
        token(CREDENTIAL_ID, "A" * 44),
        token(CREDENTIAL_ID, "!" + "A" * 42),
        token("UPPER-ID"),
        "A" * 129,
    ],
)
def test_malformed_credential_never_reads_the_registry(presented):
    source = registry()
    assert authenticate(presented, source, now=NOW) is CredentialRefusal.MALFORMED
    assert source.lookups == 0


def test_unknown_credential_id():
    assert authenticate(token("unknown-id"), registry(), now=NOW) is CredentialRefusal.UNKNOWN


def test_wrong_secret():
    presented = token(CREDENTIAL_ID, "A" * 43)
    assert authenticate(presented, registry(), now=NOW) is CredentialRefusal.MISMATCH


def test_revoked():
    revoked = registry(active_record(status="REVOKED"))
    assert authenticate(token(), revoked, now=NOW) is CredentialRefusal.REVOKED


def test_a_revoked_credential_with_a_wrong_value_is_a_mismatch_not_a_revocation_oracle():
    revoked = registry(active_record(status="REVOKED"))
    assert authenticate(token(CREDENTIAL_ID, "A" * 43), revoked, now=NOW) is (
        CredentialRefusal.MISMATCH
    )


@pytest.mark.parametrize("offset", [0, 1])
def test_expiry_is_inclusive(offset):
    expiring = registry(active_record(not_after_utc=NOW))
    assert authenticate(token(), expiring, now=NOW + timedelta(microseconds=offset)) is (
        CredentialRefusal.EXPIRED
    )


def test_just_before_expiry_is_valid():
    expiring = registry(active_record(not_after_utc=NOW))
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
def test_constant_time_digest_comparison_is_used(monkeypatch, presented, expected):
    calls = []
    original = credentials.hmac.compare_digest

    def spy(left, right):
        calls.append((left, right))
        return original(left, right)

    monkeypatch.setattr(credentials.hmac, "compare_digest", spy)
    assert authenticate(presented, registry(), now=NOW) == expected
    assert len(calls) == 1
    left, right = calls[0]
    assert left == secret_digest(presented.rsplit(".", 1)[1])
    assert len(left) == len(right) == 64
    if expected != CredentialRefusal.UNKNOWN:
        assert right == secret_digest(SYNTHETIC_SECRET)


def test_a_record_under_another_id_never_authenticates():
    class Lying:
        def lookup(self, credential_id):
            return active_record(credential_id="someone-else")

    assert authenticate(token(), Lying(), now=NOW) is CredentialRefusal.MISMATCH


# ------------------------------------------------------------------ rotation and revocation, live


def test_rotation_overlaps_then_revocation_applies_to_the_very_next_request():
    """No cache and no restart: the same registry object answers each step differently."""

    source = registry()
    assert isinstance(authenticate(token(), source, now=NOW), MachinePrincipal)
    source.put(active_record("test-radar-2", OTHER_SECRET))
    assert isinstance(authenticate(token(), source, now=NOW), MachinePrincipal)
    assert isinstance(
        authenticate(token("test-radar-2", OTHER_SECRET), source, now=NOW), MachinePrincipal
    )
    source.put(active_record(status="REVOKED"))
    assert authenticate(token(), source, now=NOW) is CredentialRefusal.REVOKED
    assert authenticate(token("test-radar-2", OTHER_SECRET), source, now=NOW) == (
        MachinePrincipal("test-radar-2")
    )
    assert source.lookups == 5, "every authentication read the registry"


def test_the_registry_is_read_on_every_authentication():
    source = registry()
    for _ in range(3):
        authenticate(token(), source, now=NOW)
    assert source.lookups == 3


def test_an_unavailable_registry_authenticates_nothing():
    class Down:
        def lookup(self, credential_id):
            raise RegistryUnavailable("synthetic outage")

    with pytest.raises(RegistryUnavailable):
        authenticate(token(), Down(), now=NOW)


# ------------------------------------------------------------------ the row shape


@pytest.mark.parametrize(
    "row",
    [
        ("BAD ID", secret_digest(SYNTHETIC_SECRET), "ACTIVE", None),
        (CREDENTIAL_ID, "A" * 64, "ACTIVE", None),
        (CREDENTIAL_ID, SYNTHETIC_SECRET, "ACTIVE", None),
        (CREDENTIAL_ID, secret_digest(SYNTHETIC_SECRET), "DISABLED", None),
        (CREDENTIAL_ID, secret_digest(SYNTHETIC_SECRET), "ACTIVE", datetime(2026, 1, 1)),
        (CREDENTIAL_ID, secret_digest(SYNTHETIC_SECRET), "ACTIVE", "2026-01-01T00:00:00Z"),
        (None, secret_digest(SYNTHETIC_SECRET), "ACTIVE", None),
    ],
)
def test_a_malformed_registry_row_fails_closed(row):
    with pytest.raises(RegistryUnavailable):
        validated_record(*row)


def test_a_well_formed_row_is_a_record_holding_only_a_digest():
    record = validated_record(
        CREDENTIAL_ID, secret_digest(SYNTHETIC_SECRET), "ACTIVE", datetime(2026, 10, 1, tzinfo=UTC)
    )
    assert record == CredentialRecord(
        CREDENTIAL_ID, secret_digest(SYNTHETIC_SECRET), "ACTIVE", datetime(2026, 10, 1, tzinfo=UTC)
    )
    assert SYNTHETIC_SECRET not in repr(record)


# ------------------------------------------------------------------ the production registry


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        self.connection.statements.append((query, params))
        if self.connection.fail_execute:
            raise RuntimeError("synthetic statement failure")

    def fetchone(self):
        return self.connection.row


class FakeConnection:
    def __init__(self, row, fail_execute=False):
        self.row = row
        self.fail_execute = fail_execute
        self.statements = []
        self.rollbacks = 0
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return FakeCursor(self)

    def rollback(self):
        self.rollbacks += 1

    def commit(self):  # pragma: no cover - the registry never commits
        self.commits += 1


class FakeDriver:
    def __init__(self, row=None, *, fail_connect=False, fail_execute=False):
        self.row = row
        self.fail_connect = fail_connect
        self.fail_execute = fail_execute
        self.connects = []
        self.connections = []

    def connect(self, *args, **kwargs):
        self.connects.append((args, kwargs))
        if self.fail_connect:
            raise OSError("synthetic: could not reach the host")
        connection = FakeConnection(self.row, self.fail_execute)
        self.connections.append(connection)
        return connection


ROW = (CREDENTIAL_ID, secret_digest(SYNTHETIC_SECRET), "ACTIVE", None)


def test_the_postgres_registry_reads_one_bounded_row_per_lookup_and_keeps_nothing():
    driver = FakeDriver(ROW)
    source = PostgresCredentialRegistry("synthetic-offline-database", connect=driver.connect)
    for _ in range(2):
        assert source.lookup(CREDENTIAL_ID) == active_record()
    assert len(driver.connects) == 2, "a connection per lookup: no cache"
    args, kwargs = driver.connects[0]
    assert args == ("synthetic-offline-database",)
    assert kwargs == {
        "connect_timeout": max(1, int(REGISTRY_TIMEOUT_SECONDS)),
        "autocommit": False,
        "prepare_threshold": None,
    }
    connection = driver.connections[0]
    (timeout_sql, timeout_params), (lookup_sql, lookup_params) = connection.statements
    assert "statement_timeout" in timeout_sql and "lock_timeout" in timeout_sql
    assert timeout_params["timeout"] == f"{int(REGISTRY_TIMEOUT_SECONDS * 1000)}ms"
    assert "FROM public.automation_credential" in lookup_sql
    assert "WHERE credential_id = %(credential_id)s" in lookup_sql
    assert lookup_params["credential_id"] == CREDENTIAL_ID
    assert connection.rollbacks == 1 and connection.commits == 0, "a read never commits"
    for statement, _params in connection.statements:
        assert not any(word in statement.upper() for word in ("INSERT", "UPDATE", "DELETE"))


def test_an_absent_row_is_unknown_not_an_error():
    source = PostgresCredentialRegistry("synthetic", connect=FakeDriver(None).connect)
    assert source.lookup(CREDENTIAL_ID) is None


def test_no_database_url_fails_closed_without_connecting():
    driver = FakeDriver(ROW)
    for url in (None, ""):
        with pytest.raises(RegistryUnavailable):
            PostgresCredentialRegistry(url, connect=driver.connect).lookup(CREDENTIAL_ID)
    assert driver.connects == []


@pytest.mark.parametrize("failure", ["connect", "execute"])
def test_a_database_failure_fails_closed_without_leaking_its_message(failure):
    driver = FakeDriver(ROW, fail_connect=failure == "connect", fail_execute=failure == "execute")
    source = PostgresCredentialRegistry("synthetic", connect=driver.connect)
    with pytest.raises(RegistryUnavailable) as refused:
        source.lookup(CREDENTIAL_ID)
    assert "synthetic" not in str(refused.value) and "host" not in str(refused.value)


def test_a_malformed_stored_row_fails_closed():
    driver = FakeDriver((CREDENTIAL_ID, "not-a-digest", "ACTIVE", None))
    with pytest.raises(RegistryUnavailable):
        PostgresCredentialRegistry("synthetic", connect=driver.connect).lookup(CREDENTIAL_ID)


def test_constructing_the_registry_never_connects():
    driver = FakeDriver(ROW)
    PostgresCredentialRegistry("synthetic", connect=driver.connect)
    assert driver.connects == []


def test_reads_beyond_the_cap_are_refused_at_once_instead_of_queueing():
    assert MAX_CONCURRENT_REGISTRY_LOOKUPS == 2
    entered = threading.Barrier(MAX_CONCURRENT_REGISTRY_LOOKUPS + 1)
    release = threading.Event()

    connects = []

    def slow_connect(*args, **kwargs):
        connects.append(threading.current_thread().name)
        if len(connects) <= MAX_CONCURRENT_REGISTRY_LOOKUPS:  # only the reads that fill the cap
            entered.wait(timeout=5)
            release.wait(timeout=5)
        return FakeConnection(ROW)

    source = PostgresCredentialRegistry("synthetic", connect=slow_connect)
    results = []
    threads = [
        threading.Thread(target=lambda: results.append(source.lookup(CREDENTIAL_ID)))
        for _ in range(MAX_CONCURRENT_REGISTRY_LOOKUPS)
    ]
    for thread in threads:
        thread.start()
    entered.wait(timeout=5)
    with pytest.raises(RegistryUnavailable, match="too many"):
        source.lookup(CREDENTIAL_ID)
    release.set()
    for thread in threads:
        thread.join(timeout=5)
    assert results == [active_record()] * MAX_CONCURRENT_REGISTRY_LOOKUPS
    assert len(connects) == MAX_CONCURRENT_REGISTRY_LOOKUPS, "the refused read never connected"
    assert source.lookup(CREDENTIAL_ID) == active_record(), "the slots are released"


def test_the_in_memory_registry_is_never_wired_in_production():
    import inspect

    from crypto_probability_engine.api import automation_endpoint

    source = inspect.getsource(automation_endpoint)
    assert "PostgresCredentialRegistry(settings.supabase_db_url)" in source
    assert "InMemoryCredentialRegistry" not in source
    assert InMemoryCredentialRegistry.__doc__ and "never wired in production" in (
        InMemoryCredentialRegistry.__doc__
    )


def test_replace_keeps_the_record_immutable():
    record = active_record()
    assert replace(record, status="REVOKED").status == "REVOKED" and record.status == "ACTIVE"
