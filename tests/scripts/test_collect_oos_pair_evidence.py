from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from crypto_probability_engine.adapters.provider_selection import ProviderSelectionResult
from crypto_probability_engine.adapters.types import MarketCandle, MarketSnapshot
from scripts import collect_oos_pair_evidence as collector

TARGET_CELL = ("BTC/USDT", "15m")


def _selection_at(
    *,
    symbol: str,
    timeframe: str,
    reference_close: datetime,
    as_of: datetime,
) -> ProviderSelectionResult:
    seconds = collector.TIMEFRAME_SECONDS[timeframe]
    candle = MarketCandle(
        open_time_utc=reference_close - timedelta(seconds=seconds),
        close_time_utc=reference_close,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1000.0,
    )
    return ProviderSelectionResult(
        snapshot=MarketSnapshot(
            provider="test",
            normalized_symbol=symbol,
            timeframe=timeframe,
            candles=(candle,),
            order_book=None,
            as_of_utc=as_of,
        ),
        provider_state={"status": "OK"},
        data_quality={
            "status": "OK",
            "is_live_data": True,
            "data_source": "TEST_LIVE",
            "warnings": [],
        },
    )


def _write_options() -> collector.CollectorOptions:
    return collector.CollectorOptions(
        dry_run=False,
        confirm_write=collector.WRITE_CONFIRMATION,
    )


def _write_environ() -> dict[str, str]:
    return {
        collector.ENABLE_ENV: "true",
        "SUPABASE_DB_URL": "postgresql://example.invalid/test",
    }


@pytest.mark.parametrize(
    ("environ", "options", "classification"),
    (
        ({}, collector.CollectorOptions(dry_run=False), "DISABLED"),
        (
            {collector.ENABLE_ENV: "true"},
            collector.CollectorOptions(dry_run=False),
            "CONFIRMATION_REQUIRED",
        ),
    ),
)
def test_absent_enable_or_confirmation_never_constructs_repository(
    environ, options, classification
) -> None:
    dependencies = collector.CollectorDependencies(
        repository_factory=lambda _settings: pytest.fail("repository was constructed")
    )
    result = collector.run_collector(
        options,
        environ=environ,
        dependencies=dependencies,
    )
    assert result["final_classification"] == classification


def test_dry_run_writes_nothing() -> None:
    dependencies = collector.CollectorDependencies(
        persist=lambda *_args: pytest.fail("dry run attempted persistence"),
        repository_factory=lambda _settings: pytest.fail("dry run constructed repository"),
    )
    result = collector.run_collector(
        collector.CollectorOptions(),
        environ={collector.ENABLE_ENV: "true"},
        dependencies=dependencies,
    )
    assert result["final_classification"] == "DRY_RUN"


def test_historical_reference_is_not_current_live_snapshot() -> None:
    now = datetime(2026, 8, 20, 8, tzinfo=UTC)
    assert not collector._is_current_live_reference(  # noqa: SLF001
        now - timedelta(hours=1),
        now,
        now,
        "1H",
    )


def test_one_arm_orphan_is_permanently_skipped_without_write() -> None:
    now = datetime(2026, 8, 20, 12, tzinfo=UTC)
    persisted = []
    analyzed = []

    class Repository:
        @staticmethod
        def fetch_latest_oos_occasion(symbol, timeframe):
            return None if (symbol, timeframe) == TARGET_CELL else now

        @staticmethod
        def count_oos_occasion_rows(symbol, timeframe, reference):
            assert (symbol, timeframe) == TARGET_CELL
            assert reference == now
            return 1

    def select(symbol, timeframe, *, settings):
        del settings
        assert (symbol.display, timeframe) == TARGET_CELL
        return _selection_at(
            symbol=symbol.display,
            timeframe=timeframe,
            reference_close=now,
            as_of=now,
        )

    def analyze(_request, *, pair_context, **_kwargs):
        analyzed.append(pair_context.run_id)
        return {"run_id": pair_context.run_id}

    dependencies = collector.CollectorDependencies(
        select=select,
        analyze=analyze,
        persist=lambda payload, _repository: (
            persisted.append(payload) or {"overall": "OK"}
        ),
        repository_factory=lambda _settings: Repository(),
        verify_freeze=lambda: None,
        now_utc=lambda: now,
    )

    result = collector.run_collector(
        _write_options(),
        environ=_write_environ(),
        dependencies=dependencies,
    )

    assert result["final_classification"] == "OK"
    assert result["occasions_inserted"] == 0
    assert result["orphans"] == 1
    assert result["skipped"] == len(collector.MATRIX)
    assert result["market_selections"] == 1
    assert result["cells"][0]["classification"] == "ORPHAN_SKIPPED"
    assert not analyzed
    assert not persisted


@pytest.mark.parametrize(
    "snapshot_as_of",
    (
        datetime(2026, 8, 20, 11, 59, tzinfo=UTC),
        datetime(2026, 8, 20, 12, 6, tzinfo=UTC),
    ),
    ids=("reference-after-stale-as-of", "as-of-too-far-in-future"),
)
def test_invalid_live_reference_window_refuses_backfill_without_write(
    snapshot_as_of,
) -> None:
    now = datetime(2026, 8, 20, 12, tzinfo=UTC)
    occasion_reads = []
    persisted = []

    class Repository:
        @staticmethod
        def fetch_latest_oos_occasion(symbol, timeframe):
            return None if (symbol, timeframe) == TARGET_CELL else now

        @staticmethod
        def count_oos_occasion_rows(symbol, timeframe, reference):
            occasion_reads.append((symbol, timeframe, reference))
            return 0

    def select(symbol, timeframe, *, settings):
        del settings
        assert (symbol.display, timeframe) == TARGET_CELL
        return _selection_at(
            symbol=symbol.display,
            timeframe=timeframe,
            reference_close=now,
            as_of=snapshot_as_of,
        )

    dependencies = collector.CollectorDependencies(
        select=select,
        analyze=lambda _request, **_kwargs: {"run_id": "unexpected"},
        persist=lambda payload, _repository: (
            persisted.append(payload) or {"overall": "OK"}
        ),
        repository_factory=lambda _settings: Repository(),
        verify_freeze=lambda: None,
        now_utc=lambda: now,
    )

    result = collector.run_collector(
        _write_options(),
        environ=_write_environ(),
        dependencies=dependencies,
    )

    assert result["final_classification"] == "PARTIAL_FAILURE"
    assert result["occasions_inserted"] == 0
    assert result["failed"] == 1
    assert result["market_selections"] == 1
    assert result["cells"][0]["classification"] == "BACKFILL_REFUSED"
    assert not occasion_reads
    assert not persisted


def test_one_selection_and_one_shared_selection_state_per_occasion() -> None:
    now = datetime(2026, 8, 20, 12, tzinfo=UTC)
    selections = []
    analyses = []
    persisted = []

    class Repository:
        @staticmethod
        def fetch_latest_oos_occasion(_symbol, _timeframe):
            return None

        @staticmethod
        def count_oos_occasion_rows(_symbol, _timeframe, _reference):
            return 0

    def select(symbol, timeframe, *, settings):
        del settings
        selections.append((symbol.display, timeframe))
        seconds = collector.TIMEFRAME_SECONDS[timeframe]
        candle = MarketCandle(
            open_time_utc=now - timedelta(seconds=seconds),
            close_time_utc=now,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000.0,
        )
        provider_state = {"status": "OK", "occasion": len(selections)}
        data_quality = {
            "status": "OK",
            "is_live_data": True,
            "data_source": "TEST_LIVE",
            "warnings": [],
            "occasion": len(selections),
        }
        return ProviderSelectionResult(
            snapshot=MarketSnapshot(
                provider="test",
                normalized_symbol=symbol.display,
                timeframe=timeframe,
                candles=(candle,),
                order_book=None,
                as_of_utc=now,
            ),
            provider_state=provider_state,
            data_quality=data_quality,
        )

    def analyze(_request, *, pair_context, arm, **_kwargs):
        arm_context = pair_context.for_arm(arm)
        analyses.append(
            (
                pair_context.run_id,
                arm,
                arm_context.provider_state,
                arm_context.data_quality,
            )
        )
        return {"run_id": pair_context.run_id}

    dependencies = collector.CollectorDependencies(
        select=select,
        resolve_skill=lambda _timeframe: {"verdict": "INSUFFICIENT_EVIDENCE"},
        analyze=analyze,
        persist=lambda payload, _repository: (
            persisted.append(payload["run_id"]) or {"overall": "OK"}
        ),
        repository_factory=lambda _settings: Repository(),
        verify_freeze=lambda: None,
        now_utc=lambda: now,
    )
    result = collector.run_collector(
        collector.CollectorOptions(
            dry_run=False,
            confirm_write=collector.WRITE_CONFIRMATION,
        ),
        environ={
            collector.ENABLE_ENV: "true",
            "SUPABASE_DB_URL": "postgresql://example.invalid/test",
        },
        dependencies=dependencies,
    )

    assert result["occasions_inserted"] == len(collector.MATRIX)
    assert len(selections) == len(collector.MATRIX)
    assert len(analyses) == len(collector.MATRIX) * 2
    assert len(persisted) == len(collector.MATRIX)
    for baseline, candidate in zip(analyses[::2], analyses[1::2], strict=True):
        assert baseline[0] == candidate[0]
        assert baseline[2] is candidate[2]
        assert baseline[3] is candidate[3]


def test_workflow_is_manual_only_and_dry_by_default() -> None:
    text = (
        Path(__file__).resolve().parents[2]
        / ".github/workflows/oos-pair-evidence.yml"
    ).read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "default: true" in text
