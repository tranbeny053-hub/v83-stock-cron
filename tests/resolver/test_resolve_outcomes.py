from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from crypto_probability_engine.adapters.provider_selection import DATA_SOURCE_BY_PROVIDER
from crypto_probability_engine.adapters.types import MarketCandle, ProviderError
from crypto_probability_engine.config.defaults import RESOLVER_VERSION, TIMEFRAME_SECONDS
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.repository import (
    InMemoryPersistenceRepository,
    SupabasePersistenceRepository,
    SupabaseRestRepository,
)
from scripts import resolve_outcomes

ROOT = Path(__file__).resolve().parents[2]
STATS_KEYS = (
    "due", "resolved", "skipped", "failed", "deferred",
    "scanned", "selected", "fresh", "stuck",
    "skip_ineligible", "skip_invalid_target", "skip_not_due", "skip_terminal_bar_missing",
    "error_row_unreadable", "error_provider_rejected", "error_provider_unavailable",
    "error_candle_invalid", "error_save_not_ok", "error_save_exception",
    "error_outcome_conflict", "error_other",
    "status_written", "status_quarantined", "status_resolved", "status_outage_suppressed",
    "status_error",
)


def _stats(*, due, resolved=0, skipped=0, failed=0, stuck=0, **reasons):
    """The whole stats dict of a run that selected every scanned row and deferred none."""

    expected = dict.fromkeys(STATS_KEYS, 0)
    expected.update(
        due=due, resolved=resolved, skipped=skipped, failed=failed,
        scanned=due, selected=due, fresh=due - stuck, stuck=stuck,
    )
    expected.update(reasons)  # a misspelt reason adds a key, so the comparison fails
    return expected


@pytest.fixture(autouse=True)
def block_public_network(monkeypatch: pytest.MonkeyPatch) -> None:
    class NoNetworkClient:
        @classmethod
        def from_settings(cls, settings):
            return cls()

        def get_json(self, **kwargs):
            raise AssertionError("network")

    monkeypatch.setattr(resolve_outcomes, "PublicHttpClient", NoNetworkClient)


class RecordingRepository:
    def __init__(self, predictions, status="OK"):
        self.predictions = predictions
        self.status = status
        self.saved = []
        self.due_calls = []

    def fetch_due_unresolved_predictions(
        self, now_utc, limit, *, data_sources=None, timeframes=None, prediction_origins=None
    ):
        self.due_calls.append((now_utc, limit, data_sources, timeframes, prediction_origins))
        return self.predictions

    def save_prediction_outcome(self, row):
        self.saved.append(row)
        if isinstance(self.status, Exception):
            raise self.status
        return self.status


@pytest.fixture
def recording_client(monkeypatch: pytest.MonkeyPatch):
    class RecordingClient:
        def __init__(self):
            self.calls = []
            self.payload = None
            self.error = None

        def get_json(self, **kwargs):
            self.calls.append(kwargs)
            if self.error is not None:
                raise self.error
            return self.payload

    client = RecordingClient()

    class ClientFactory:
        @staticmethod
        def from_settings(settings):
            return client

    monkeypatch.setattr(resolve_outcomes, "PublicHttpClient", ClientFactory)
    return client


def test_resolver_repository_prefers_db_url_over_rest_when_both_configured() -> None:
    repo = resolve_outcomes.build_resolver_repository(
        Settings(
            **{
                "supabase_db_url": "postgresql://operator-db.example.invalid/db",
                "supabase_url": "https://project.example.invalid",
                "supabase_service_role_key": "test-service-role-key",
            }
        )
    )

    try:
        assert isinstance(repo, SupabasePersistenceRepository)
        assert repo.repository_type() == "SUPABASE_POSTGRES"
    finally:
        close = getattr(repo, "close", None)
        if callable(close):
            close()


def test_resolver_repository_falls_back_to_rest_when_db_url_absent() -> None:
    repo = resolve_outcomes.build_resolver_repository(
        Settings(
            **{
                "supabase_url": "https://project.example.invalid",
                "supabase_service_role_key": "test-service-role-key",
            }
        )
    )

    try:
        assert isinstance(repo, SupabaseRestRepository)
        assert repo.repository_type() == "SUPABASE_REST"
    finally:
        close = getattr(repo, "close", None)
        if callable(close):
            close()


def test_resolver_repository_uses_memory_without_external_store() -> None:
    repo = resolve_outcomes.build_resolver_repository(Settings())

    assert isinstance(repo, InMemoryPersistenceRepository)
    assert repo.repository_type() == "IN_MEMORY"


def test_main_output_includes_safe_repository_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_resolve_due_predictions(repository, **kwargs):
        assert repository.repository_type() == "SUPABASE_POSTGRES"
        assert kwargs["limit"] == 7
        return {"due": 4, "resolved": 2, "skipped": 2, "failed": 0}

    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://operator-db.example.invalid/db")
    monkeypatch.setenv("SUPABASE_URL", "https://project.example.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setattr(resolve_outcomes, "resolve_due_predictions", fake_resolve_due_predictions)

    result = resolve_outcomes.main(["--limit", "7"])
    output = capsys.readouterr().out

    assert result == 0
    assert "resolved_outcomes repository=SUPABASE_POSTGRES limit=7" in output
    assert "due=4 resolved=2 skipped=2 failed=0" in output
    assert "operator-db.example.invalid" not in output
    assert "project.example.invalid" not in output
    assert "test-service-role-key" not in output


def test_main_returns_zero_when_no_prediction_failures(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        resolve_outcomes,
        "build_resolver_repository",
        lambda settings: InMemoryPersistenceRepository(),
    )
    monkeypatch.setattr(
        resolve_outcomes,
        "resolve_due_predictions",
        lambda repository, **kwargs: {"due": 2, "resolved": 2, "skipped": 0, "failed": 0},
    )

    result = resolve_outcomes.main(["--limit", "2"])
    output = capsys.readouterr().out

    assert result == 0
    assert "resolved_outcomes repository=IN_MEMORY limit=2" in output
    assert "due=2 resolved=2 skipped=0 failed=0" in output


def test_main_returns_nonzero_when_prediction_failures_occur(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        resolve_outcomes,
        "build_resolver_repository",
        lambda settings: InMemoryPersistenceRepository(),
    )
    monkeypatch.setattr(
        resolve_outcomes,
        "resolve_due_predictions",
        lambda repository, **kwargs: {"due": 3, "resolved": 2, "skipped": 0, "failed": 1},
    )

    result = resolve_outcomes.main(["--limit", "3"])
    output = capsys.readouterr().out

    assert result == 1
    assert "resolved_outcomes repository=IN_MEMORY limit=3" in output
    assert "due=3 resolved=2 skipped=0 failed=1" in output


def test_main_db_fetch_failure_is_visible_without_secret_leak(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FailingRepository(InMemoryPersistenceRepository):
        def repository_type(self) -> str:
            return "SUPABASE_POSTGRES"

        def fetch_due_unresolved_predictions(
            self, now_utc, limit, *, data_sources=None, timeframes=None, prediction_origins=None
        ):
            raise RuntimeError("SUPABASE_POSTGRES due query failed or unavailable.")

    monkeypatch.setattr(
        resolve_outcomes,
        "build_resolver_repository",
        lambda settings: FailingRepository(),
    )

    result = resolve_outcomes.main(["--limit", "10"])
    output = capsys.readouterr().out

    assert result == 1
    assert "resolved_outcomes repository=SUPABASE_POSTGRES limit=10" in output
    assert "due=0 resolved=0 skipped=0 failed=1" in output
    assert "SUPABASE_POSTGRES due query failed or unavailable." in output
    assert "SUPABASE_DB_URL" not in output
    assert "SUPABASE_SERVICE_ROLE_KEY" not in output
    assert "Authorization" not in output


def test_no_lookahead_candles_at_or_before_reference_do_not_influence_outcome() -> None:
    prediction = _prediction()
    reference = _dt("2026-06-07T00:00:00Z")
    horizon = _dt("2026-06-08T00:00:00Z")
    candles = (
        _candle(reference - timedelta(hours=4), close=10_000.0, high=20_000.0, low=1.0),
        _candle(reference, close=10_000.0, high=50_000.0, low=1.0),
        _candle(reference + timedelta(hours=4), close=100.0, high=100.5, low=99.7),
        _candle(horizon, close=101.0, high=101.5, low=99.8),
    )

    row = resolve_outcomes.build_outcome_row(
        prediction,
        now_utc=_dt("2026-06-08T00:05:00Z"),
        settings=Settings(),
        fetch_candles=lambda _window, _settings: candles,
    )

    assert row is not None
    assert row["realized_label"] == "UP"
    assert row["terminal_return_frac"] == 0.01
    assert row["max_favorable_frac"] == 0.015
    assert row["max_adverse_frac"] == pytest.approx(-0.003)
    assert row["candles_observed"] == 2


def test_unfinished_horizon_writes_no_outcome() -> None:
    prediction = _prediction()
    candles = (
        _candle(_dt("2026-06-07T04:00:00Z"), close=100.5),
        _candle(_dt("2026-06-07T20:00:00Z"), close=101.0),
    )

    row = resolve_outcomes.build_outcome_row(
        prediction,
        now_utc=_dt("2026-06-08T00:05:00Z"),
        settings=Settings(),
        fetch_candles=lambda _window, _settings: candles,
    )

    assert row is None


def test_stale_window_overshoot_skips_outcome_and_writes_nothing() -> None:
    repo = InMemoryPersistenceRepository()
    prediction = _prediction()
    repo.save_prediction(prediction)
    stale_candles = (
        _candle(_dt("2026-06-09T00:00:01Z"), close=110.0),
        _candle(_dt("2026-06-09T04:00:01Z"), close=111.0),
    )

    stats = resolve_outcomes.resolve_due_predictions(
        repo,
        settings=Settings(),
        now_utc=_dt("2026-06-10T00:00:00Z"),
        fetch_candles=lambda _window, _settings: stale_candles,
    )

    assert stats == _stats(due=1, skipped=1, skip_terminal_bar_missing=1)
    assert repo._prediction_outcomes == {}  # noqa: SLF001


def test_one_bar_late_candle_is_not_accepted_as_the_terminal_bar() -> None:
    row = resolve_outcomes.build_outcome_row(
        _prediction(),
        now_utc=_dt("2026-06-08T04:05:00Z"),
        settings=Settings(),
        fetch_candles=lambda _window, _settings: (
            _candle(_dt("2026-06-08T04:00:00Z"), close=101.0),
        ),
    )

    assert row is None


def test_up_down_timeout_label_fixtures() -> None:
    assert _label_for_close(101.0) == "UP"
    assert _label_for_close(99.0) == "DOWN"
    assert _label_for_close(100.2) == "TIMEOUT"


def test_resolver_uses_fallback_band_when_prediction_band_missing() -> None:
    prediction = {**_prediction(), "decision_band_frac": None}
    row = resolve_outcomes.build_outcome_row(
        prediction,
        now_utc=_dt("2026-06-08T00:05:00Z"),
        settings=Settings(),
        fetch_candles=lambda _window, _settings: (
            _candle(_dt("2026-06-08T00:00:00Z"), close=100.15),
        ),
    )

    assert row is not None
    assert row["decision_band_frac"] == 0.002
    assert row["realized_label"] == "TIMEOUT"


def test_resolve_due_predictions_isolates_bad_prediction_failure() -> None:
    repo = RecordingRepository([])
    bad = _prediction(prediction_id="bad:4H")
    good = _prediction(prediction_id="good:4H")
    bad["normalized_symbol"] = "BAD/USDT"
    repo.predictions = [bad, good]

    def fetch(window, settings):
        if window.normalized_symbol == "BAD/USDT":
            raise RuntimeError("mocked provider failure")
        return (_candle(_dt("2026-06-08T00:00:00Z"), close=101.0),)

    stats = resolve_outcomes.resolve_due_predictions(
        repo,
        settings=Settings(),
        now_utc=_dt("2026-06-08T00:05:00Z"),
        fetch_candles=fetch,
    )

    assert stats == _stats(due=2, resolved=1, failed=1, error_other=1)
    assert [row["prediction_id"] for row in repo.saved] == ["good:4H"]


def test_prediction_row_is_not_mutated_by_resolution() -> None:
    prediction = _prediction()
    original = deepcopy(prediction)

    resolve_outcomes.build_outcome_row(
        prediction,
        now_utc=_dt("2026-06-08T00:05:00Z"),
        settings=Settings(),
        fetch_candles=lambda _window, _settings: (
            _candle(_dt("2026-06-08T00:00:00Z"), close=101.0),
        ),
    )

    assert prediction == original


def test_outcome_row_contains_resolver_version_and_no_prediction_update_fields() -> None:
    row = resolve_outcomes.build_outcome_row(
        _prediction(),
        now_utc=_dt("2026-06-08T00:05:00Z"),
        settings=Settings(),
        fetch_candles=lambda _window, _settings: (
            _candle(_dt("2026-06-08T00:00:00Z"), close=101.0),
        ),
    )

    assert row is not None
    assert row["resolver_version"] == "resolver-v2b-tc-v1-rq-v1"
    assert row["resolver_version"] == resolve_outcomes.RESOLVER_VERSION
    assert RESOLVER_VERSION == "resolver-v1-wave4b2"
    assert "calibration_status" not in row
    assert "reliability_status" not in row
    assert "profitability_claim" not in row


def test_resolve_outcomes_script_is_not_imported_by_api_package() -> None:
    api_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src" / "crypto_probability_engine" / "api").glob("*.py")
    )

    assert "resolve_outcomes" not in api_text


def _label_for_close(close: float) -> str:
    row = resolve_outcomes.build_outcome_row(
        _prediction(),
        now_utc=_dt("2026-06-08T00:05:00Z"),
        settings=Settings(),
        fetch_candles=lambda _window, _settings: (
            _candle(_dt("2026-06-08T00:00:00Z"), close=close),
        ),
    )
    assert row is not None
    return str(row["realized_label"])


def _prediction(prediction_id: str = "run_1:4H") -> dict:
    return {
        "prediction_id": prediction_id,
        "run_id": "run_1",
        "operator_id": "operator",
        "symbol": "BTC",
        "normalized_symbol": "BTC/USDT",
        "timeframe": "4H",
        "horizon_bars": 6,
        "predicted_at_utc": "2026-06-07T00:00:00Z",
        "reference_close_utc": "2026-06-07T00:00:00Z",
        "reference_price": 100.0,
        "horizon_end_utc": "2026-06-08T00:00:00Z",
        "p_up_frac": 0.40,
        "p_down_frac": 0.35,
        "p_timeout_frac": 0.25,
        "decision_band_frac": 0.003,
        "model_version": "phase1a-wave4b0",
        "methodology_version": "heuristic-v1-wave4b0",
        "calibration_status": "DEFAULT_PHASE1A",
        "reliability_status": "INSUFFICIENT_SAMPLE",
        "epistemic_sufficiency": "SUFFICIENT",
        "gate_action": "WATCH",
        "data_source": "BINANCE_PUBLIC",
        "is_live_data": True,
        "cross_provider_state": "UNAVAILABLE",
    }


def _candle(
    close_time: datetime,
    *,
    close: float,
    high: float | None = None,
    low: float | None = None,
) -> MarketCandle:
    high = close if high is None else high
    low = close if low is None else low
    return MarketCandle(
        open_time_utc=close_time - timedelta(hours=4),
        close_time_utc=close_time,
        open=close,
        high=high,
        low=low,
        close=close,
        volume=1_000.0,
    )


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


MISSING = object()


@pytest.mark.parametrize(
    "source",
    [
        "CROSS_PROVIDER",
        "DEGRADED",
        "UNAVAILABLE",
        "FIXTURE_DEMO",
        "",
        None,
        MISSING,
        "binance_public",
        "BINANCE_PUBLIC ",
        " OKX_PUBLIC",
        "OKX",
        1,
        [],
    ],
)
def test_ambiguous_source_skips_without_fetch_or_save(source) -> None:
    prediction = _prediction()
    if source is MISSING:
        del prediction["data_source"]
    else:
        prediction["data_source"] = source
    calls = []

    def fetch(window, settings):
        calls.append(window)
        return (_candle(_dt(prediction["horizon_end_utc"]), close=101.0),)

    assert _build(prediction, fetch) is None
    repo = RecordingRepository([prediction])
    assert _resolve(repo, fetch_candles=fetch) == _stats(
        due=1, skipped=1, skip_ineligible=1
    )
    assert calls == []
    assert repo.saved == []


@pytest.mark.parametrize("source,provider", [("BINANCE_PUBLIC", "binance"), ("OKX_PUBLIC", "okx")])
def test_exact_source_builds_immutable_window_and_preserves_source(source, provider) -> None:
    prediction = {**_prediction(), "data_source": source}
    calls = []
    settings = Settings()
    now = _dt("2026-06-08T00:05:00Z")

    def fetch(window, received_settings):
        calls.append(window)
        assert received_settings is settings
        return (_candle(window.terminal_close_utc, close=101.0),)

    row = resolve_outcomes.build_outcome_row(
        prediction,
        now_utc=now,
        settings=settings,
        fetch_candles=fetch,
    )
    assert calls == [
        resolve_outcomes.CandleWindow(
            provider=provider,
            data_source=source,
            normalized_symbol="BTC/USDT",
            timeframe="4H",
            first_open_utc=_dt("2026-06-07T00:00:00Z"),
            terminal_open_utc=_dt("2026-06-07T20:00:00Z"),
            terminal_close_utc=_dt("2026-06-08T00:00:00Z"),
            bars=6,
            now_utc=now,
        )
    ]
    with pytest.raises(FrozenInstanceError):
        calls[0].bars = 7
    assert row is not None
    assert row["data_source"] == source
    assert row["outcome_close_utc"] == prediction["horizon_end_utc"]


@pytest.mark.parametrize("timeframe", ["15m", "1H", "4H", "1D", "1W"])
def test_binance_default_fetch_is_bounded_and_resolves_exactly(recording_client, timeframe) -> None:
    prediction = _prediction_for_timeframe(timeframe)
    recording_client.payload = _binance_payload(prediction)
    repo = RecordingRepository([prediction])
    now = _dt(prediction["horizon_end_utc"]) + timedelta(minutes=5)

    assert _resolve(repo, now_utc=now) == _stats(due=1, resolved=1)
    _assert_binance_request(recording_client, prediction)
    assert repo.saved[0]["outcome_close_utc"] == prediction["horizon_end_utc"]
    assert repo.saved[0]["candles_observed"] == 6
    assert repo.saved[0]["outcome_reference_price"] == 101.0
    assert repo.saved[0]["max_favorable_frac"] == 0.02
    assert repo.saved[0]["max_adverse_frac"] == -0.01


def test_binance_dropped_terminal_bar_is_skipped_without_save(recording_client) -> None:
    prediction = _prediction()
    recording_client.payload = _binance_payload(prediction)[:6]
    repo = RecordingRepository([prediction])

    assert _resolve(repo) == _stats(due=1, skipped=1, skip_terminal_bar_missing=1)
    _assert_binance_request(recording_client, prediction)
    assert repo.saved == []


@pytest.mark.parametrize(
    "age_days,path",
    [
        (0, "/api/v5/market/candles"),
        (20, "/api/v5/market/history-candles"),
    ],
)
def test_okx_default_fetch_uses_target_age_and_exact_bounds(
    recording_client, age_days, path
) -> None:
    prediction = {**_prediction_for_timeframe("15m"), "data_source": "OKX_PUBLIC"}
    recording_client.payload = _okx_payload(prediction)
    repo = RecordingRepository([prediction])
    horizon = _dt(prediction["horizon_end_utc"])

    stats = _resolve(repo, now_utc=horizon + timedelta(days=age_days, minutes=5))

    assert stats == _stats(due=1, resolved=1, stuck=1 if age_days else 0)
    assert recording_client.calls == [
        {
            "base_url": resolve_outcomes.OKX_BASE_URL,
            "path": path,
            "params": {"instId": "BTC-USDT", "bar": "15m", "after": _ms(horizon), "limit": 8},
            "provider": "okx",
        }
    ]
    assert repo.saved[0]["outcome_close_utc"] == prediction["horizon_end_utc"]
    assert repo.saved[0]["candles_observed"] == 6
    assert repo.saved[0]["data_source"] == "OKX_PUBLIC"


@pytest.mark.parametrize(
    "extra_microseconds,expected_path",
    [
        (0, "/api/v5/market/candles"),
        (1, "/api/v5/market/history-candles"),
        (900_000_000, "/api/v5/market/history-candles"),
    ],
)
def test_okx_path_boundary_rounds_age_up(extra_microseconds, expected_path) -> None:
    horizon = _dt("2026-06-08T00:00:00Z")
    interval = timedelta(minutes=15)
    window = resolve_outcomes.CandleWindow(
        provider="okx",
        data_source="OKX_PUBLIC",
        normalized_symbol="BTC/USDT",
        timeframe="15m",
        first_open_utc=horizon - 6 * interval,
        terminal_open_utc=horizon - interval,
        terminal_close_utc=horizon,
        bars=6,
        now_utc=horizon + 1392 * interval + timedelta(microseconds=extra_microseconds),
    )
    assert resolve_outcomes._okx_candles_path(window) == expected_path


@pytest.mark.parametrize(
    "source,provider,base_url,path",
    [
        ("BINANCE_PUBLIC", "binance", resolve_outcomes.BINANCE_BASE_URL, "/api/v3/klines"),
        ("OKX_PUBLIC", "okx", resolve_outcomes.OKX_BASE_URL, "/api/v5/market/candles"),
    ],
)
def test_venue_failure_never_falls_back(recording_client, source, provider, base_url, path) -> None:
    prediction = {**_prediction(), "data_source": source}
    error = ProviderError("PROVIDER_DEGRADED", "synthetic outage", provider=provider)
    recording_client.error = error
    repo = RecordingRepository([prediction])

    assert _resolve(repo) == _stats(due=1, failed=1, error_provider_unavailable=1)
    assert len(recording_client.calls) == 1
    assert recording_client.calls[0]["provider"] == provider
    assert recording_client.calls[0]["base_url"] == base_url
    assert recording_client.calls[0]["path"] == path
    assert repo.saved == []
    with pytest.raises(ProviderError) as raised:
        _build(prediction, resolve_outcomes.fetch_public_candles)
    assert raised.value is error


def test_outage_longer_than_latest_50_bars_resolves_exact_target(recording_client) -> None:
    prediction = _prediction_for_timeframe("15m")
    recording_client.payload = _binance_payload(prediction)
    repo = RecordingRepository([prediction])
    now = _dt(prediction["horizon_end_utc"]) + timedelta(hours=13)

    assert _resolve(repo, now_utc=now) == _stats(due=1, resolved=1)
    _assert_binance_request(recording_client, prediction)
    assert repo.saved[0]["outcome_close_utc"] == prediction["horizon_end_utc"]
    assert repo.saved[0]["candles_observed"] == 6


@pytest.mark.parametrize(
    "status,resolved,failed",
    [
        ("OK", 1, 0),
        ("UNAVAILABLE", 0, 1),
        ("STATELESS", 0, 1),
        (None, 0, 1),
        (RuntimeError("synthetic save failure"), 0, 1),
        ("ok", 0, 1),
        ("OK ", 0, 1),
    ],
)
def test_resolved_requires_save_ok(status, resolved, failed) -> None:
    repo = RecordingRepository([_prediction()], status=status)
    stats = _resolve(repo, fetch_candles=_terminal_candles)
    reason = "error_save_exception" if isinstance(status, Exception) else "error_save_not_ok"
    reasons = {reason: failed} if failed else {}
    assert stats == _stats(due=1, resolved=resolved, failed=failed, **reasons)
    assert len(repo.saved) == 1


def test_real_memory_repository_stateless_save_is_not_resolved() -> None:
    repo = InMemoryPersistenceRepository()
    repo.save_prediction(_prediction())
    assert _resolve(repo, fetch_candles=_terminal_candles) == _stats(
        due=1, failed=1, error_save_not_ok=1
    )


@pytest.mark.parametrize("offset", [timedelta(0), -timedelta(microseconds=1)])
def test_not_due_never_fetches(offset) -> None:
    prediction = _prediction()
    calls = []
    row = _build(
        prediction,
        lambda window, settings: calls.append(window),
        now_utc=_dt(prediction["horizon_end_utc"]) + offset,
    )
    assert row is None
    assert calls == []


@pytest.mark.parametrize(
    "updates",
    [
        {"reference_price": 0},
        {"reference_price": -1},
        {"reference_price": float("nan")},
        {"reference_price": float("inf")},
        {"reference_price": float("-inf")},
        {"timeframe": "1M"},
        {"timeframe": "2H"},
        {"timeframe": None},
        {"timeframe": []},
        {"horizon_end_utc": "2026-06-08T00:01:00Z"},
        {"horizon_end_utc": "2026-06-07T00:00:00Z"},
        {"horizon_end_utc": "2026-06-06T20:00:00Z"},
        {"horizon_bars": 5},
        {"horizon_bars": "invalid"},
        {"horizon_bars": []},
        {"horizon_bars": float("inf")},
        {"horizon_end_utc": "2026-06-23T04:00:00Z", "horizon_bars": 97},
    ],
)
def test_malformed_target_skips_before_fetch(updates) -> None:
    calls = []
    prediction = {**_prediction(), **updates}

    def fetch(window, settings):
        calls.append(window)
        return _terminal_candles(window, settings)

    assert _build(prediction, fetch, now_utc=_dt("2026-07-01T00:00:00Z")) is None
    repo = RecordingRepository([prediction])
    reason = "skip_ineligible" if "timeframe" in updates else "skip_invalid_target"
    assert _resolve(repo, fetch_candles=fetch, now_utc=_dt("2026-07-01T00:00:00Z")) == _stats(
        due=1, skipped=1, stuck=1, **{reason: 1}
    )
    assert calls == []
    assert repo.saved == []


@pytest.mark.parametrize("field", ["reference_close_utc", "horizon_end_utc", "reference_price"])
def test_parse_errors_propagate_and_count_failed_without_fetch(field) -> None:
    prediction = {**_prediction(), field: "invalid"}
    calls = []

    def fetch(window, settings):
        calls.append(window)
        return _terminal_candles(window, settings)

    with pytest.raises(ValueError):
        _build(prediction, fetch)
    repo = RecordingRepository([prediction])
    assert _resolve(repo, fetch_candles=fetch) == _stats(
        due=1,
        failed=1,
        stuck=1 if field == "horizon_end_utc" else 0,  # an unreadable horizon counts as stuck
        error_row_unreadable=1,
    )
    assert calls == []
    assert repo.saved == []


@pytest.mark.parametrize("horizon_bars", [None, MISSING, "96", 96])
def test_maximum_window_and_optional_horizon_bars(horizon_bars) -> None:
    prediction = {**_prediction(), "horizon_end_utc": "2026-06-23T00:00:00Z"}
    if horizon_bars is MISSING:
        del prediction["horizon_bars"]
    else:
        prediction["horizon_bars"] = horizon_bars
    calls = []

    def fetch(window, settings):
        calls.append(window)
        return _terminal_candles(window, settings)

    assert _build(prediction, fetch, now_utc=_dt("2026-07-01T00:00:00Z")) is not None
    assert len(calls) == 1
    assert calls[0].bars == 96


@pytest.mark.parametrize(
    "field,value",
    [
        ("close", 102.0),
        ("open", 99.0),
        ("high", 103.0),
        ("low", 98.0),
        ("volume", 2.0),
    ],
)
def test_conflicting_duplicates_fail_without_save(field, value) -> None:
    terminal = _candle(_dt("2026-06-08T00:00:00Z"), close=101.0)
    candles = (terminal, replace(terminal, **{field: value}))
    def fetch(window, settings):
        return candles

    with pytest.raises(ValueError, match="^conflicting duplicate candles in resolver window$"):
        _build(_prediction(), fetch)
    repo = RecordingRepository([_prediction()])
    assert _resolve(repo, fetch_candles=fetch) == _stats(
        due=1, failed=1, error_candle_invalid=1
    )
    assert repo.saved == []


def test_identical_duplicates_collapse_and_outside_window_is_ignored() -> None:
    terminal = _candle(_dt("2026-06-08T00:00:00Z"), close=101.0)
    earlier = _candle(_dt("2026-06-07T04:00:00Z"), close=100.0, high=102.0, low=99.0)
    later = _candle(_dt("2026-06-08T04:00:00Z"), close=1000.0)
    anchor = _candle(_dt("2026-06-07T00:00:00Z"), close=1.0)
    candles = (terminal, earlier, replace(terminal), later, anchor, replace(later, close=2.0))
    repo = RecordingRepository([_prediction()])
    assert _resolve(repo, fetch_candles=lambda window, settings: candles) == _stats(
        due=1, resolved=1
    )
    assert repo.saved[0]["candles_observed"] == 2
    assert repo.saved[0]["max_favorable_frac"] == 0.02
    assert repo.saved[0]["max_adverse_frac"] == -0.01
    assert repo.saved[0]["terminal_return_frac"] == 0.01


@pytest.mark.parametrize("close_time", ["2026-06-08T00:00:00Z", "2026-06-07T04:00:00Z"])
def test_wrong_duration_in_window_fails_without_save(close_time) -> None:
    terminal = _candle(_dt("2026-06-08T00:00:00Z"), close=101.0)
    wrong = replace(
        _candle(_dt(close_time), close=101.0),
        open_time_utc=_dt(close_time) - timedelta(hours=1),
    )
    def fetch(window, settings):
        return (wrong, terminal)

    with pytest.raises(ValueError, match="^resolver candle does not span exactly one bar$"):
        _build(_prediction(), fetch)
    repo = RecordingRepository([_prediction()])
    assert _resolve(repo, fetch_candles=fetch) == _stats(
        due=1, failed=1, error_candle_invalid=1
    )
    assert repo.saved == []


def test_exact_sources_match_provider_labels_and_are_immutable() -> None:
    assert resolve_outcomes.EXACT_SOURCE_PROVIDERS == {
        source: provider for provider, source in DATA_SOURCE_BY_PROVIDER.items()
    }
    with pytest.raises(TypeError):
        resolve_outcomes.EXACT_SOURCE_PROVIDERS["OTHER"] = "other"


def test_mixed_batch_fetches_and_saves_only_exact_sources() -> None:
    predictions = [
        {**_prediction(prediction_id=str(index)), "data_source": source}
        for index, source in enumerate(["BINANCE_PUBLIC", "CROSS_PROVIDER", "OKX_PUBLIC"])
    ]
    repo = RecordingRepository(predictions)
    calls = []

    def fetch(window, settings):
        calls.append(window.provider)
        return _terminal_candles(window, settings)

    assert _resolve(repo, fetch_candles=fetch) == _stats(
        due=3, resolved=2, skipped=1, skip_ineligible=1
    )
    assert calls == ["binance", "okx"]
    assert [row["prediction_id"] for row in repo.saved] == ["0", "2"]
    assert [row["data_source"] for row in repo.saved] == ["BINANCE_PUBLIC", "OKX_PUBLIC"]


def test_candle_times_and_now_are_coerced_to_utc() -> None:
    terminal = _candle(_dt("2026-06-08T00:00:00Z"), close=101.0)
    terminal = replace(
        terminal,
        open_time_utc=datetime(2026, 6, 7, 20),
        close_time_utc=datetime.fromisoformat("2026-06-08T07:00:00+07:00"),
    )
    row = _build(
        _prediction(),
        lambda window, settings: (terminal,),
        now_utc=datetime(2026, 6, 8, 0, 5),
    )
    assert row is not None
    assert row["outcome_close_utc"] == "2026-06-08T00:00:00Z"
    assert row["resolved_at_utc"] == "2026-06-08T00:05:00Z"


@pytest.mark.parametrize(
    "dt,expected",
    [
        (datetime(1970, 1, 1, tzinfo=UTC), 0),
        (datetime(1969, 12, 31, 23, 59, 59, 999999, tzinfo=UTC), -1),
        (datetime(9999, 1, 1, 0, 0, 0, 999999, tzinfo=UTC), 253370764800999),
    ],
)
def test_millis_uses_exact_integer_arithmetic(dt, expected) -> None:
    assert resolve_outcomes._millis(dt) == expected


def test_unsupported_provider_raises_without_request(recording_client) -> None:
    captured = []

    def capture(window, settings):
        captured.append(window)
        return ()

    _build(_prediction(), capture)
    with pytest.raises(ProviderError, match="Unsupported resolver provider"):
        resolve_outcomes.fetch_public_candles(replace(captured[0], provider="other"), Settings())
    assert recording_client.calls == []


def _build(prediction, fetch, *, now_utc=None):
    return resolve_outcomes.build_outcome_row(
        prediction,
        settings=Settings(),
        fetch_candles=fetch,
        now_utc=now_utc or _dt("2026-06-08T00:05:00Z"),
    )


def _resolve(repo, *, now_utc=None, **kwargs):
    return resolve_outcomes.resolve_due_predictions(
        repo,
        settings=Settings(),
        now_utc=now_utc or _dt("2026-06-08T00:05:00Z"),
        **kwargs,
    )


def _terminal_candles(window, settings):
    return (_candle(window.terminal_close_utc, close=101.0),)


def _prediction_for_timeframe(timeframe):
    prediction = _prediction()
    reference = _dt(prediction["reference_close_utc"])
    horizon = reference + 6 * timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
    return {
        **prediction,
        "timeframe": timeframe,
        "horizon_end_utc": horizon.isoformat().replace(
            "+00:00",
            "Z",
        ),
    }


def _ms(dt):
    return (dt - datetime(1970, 1, 1, tzinfo=UTC)) // timedelta(milliseconds=1)


def _binance_payload(prediction):
    reference = _dt(prediction["reference_close_utc"])
    interval = timedelta(seconds=TIMEFRAME_SECONDS[prediction["timeframe"]])
    return [
        [
            _ms(reference + k * interval),
            "100",
            "102",
            "99",
            "101",
            "1000",
            _ms(reference + (k + 1) * interval) - 1,
            "0",
            1,
            "0",
            "0",
            "0",
        ]
        for k in range(prediction["horizon_bars"] + 2)
    ]


def _okx_payload(prediction):
    reference = _dt(prediction["reference_close_utc"])
    interval = timedelta(seconds=TIMEFRAME_SECONDS[prediction["timeframe"]])
    return {
        "code": "0",
        "data": [
            [str(_ms(reference + k * interval)), "100", "102", "99", "101", "1000", "0", "0", "1"]
            for k in reversed(range(-2, prediction["horizon_bars"]))
        ],
    }


def _assert_binance_request(client, prediction):
    timeframe = prediction["timeframe"]
    assert client.calls == [
        {
            "base_url": resolve_outcomes.BINANCE_BASE_URL,
            "path": "/api/v3/klines",
            "params": {
                "symbol": "BTCUSDT",
                "interval": {"15m": "15m", "1H": "1h", "4H": "4h", "1D": "1d", "1W": "1w"}[
                    timeframe
                ],
                "startTime": _ms(_dt(prediction["reference_close_utc"])),
                "endTime": _ms(_dt(prediction["horizon_end_utc"]))
                + TIMEFRAME_SECONDS[timeframe] * 1000,
                "limit": prediction["horizon_bars"] + 3,
            },
            "provider": "binance",
        }
    ]


def test_resolver_passes_exact_eligibility_filters() -> None:
    repo = RecordingRepository([])
    now = _dt("2026-06-08T00:05:00Z")
    assert _resolve(repo, now_utc=now, limit=50) == _stats(due=0)
    # It scans min(max(limit * 20, limit), 1000) rows, so stuck rows cannot starve fresh ones.
    assert repo.due_calls == [
        (now, 1000, ("BINANCE_PUBLIC", "OKX_PUBLIC"),
         ("15m", "1D", "1H", "1W", "4H"), ("USER_REQUESTED",))
    ]


def test_resolver_eligible_row_is_not_starved_by_older_cross_provider_rows() -> None:
    class SavingRepository(InMemoryPersistenceRepository):
        def save_prediction_outcome(self, row):
            super().save_prediction_outcome(row)
            return "OK"

    repo = SavingRepository()
    for index in range(60):
        repo.save_prediction({
            **_prediction(prediction_id=f"cross-{index}"),
            "data_source": "CROSS_PROVIDER",
            "horizon_end_utc": "2026-06-07T00:00:00Z",
        })
    exact = _prediction(prediction_id="exact")
    repo.save_prediction(exact)
    calls = []

    def fetch(window, settings):
        calls.append(window)
        return _terminal_candles(window, settings)

    assert _resolve(repo, limit=50, fetch_candles=fetch) == _stats(due=1, resolved=1)
    assert len(calls) == 1
    assert calls[0].data_source == "BINANCE_PUBLIC"
    assert calls[0].terminal_close_utc == _dt(exact["horizon_end_utc"])
    assert list(repo._prediction_outcomes) == ["exact"]
    assert repo._prediction_outcomes["exact"]["prediction_id"] == "exact"


def test_resolver_user_row_is_not_starved_by_older_shadow_and_smoke_rows() -> None:
    class SavingRepository(InMemoryPersistenceRepository):
        def save_prediction_outcome(self, row):
            super().save_prediction_outcome(row)
            return "OK"

    repo = SavingRepository()
    excluded = [
        (f"shadow-{index}", "SCHEDULED_SHADOW_EVIDENCE") for index in range(60)
    ] + [
        (f"oosb-{index:032x}:4H:BASELINE", "SCHEDULED_SHADOW_EVIDENCE")
        for index in range(3)
    ] + [(f"smoke-{index}", "CONTROLLED_SMOKE") for index in range(5)]
    for identifier, origin in excluded:
        repo.save_prediction({
            **_prediction(prediction_id=identifier),
            "prediction_origin": origin,
            "horizon_end_utc": "2026-06-07T00:00:00Z",
        })
    repo.save_prediction({
        **_prediction(prediction_id="user"), "prediction_origin": "USER_REQUESTED",
    })
    calls = []

    def fetch(window, settings):
        calls.append(window)
        return _terminal_candles(window, settings)

    assert _resolve(repo, limit=50, fetch_candles=fetch) == _stats(due=1, resolved=1)
    assert len(calls) == 1
    assert calls[0].data_source == "BINANCE_PUBLIC"
    assert list(repo._prediction_outcomes) == ["user"]
    assert repo._prediction_outcomes["user"]["prediction_id"] == "user"
