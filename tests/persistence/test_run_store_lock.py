"""The in-memory run store used from several threads (persistence/run_store.py).

Each request runs on its own thread, so one adds a run while another lists the store. Before the
store had a lock, that listing could raise ("OrderedDict mutated during iteration"), an add could
raise while it evicted, a run could be listed for an instant without its origin, and the store
could come to rest one run short or keep the origin of a run it no longer held. put, get and the
copy a listing is made from now each happen whole under the store's lock; the rows are built
after it is released.

The stress switches threads every microsecond (a server switches every five milliseconds), so
that what the lock prevents would show within its one second. Nothing here asserts on time: the
second and the counts only end the stress, and every other wait is a guard against a hang.
"""

from __future__ import annotations

import sys
import threading
from collections import Counter
from dataclasses import dataclass, field

import pytest

from crypto_probability_engine.persistence.run_store import InMemoryRunStore

USER = "USER_REQUESTED"
OTHER_ORIGINS = ("CONTROLLED_SMOKE", "SCHEDULED_SHADOW_EVIDENCE")
WRITERS = READERS = 6
SWITCH_EVERY_SECONDS = 1e-6
# The stress ends at whichever comes first: its second, or one thread's count.
STRESS_SECONDS = 1.0
PUTS_PER_WRITER = 5_000
LISTINGS_PER_READER = 500
# No test waits this long unless the store hangs; then it fails instead of hanging the suite.
HANG_GUARD_SECONDS = 30.0


def payload(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "symbol": "BTC/USDT",
        "normalized_symbol": "BTC/USDT",
        "analysis_mode": "METRICS_ONLY",
        "as_of_utc": "2026-10-11T00:00:00Z",
        "analysis_hash": f"hash-{run_id}",
        "timeframes": {"primary": "4H"},
        "data_quality": {"data_source": "FIXTURE_DEMO", "is_live_data": False},
        "detail_view": {"run_id": run_id},
    }


def origin_for(number: int) -> str:
    """One run in four is of another origin, as a smoke or a scheduled run is."""

    return OTHER_ORIGINS[(number // 4) % 2] if number % 4 == 3 else USER


def named(origin: str, name: str) -> str:
    """A run id that says which origin the run is put under."""

    return f"{origin}:{name}"


def put_under(run_id: str) -> str:
    return run_id.split(":", maxsplit=1)[0]


@dataclass
class Seen:
    """What the threads of one stress saw. Each thread fills its own, and they are added up."""

    puts: int = 0
    listings: int = 0
    put_errors: Counter = field(default_factory=Counter)
    listing_errors: Counter = field(default_factory=Counter)
    rows_in_a_listing: Counter = field(default_factory=Counter)
    listings_with_a_run_twice: int = 0
    listed_under_a_wrong_origin: Counter = field(default_factory=Counter)
    rows_of_another_origin: int = 0
    rows_shown_as_user_requested: int = 0
    of_another_origin_shown_as_user_requested: int = 0
    gets_of_another_run: int = 0
    threads_that_never_ended: int = 0

    def add(self, other: Seen) -> None:
        for name, value in vars(other).items():
            if isinstance(value, Counter):
                getattr(self, name).update(value)
            else:
                setattr(self, name, getattr(self, name) + value)


def stressed(store: InMemoryRunStore) -> Seen:
    """Writers add runs non-stop to a full store, so every add evicts; readers list it non-stop
    and check every row they are given."""

    limit = store.limit
    for number in range(limit):
        run_id = named(origin_for(number), f"held-{number}")
        store.put(run_id, payload(run_id), prediction_origin=put_under(run_id))
    stop = threading.Event()

    def write(writer: int, seen: Seen) -> None:
        for number in range(PUTS_PER_WRITER):
            run_id = named(origin_for(number), f"writer-{writer}-{number}")
            added = payload(run_id)
            seen.puts += 1
            try:
                store.put(run_id, added, prediction_origin=put_under(run_id))
                held = store.get(run_id)
            except Exception as error:
                seen.put_errors[f"{type(error).__name__}: {error}"] += 1
            else:
                # Its own run, or nothing once later adds have evicted it: never another's.
                seen.gets_of_another_run += held is not None and held is not added
            if stop.is_set():
                return
        stop.set()

    def read(_reader: int, seen: Seen) -> None:
        for _number in range(LISTINGS_PER_READER):
            seen.listings += 1
            try:
                rows = store.list_runs()
            except Exception as error:
                seen.listing_errors[f"{type(error).__name__}: {error}"] += 1
                rows = []
            else:
                seen.rows_in_a_listing[len(rows)] += 1
            run_ids = [row["run_id"] for row in rows]
            seen.listings_with_a_run_twice += len(set(run_ids)) != len(run_ids)
            for row in rows:
                was_put_under, listed_under = put_under(row["run_id"]), row["prediction_origin"]
                if listed_under != was_put_under:
                    seen.listed_under_a_wrong_origin[f"{was_put_under} as {listed_under}"] += 1
                seen.rows_of_another_origin += was_put_under != USER
                # What the routes show a signed-in user: the rows listed as USER_REQUESTED.
                if listed_under == USER:
                    seen.rows_shown_as_user_requested += 1
                    seen.of_another_origin_shown_as_user_requested += was_put_under != USER
            if stop.is_set():
                return
        stop.set()

    each = [(write, number, Seen()) for number in range(WRITERS)]
    each += [(read, number, Seen()) for number in range(READERS)]
    threads = [
        threading.Thread(target=work, args=(number, seen), daemon=True)
        for work, number, seen in each
    ]
    for thread in threads:
        thread.start()
    stop.wait(STRESS_SECONDS)
    stop.set()
    total = Seen()
    for thread, (_work, _number, seen) in zip(threads, each, strict=True):
        thread.join(HANG_GUARD_SECONDS)
        total.threads_that_never_ended += thread.is_alive()
        total.add(seen)
    return total


@dataclass
class Stress:
    store: InMemoryRunStore
    seen: Seen


@pytest.fixture(scope="module")
def stress() -> Stress:
    """One stress of one store, for the tests below: threads are switched every microsecond while
    it runs, and as they were before as soon as it ends."""

    store = InMemoryRunStore()
    usual = sys.getswitchinterval()
    sys.setswitchinterval(SWITCH_EVERY_SECONDS)
    try:
        return Stress(store, stressed(store))
    finally:
        sys.setswitchinterval(usual)


def test_no_add_and_no_listing_raises_while_the_store_is_added_to_and_listed(
    stress: Stress,
) -> None:
    seen = stress.seen

    assert seen.threads_that_never_ended == 0
    assert seen.puts >= WRITERS and seen.listings >= READERS, "every thread did its work"
    assert seen.put_errors == {}, "an add raised"
    assert seen.listing_errors == {}, "a listing raised"


def test_every_listing_under_stress_is_the_whole_store_as_it_stood(stress: Stress) -> None:
    seen, limit = stress.seen, stress.store.limit

    assert seen.rows_in_a_listing == {limit: seen.listings}, "a full store lists its limit"
    assert seen.listings_with_a_run_twice == 0
    assert seen.listed_under_a_wrong_origin == {}, "each run is listed under the origin it has"
    assert seen.gets_of_another_run == 0


def test_the_store_rests_at_its_limit_and_every_origin_entry_has_its_run(stress: Stress) -> None:
    store = stress.store

    assert store.limit == 100, "the limit the server runs with"
    assert len(store.runs) == store.limit, "exactly the limit: not one over, not one short"
    assert set(store._prediction_origins) == set(store.runs)  # noqa: SLF001
    assert all(
        store._prediction_origins[run_id] == put_under(run_id)  # noqa: SLF001
        for run_id in store.runs
    )
    assert [row["run_id"] for row in store.list_runs()] == list(reversed(store.runs))


def test_a_run_of_another_origin_is_never_listed_as_user_requested_under_stress(
    stress: Stress,
) -> None:
    seen = stress.seen

    assert seen.rows_of_another_origin > 0, "runs of another origin were held, and were listed"
    assert seen.rows_shown_as_user_requested > 0
    assert seen.of_another_origin_shown_as_user_requested == 0


class ReadWhileARunIsAdded(dict):
    """A held analysis that stands for another request: while the listing reads it, another thread
    adds a run to the store and ends, as an analysis finishing at that moment does."""

    def __init__(self, held: dict, store: InMemoryRunStore) -> None:
        super().__init__(held)
        self.store, self.added = store, []

    def get(self, key: str, default: object = None) -> object:
        if key == "normalized_symbol" and not self.added:
            run_id = "added-1"
            adding = threading.Thread(
                target=self.store.put,
                args=(run_id, payload(run_id)),
                kwargs={"prediction_origin": OTHER_ORIGINS[0]},
                daemon=True,
            )
            adding.start()
            adding.join(HANG_GUARD_SECONDS)
            self.added.append(run_id if not adding.is_alive() else "an add that had to wait")
        return super().get(key, default)


def test_a_run_added_during_a_listing_does_not_disturb_it_and_is_in_the_next() -> None:
    store = InMemoryRunStore(limit=2)  # full: the add evicts the older run, and its origin
    store.put("older", payload("older"), prediction_origin=OTHER_ORIGINS[1])
    reading = ReadWhileARunIsAdded(payload("newer"), store)
    store.put("newer", reading, prediction_origin=USER)

    listed = store.list_runs()

    assert reading.added == ["added-1"], "the add did not wait for the listing to end"
    assert [(row["run_id"], row["prediction_origin"]) for row in listed] == [
        ("newer", USER),
        ("older", OTHER_ORIGINS[1]),
    ], "the store as it stood when the listing began: each run it held, under its origin"
    assert [(row["run_id"], row["prediction_origin"]) for row in store.list_runs()] == [
        ("added-1", OTHER_ORIGINS[0]),
        ("newer", USER),
    ], "the next listing has the run that was added, and no longer the run it evicted"
    assert store.get("older") is None and store.get("added-1") == payload("added-1")


class HeldByTheTest:
    """Stands in for the store's lock while the test holds it: it says when a call comes to it,
    and what the store holds each time the call lets go of it."""

    def __init__(self, store: InMemoryRunStore, something_happened: threading.Event) -> None:
        self.lock, self.times_come_to, self.store_when_let_go = threading.Lock(), 0, []
        self.store, self.something_happened = store, something_happened

    def __enter__(self) -> None:
        self.times_come_to += 1
        self.something_happened.set()
        self.lock.acquire()

    def __exit__(self, *_error: object) -> None:
        origins = dict(self.store._prediction_origins)  # noqa: SLF001
        self.store_when_let_go.append((list(self.store.runs), origins))
        self.lock.release()


CALLS = {
    "put": lambda store: store.put("added", payload("added"), prediction_origin=USER),
    "get": lambda store: store.get("held"),
    "list_runs": lambda store: [row["run_id"] for row in store.list_runs()],
}
RETURNS = {"put": None, "get": payload("held"), "list_runs": ["held"]}


@pytest.mark.parametrize("name", list(CALLS))
def test_put_get_and_the_listing_each_wait_for_the_lock_and_take_it_once(name: str) -> None:
    store = InMemoryRunStore(limit=1)  # full: the add evicts the run that is held
    store.put("held", payload("held"), prediction_origin=OTHER_ORIGINS[0])
    something_happened = threading.Event()
    lock = HeldByTheTest(store, something_happened)
    store._lock = lock  # noqa: SLF001
    returned = []

    def call() -> None:
        try:
            returned.append(CALLS[name](store))
        finally:
            something_happened.set()

    calling = threading.Thread(target=call, daemon=True)
    with lock.lock:
        calling.start()
        # The call came to the lock, or it ended without it: either is the end of the wait.
        assert something_happened.wait(HANG_GUARD_SECONDS)
        assert lock.times_come_to == 1 and returned == [], f"{name} did not wait for the lock"
        assert list(store.runs) == ["held"], "and it changed nothing while it waited"
    calling.join(HANG_GUARD_SECONDS)

    assert not calling.is_alive() and returned == [RETURNS[name]]
    # One taking of the lock, and the store is whole when it is let go: for an add, the new run
    # and its origin are in, and the run it evicted and that run's origin are out.
    assert lock.store_when_let_go == [
        (["added"], {"added": USER}) if name == "put" else (["held"], {"held": OTHER_ORIGINS[0]})
    ]


def test_the_lock_is_no_part_of_what_a_store_is() -> None:
    """Built, compared and shown as before: the lock is the store's own, one for each store."""

    one, another = InMemoryRunStore(limit=3), InMemoryRunStore(limit=3)

    assert one == another and one._lock is not another._lock  # noqa: SLF001
    assert repr(one) == "InMemoryRunStore(limit=3, runs=OrderedDict())"
    with pytest.raises(TypeError):
        InMemoryRunStore(_lock=threading.Lock())  # type: ignore[call-arg]
