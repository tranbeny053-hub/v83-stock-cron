"""W-A (plan §8.1) and E4: the REST writer's forecast bundle through migration 0017's RPC, and its
least-privilege credentials.

No database is contacted here: the PostgREST endpoint is an httpx.MockTransport. The function's
behaviour on a real PostgreSQL, called exactly as PostgREST calls it, is proven by:
- the PERS-0 rehearsal (scripts/persistence_rehearsal);
- P3-PRIV-R's W1-W10 behind a real PostgREST (scripts/privilege_rehearsal);
- the 0017 migration rehearsal in CI.
"""

from __future__ import annotations

import json

import httpx
import pytest

from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.repository import (
    CoreRowWriteStatus,
    ForecastBundleWrite,
    InMemoryPersistenceRepository,
    PredictionBundleWrite,
    PredictionWriteStatus,
    SupabasePersistenceRepository,
    SupabaseRestRepository,
    _forecast_write_from_rpc,
    build_operator_repository,
    build_persistence_repository,
)

BASE = "https://project.example.invalid"
RPC_URL = f"{BASE}/rest/v1/rpc/save_forecast_bundle"
SERVICE_KEY = "service-role-test-key"
PUBLISHABLE = "sb_publishable_test_value"
WRITER_JWT = "header.writer-claims.signature"


def run_summary(**changes) -> dict:
    summary = {
        "run_id": "run_wa",
        "operator_id": "operator",
        "symbol": "BTC",
        "normalized_symbol": "BTC/USDT",
        "analysis_mode": "CRYPTO_SPOT",
        "asset_class": "CRYPTO",
        "primary_timeframe": "4H",
        "disposition": "WAIT",
        "total_score": 41.5,
        "data_source": "BINANCE_PUBLIC",
        "is_live_data": True,
        "persistence_status": "OK",
        "analysis_hash": "h" * 64,
        "as_of_utc": "2026-10-03T08:00:00Z",
    }
    summary.update(changes)
    return summary


def prediction(**changes) -> dict:
    row = {"prediction_id": "run_wa:4H:6", "run_id": "run_wa",
           "prediction_origin": "USER_REQUESTED"}
    row.update(changes)
    return row


def snapshot(prediction_id: str = "run_wa:4H:6") -> dict:
    return {"prediction_id": prediction_id, "snapshot_payload": {"k": 1}, "snapshot_hash": "a" * 64}


def detail(run_id: str = "run_wa") -> dict:
    return {"run_id": run_id, "analysis_hash": "h" * 64, "detail_payload": {"run_id": run_id}}


def answer(
    run: str = "INSERTED",
    run_detail: str | None = "INSERTED",
    prediction_status: str | None = "INSERTED",
    feature: str | None = "INSERTED",
    derivatives: str | None = None,
    refused: bool = False,
) -> dict:
    return {
        "run": run,
        "run_detail": run_detail,
        "prediction": prediction_status,
        "feature_snapshot": feature,
        "derivatives_snapshot": derivatives,
        "refused": refused,
    }


class Endpoint:
    """A PostgREST stand-in: records every request; the forecast RPC answers from a queue."""

    def __init__(self, *answers: object) -> None:
        self.answers = list(answers)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if str(request.url) != RPC_URL:
            return httpx.Response(200, json=[])
        answer_ = self.answers.pop(0) if self.answers else None
        if isinstance(answer_, Exception):
            raise answer_
        if isinstance(answer_, httpx.Response):
            return answer_
        return httpx.Response(200, json=answer_)

    def rpc_bodies(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests if str(r.url) == RPC_URL]


def repository(endpoint: Endpoint, **credentials) -> SupabaseRestRepository:
    return SupabaseRestRepository(
        BASE,
        credentials.pop("service_role_key", SERVICE_KEY),
        client=httpx.Client(transport=httpx.MockTransport(endpoint)),
        **credentials,
    )


def write(endpoint: Endpoint, **credentials) -> tuple[ForecastBundleWrite, SupabaseRestRepository]:
    writer = repository(endpoint, **credentials)
    return writer.save_forecast_bundle(run_summary(), prediction(), snapshot(), None, detail()), (
        writer
    )


# ------------------------------------------------------------------------ the one request


def test_the_forecast_bundle_is_one_post_with_the_run_the_detail_and_the_normalized_rows() -> None:
    endpoint = Endpoint(answer())
    row = prediction()
    del row["prediction_origin"]  # normalized exactly as save_prediction normalizes it
    writer = repository(endpoint)
    written = writer.save_forecast_bundle(run_summary(), row, snapshot(), None, detail())
    (request,) = endpoint.requests
    assert (request.method, str(request.url)) == ("POST", RPC_URL)
    (body,) = endpoint.rpc_bodies()
    assert body == {
        "p_run": run_summary(),
        "p_prediction": {**row, "prediction_origin": "USER_REQUESTED"},
        "p_feature_snapshot": snapshot(),
        "p_derivatives_snapshot": None,
        "p_run_detail": detail(),
    }
    assert written == ForecastBundleWrite(
        CoreRowWriteStatus.INSERTED,
        CoreRowWriteStatus.INSERTED,
        PredictionBundleWrite(PredictionWriteStatus.INSERTED, "INSERTED"),
    )
    assert writer.circuit_state() == "CLOSED"


def test_no_detail_is_sent_as_null_and_answered_as_none() -> None:
    endpoint = Endpoint(answer(run_detail=None))
    written = repository(endpoint).save_forecast_bundle(run_summary(), prediction(), snapshot())
    assert endpoint.rpc_bodies()[0]["p_run_detail"] is None
    assert written.run_detail is None and written.run is CoreRowWriteStatus.INSERTED


def test_oos_identities_keep_their_own_path() -> None:
    endpoint = Endpoint()
    oos = prediction(prediction_id="oosb-" + "1" * 32 + ":4H:CANDIDATE")
    with pytest.raises(ValueError, match="OOS"):
        repository(endpoint).save_forecast_bundle(run_summary(), oos, snapshot())
    assert endpoint.requests == []


# ------------------------------------------------------------------------ the strict reader


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (
            answer(run="IDENTICAL_DUPLICATE", run_detail="IDENTICAL_DUPLICATE",
                   prediction_status="IDENTICAL_DUPLICATE", feature="IDENTICAL_DUPLICATE"),
            ("IDENTICAL_DUPLICATE", "IDENTICAL_DUPLICATE", "IDENTICAL_DUPLICATE", False),
        ),
        (
            answer(run="CONFLICT", run_detail=None, prediction_status=None, feature=None,
                   refused=True),
            ("CONFLICT", None, "CONFLICT", True),
        ),
        (
            answer(run="NOT_KEPT", run_detail="CONFLICT", prediction_status=None, feature=None,
                   refused=True),
            ("NOT_KEPT", "CONFLICT", "CONFLICT", True),
        ),
        (
            answer(run="NOT_KEPT", run_detail="NOT_KEPT", prediction_status="CONFLICT",
                   feature=None, refused=True),
            ("NOT_KEPT", "NOT_KEPT", "CONFLICT", True),
        ),
        (
            answer(run="IDENTICAL_DUPLICATE", run_detail="IDENTICAL_DUPLICATE",
                   prediction_status="IDENTICAL_DUPLICATE", feature="CONFLICT", refused=True),
            ("IDENTICAL_DUPLICATE", "IDENTICAL_DUPLICATE", "IDENTICAL_DUPLICATE", True),
        ),
    ],
    ids=["identical", "run-conflict", "detail-conflict", "prediction-conflict",
         "snapshot-conflict"],
)
def test_every_answer_the_function_can_give_is_read_exactly(given: dict, expected: tuple) -> None:
    written = _forecast_write_from_rpc(
        given, detail_submitted=True, feature_submitted=True, derivatives_submitted=False
    )
    assert written is not None
    run, run_detail, prediction_status, refused = expected
    assert written.run == run
    assert written.run_detail == run_detail
    assert written.bundle.prediction == prediction_status
    assert written.bundle.refused is refused


@pytest.mark.parametrize(
    "given",
    [
        None,
        [],
        {**answer(), "extra": 1},
        {key: value for key, value in answer().items() if key != "run_detail"},
        answer(refused="false"),
        answer(run="NOT_KEPT"),
        answer(run="CONFLICT"),
        answer(run_detail="NOT_KEPT"),
        answer(run_detail=None),
        answer(run="CONFLICT", run_detail=None, prediction_status="INSERTED", refused=True),
        answer(run="CONFLICT", run_detail="NOT_KEPT", prediction_status=None, feature=None,
               refused=True),
        answer(run="INSERTED", run_detail="CONFLICT", prediction_status=None, feature=None,
               refused=True),
        answer(run="NOT_KEPT", run_detail="CONFLICT", prediction_status="INSERTED",
               refused=True),
        answer(run="NOT_KEPT", run_detail="INSERTED", prediction_status="CONFLICT",
               feature=None, refused=True),
        answer(run="NOT_KEPT", run_detail="NOT_KEPT", prediction_status="INSERTED",
               refused=True),
        answer(feature=None),
        answer(prediction_status="CONFLICT"),
        answer(run="WRITTEN"),
    ],
    ids=["none", "list", "extra-key", "missing-key", "refused-not-bool", "kept-run-not-kept",
         "kept-run-conflict", "kept-detail-not-kept", "kept-detail-missing",
         "run-conflict-with-bundle", "run-conflict-with-detail", "detail-conflict-run-kept",
         "detail-conflict-with-bundle", "bundle-conflict-detail-kept",
         "refused-without-conflict", "kept-snapshot-missing", "kept-with-conflict",
         "unknown-status"],
)
def test_any_other_answer_is_unreadable(given: object) -> None:
    assert _forecast_write_from_rpc(
        given, detail_submitted=True, feature_submitted=True, derivatives_submitted=False
    ) is None


def test_a_detail_answered_but_never_submitted_is_unreadable() -> None:
    assert _forecast_write_from_rpc(
        answer(), detail_submitted=False, feature_submitted=True, derivatives_submitted=False
    ) is None


def test_an_unreadable_answer_is_unavailable_and_opens_the_circuit() -> None:
    written, writer = write(Endpoint({"prediction": "INSERTED"}))
    assert written.run is CoreRowWriteStatus.UNAVAILABLE
    assert written.run_detail is CoreRowWriteStatus.UNAVAILABLE
    assert written.bundle.prediction is PredictionWriteStatus.UNAVAILABLE
    assert writer.circuit_state() == "OPEN"


@pytest.mark.parametrize(
    "failure",
    [httpx.Response(500), httpx.Response(404), httpx.ReadError("lost after the commit")],
    ids=["500", "function-missing-404", "lost-response"],
)
def test_a_failed_request_is_unavailable_and_opens_the_circuit(failure: object) -> None:
    written, writer = write(Endpoint(failure))
    assert written.bundle.prediction is PredictionWriteStatus.UNAVAILABLE
    assert written.run is CoreRowWriteStatus.UNAVAILABLE
    assert writer.circuit_state() == "OPEN"


def test_a_refusal_is_an_answer_and_keeps_the_circuit_closed() -> None:
    refused = answer(run="CONFLICT", run_detail=None, prediction_status=None, feature=None,
                     refused=True)
    written, writer = write(Endpoint(refused))
    assert written.bundle.refused is True and written.run is CoreRowWriteStatus.CONFLICT
    assert writer.circuit_state() == "CLOSED"


# ------------------------------------------------------------------------ E4: the two headers


def headers_of(endpoint: Endpoint) -> list[tuple[str, str]]:
    return [(r.headers["apikey"], r.headers["Authorization"]) for r in endpoint.requests]


def test_the_service_role_writer_still_sends_its_one_key_in_both_headers() -> None:
    endpoint = Endpoint(answer())
    write(endpoint)
    repository(endpoint).recent_runs(5)
    assert headers_of(endpoint) == [(SERVICE_KEY, f"Bearer {SERVICE_KEY}")] * 2


def test_the_least_privilege_writer_sends_the_api_key_and_its_jwt_apart_on_every_request() -> None:
    endpoint = Endpoint(answer())
    credentials = {"publishable_key": PUBLISHABLE, "writer_jwt": WRITER_JWT}
    write(endpoint, service_role_key="", **credentials)
    reader = repository(endpoint, service_role_key="", **credentials)
    reader.recent_runs(5)
    reader.add_watchlist("ETH/USDT", operator_id="operator")
    assert len(endpoint.requests) >= 3
    assert set(headers_of(endpoint)) == {(PUBLISHABLE, f"Bearer {WRITER_JWT}")}
    for request in endpoint.requests:
        assert SERVICE_KEY not in str(request.headers)


@pytest.mark.parametrize(
    "credentials",
    [{"publishable_key": PUBLISHABLE}, {"writer_jwt": WRITER_JWT},
     {"publishable_key": PUBLISHABLE, "writer_jwt": ""}],
    ids=["key-only", "jwt-only", "empty-jwt"],
)
def test_half_a_least_privilege_writer_is_refused(credentials: dict) -> None:
    with pytest.raises(ValueError, match="both its API key and its JWT"):
        repository(Endpoint(), **credentials)


# ------------------------------------------------------------------------ settings and factories


def test_the_settings_read_both_writer_values_and_never_show_them(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", BASE)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", PUBLISHABLE)
    monkeypatch.setenv("SUPABASE_WRITER_JWT", WRITER_JWT)
    settings = Settings.from_env()
    assert (settings.supabase_publishable_key, settings.supabase_writer_jwt) == (
        PUBLISHABLE, WRITER_JWT)
    assert settings.external_store_configured is True
    assert PUBLISHABLE not in repr(settings) and WRITER_JWT not in repr(settings)
    monkeypatch.delenv("SUPABASE_WRITER_JWT")
    assert Settings.from_env().external_store_configured is False


def _headers_used(repository_: object) -> tuple[str, str]:
    assert isinstance(repository_, SupabaseRestRepository)
    headers = repository_._headers()
    return headers["apikey"], headers["Authorization"]


def settings_of(**values: str) -> Settings:
    """Settings from a mapping, as the other persistence tests build them."""

    return Settings(**{f"supabase_{name}": value for name, value in values.items()})


def test_the_factory_builds_the_least_privilege_writer_when_both_values_are_set() -> None:
    settings = settings_of(url=BASE, service_role_key=SERVICE_KEY,
                           publishable_key=PUBLISHABLE, writer_jwt=WRITER_JWT)
    for build in (build_persistence_repository, build_operator_repository):
        assert _headers_used(build(settings)) == (PUBLISHABLE, f"Bearer {WRITER_JWT}")


def test_without_a_service_role_key_the_writer_still_works() -> None:
    settings = settings_of(url=BASE, publishable_key=PUBLISHABLE, writer_jwt=WRITER_JWT)
    assert _headers_used(build_persistence_repository(settings)) == (
        PUBLISHABLE, f"Bearer {WRITER_JWT}")


@pytest.mark.parametrize(
    "half", [{"publishable_key": PUBLISHABLE}, {"writer_jwt": WRITER_JWT}],
    ids=["key-only", "jwt-only"],
)
def test_half_a_writer_configuration_keeps_today_s_rest_writer(half: dict) -> None:
    """A cutover in progress never switches the writer's transport (for example to the Space's
    direct database URL): the service-role REST writer stays until both values are set."""

    settings = settings_of(url=BASE, service_role_key=SERVICE_KEY,
                           db_url="postgresql://never-contacted.invalid/none", **half)
    assert _headers_used(build_persistence_repository(settings)) == (
        SERVICE_KEY, f"Bearer {SERVICE_KEY}")


def test_without_rest_credentials_the_factories_are_unchanged() -> None:
    database = "postgresql://never-contacted.invalid/none"
    assert isinstance(
        build_persistence_repository(settings_of(db_url=database)), SupabasePersistenceRepository
    )
    assert isinstance(build_persistence_repository(Settings()), InMemoryPersistenceRepository)
    assert isinstance(
        build_persistence_repository(settings_of(url=BASE, writer_jwt=WRITER_JWT)),
        InMemoryPersistenceRepository,
    )
