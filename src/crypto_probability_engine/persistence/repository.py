"""Best-effort persistence repositories for compact app state."""

from __future__ import annotations

import json
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

import httpx

from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.derivatives_snapshot import (
    DerivativesSnapshotWriteStatus,
)
from crypto_probability_engine.persistence.feature_snapshot import (
    FeatureSnapshotWriteStatus,
)
from crypto_probability_engine.persistence.prediction_origin import (
    DEFAULT_PREDICTION_ORIGIN,
    validate_prediction_origin,
)
from crypto_probability_engine.utils import canonical_json

PersistenceStatus = Literal["STATELESS", "OK", "UNAVAILABLE"]
RUN_SUMMARY_RETENTION_LIMIT = 100
RUN_DETAIL_AVAILABILITY_LIMIT = 500


class OOSArmIdentityConflict(RuntimeError):
    """An OOS arm identity was already occupied instead of being inserted."""


class PersistenceRepository(Protocol):
    def persistence_status(self) -> PersistenceStatus:
        """Return current persistence health without exposing connection details."""

    def save_run(self, summary: Mapping[str, Any]) -> PersistenceStatus:
        """Persist compact analysis run summary."""

    def save_run_detail(self, row: Mapping[str, Any]) -> PersistenceStatus:
        """Persist a sanitized analysis Detail document."""

    def save_timeframe_result(self, row: Mapping[str, Any]) -> PersistenceStatus:
        """Persist compact per-timeframe analysis result."""

    def save_provider_observation(self, row: Mapping[str, Any]) -> PersistenceStatus:
        """Persist compact provider observation."""

    def save_news_item(self, row: Mapping[str, Any]) -> PersistenceStatus:
        """Persist compact news metadata item."""

    def save_news_cluster(self, row: Mapping[str, Any]) -> PersistenceStatus:
        """Persist compact news cluster summary."""

    def save_news_evidence_link(self, row: Mapping[str, Any]) -> PersistenceStatus:
        """Persist compact run-to-news evidence link."""

    def save_prediction(self, row: Mapping[str, Any]) -> PersistenceStatus:
        """Persist immutable prediction ledger row."""

    def save_feature_snapshot(
        self, row: Mapping[str, Any]
    ) -> FeatureSnapshotWriteStatus:
        """Persist immutable prediction-time Quant V2 evidence."""

    def save_derivatives_snapshot(
        self, row: Mapping[str, Any]
    ) -> DerivativesSnapshotWriteStatus:
        """Persist immutable prediction-linked derivatives evidence."""

    def fetch_due_unresolved_predictions(self, now_utc: Any, limit: int) -> list[dict]:
        """Fetch due live predictions with no immutable outcome row yet."""

    def fetch_latest_oos_occasion(
        self, normalized_symbol: str, timeframe: str
    ) -> datetime | None:
        """Return the latest OOS reference close for one matrix cell."""

    def oos_occasion_exists(
        self,
        normalized_symbol: str,
        timeframe: str,
        reference_close_utc: Any,
    ) -> bool:
        """Return whether any row in the strict OOS namespace occupies an occasion."""

    def count_oos_occasion_rows(
        self,
        normalized_symbol: str,
        timeframe: str,
        reference_close_utc: Any,
    ) -> int:
        """Count strict-namespace rows occupying one OOS occasion."""

    def fetch_oos_t0(self) -> datetime | None:
        """Return the first exact, same-run baseline/candidate OOS pair close."""

    def fetch_oos_paired_evidence(self, *, include_probabilities: bool) -> list[dict]:
        """Return Tier-1 qualifying OOS pairs with outcomes joined.

        ``include_probabilities=False`` omits every probability field so a readiness
        run cannot compute a score at all.
        """

    def count_oos_origin_anomalies(self) -> int:
        """Count OOS-namespace rows whose prediction_origin is unexpected."""

    def fetch_oos_feature_diagnostics(self) -> list[dict]:
        """Return the four persisted quant_v2 diagnostic values per OOS prediction."""

    def claim_section_5a_seal(self, payload: Mapping[str, Any]) -> bool:
        """Atomically claim the one-look seal, before any probability is exposed.

        Returns ``True`` when this call claimed it, ``False`` when a seal already
        existed. The payload carries no evidence. The durable authority requires a verified
        ``run_provenance`` record in it (owner ruling E2=A).
        """

    def fetch_section_5a_seal(self) -> dict | None:
        """Return the durable seal row, or ``None`` when the look is unspent."""

    def advance_section_5a_seal_state(self, state: str, detail: str = "") -> None:
        """Advance the seal state. The captured evidence stays immutable."""

    def capture_section_5a_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        """Durably record the canonical snapshot and its digests, exactly once."""

    def section_5a_seal_authority(self) -> str:
        """Declare what kind of one-look seal this repository can provide.

        Only ``POSTGRES_DURABLE`` is a cross-process, durable authority. Anything else must be
        refused for consumption (finding G8).
        """

    def save_prediction_outcome(self, row: Mapping[str, Any]) -> PersistenceStatus:
        """Persist immutable prediction outcome row."""

    def fetch_resolved_prediction_outcomes_for_calibration(
        self,
        *,
        timeframe: str | None = None,
        symbol: str | None = None,
        normalized_symbol: str | None = None,
        model_version: str | None = None,
        methodology_version: str | None = None,
        since: Any | None = None,
        until: Any | None = None,
        limit: int | None = None,
        prediction_origin: str = DEFAULT_PREDICTION_ORIGIN,
    ) -> list[dict]:
        """Fetch resolved live prediction/outcome rows for read-only calibration."""

    def fetch_feature_snapshot_validation_coverage(
        self,
        *,
        feature_methodology_version: str,
        timeframe: str | None,
        since: datetime | None,
        until: datetime | None,
        prediction_origin: str = DEFAULT_PREDICTION_ORIGIN,
    ) -> dict[str, Any]:
        """Return aggregate read-only snapshot-validation coverage."""

    def fetch_feature_snapshot_validation_rows(
        self,
        *,
        feature_methodology_version: str,
        timeframe: str | None,
        since: datetime | None,
        until: datetime | None,
        limit: int,
        prediction_origin: str = DEFAULT_PREDICTION_ORIGIN,
    ) -> list[dict[str, Any]]:
        """Return bounded joined rows for offline shadow validation."""

    def list_watchlist(self, operator_id: str = "operator") -> list[str]:
        """List normalized watchlist symbols for an operator."""

    def add_watchlist(self, symbol: str, operator_id: str = "operator") -> PersistenceStatus:
        """Add a normalized symbol to an operator watchlist."""

    def remove_watchlist(self, symbol: str, operator_id: str = "operator") -> PersistenceStatus:
        """Remove a normalized symbol from an operator watchlist."""

    def recent_runs(self, limit: int) -> list[dict]:
        """Return compact recent run summaries."""

    def recent_runs_for_origin(
        self, limit: int, *, prediction_origin: str
    ) -> list[dict]:
        """Return recent runs joined to predictions of the required origin."""

    def get_run(self, run_id: str) -> dict | None:
        """Return compact run summary by id."""

    def get_run_detail(
        self, run_id: str, *, prediction_origin: str
    ) -> dict | None:
        """Return Detail only when prediction provenance matches."""

    def run_ids_with_detail(
        self, run_ids: Sequence[str], *, prediction_origin: str
    ) -> set[str]:
        """Return bounded run ids with Detail and matching prediction provenance."""


class InMemoryPersistenceRepository:
    """Stateless process-memory repository used when external persistence is absent."""

    def __init__(self) -> None:
        self._runs: OrderedDict[str, dict] = OrderedDict()
        self._run_details: OrderedDict[str, dict] = OrderedDict()
        self._predictions: OrderedDict[str, dict] = OrderedDict()
        self._feature_snapshots: OrderedDict[str, dict] = OrderedDict()
        self._derivatives_snapshots: OrderedDict[str, dict] = OrderedDict()
        self._prediction_outcomes: OrderedDict[str, dict] = OrderedDict()
        self._watchlists: dict[str, OrderedDict[str, None]] = {}
        self._section_5a_seal: dict | None = None

    def persistence_status(self) -> PersistenceStatus:
        return "STATELESS"

    def repository_type(self) -> str:
        return "IN_MEMORY"

    def circuit_state(self) -> str:
        return "STATELESS"

    def save_run(self, summary: Mapping[str, Any]) -> PersistenceStatus:
        run_id = str(summary.get("run_id", ""))
        if run_id:
            self._runs[run_id] = dict(summary)
            self._runs.move_to_end(run_id)
            while len(self._runs) > RUN_SUMMARY_RETENTION_LIMIT:
                self._runs.popitem(last=False)
        return self.persistence_status()

    def save_run_detail(self, row: Mapping[str, Any]) -> PersistenceStatus:
        run_id = str(row.get("run_id", ""))
        if run_id:
            self._run_details[run_id] = deepcopy(dict(row))
        return self.persistence_status()

    def save_timeframe_result(self, row: Mapping[str, Any]) -> PersistenceStatus:
        return self.persistence_status()

    def save_provider_observation(self, row: Mapping[str, Any]) -> PersistenceStatus:
        return self.persistence_status()

    def save_news_item(self, row: Mapping[str, Any]) -> PersistenceStatus:
        return self.persistence_status()

    def save_news_cluster(self, row: Mapping[str, Any]) -> PersistenceStatus:
        return self.persistence_status()

    def save_news_evidence_link(self, row: Mapping[str, Any]) -> PersistenceStatus:
        return self.persistence_status()

    def save_prediction(self, row: Mapping[str, Any]) -> PersistenceStatus:
        normalized_row = _prediction_row_with_origin(row)
        prediction_id = str(normalized_row.get("prediction_id", ""))
        if prediction_id in self._predictions:
            if _is_oos_arm_prediction_id(prediction_id):
                raise OOSArmIdentityConflict(
                    "OOS arm prediction identity is already occupied."
                )
            return self.persistence_status()
        if prediction_id:
            self._predictions[prediction_id] = normalized_row
        return self.persistence_status()

    def save_feature_snapshot(
        self, row: Mapping[str, Any]
    ) -> FeatureSnapshotWriteStatus:
        prediction_id = str(row.get("prediction_id", ""))
        snapshot_hash = str(row.get("snapshot_hash", ""))
        if not prediction_id or not snapshot_hash:
            return FeatureSnapshotWriteStatus.UNAVAILABLE
        existing = self._feature_snapshots.get(prediction_id)
        if existing is None:
            self._feature_snapshots[prediction_id] = deepcopy(dict(row))
            return FeatureSnapshotWriteStatus.INSERTED
        if str(existing.get("snapshot_hash", "")) == snapshot_hash:
            return FeatureSnapshotWriteStatus.IDENTICAL_DUPLICATE
        return FeatureSnapshotWriteStatus.CONFLICT

    def get_feature_snapshot(self, prediction_id: str) -> dict | None:
        """Return an isolated snapshot copy for focused internal tests."""

        row = self._feature_snapshots.get(prediction_id)
        return deepcopy(row) if row is not None else None

    def save_derivatives_snapshot(
        self, row: Mapping[str, Any]
    ) -> DerivativesSnapshotWriteStatus:
        prediction_id = str(row.get("prediction_id", ""))
        snapshot_hash = str(row.get("snapshot_hash", ""))
        if not prediction_id or not snapshot_hash:
            return DerivativesSnapshotWriteStatus.UNAVAILABLE
        existing = self._derivatives_snapshots.get(prediction_id)
        if existing is None:
            self._derivatives_snapshots[prediction_id] = deepcopy(dict(row))
            return DerivativesSnapshotWriteStatus.INSERTED
        if str(existing.get("snapshot_hash", "")) == snapshot_hash:
            return DerivativesSnapshotWriteStatus.IDENTICAL_DUPLICATE
        return DerivativesSnapshotWriteStatus.CONFLICT

    def get_derivatives_snapshot(self, prediction_id: str) -> dict | None:
        """Return an isolated derivatives snapshot copy for focused tests."""

        row = self._derivatives_snapshots.get(prediction_id)
        return deepcopy(row) if row is not None else None

    def fetch_due_unresolved_predictions(self, now_utc: Any, limit: int) -> list[dict]:
        due = [
            dict(row)
            for row in self._predictions.values()
            if row.get("is_live_data") is True
            and str(row.get("prediction_id", "")) not in self._prediction_outcomes
            and _timestamp_before(row.get("horizon_end_utc"), now_utc)
        ]
        due.sort(key=lambda row: str(row.get("horizon_end_utc", "")))
        return due[: max(0, int(limit))]

    def fetch_latest_oos_occasion(
        self, normalized_symbol: str, timeframe: str
    ) -> datetime | None:
        closes = [
            _to_utc_datetime(row.get("reference_close_utc"))
            for row in self._predictions.values()
            if _is_oos_run_id(row.get("run_id"))
            and row.get("normalized_symbol") == normalized_symbol
            and row.get("timeframe") == timeframe
            and row.get("reference_close_utc") is not None
        ]
        return max(closes, default=None)

    def oos_occasion_exists(
        self,
        normalized_symbol: str,
        timeframe: str,
        reference_close_utc: Any,
    ) -> bool:
        target = _to_utc_datetime(reference_close_utc)
        return any(
            _is_oos_run_id(row.get("run_id"))
            and row.get("normalized_symbol") == normalized_symbol
            and row.get("timeframe") == timeframe
            and _same_timestamp(row.get("reference_close_utc"), target)
            for row in self._predictions.values()
        )

    def count_oos_occasion_rows(
        self,
        normalized_symbol: str,
        timeframe: str,
        reference_close_utc: Any,
    ) -> int:
        target = _to_utc_datetime(reference_close_utc)
        return sum(
            _is_oos_run_id(row.get("run_id"))
            and row.get("normalized_symbol") == normalized_symbol
            and row.get("timeframe") == timeframe
            and _same_timestamp(row.get("reference_close_utc"), target)
            for row in self._predictions.values()
        )

    def fetch_oos_t0(self) -> datetime | None:
        return _oos_t0_from_rows(self._predictions.values())

    def fetch_oos_paired_evidence(self, *, include_probabilities: bool) -> list[dict]:
        return _oos_paired_evidence_from_rows(
            self._predictions.values(),
            self._prediction_outcomes.get,
            include_probabilities=include_probabilities,
        )

    def count_oos_origin_anomalies(self) -> int:
        return _oos_origin_anomalies_from_rows(self._predictions.values())

    def fetch_oos_feature_diagnostics(self) -> list[dict]:
        return _oos_feature_diagnostics_from_rows(
            self._predictions.values(), self._feature_snapshots.get
        )

    def claim_section_5a_seal(self, payload: Mapping[str, Any]) -> bool:
        if self._section_5a_seal is not None:
            return False
        self._section_5a_seal = dict(payload)
        return True

    def fetch_section_5a_seal(self) -> dict | None:
        return None if self._section_5a_seal is None else dict(self._section_5a_seal)

    def advance_section_5a_seal_state(self, state: str, detail: str = "") -> None:
        if self._section_5a_seal is None:
            raise RuntimeError("no section 5A seal to advance")
        self._section_5a_seal["state"] = state
        self._section_5a_seal["state_detail"] = detail

    def capture_section_5a_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        seal = self._section_5a_seal
        if seal is None or seal.get("state") != SECTION_5A_STATE_CLAIMED:
            raise RuntimeError("no CLAIMED section 5A seal to capture into")
        if seal.get("snapshot_payload") is not None:
            raise RuntimeError("section 5A snapshot is already captured")
        seal.update(
            snapshot_payload=dict(snapshot),
            evidence_snapshot_id=snapshot["evidence_snapshot_id"],
            result_inputs_digest=snapshot["result_inputs_digest"],
            state="SEALED_RAW_CAPTURED",
        )

    def section_5a_seal_authority(self) -> str:
        # Its seal dies with this object. It can never be the one-look authority (G8).
        return "PROCESS_LOCAL"

    def save_prediction_outcome(self, row: Mapping[str, Any]) -> PersistenceStatus:
        prediction_id = str(row.get("prediction_id", ""))
        if prediction_id and prediction_id not in self._prediction_outcomes:
            self._prediction_outcomes[prediction_id] = dict(row)
        return self.persistence_status()

    def fetch_resolved_prediction_outcomes_for_calibration(
        self,
        *,
        timeframe: str | None = None,
        symbol: str | None = None,
        normalized_symbol: str | None = None,
        model_version: str | None = None,
        methodology_version: str | None = None,
        since: Any | None = None,
        until: Any | None = None,
        limit: int | None = None,
        prediction_origin: str = DEFAULT_PREDICTION_ORIGIN,
    ) -> list[dict]:
        prediction_origin = validate_prediction_origin(prediction_origin)
        rows = []
        for prediction_id, prediction in self._predictions.items():
            outcome = self._prediction_outcomes.get(prediction_id)
            if not outcome:
                continue
            row = _calibration_row_from_parts(prediction, outcome)
            if _calibration_row_matches(
                row,
                timeframe=timeframe,
                symbol=symbol,
                normalized_symbol=normalized_symbol,
                model_version=model_version,
                methodology_version=methodology_version,
                prediction_origin=prediction_origin,
                since=since,
                until=until,
            ):
                rows.append(row)
        rows.sort(key=lambda row: str(row.get("outcome_close_utc", "")))
        if limit is not None:
            return rows[: max(0, int(limit))]
        return rows

    def fetch_feature_snapshot_validation_coverage(
        self,
        *,
        feature_methodology_version: str,
        timeframe: str | None,
        since: datetime | None,
        until: datetime | None,
        prediction_origin: str = DEFAULT_PREDICTION_ORIGIN,
    ) -> dict[str, Any]:
        prediction_origin = validate_prediction_origin(prediction_origin)
        predictions = [
            row
            for row in self._predictions.values()
            if row.get("is_live_data") is True
            and (timeframe is None or row.get("timeframe") == timeframe)
            and _prediction_origin_matches(row, prediction_origin)
            and _validation_within_upper_bound(row.get("predicted_at_utc"), until)
        ]
        snapshots = [
            row
            for row in self._feature_snapshots.values()
            if row.get("feature_methodology_version") == feature_methodology_version
            and _prediction_origin_matches(
                self._predictions.get(str(row.get("prediction_id", ""))),
                prediction_origin,
            )
            and (timeframe is None or row.get("timeframe") == timeframe)
            and _validation_within_upper_bound(row.get("prediction_as_of_utc"), until)
        ]
        snapshot_times = [
            row.get("prediction_as_of_utc")
            for row in snapshots
            if row.get("prediction_as_of_utc") is not None
        ]
        first_snapshot = min(snapshot_times, key=_to_utc_datetime) if snapshot_times else None
        latest_snapshot = max(snapshot_times, key=_to_utc_datetime) if snapshot_times else None
        era_start = since if since is not None else first_snapshot
        eligible_predictions = [
            row
            for row in predictions
            if _validation_at_or_after(row.get("predicted_at_utc"), era_start)
        ]
        eligible_snapshots = [
            row
            for row in snapshots
            if _validation_at_or_after(row.get("prediction_as_of_utc"), era_start)
        ]
        eligible_snapshot_ids = {
            str(row.get("prediction_id", "")) for row in eligible_snapshots
        }
        resolved_ids = {
            str(prediction.get("prediction_id", ""))
            for prediction in eligible_predictions
            if _validation_live_outcome(
                self._prediction_outcomes.get(str(prediction.get("prediction_id", "")))
            )
        }
        eligible_prediction_ids = {
            str(row.get("prediction_id", "")) for row in eligible_predictions
        }
        return {
            "live_predictions_all_time": len(predictions),
            "live_predictions_eligible_era": len(eligible_predictions),
            "snapshots_all_time": len(snapshots),
            "snapshots_eligible_era": len(eligible_snapshots),
            "resolved_outcomes_eligible_era": len(resolved_ids),
            "snapshot_outcome_joins_eligible_era": len(
                eligible_snapshot_ids & resolved_ids
            ),
            "predictions_missing_snapshot_eligible_era": len(
                eligible_prediction_ids - eligible_snapshot_ids
            ),
            "snapshots_missing_outcome_eligible_era": len(
                eligible_snapshot_ids - resolved_ids
            ),
            "first_snapshot_as_of_utc": first_snapshot,
            "latest_snapshot_as_of_utc": latest_snapshot,
        }

    def fetch_feature_snapshot_validation_rows(
        self,
        *,
        feature_methodology_version: str,
        timeframe: str | None,
        since: datetime | None,
        until: datetime | None,
        limit: int,
        prediction_origin: str = DEFAULT_PREDICTION_ORIGIN,
    ) -> list[dict[str, Any]]:
        prediction_origin = validate_prediction_origin(prediction_origin)
        bounded_limit = _validation_limit(limit)
        rows: list[dict[str, Any]] = []
        for prediction_id, snapshot in self._feature_snapshots.items():
            prediction = self._predictions.get(prediction_id)
            outcome = self._prediction_outcomes.get(prediction_id)
            if not prediction or not _validation_live_outcome(outcome):
                continue
            if prediction.get("is_live_data") is not True:
                continue
            if not _prediction_origin_matches(prediction, prediction_origin):
                continue
            if snapshot.get("feature_methodology_version") != feature_methodology_version:
                continue
            if timeframe is not None and prediction.get("timeframe") != timeframe:
                continue
            predicted_at = prediction.get("predicted_at_utc")
            if not _validation_in_window(predicted_at, since, until):
                continue
            rows.append(_validation_row_from_parts(prediction, outcome, snapshot))
        rows.sort(
            key=lambda row: (
                _to_utc_datetime(row["predicted_at_utc"]),
                str(row["prediction_id"]),
            )
        )
        return rows[:bounded_limit]

    def list_watchlist(self, operator_id: str = "operator") -> list[str]:
        return list(self._watchlists.get(operator_id, OrderedDict()).keys())

    def add_watchlist(self, symbol: str, operator_id: str = "operator") -> PersistenceStatus:
        self._watchlists.setdefault(operator_id, OrderedDict())[symbol] = None
        return self.persistence_status()

    def remove_watchlist(self, symbol: str, operator_id: str = "operator") -> PersistenceStatus:
        self._watchlists.setdefault(operator_id, OrderedDict()).pop(symbol, None)
        return self.persistence_status()

    def recent_runs(self, limit: int) -> list[dict]:
        values = list(reversed(self._runs.values()))
        return [dict(item) for item in values[:limit]]

    def recent_runs_for_origin(
        self, limit: int, *, prediction_origin: str
    ) -> list[dict]:
        prediction_origin = validate_prediction_origin(prediction_origin)
        matching_run_ids = {
            str(prediction.get("run_id"))
            for prediction in self._predictions.values()
            if prediction.get("prediction_origin") == prediction_origin
            and prediction.get("run_id")
        }
        values = (
            run
            for run in reversed(self._runs.values())
            if run.get("run_id") and str(run.get("run_id")) in matching_run_ids
        )
        return [dict(item) for item in list(values)[:limit]]

    def get_run(self, run_id: str) -> dict | None:
        value = self._runs.get(run_id)
        return dict(value) if value else None

    def get_run_detail(
        self, run_id: str, *, prediction_origin: str
    ) -> dict | None:
        prediction_origin = validate_prediction_origin(prediction_origin)
        if not any(
            str(prediction.get("run_id")) == run_id
            and prediction.get("prediction_origin") == prediction_origin
            for prediction in self._predictions.values()
        ):
            return None
        value = self._run_details.get(run_id)
        if not value or not isinstance(value.get("detail_payload"), Mapping):
            return None
        return deepcopy(value["detail_payload"])

    def run_ids_with_detail(
        self, run_ids: Sequence[str], *, prediction_origin: str
    ) -> set[str]:
        prediction_origin = validate_prediction_origin(prediction_origin)
        candidate_ids = set(run_ids[:RUN_DETAIL_AVAILABILITY_LIMIT])
        if not candidate_ids:
            return set()
        predicted_ids = {
            str(prediction.get("run_id"))
            for prediction in self._predictions.values()
            if prediction.get("prediction_origin") == prediction_origin
            and prediction.get("run_id")
        }
        return candidate_ids.intersection(self._run_details, predicted_ids)


class SupabasePersistenceRepository:
    """Postgres persistence adapter for Supabase direct database URL usage."""

    def __init__(
        self,
        db_url: str,
        *,
        connect_timeout_seconds: int = 3,
        operation_timeout_seconds: float = 3.0,
        circuit_cooldown_seconds: float = 60.0,
        pool_factory: Callable[[], Any] | None = None,
        direct_connection_factory: Callable[[], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._db_url = db_url
        self._connect_timeout_seconds = connect_timeout_seconds
        self._operation_timeout_seconds = operation_timeout_seconds
        self._statement_timeout_ms = max(1000, int(operation_timeout_seconds * 1000))
        self._circuit_cooldown_seconds = circuit_cooldown_seconds
        self._pool_factory = pool_factory
        self._direct_connection_factory = direct_connection_factory
        self._clock = clock
        self._pool: Any | None = None
        self._lock = threading.Lock()
        self._last_status: PersistenceStatus = "OK"
        self._circuit_open_until = 0.0
        self._trial_in_progress = False
        self._fallback = InMemoryPersistenceRepository()

    def persistence_status(self) -> PersistenceStatus:
        with self._lock:
            if self._last_status == "UNAVAILABLE" and self._clock() < self._circuit_open_until:
                return "UNAVAILABLE"
            return self._last_status

    def repository_type(self) -> str:
        return "SUPABASE_POSTGRES"

    def circuit_state(self) -> str:
        with self._lock:
            now = self._clock()
            if self._last_status != "UNAVAILABLE":
                return "CLOSED"
            if now < self._circuit_open_until:
                return "OPEN"
            if self._trial_in_progress:
                return "HALF_OPEN"
            return "HALF_OPEN"

    def maybe_can_attempt(self) -> bool:
        with self._lock:
            now = self._clock()
            if self._last_status != "UNAVAILABLE":
                return True
            if now < self._circuit_open_until:
                return False
            if self._trial_in_progress:
                return False
            self._trial_in_progress = True
            return True

    def mark_unavailable(self) -> PersistenceStatus:
        with self._lock:
            self._last_status = "UNAVAILABLE"
            self._circuit_open_until = self._clock() + self._circuit_cooldown_seconds
            self._trial_in_progress = False
        return self._last_status

    def _mark_ok(self) -> PersistenceStatus:
        with self._lock:
            self._last_status = "OK"
            self._circuit_open_until = 0.0
            self._trial_in_progress = False
        return self._last_status

    def _get_pool(self):
        if self._pool is None:
            if self._pool_factory is not None:
                self._pool = self._pool_factory()
            else:
                from psycopg_pool import ConnectionPool

                self._pool = ConnectionPool(
                    conninfo=self._db_url,
                    min_size=0,
                    max_size=2,
                    timeout=self._operation_timeout_seconds,
                    kwargs={
                        "connect_timeout": self._connect_timeout_seconds,
                        "prepare_threshold": None,
                    },
                    open=False,
                )
            open_pool = getattr(self._pool, "open", None)
            if callable(open_pool):
                open_pool(wait=False)
        return self._pool

    def _connection(self):
        return self._get_pool().connection(timeout=self._operation_timeout_seconds)

    def _direct_connection(self):
        if self._direct_connection_factory is not None:
            return self._direct_connection_factory()
        import psycopg

        return psycopg.connect(
            self._db_url,
            connect_timeout=self._connect_timeout_seconds,
            prepare_threshold=None,
        )

    def _run_db(self, operation):
        if not self.maybe_can_attempt():
            return "UNAVAILABLE", None
        try:
            with self._connection() as conn:
                with conn.cursor() as cursor:
                    _set_local_statement_timeout(cursor, self._statement_timeout_ms)
                    result = operation(cursor)
        except Exception:
            return self.mark_unavailable(), None
        return self._mark_ok(), result

    def close(self) -> None:
        pool = self._pool
        if pool is None:
            return
        close_pool = getattr(pool, "close", None)
        if callable(close_pool):
            close_pool()

    def save_run(self, summary: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_run(summary)
        status, _ = self._run_db(
            lambda cursor: cursor.execute(
                """
                INSERT INTO analysis_runs (
                  run_id, operator_id, symbol, normalized_symbol, analysis_mode,
                  asset_class, primary_timeframe, disposition, total_score,
                  data_source, is_live_data, persistence_status, analysis_hash,
                  as_of_utc
                )
                VALUES (
                  %(run_id)s, %(operator_id)s, %(symbol)s, %(normalized_symbol)s,
                  %(analysis_mode)s, %(asset_class)s, %(primary_timeframe)s,
                  %(disposition)s, %(total_score)s, %(data_source)s,
                  %(is_live_data)s, %(persistence_status)s, %(analysis_hash)s,
                  %(as_of_utc)s
                )
                ON CONFLICT (run_id) DO UPDATE SET
                  disposition = EXCLUDED.disposition,
                  total_score = EXCLUDED.total_score,
                  data_source = EXCLUDED.data_source,
                  is_live_data = EXCLUDED.is_live_data,
                  persistence_status = EXCLUDED.persistence_status,
                  analysis_hash = EXCLUDED.analysis_hash
                """,
                dict(summary),
            )
        )
        return status

    def save_run_detail(self, row: Mapping[str, Any]) -> PersistenceStatus:
        database_row = dict(row)
        database_row["detail_payload"] = json.dumps(row.get("detail_payload"))
        try:
            with self._connection() as conn:
                with conn.cursor() as cursor:
                    _set_local_statement_timeout(cursor, self._statement_timeout_ms)
                    cursor.execute(
                        """
                        INSERT INTO analysis_run_details (
                          run_id, analysis_hash, detail_payload
                        )
                        VALUES (%(run_id)s, %(analysis_hash)s, %(detail_payload)s::jsonb)
                        ON CONFLICT (run_id) DO UPDATE SET
                          analysis_hash = EXCLUDED.analysis_hash,
                          detail_payload = EXCLUDED.detail_payload
                        """,
                        database_row,
                    )
        except Exception:
            return "UNAVAILABLE"
        return "OK"

    def save_timeframe_result(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_timeframe_result(row)
        status, _ = self._run_db(
            lambda cursor: cursor.execute(
                """
                INSERT INTO analysis_timeframe_results (
                  run_id, timeframe, disposition, total_score, prob_up_pct,
                  prob_down_pct, prob_timeout_pct, gate_action, data_source,
                  is_live_data
                )
                VALUES (
                  %(run_id)s, %(timeframe)s, %(disposition)s, %(total_score)s,
                  %(prob_up_pct)s, %(prob_down_pct)s, %(prob_timeout_pct)s,
                  %(gate_action)s, %(data_source)s, %(is_live_data)s
                )
                """,
                dict(row),
            )
        )
        return status

    def save_provider_observation(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_provider_observation(row)
        status, _ = self._run_db(
            lambda cursor: cursor.execute(
                """
                INSERT INTO provider_observations (
                  run_id, provider, provider_status, active_provider, data_source,
                  is_live_data, warning_count
                )
                VALUES (
                  %(run_id)s, %(provider)s, %(provider_status)s,
                  %(active_provider)s, %(data_source)s, %(is_live_data)s,
                  %(warning_count)s
                )
                """,
                dict(row),
            )
        )
        return status

    def save_news_item(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_news_item(row)
        status, _ = self._run_db(
            lambda cursor: cursor.execute(
                """
                INSERT INTO news_items (
                  item_id, run_id, normalized_symbol, provider, source_name, domain,
                  title, snippet, url, url_hash, title_hash, published_at, fetched_at,
                  language, macro_or_micro, event_class, relevance_score, freshness_score,
                  source_authority_score, confidence_score, cluster_id
                )
                VALUES (
                  %(item_id)s, %(run_id)s, %(normalized_symbol)s, %(provider)s,
                  %(source_name)s, %(domain)s, %(title)s, %(snippet)s, %(url)s,
                  %(url_hash)s, %(title_hash)s, %(published_at)s, %(fetched_at)s,
                  %(language)s, %(macro_or_micro)s, %(event_class)s, %(relevance_score)s,
                  %(freshness_score)s, %(source_authority_score)s, %(confidence_score)s,
                  %(cluster_id)s
                )
                ON CONFLICT (item_id) DO UPDATE SET
                  run_id = EXCLUDED.run_id,
                  normalized_symbol = EXCLUDED.normalized_symbol,
                  relevance_score = EXCLUDED.relevance_score,
                  freshness_score = EXCLUDED.freshness_score,
                  source_authority_score = EXCLUDED.source_authority_score,
                  confidence_score = EXCLUDED.confidence_score,
                  cluster_id = EXCLUDED.cluster_id
                """,
                dict(row),
            )
        )
        return status

    def save_news_cluster(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_news_cluster(row)
        status, _ = self._run_db(
            lambda cursor: cursor.execute(
                """
                INSERT INTO news_clusters (
                  cluster_id, run_id, normalized_symbol, representative_title,
                  macro_or_micro, event_class, source_count, item_count,
                  dropped_count, max_relevance_score
                )
                VALUES (
                  %(cluster_id)s, %(run_id)s, %(normalized_symbol)s,
                  %(representative_title)s, %(macro_or_micro)s, %(event_class)s,
                  %(source_count)s, %(item_count)s, %(dropped_count)s,
                  %(max_relevance_score)s
                )
                ON CONFLICT (cluster_id) DO UPDATE SET
                  run_id = EXCLUDED.run_id,
                  normalized_symbol = EXCLUDED.normalized_symbol,
                  source_count = EXCLUDED.source_count,
                  item_count = EXCLUDED.item_count,
                  dropped_count = EXCLUDED.dropped_count,
                  max_relevance_score = EXCLUDED.max_relevance_score
                """,
                dict(row),
            )
        )
        return status

    def save_news_evidence_link(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_news_evidence_link(row)
        status, _ = self._run_db(
            lambda cursor: cursor.execute(
                """
                INSERT INTO news_evidence_links (
                  run_id, cluster_id, item_id, evidence_type, relevance_score
                )
                VALUES (
                  %(run_id)s, %(cluster_id)s, %(item_id)s, %(evidence_type)s,
                  %(relevance_score)s
                )
                ON CONFLICT (run_id, cluster_id, item_id) DO UPDATE SET
                  evidence_type = EXCLUDED.evidence_type,
                  relevance_score = EXCLUDED.relevance_score
                """,
                dict(row),
            )
        )
        return status

    def save_prediction(self, row: Mapping[str, Any]) -> PersistenceStatus:
        normalized_row = _prediction_row_with_origin(row)
        self._fallback.save_prediction(normalized_row)
        if _is_oos_arm_prediction_id(normalized_row.get("prediction_id")):
            return self._save_oos_prediction(normalized_row)
        status, _ = self._run_db(
            lambda cursor: _insert_prediction(cursor, normalized_row)
        )
        return status

    def _save_oos_prediction(self, row: Mapping[str, Any]) -> PersistenceStatus:
        if not self.maybe_can_attempt():
            raise OOSArmIdentityConflict("OOS arm prediction write could not be confirmed.")
        try:
            with self._connection() as conn:
                with conn.cursor() as cursor:
                    _set_local_statement_timeout(cursor, self._statement_timeout_ms)
                    _insert_prediction(cursor, row, reject_conflict=True)
        except Exception as exc:
            self.mark_unavailable()
            raise OOSArmIdentityConflict(
                "OOS arm prediction identity clash or unconfirmed write."
            ) from exc
        self._mark_ok()
        return self.persistence_status()

    def save_feature_snapshot(
        self, row: Mapping[str, Any]
    ) -> FeatureSnapshotWriteStatus:
        database_row = dict(row)
        database_row["snapshot_payload"] = json.dumps(
            row.get("snapshot_payload"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        status, result = self._run_db(
            lambda cursor: _insert_feature_snapshot(cursor, database_row)
        )
        if status == "UNAVAILABLE" or not isinstance(
            result, FeatureSnapshotWriteStatus
        ):
            return FeatureSnapshotWriteStatus.UNAVAILABLE
        return result

    def save_derivatives_snapshot(
        self, row: Mapping[str, Any]
    ) -> DerivativesSnapshotWriteStatus:
        database_row = dict(row)
        database_row["snapshot_payload"] = json.dumps(
            row.get("snapshot_payload"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        status, result = self._run_db(
            lambda cursor: _insert_derivatives_snapshot(cursor, database_row)
        )
        if status == "UNAVAILABLE" or not isinstance(
            result, DerivativesSnapshotWriteStatus
        ):
            return DerivativesSnapshotWriteStatus.UNAVAILABLE
        return result

    def fetch_due_unresolved_predictions(self, now_utc: Any, limit: int) -> list[dict]:
        if not self.maybe_can_attempt():
            raise RuntimeError(
                "SUPABASE_POSTGRES due query failed: RuntimeError [circuit] CircuitOpen"
            )
        phase = "connect"
        try:
            with self._direct_connection() as conn:
                with conn.cursor() as cursor:
                    phase = "set_timeout"
                    _set_local_statement_timeout(cursor, self._statement_timeout_ms)
                    phase = "query"
                    _execute_due_prediction_query(cursor, now_utc, max(0, int(limit)))
                    phase = "fetch"
                    rows = cursor.fetchall()
                    phase = "convert"
                    converted = [_prediction_row_from_db(row) for row in rows]
        except Exception as exc:
            self.mark_unavailable()
            raise RuntimeError(_postgres_error_message("due query", phase, exc)) from None
        self._mark_ok()
        return converted

    def fetch_latest_oos_occasion(
        self, normalized_symbol: str, timeframe: str
    ) -> datetime | None:
        row = self._run_required_oos_read(
            "latest OOS occasion",
            lambda cursor: _fetch_latest_oos_occasion_row(
                cursor, normalized_symbol, timeframe
            ),
        )
        value = _first_db_value(row)
        return _to_utc_datetime(value) if value is not None else None

    def oos_occasion_exists(
        self,
        normalized_symbol: str,
        timeframe: str,
        reference_close_utc: Any,
    ) -> bool:
        row = self._run_required_oos_read(
            "OOS occasion existence",
            lambda cursor: _fetch_oos_occasion_existence_row(
                cursor,
                normalized_symbol,
                timeframe,
                reference_close_utc,
            ),
        )
        return row is not None

    def count_oos_occasion_rows(
        self,
        normalized_symbol: str,
        timeframe: str,
        reference_close_utc: Any,
    ) -> int:
        row = self._run_required_oos_read(
            "OOS occasion count",
            lambda cursor: _fetch_oos_occasion_count_row(
                cursor,
                normalized_symbol,
                timeframe,
                reference_close_utc,
            ),
        )
        return int(_first_db_value(row) or 0)

    def fetch_oos_t0(self) -> datetime | None:
        row = self._run_required_oos_read("OOS T0", _fetch_oos_t0_row)
        value = _first_db_value(row)
        return _to_utc_datetime(value) if value is not None else None

    def fetch_oos_paired_evidence(self, *, include_probabilities: bool) -> list[dict]:
        if include_probabilities:
            # Never a plain read: probabilities leave Postgres only after they are durably
            # captured into a CLAIMED seal, inside the same transaction.
            return self._run_required_oos_read(
                "OOS paired evidence (capture-before-exposure)",
                _fetch_oos_paired_evidence_for_consumption,
            )
        return self._run_required_oos_read(
            "OOS paired evidence",
            lambda cursor: _fetch_oos_paired_evidence_rows(cursor, include_probabilities=False),
        )

    def count_oos_origin_anomalies(self) -> int:
        row = self._run_required_oos_read(
            "OOS origin anomalies", _fetch_oos_origin_anomaly_row
        )
        return int(_first_db_value(row) or 0)

    def fetch_oos_feature_diagnostics(self) -> list[dict]:
        return self._run_required_oos_read(
            "OOS feature diagnostics", _fetch_oos_feature_diagnostic_rows
        )

    def claim_section_5a_seal(self, payload: Mapping[str, Any]) -> bool:
        # OWNER RULING E2=A. The durable authority itself refuses a claim that does not carry a
        # verified run provenance, before any statement executes; migration 0009 refuses the same
        # in SQL. The look can therefore be spent only by a verified dispatch, whichever caller
        # reached this method.
        from crypto_probability_engine.oos.evaluation.provenance import (
            require_verified_provenance,
        )

        require_verified_provenance(payload.get("run_provenance"))
        return bool(
            self._run_required_oos_read(
                "section 5A seal claim",
                lambda cursor: _claim_section_5a_seal_row(cursor, payload),
            )
        )

    def fetch_section_5a_seal(self) -> dict | None:
        return self._run_required_oos_read(
            "section 5A seal read", _fetch_section_5a_seal_row
        )

    def advance_section_5a_seal_state(self, state: str, detail: str = "") -> None:
        if not self._run_required_oos_read(
            "section 5A seal state",
            lambda cursor: _advance_section_5a_seal_state_row(cursor, state, detail),
        ):
            raise RuntimeError("section 5A seal state did not advance; no seal row exists")

    def capture_section_5a_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        if not self._run_required_oos_read(
            "section 5A snapshot capture",
            lambda cursor: _capture_section_5a_snapshot_row(cursor, snapshot),
        ):
            raise RuntimeError(
                "section 5A snapshot capture did not land: the seal is not CLAIMED with raw "
                "evidence, is already captured, or was claimed under a different pin"
            )

    def section_5a_seal_authority(self) -> str:
        return SECTION_5A_SEAL_AUTHORITY_POSTGRES

    def _run_required_oos_read(self, label: str, operation):
        if not self.maybe_can_attempt():
            raise RuntimeError(f"SUPABASE_POSTGRES {label} failed: circuit open")
        phase = "connect"
        try:
            with self._direct_connection() as conn:
                with conn.cursor() as cursor:
                    phase = "set_timeout"
                    _set_local_statement_timeout(cursor, self._statement_timeout_ms)
                    phase = "query"
                    row = operation(cursor)
        except Exception as exc:
            self.mark_unavailable()
            raise RuntimeError(_postgres_error_message(label, phase, exc)) from None
        self._mark_ok()
        return row

    def save_prediction_outcome(self, row: Mapping[str, Any]) -> PersistenceStatus:
        if not self.maybe_can_attempt():
            raise RuntimeError(
                "SUPABASE_POSTGRES outcome write failed: RuntimeError [circuit] CircuitOpen"
            )
        phase = "connect"
        try:
            with self._direct_connection() as conn:
                with conn.cursor() as cursor:
                    phase = "set_timeout"
                    _set_local_statement_timeout(cursor, self._statement_timeout_ms)
                    phase = "write"
                    cursor.execute(
                        """
                        INSERT INTO public.prediction_outcomes (
                          prediction_id, resolved_at_utc, outcome_close_utc,
                          outcome_reference_price, terminal_return_frac, realized_label,
                          decision_band_frac, max_favorable_frac, max_adverse_frac,
                          candles_observed, resolver_version, data_source, is_live_data
                        )
                        VALUES (
                          %(prediction_id)s, %(resolved_at_utc)s, %(outcome_close_utc)s,
                          %(outcome_reference_price)s, %(terminal_return_frac)s,
                          %(realized_label)s, %(decision_band_frac)s, %(max_favorable_frac)s,
                          %(max_adverse_frac)s, %(candles_observed)s, %(resolver_version)s,
                          %(data_source)s, %(is_live_data)s
                        )
                        ON CONFLICT (prediction_id) DO NOTHING
                        """,
                        dict(row),
                    )
        except Exception as exc:
            self.mark_unavailable()
            raise RuntimeError(_postgres_error_message("outcome write", phase, exc)) from None
        self._mark_ok()
        return self.persistence_status()

    def fetch_resolved_prediction_outcomes_for_calibration(
        self,
        *,
        timeframe: str | None = None,
        symbol: str | None = None,
        normalized_symbol: str | None = None,
        model_version: str | None = None,
        methodology_version: str | None = None,
        since: Any | None = None,
        until: Any | None = None,
        limit: int | None = None,
        prediction_origin: str = DEFAULT_PREDICTION_ORIGIN,
    ) -> list[dict]:
        prediction_origin = validate_prediction_origin(prediction_origin)
        if not self.maybe_can_attempt():
            raise RuntimeError(
                "SUPABASE_POSTGRES calibration read failed: RuntimeError [circuit] CircuitOpen"
            )
        phase = "connect"
        try:
            with self._direct_connection() as conn:
                with conn.cursor() as cursor:
                    phase = "set_timeout"
                    _set_local_statement_timeout(cursor, self._statement_timeout_ms)
                    phase = "query"
                    _execute_calibration_query(
                        cursor,
                        timeframe=timeframe,
                        symbol=symbol,
                        normalized_symbol=normalized_symbol,
                        model_version=model_version,
                        methodology_version=methodology_version,
                        since=since,
                        until=until,
                        limit=limit,
                        prediction_origin=prediction_origin,
                    )
                    phase = "fetch"
                    rows = cursor.fetchall()
                    phase = "convert"
                    converted = [_calibration_row_from_db(row) for row in rows]
        except Exception as exc:
            self.mark_unavailable()
            raise RuntimeError(_postgres_error_message("calibration read", phase, exc)) from None
        self._mark_ok()
        return converted

    def fetch_feature_snapshot_validation_coverage(
        self,
        *,
        feature_methodology_version: str,
        timeframe: str | None,
        since: datetime | None,
        until: datetime | None,
        prediction_origin: str = DEFAULT_PREDICTION_ORIGIN,
    ) -> dict[str, Any]:
        prediction_origin = validate_prediction_origin(prediction_origin)
        try:
            with self._direct_connection() as conn:
                with conn.cursor() as cursor:
                    _execute_feature_snapshot_coverage_query(
                        cursor,
                        feature_methodology_version=feature_methodology_version,
                        timeframe=timeframe,
                        since=since,
                        until=until,
                        prediction_origin=prediction_origin,
                    )
                    row = cursor.fetchone()
        except Exception as exc:
            raise RuntimeError(
                _postgres_error_message("feature snapshot coverage read", "query", exc)
            ) from None
        return _validation_coverage_from_db(row)

    def fetch_feature_snapshot_validation_rows(
        self,
        *,
        feature_methodology_version: str,
        timeframe: str | None,
        since: datetime | None,
        until: datetime | None,
        limit: int,
        prediction_origin: str = DEFAULT_PREDICTION_ORIGIN,
    ) -> list[dict[str, Any]]:
        prediction_origin = validate_prediction_origin(prediction_origin)
        bounded_limit = _validation_limit(limit)
        try:
            with self._direct_connection() as conn:
                with conn.cursor() as cursor:
                    _execute_feature_snapshot_validation_query(
                        cursor,
                        feature_methodology_version=feature_methodology_version,
                        timeframe=timeframe,
                        since=since,
                        until=until,
                        limit=bounded_limit,
                        prediction_origin=prediction_origin,
                    )
                    rows = cursor.fetchall()
        except Exception as exc:
            raise RuntimeError(
                _postgres_error_message("feature snapshot validation read", "query", exc)
            ) from None
        return [_validation_row_from_db(row) for row in rows]

    def list_watchlist(self, operator_id: str = "operator") -> list[str]:
        status, rows = self._run_db(lambda cursor: _fetch_watchlist_rows(cursor, operator_id))
        if status == "UNAVAILABLE" or rows is None:
            return self._fallback.list_watchlist(operator_id)
        return [str(row[0]) for row in rows]

    def add_watchlist(self, symbol: str, operator_id: str = "operator") -> PersistenceStatus:
        self._fallback.add_watchlist(symbol, operator_id)
        status, _ = self._run_db(
            lambda cursor: cursor.execute(
                """
                INSERT INTO watchlist (operator_id, normalized_symbol, display_symbol)
                VALUES (%s, %s, %s)
                ON CONFLICT (operator_id, normalized_symbol) DO NOTHING
                """,
                (operator_id, symbol, symbol),
            )
        )
        return status

    def remove_watchlist(self, symbol: str, operator_id: str = "operator") -> PersistenceStatus:
        self._fallback.remove_watchlist(symbol, operator_id)
        status, _ = self._run_db(
            lambda cursor: cursor.execute(
                """
                DELETE FROM watchlist
                WHERE operator_id = %s AND normalized_symbol = %s
                """,
                (operator_id, symbol),
            )
        )
        return status

    def recent_runs(self, limit: int) -> list[dict]:
        status, rows = self._run_db(lambda cursor: _fetch_recent_runs(cursor, limit))
        if status == "UNAVAILABLE" or rows is None:
            return self._fallback.recent_runs(limit)
        return [
            {
                "run_id": row[0],
                "symbol": row[1],
                "normalized_symbol": row[2],
                "analysis_mode": row[3],
                "primary_timeframe": row[4],
                "disposition": row[5],
                "total_score": float(row[6]) if row[6] is not None else None,
                "data_source": row[7],
                "is_live_data": row[8],
                "analysis_hash": row[9],
                "as_of_utc": row[10].isoformat() if row[10] else None,
                "created_at": row[11].isoformat() if row[11] else None,
            }
            for row in rows
        ]

    def recent_runs_for_origin(
        self, limit: int, *, prediction_origin: str
    ) -> list[dict]:
        prediction_origin = validate_prediction_origin(prediction_origin)
        status, rows = self._run_db(
            lambda cursor: _fetch_recent_runs_for_origin(
                cursor, limit, prediction_origin=prediction_origin
            )
        )
        if status == "UNAVAILABLE" or rows is None:
            return self._fallback.recent_runs_for_origin(
                limit, prediction_origin=prediction_origin
            )
        return [
            {
                "run_id": row[0],
                "symbol": row[1],
                "normalized_symbol": row[2],
                "analysis_mode": row[3],
                "primary_timeframe": row[4],
                "disposition": row[5],
                "total_score": float(row[6]) if row[6] is not None else None,
                "data_source": row[7],
                "is_live_data": row[8],
                "analysis_hash": row[9],
                "as_of_utc": row[10].isoformat() if row[10] else None,
                "created_at": row[11].isoformat() if row[11] else None,
            }
            for row in rows
        ]

    def get_run(self, run_id: str) -> dict | None:
        status, row = self._run_db(lambda cursor: _fetch_run(cursor, run_id))
        if status == "UNAVAILABLE":
            return self._fallback.get_run(run_id)
        if row is None:
            return None
        return {
            "run_id": row[0],
            "symbol": row[1],
            "normalized_symbol": row[2],
            "analysis_mode": row[3],
            "primary_timeframe": row[4],
            "disposition": row[5],
            "total_score": float(row[6]) if row[6] is not None else None,
            "data_source": row[7],
            "is_live_data": row[8],
            "analysis_hash": row[9],
            "as_of_utc": row[10].isoformat() if row[10] else None,
            "created_at": row[11].isoformat() if row[11] else None,
        }

    def get_run_detail(
        self, run_id: str, *, prediction_origin: str
    ) -> dict | None:
        prediction_origin = validate_prediction_origin(prediction_origin)
        try:
            with self._connection() as conn:
                with conn.cursor() as cursor:
                    _set_local_statement_timeout(cursor, self._statement_timeout_ms)
                    row = _fetch_run_detail(
                        cursor, run_id, prediction_origin=prediction_origin
                    )
        except Exception:
            return None
        if row is None:
            return None
        detail_payload = row[2]
        if isinstance(detail_payload, str):
            detail_payload = json.loads(detail_payload)
        return dict(detail_payload) if isinstance(detail_payload, Mapping) else None

    def run_ids_with_detail(
        self, run_ids: Sequence[str], *, prediction_origin: str
    ) -> set[str]:
        prediction_origin = validate_prediction_origin(prediction_origin)
        candidate_ids = list(run_ids[:RUN_DETAIL_AVAILABILITY_LIMIT])
        if not candidate_ids:
            return set()
        try:
            with self._connection() as conn:
                with conn.cursor() as cursor:
                    _set_local_statement_timeout(cursor, self._statement_timeout_ms)
                    rows = _fetch_run_ids_with_detail(
                        cursor,
                        candidate_ids,
                        prediction_origin=prediction_origin,
                    )
        except Exception:
            return set()
        return {str(row[0]) for row in rows if row and row[0] is not None}


class SupabaseRestRepository:
    """Supabase PostgREST persistence adapter for HTTPS-only runtimes."""

    def __init__(
        self,
        supabase_url: str,
        service_role_key: str,
        *,
        timeout_seconds: float = 3.0,
        circuit_cooldown_seconds: float = 60.0,
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._base_url = f"{supabase_url.rstrip('/')}/rest/v1"
        self._service_role_key = service_role_key
        self._timeout_seconds = timeout_seconds
        self._circuit_cooldown_seconds = circuit_cooldown_seconds
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._owns_client = client is None
        self._clock = clock
        self._lock = threading.Lock()
        self._last_status: PersistenceStatus = "OK"
        self._circuit_open_until = 0.0
        self._trial_in_progress = False
        self._fallback = InMemoryPersistenceRepository()

    def persistence_status(self) -> PersistenceStatus:
        with self._lock:
            if self._last_status == "UNAVAILABLE" and self._clock() < self._circuit_open_until:
                return "UNAVAILABLE"
            return self._last_status

    def repository_type(self) -> str:
        return "SUPABASE_REST"

    def circuit_state(self) -> str:
        with self._lock:
            now = self._clock()
            if self._last_status != "UNAVAILABLE":
                return "CLOSED"
            if now < self._circuit_open_until:
                return "OPEN"
            return "HALF_OPEN"

    def maybe_can_attempt(self) -> bool:
        with self._lock:
            now = self._clock()
            if self._last_status != "UNAVAILABLE":
                return True
            if now < self._circuit_open_until:
                return False
            if self._trial_in_progress:
                return False
            self._trial_in_progress = True
            return True

    def mark_unavailable(self) -> PersistenceStatus:
        with self._lock:
            self._last_status = "UNAVAILABLE"
            self._circuit_open_until = self._clock() + self._circuit_cooldown_seconds
            self._trial_in_progress = False
        return self._last_status

    def _mark_ok(self) -> PersistenceStatus:
        with self._lock:
            self._last_status = "OK"
            self._circuit_open_until = 0.0
            self._trial_in_progress = False
        return self._last_status

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def save_run(self, summary: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_run(summary)
        status, _ = self._run_rest(
            lambda: self._request(
                "POST",
                "analysis_runs",
                json=dict(summary),
                params={"on_conflict": "run_id"},
                prefer="resolution=merge-duplicates,return=minimal",
            )
        )
        return status

    def save_run_detail(self, row: Mapping[str, Any]) -> PersistenceStatus:
        try:
            self._request(
                "POST",
                "analysis_run_details",
                json=dict(row),
                params={"on_conflict": "run_id"},
                prefer="resolution=merge-duplicates,return=minimal",
            )
        except Exception:
            return "UNAVAILABLE"
        return "OK"

    def save_timeframe_result(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_timeframe_result(row)
        status, _ = self._run_rest(
            lambda: self._request(
                "POST",
                "analysis_timeframe_results",
                json=dict(row),
                prefer="return=minimal",
            )
        )
        return status

    def save_provider_observation(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_provider_observation(row)
        status, _ = self._run_rest(
            lambda: self._request(
                "POST",
                "provider_observations",
                json=dict(row),
                prefer="return=minimal",
            )
        )
        return status

    def save_news_item(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_news_item(row)
        status, _ = self._run_rest(
            lambda: self._request(
                "POST",
                "news_items",
                json=dict(row),
                params={"on_conflict": "item_id"},
                prefer="resolution=merge-duplicates,return=minimal",
            )
        )
        return status

    def save_news_cluster(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_news_cluster(row)
        status, _ = self._run_rest(
            lambda: self._request(
                "POST",
                "news_clusters",
                json=dict(row),
                params={"on_conflict": "cluster_id"},
                prefer="resolution=merge-duplicates,return=minimal",
            )
        )
        return status

    def save_news_evidence_link(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_news_evidence_link(row)
        status, _ = self._run_rest(
            lambda: self._request(
                "POST",
                "news_evidence_links",
                json=dict(row),
                params={"on_conflict": "run_id,cluster_id,item_id"},
                prefer="resolution=merge-duplicates,return=minimal",
            )
        )
        return status

    def save_prediction(self, row: Mapping[str, Any]) -> PersistenceStatus:
        normalized_row = _prediction_row_with_origin(row)
        self._fallback.save_prediction(normalized_row)
        if _is_oos_arm_prediction_id(normalized_row.get("prediction_id")):
            return self._save_oos_prediction(normalized_row)
        status, _ = self._run_rest(
            lambda: self._request(
                "POST",
                "predictions",
                json=normalized_row,
                params={"on_conflict": "prediction_id"},
                prefer="resolution=ignore-duplicates,return=minimal",
            )
        )
        return status

    def _save_oos_prediction(self, row: Mapping[str, Any]) -> PersistenceStatus:
        if not self.maybe_can_attempt():
            raise OOSArmIdentityConflict("OOS arm prediction write could not be confirmed.")
        try:
            self._request(
                "POST",
                "predictions",
                json=dict(row),
                prefer="return=minimal",
            )
        except Exception as exc:
            self.mark_unavailable()
            raise OOSArmIdentityConflict(
                "OOS arm prediction identity clash or unconfirmed write."
            ) from exc
        self._mark_ok()
        return self.persistence_status()

    def save_feature_snapshot(
        self, row: Mapping[str, Any]
    ) -> FeatureSnapshotWriteStatus:
        status, inserted = self._run_rest(
            lambda: self._request(
                "POST",
                "prediction_feature_snapshots",
                json=dict(row),
                params={"on_conflict": "prediction_id"},
                prefer="resolution=ignore-duplicates,return=representation",
            )
        )
        if status == "UNAVAILABLE":
            return FeatureSnapshotWriteStatus.UNAVAILABLE
        if _rest_returned_inserted_snapshot(inserted):
            return FeatureSnapshotWriteStatus.INSERTED
        status, rows = self._run_rest(
            lambda: self._request(
                "GET",
                "prediction_feature_snapshots",
                params={
                    "select": "prediction_id,snapshot_hash",
                    "prediction_id": f"eq.{row.get('prediction_id', '')}",
                    "limit": "1",
                },
            )
        )
        if status == "UNAVAILABLE" or not isinstance(rows, list) or not rows:
            return FeatureSnapshotWriteStatus.UNAVAILABLE
        stored_hash = str(rows[0].get("snapshot_hash", ""))
        incoming_hash = str(row.get("snapshot_hash", ""))
        if stored_hash and stored_hash == incoming_hash:
            return FeatureSnapshotWriteStatus.IDENTICAL_DUPLICATE
        if stored_hash:
            return FeatureSnapshotWriteStatus.CONFLICT
        return FeatureSnapshotWriteStatus.UNAVAILABLE

    def save_derivatives_snapshot(
        self, row: Mapping[str, Any]
    ) -> DerivativesSnapshotWriteStatus:
        status, inserted = self._run_rest(
            lambda: self._request(
                "POST",
                "prediction_derivatives_snapshots",
                json=dict(row),
                params={"on_conflict": "prediction_id"},
                prefer="resolution=ignore-duplicates,return=representation",
            )
        )
        if status == "UNAVAILABLE":
            return DerivativesSnapshotWriteStatus.UNAVAILABLE
        if _rest_returned_inserted_snapshot(inserted):
            return DerivativesSnapshotWriteStatus.INSERTED
        status, rows = self._run_rest(
            lambda: self._request(
                "GET",
                "prediction_derivatives_snapshots",
                params={
                    "select": "prediction_id,snapshot_hash",
                    "prediction_id": f"eq.{row.get('prediction_id', '')}",
                    "limit": "1",
                },
            )
        )
        if status == "UNAVAILABLE" or not isinstance(rows, list) or not rows:
            return DerivativesSnapshotWriteStatus.UNAVAILABLE
        stored_hash = str(rows[0].get("snapshot_hash", ""))
        incoming_hash = str(row.get("snapshot_hash", ""))
        if stored_hash and stored_hash == incoming_hash:
            return DerivativesSnapshotWriteStatus.IDENTICAL_DUPLICATE
        if stored_hash:
            return DerivativesSnapshotWriteStatus.CONFLICT
        return DerivativesSnapshotWriteStatus.UNAVAILABLE

    def fetch_due_unresolved_predictions(self, now_utc: Any, limit: int) -> list[dict]:
        status, rows = self._run_rest(
            lambda: self._request(
                "GET",
                "predictions",
                params={
                    "select": (
                        "prediction_id,run_id,operator_id,symbol,normalized_symbol,timeframe,"
                        "horizon_bars,predicted_at_utc,reference_close_utc,reference_price,"
                        "horizon_end_utc,p_up_frac,p_down_frac,p_timeout_frac,"
                        "decision_band_frac,model_version,methodology_version,"
                        "calibration_status,reliability_status,epistemic_sufficiency,"
                        "gate_action,data_source,is_live_data,cross_provider_state"
                    ),
                    "horizon_end_utc": f"lt.{_iso_for_query(now_utc)}",
                    "is_live_data": "eq.true",
                    "order": "horizon_end_utc.asc",
                    "limit": str(limit),
                },
            )
        )
        if status == "UNAVAILABLE" or not isinstance(rows, list):
            return self._fallback.fetch_due_unresolved_predictions(now_utc, limit)
        prediction_ids = [str(row.get("prediction_id", "")) for row in rows]
        existing = self._fetch_existing_outcome_ids(prediction_ids)
        return [dict(row) for row in rows if str(row.get("prediction_id", "")) not in existing]

    def fetch_latest_oos_occasion(
        self, normalized_symbol: str, timeframe: str
    ) -> datetime | None:
        rows = self._required_oos_rows(
            params={
                "select": "run_id,reference_close_utc",
                "normalized_symbol": f"eq.{normalized_symbol}",
                "timeframe": f"eq.{timeframe}",
                "run_id": "like.oosb-*",
                "order": "reference_close_utc.desc",
            },
            label="latest OOS occasion",
        )
        closes = [
            _to_utc_datetime(row["reference_close_utc"])
            for row in rows
            if _is_oos_run_id(row.get("run_id")) and row.get("reference_close_utc")
        ]
        return max(closes, default=None)

    def oos_occasion_exists(
        self,
        normalized_symbol: str,
        timeframe: str,
        reference_close_utc: Any,
    ) -> bool:
        rows = self._required_oos_rows(
            params={
                "select": "run_id,reference_close_utc",
                "normalized_symbol": f"eq.{normalized_symbol}",
                "timeframe": f"eq.{timeframe}",
                "reference_close_utc": f"eq.{_iso_for_query(reference_close_utc)}",
                "run_id": "like.oosb-*",
            },
            label="OOS occasion existence",
        )
        return any(_is_oos_run_id(row.get("run_id")) for row in rows)

    def count_oos_occasion_rows(
        self,
        normalized_symbol: str,
        timeframe: str,
        reference_close_utc: Any,
    ) -> int:
        rows = self._required_oos_rows(
            params={
                "select": "run_id",
                "normalized_symbol": f"eq.{normalized_symbol}",
                "timeframe": f"eq.{timeframe}",
                "reference_close_utc": f"eq.{_iso_for_query(reference_close_utc)}",
                "run_id": "like.oosb-*",
            },
            label="OOS occasion count",
        )
        return sum(_is_oos_run_id(row.get("run_id")) for row in rows)

    def fetch_oos_t0(self) -> datetime | None:
        rows = self._required_oos_rows(
            params={
                "select": (
                    "prediction_id,run_id,normalized_symbol,timeframe,"
                    "reference_close_utc,methodology_version"
                ),
                "run_id": "like.oosb-*",
            },
            label="OOS T0",
        )
        return _oos_t0_from_rows(rows)

    def fetch_oos_paired_evidence(self, *, include_probabilities: bool) -> list[dict]:
        select = (
            "prediction_id,run_id,normalized_symbol,timeframe,reference_close_utc,"
            "predicted_at_utc,horizon_end_utc,prediction_origin,methodology_version"
        )
        if include_probabilities:
            select += "," + ",".join(OOS_PROBABILITY_FIELDS)
        rows = self._required_oos_rows(
            params={"select": select, "run_id": "like.oosb-*"},
            label="OOS paired evidence",
        )
        outcomes = self._fetch_oos_outcome_labels(
            [str(row.get("prediction_id", "")) for row in rows]
        )
        return _oos_paired_evidence_from_rows(
            rows, outcomes.get, include_probabilities=include_probabilities
        )

    def count_oos_origin_anomalies(self) -> int:
        rows = self._required_oos_rows(
            params={"select": "run_id,prediction_origin", "run_id": "like.oosb-*"},
            label="OOS origin anomalies",
        )
        return _oos_origin_anomalies_from_rows(rows)

    def fetch_oos_feature_diagnostics(self) -> list[dict]:
        rows = self._required_oos_rows(
            params={
                "select": (
                    "prediction_id,run_id,normalized_symbol,timeframe,reference_close_utc"
                ),
                "run_id": "like.oosb-*",
            },
            label="OOS feature diagnostics",
        )
        identifiers = [str(row.get("prediction_id", "")) for row in rows]
        status, snapshot_rows = self._run_rest(
            lambda: self._request(
                "GET",
                "prediction_feature_snapshots",
                params={
                    "select": "prediction_id,snapshot_payload",
                    "prediction_id": f"in.({_postgrest_csv(identifiers)})",
                },
            )
        )
        snapshots: dict[str, dict] = {}
        if status != "UNAVAILABLE" and isinstance(snapshot_rows, list):
            for row in snapshot_rows:
                if isinstance(row, Mapping) and row.get("prediction_id"):
                    snapshots[str(row["prediction_id"])] = dict(row)
        return _oos_feature_diagnostics_from_rows(rows, snapshots.get)

    def claim_section_5a_seal(self, payload: Mapping[str, Any]) -> bool:
        raise RuntimeError(_SEAL_POSTGRES_ONLY)

    def fetch_section_5a_seal(self) -> dict | None:
        raise RuntimeError(_SEAL_POSTGRES_ONLY)

    def advance_section_5a_seal_state(self, state: str, detail: str = "") -> None:
        raise RuntimeError(_SEAL_POSTGRES_ONLY)

    def capture_section_5a_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        raise RuntimeError(_SEAL_POSTGRES_ONLY)

    def section_5a_seal_authority(self) -> str:
        return "REST_NOT_A_SEAL_AUTHORITY"

    def _fetch_oos_outcome_labels(self, prediction_ids: list[str]) -> dict[str, dict]:
        identifiers = [identifier for identifier in prediction_ids if identifier]
        if not identifiers:
            return {}
        status, rows = self._run_rest(
            lambda: self._request(
                "GET",
                "prediction_outcomes",
                params={
                    "select": "prediction_id,realized_label",
                    "prediction_id": f"in.({_postgrest_csv(identifiers)})",
                },
            )
        )
        if status == "UNAVAILABLE" or not isinstance(rows, list):
            raise RuntimeError("SUPABASE_REST OOS outcome labels read failed")
        return {
            str(row["prediction_id"]): dict(row)
            for row in rows
            if isinstance(row, Mapping) and row.get("prediction_id")
        }

    def _required_oos_rows(
        self, *, params: Mapping[str, str], label: str
    ) -> list[dict]:
        status, rows = self._run_rest(
            lambda: self._request("GET", "predictions", params=dict(params))
        )
        if status == "UNAVAILABLE" or not isinstance(rows, list):
            raise RuntimeError(f"SUPABASE_REST {label} read failed")
        return [dict(row) for row in rows if isinstance(row, Mapping)]

    def save_prediction_outcome(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_prediction_outcome(row)
        status, _ = self._run_rest(
            lambda: self._request(
                "POST",
                "prediction_outcomes",
                json=dict(row),
                params={"on_conflict": "prediction_id"},
                prefer="resolution=ignore-duplicates,return=minimal",
            )
        )
        return status

    def fetch_resolved_prediction_outcomes_for_calibration(
        self,
        *,
        timeframe: str | None = None,
        symbol: str | None = None,
        normalized_symbol: str | None = None,
        model_version: str | None = None,
        methodology_version: str | None = None,
        since: Any | None = None,
        until: Any | None = None,
        limit: int | None = None,
        prediction_origin: str = DEFAULT_PREDICTION_ORIGIN,
    ) -> list[dict]:
        raise NotImplementedError("Supabase REST calibration read is not implemented.")

    def fetch_feature_snapshot_validation_coverage(
        self,
        *,
        feature_methodology_version: str,
        timeframe: str | None,
        since: datetime | None,
        until: datetime | None,
        prediction_origin: str = DEFAULT_PREDICTION_ORIGIN,
    ) -> dict[str, Any]:
        raise NotImplementedError("Supabase REST snapshot validation read is not implemented.")

    def fetch_feature_snapshot_validation_rows(
        self,
        *,
        feature_methodology_version: str,
        timeframe: str | None,
        since: datetime | None,
        until: datetime | None,
        limit: int,
        prediction_origin: str = DEFAULT_PREDICTION_ORIGIN,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("Supabase REST snapshot validation read is not implemented.")

    def list_watchlist(self, operator_id: str = "operator") -> list[str]:
        status, rows = self._run_rest(
            lambda: self._request(
                "GET",
                "watchlist",
                params={
                    "select": "display_symbol",
                    "operator_id": f"eq.{operator_id}",
                    "order": "created_at.asc",
                },
            )
        )
        if status == "UNAVAILABLE" or not isinstance(rows, list):
            return self._fallback.list_watchlist(operator_id)
        return [str(row["display_symbol"]) for row in rows if "display_symbol" in row]

    def add_watchlist(self, symbol: str, operator_id: str = "operator") -> PersistenceStatus:
        self._fallback.add_watchlist(symbol, operator_id)
        status, _ = self._run_rest(
            lambda: self._request(
                "POST",
                "watchlist",
                json={
                    "operator_id": operator_id,
                    "normalized_symbol": symbol,
                    "display_symbol": symbol,
                },
                params={"on_conflict": "operator_id,normalized_symbol"},
                prefer="resolution=merge-duplicates,return=minimal",
            )
        )
        return status

    def remove_watchlist(self, symbol: str, operator_id: str = "operator") -> PersistenceStatus:
        self._fallback.remove_watchlist(symbol, operator_id)
        status, _ = self._run_rest(
            lambda: self._request(
                "DELETE",
                "watchlist",
                params={
                    "operator_id": f"eq.{operator_id}",
                    "normalized_symbol": f"eq.{symbol}",
                },
                prefer="return=minimal",
            )
        )
        return status

    def recent_runs(self, limit: int) -> list[dict]:
        status, rows = self._run_rest(
            lambda: self._request(
                "GET",
                "analysis_runs",
                params={
                    "select": (
                        "run_id,symbol,normalized_symbol,analysis_mode,primary_timeframe,"
                        "disposition,total_score,data_source,is_live_data,analysis_hash,"
                        "as_of_utc,created_at"
                    ),
                    "order": "created_at.desc",
                    "limit": str(limit),
                },
            )
        )
        if status == "UNAVAILABLE" or not isinstance(rows, list):
            return self._fallback.recent_runs(limit)
        return [dict(row) for row in rows]

    def recent_runs_for_origin(
        self, limit: int, *, prediction_origin: str
    ) -> list[dict]:
        prediction_origin = validate_prediction_origin(prediction_origin)
        candidate_limit = min(max(limit * 5, limit), 500)
        status, candidates = self._run_rest(
            lambda: self._request(
                "GET",
                "analysis_runs",
                params={
                    "select": (
                        "run_id,symbol,normalized_symbol,analysis_mode,primary_timeframe,"
                        "disposition,total_score,data_source,is_live_data,analysis_hash,"
                        "as_of_utc,created_at"
                    ),
                    "order": "created_at.desc",
                    "limit": str(candidate_limit),
                },
            )
        )
        if status == "UNAVAILABLE" or not isinstance(candidates, list):
            return self._fallback.recent_runs_for_origin(
                limit, prediction_origin=prediction_origin
            )
        if not candidates:
            return []

        candidate_ids = [
            str(row["run_id"])
            for row in candidates
            if isinstance(row, Mapping) and row.get("run_id") is not None
        ]
        if not candidate_ids:
            return []
        escaped_ids = ",".join(
            _quote_postgrest_filter_value(run_id) for run_id in candidate_ids
        )
        status, predictions = self._run_rest(
            lambda: self._request(
                "GET",
                "predictions",
                params={
                    "select": "run_id",
                    "prediction_origin": f"eq.{prediction_origin}",
                    "run_id": f"in.({escaped_ids})",
                },
            )
        )
        if status == "UNAVAILABLE" or not isinstance(predictions, list):
            return self._fallback.recent_runs_for_origin(
                limit, prediction_origin=prediction_origin
            )
        matching_ids = {
            str(row["run_id"])
            for row in predictions
            if isinstance(row, Mapping) and row.get("run_id") is not None
        }
        # Bounded approximation: older matches outside the candidate window are omitted;
        # only runs proven to have a prediction of this origin can be returned.
        return [
            dict(row)
            for row in candidates
            if isinstance(row, Mapping) and str(row.get("run_id")) in matching_ids
        ][:limit]

    def get_run(self, run_id: str) -> dict | None:
        status, rows = self._run_rest(
            lambda: self._request(
                "GET",
                "analysis_runs",
                params={
                    "select": (
                        "run_id,symbol,normalized_symbol,analysis_mode,primary_timeframe,"
                        "disposition,total_score,data_source,is_live_data,analysis_hash,"
                        "as_of_utc,created_at"
                    ),
                    "run_id": f"eq.{run_id}",
                    "limit": "1",
                },
            )
        )
        if status == "UNAVAILABLE":
            return self._fallback.get_run(run_id)
        if not isinstance(rows, list) or not rows:
            return None
        return dict(rows[0])

    def get_run_detail(
        self, run_id: str, *, prediction_origin: str
    ) -> dict | None:
        prediction_origin = validate_prediction_origin(prediction_origin)
        try:
            predictions = self._request(
                "GET",
                "predictions",
                params={
                    "select": "run_id",
                    "run_id": f"eq.{run_id}",
                    "prediction_origin": f"eq.{prediction_origin}",
                    "limit": "1",
                },
            )
            if not isinstance(predictions, list) or not predictions:
                return None
            rows = self._request(
                "GET",
                "analysis_run_details",
                params={
                    "select": "run_id,analysis_hash,detail_payload,created_at",
                    "run_id": f"eq.{run_id}",
                    "limit": "1",
                },
            )
        except Exception:
            return None
        if not isinstance(rows, list) or not rows:
            return None
        detail_payload = rows[0].get("detail_payload")
        return dict(detail_payload) if isinstance(detail_payload, Mapping) else None

    def run_ids_with_detail(
        self, run_ids: Sequence[str], *, prediction_origin: str
    ) -> set[str]:
        prediction_origin = validate_prediction_origin(prediction_origin)
        candidate_ids = list(run_ids[:RUN_DETAIL_AVAILABILITY_LIMIT])
        if not candidate_ids:
            return set()
        escaped_ids = ",".join(
            _quote_postgrest_filter_value(run_id) for run_id in candidate_ids
        )
        try:
            predictions = self._request(
                "GET",
                "predictions",
                params={
                    "select": "run_id",
                    "run_id": f"in.({escaped_ids})",
                    "prediction_origin": f"eq.{prediction_origin}",
                },
            )
            if not isinstance(predictions, list):
                return set()
            matching_ids = {
                str(row["run_id"])
                for row in predictions
                if isinstance(row, Mapping) and row.get("run_id") is not None
            }
            predicted_ids = [
                run_id for run_id in candidate_ids if run_id in matching_ids
            ]
            if not predicted_ids:
                return set()
            escaped_predicted_ids = ",".join(
                _quote_postgrest_filter_value(run_id) for run_id in predicted_ids
            )
            details = self._request(
                "GET",
                "analysis_run_details",
                params={
                    "select": "run_id",
                    "run_id": f"in.({escaped_predicted_ids})",
                },
            )
        except Exception:
            return set()
        if not isinstance(details, list):
            return set()
        return {
            str(row["run_id"])
            for row in details
            if isinstance(row, Mapping) and row.get("run_id") is not None
        }

    def _run_rest(self, operation):
        if not self.maybe_can_attempt():
            return "UNAVAILABLE", None
        try:
            result = operation()
        except Exception:
            return self.mark_unavailable(), None
        return self._mark_ok(), result

    def _request(
        self,
        method: str,
        table: str,
        *,
        json: Mapping[str, Any] | None = None,
        params: Mapping[str, str] | None = None,
        prefer: str | None = None,
    ):
        headers = self._headers(prefer=prefer)
        response = self._client.request(
            method,
            f"{self._base_url}/{table}",
            headers=headers,
            params=dict(params or {}),
            json=dict(json) if json is not None else None,
            timeout=self._timeout_seconds,
        )
        if response.status_code not in {200, 201, 204}:
            raise RuntimeError("Supabase REST persistence request failed.")
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def _fetch_existing_outcome_ids(self, prediction_ids: list[str]) -> set[str]:
        prediction_ids = [prediction_id for prediction_id in prediction_ids if prediction_id]
        if not prediction_ids:
            return set()
        status, rows = self._run_rest(
            lambda: self._request(
                "GET",
                "prediction_outcomes",
                params={
                    "select": "prediction_id",
                    "prediction_id": f"in.({_postgrest_csv(prediction_ids)})",
                },
            )
        )
        if status == "UNAVAILABLE" or not isinstance(rows, list):
            return set()
        return {str(row.get("prediction_id")) for row in rows if row.get("prediction_id")}

    def _headers(self, *, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self._service_role_key,
            "Authorization": f"Bearer {self._service_role_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers


def _fetch_watchlist_rows(cursor, operator_id: str):
    cursor.execute(
        """
        SELECT display_symbol
        FROM watchlist
        WHERE operator_id = %s
        ORDER BY created_at ASC
        """,
        (operator_id,),
    )
    return cursor.fetchall()


def _fetch_recent_runs(cursor, limit: int):
    cursor.execute(
        """
        SELECT run_id, symbol, normalized_symbol, analysis_mode,
               primary_timeframe, disposition, total_score, data_source,
               is_live_data, analysis_hash, as_of_utc, created_at
        FROM analysis_runs
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return cursor.fetchall()


def _quote_postgrest_filter_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _fetch_recent_runs_for_origin(
    cursor, limit: int, *, prediction_origin: str
):
    cursor.execute(
        """
        SELECT run_id, symbol, normalized_symbol, analysis_mode,
               primary_timeframe, disposition, total_score, data_source,
               is_live_data, analysis_hash, as_of_utc, created_at
        FROM analysis_runs
        WHERE EXISTS (
            SELECT 1
            FROM predictions p
            WHERE p.run_id = analysis_runs.run_id
              AND p.prediction_origin = %s
        )
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (prediction_origin, limit),
    )
    return cursor.fetchall()


def _fetch_run(cursor, run_id: str):
    cursor.execute(
        """
        SELECT run_id, symbol, normalized_symbol, analysis_mode,
               primary_timeframe, disposition, total_score, data_source,
               is_live_data, analysis_hash, as_of_utc, created_at
        FROM analysis_runs
        WHERE run_id = %s
        """,
        (run_id,),
    )
    return cursor.fetchone()


def _fetch_run_detail(cursor, run_id: str, *, prediction_origin: str):
    cursor.execute(
        """
        SELECT d.run_id, d.analysis_hash, d.detail_payload, d.created_at
        FROM analysis_run_details d
        WHERE d.run_id = %s
          AND EXISTS (
              SELECT 1
              FROM predictions p
              WHERE p.run_id = d.run_id
                AND p.prediction_origin = %s
          )
        """,
        (run_id, prediction_origin),
    )
    return cursor.fetchone()


def _fetch_run_ids_with_detail(
    cursor, run_ids: Sequence[str], *, prediction_origin: str
):
    cursor.execute(
        """
        SELECT d.run_id
        FROM analysis_run_details d
        WHERE d.run_id = ANY(%s)
          AND EXISTS (
              SELECT 1
              FROM predictions p
              WHERE p.run_id = d.run_id
                AND p.prediction_origin = %s
          )
        """,
        (list(run_ids), prediction_origin),
    )
    return cursor.fetchall()


def _set_local_statement_timeout(cursor, timeout_ms: int) -> None:
    cursor.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")


def _fetch_latest_oos_occasion_row(
    cursor, normalized_symbol: str, timeframe: str
):
    cursor.execute(
        """
        SELECT max(reference_close_utc) AS reference_close_utc
        FROM public.predictions
        WHERE run_id ~ '^oosb-[0-9a-f]{32}$'
          AND normalized_symbol = %(normalized_symbol)s
          AND timeframe = %(timeframe)s
        """,
        {"normalized_symbol": normalized_symbol, "timeframe": timeframe},
    )
    return cursor.fetchone()


def _fetch_oos_occasion_existence_row(
    cursor,
    normalized_symbol: str,
    timeframe: str,
    reference_close_utc: Any,
):
    cursor.execute(
        """
        SELECT 1
        FROM public.predictions
        WHERE run_id ~ '^oosb-[0-9a-f]{32}$'
          AND normalized_symbol = %(normalized_symbol)s
          AND timeframe = %(timeframe)s
          AND reference_close_utc = %(reference_close_utc)s
        LIMIT 1
        """,
        {
            "normalized_symbol": normalized_symbol,
            "timeframe": timeframe,
            "reference_close_utc": reference_close_utc,
        },
    )
    return cursor.fetchone()


def _fetch_oos_occasion_count_row(
    cursor,
    normalized_symbol: str,
    timeframe: str,
    reference_close_utc: Any,
):
    cursor.execute(
        """
        SELECT count(*)
        FROM public.predictions
        WHERE run_id ~ '^oosb-[0-9a-f]{32}$'
          AND normalized_symbol = %(normalized_symbol)s
          AND timeframe = %(timeframe)s
          AND reference_close_utc = %(reference_close_utc)s
        """,
        {
            "normalized_symbol": normalized_symbol,
            "timeframe": timeframe,
            "reference_close_utc": reference_close_utc,
        },
    )
    return cursor.fetchone()


OOS_EVIDENCE_BASE_COLUMNS = (
    "prediction_id",
    "run_id",
    "normalized_symbol",
    "timeframe",
    "reference_close_utc",
    "predicted_at_utc",
    "horizon_end_utc",
    "prediction_origin",
    "methodology_version",
)


def _fetch_oos_prediction_rows(cursor, *, include_probabilities: bool) -> list[dict]:
    """Read every OOS-namespace prediction row, with or without probabilities.

    Columns are zipped against an explicit tuple rather than relying on a row factory,
    so the projection is identical whatever psycopg returns.
    """

    columns = list(OOS_EVIDENCE_BASE_COLUMNS)
    if include_probabilities:
        columns.extend(OOS_PROBABILITY_FIELDS)
    cursor.execute(
        f"""
        SELECT {", ".join(columns)}
        FROM public.predictions
        WHERE run_id ~ '^oosb-[0-9a-f]{{32}}$'
        ORDER BY prediction_id
        """
    )
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _fetch_oos_outcome_labels(cursor) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT o.prediction_id, o.realized_label
        FROM public.prediction_outcomes AS o
        JOIN public.predictions AS p ON p.prediction_id = o.prediction_id
        WHERE p.run_id ~ '^oosb-[0-9a-f]{32}$'
        ORDER BY o.prediction_id
        """
    )
    return {
        str(row[0]): {"realized_label": row[1]} for row in cursor.fetchall()
    }


def _fetch_oos_paired_evidence_rows(cursor, *, include_probabilities: bool) -> list[dict]:
    predictions = _fetch_oos_prediction_rows(
        cursor, include_probabilities=include_probabilities
    )
    outcomes = _fetch_oos_outcome_labels(cursor)
    return _oos_paired_evidence_from_rows(
        predictions, outcomes.get, include_probabilities=include_probabilities
    )


def _fetch_oos_origin_anomaly_row(cursor):
    cursor.execute(
        """
        SELECT count(*)
        FROM public.predictions
        WHERE run_id ~ '^oosb-[0-9a-f]{32}$'
          AND (prediction_origin IS DISTINCT FROM %(expected_origin)s)
        """,
        {"expected_origin": OOS_EXPECTED_ORIGIN},
    )
    return cursor.fetchone()


def _fetch_oos_feature_diagnostic_rows(cursor) -> list[dict]:
    cursor.execute(
        """
        SELECT p.prediction_id, p.normalized_symbol, p.timeframe,
               p.reference_close_utc, s.snapshot_payload
        FROM public.predictions AS p
        LEFT JOIN public.prediction_feature_snapshots AS s
               ON s.prediction_id = p.prediction_id
        WHERE p.run_id ~ '^oosb-[0-9a-f]{32}$'
        ORDER BY p.prediction_id
        """
    )
    predictions: list[dict] = []
    snapshots: dict[str, dict] = {}
    for prediction_id, symbol, timeframe, reference_close, payload in cursor.fetchall():
        identifier = str(prediction_id)
        predictions.append(
            {
                "prediction_id": identifier,
                "run_id": "oosb-" + "0" * 32,
                "normalized_symbol": symbol,
                "timeframe": timeframe,
                "reference_close_utc": reference_close,
            }
        )
        snapshots[identifier] = {"snapshot_payload": payload}
    return _oos_feature_diagnostics_from_rows(predictions, snapshots.get)


_SEAL_POSTGRES_ONLY = (
    "the section 5A one-look seal requires the Postgres authority; the REST fallback "
    "cannot provide an atomic durable claim and must never be used to spend the look"
)


SECTION_5A_SEAL_AUTHORITY_POSTGRES = "POSTGRES_DURABLE"
SECTION_5A_STATE_CLAIMED = "CLAIMED"


def _canonical_text(value: Any) -> str:
    """THE serializer for every section 5A JSON column (finding G9).

    The same encoder backs the evidence digest, so the seal can never refuse a value the digest
    accepted — the gap that let a timestamp-bearing snapshot pass the digest and then crash the
    claim.
    """

    return canonical_json.dumps(value).decode("utf-8")


def _decode_json_column(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray, memoryview)):
        value = bytes(value).decode("utf-8")
    if isinstance(value, str):
        return canonical_json.loads(value)
    return canonical_json.decode(value)


def _claim_section_5a_seal_row(cursor, payload: Mapping[str, Any]) -> bool:
    """Claim the one-look singleton. Runs BEFORE any probability is exposed (G1.1, G3).

    Always inserts state CLAIMED. Every JSON-bearing field is serialized with the canonical
    encoder, including a snapshot if a caller supplies one; the table's CHECK constraint is the
    authority that refuses evidence on a CLAIMED row, so claim-before-read cannot be bypassed by
    handing evidence to the claim.
    """

    snapshot = payload.get("snapshot_payload")
    run_provenance = payload.get("run_provenance")
    cursor.execute(
        """
        INSERT INTO public.section_5a_evaluation_seal (
          seal_id, sealed_at_utc, evaluator_pin_digest, contract_instants, run_provenance,
          state, evidence_snapshot_id, result_inputs_digest, snapshot_payload
        ) VALUES (
          'SINGLETON', %(sealed_at_utc)s, %(evaluator_pin_digest)s,
          %(contract_instants)s::jsonb, %(run_provenance)s::jsonb, 'CLAIMED',
          %(evidence_snapshot_id)s, %(result_inputs_digest)s, %(snapshot_payload)s::jsonb
        )
        ON CONFLICT (seal_id) DO NOTHING
        RETURNING seal_id
        """,
        {
            "sealed_at_utc": payload["sealed_at_utc"],
            "evaluator_pin_digest": payload["evaluator_pin_digest"],
            "contract_instants": _canonical_text(payload["contract_instants"]),
            # E2=A: NULL here is refused by the table (NOT NULL plus a CHECK on the record).
            "run_provenance": None if run_provenance is None else _canonical_text(run_provenance),
            "evidence_snapshot_id": payload.get("evidence_snapshot_id"),
            "result_inputs_digest": payload.get("result_inputs_digest"),
            "snapshot_payload": None if snapshot is None else _canonical_text(snapshot),
        },
    )
    return cursor.fetchone() is not None


def _fetch_oos_paired_evidence_for_consumption(cursor) -> list[dict]:
    """The ONLY Postgres path that returns probabilities: capture-before-exposure.

    In one transaction: lock the seal and require it CLAIMED and uncaptured; read the
    predictions and outcomes; write them verbatim, canonically encoded, into the seal's
    raw_evidence; and only then return. The caller receives probabilities strictly after they
    are durably captured, so there is no state in which the look was exposed but unrecorded. If
    anything fails, the transaction rolls back and nothing is returned.
    """

    cursor.execute(
        """
        SELECT state, raw_evidence IS NULL
        FROM public.section_5a_evaluation_seal
        WHERE seal_id = 'SINGLETON'
        FOR UPDATE
        """
    )
    seal = cursor.fetchone()
    if seal is None or seal[0] != SECTION_5A_STATE_CLAIMED or seal[1] is not True:
        raise RuntimeError(
            "section 5A probabilities may be read only under a CLAIMED, uncaptured seal"
        )
    predictions = _fetch_oos_prediction_rows(cursor, include_probabilities=True)
    outcomes = _fetch_oos_outcome_labels(cursor)
    cursor.execute(
        """
        UPDATE public.section_5a_evaluation_seal
        SET raw_evidence = %(raw_evidence)s::jsonb, updated_at_utc = now()
        WHERE seal_id = 'SINGLETON' AND state = 'CLAIMED' AND raw_evidence IS NULL
        RETURNING seal_id
        """,
        {"raw_evidence": _canonical_text({"predictions": predictions, "outcomes": outcomes})},
    )
    if cursor.fetchone() is None:
        raise RuntimeError("section 5A raw evidence capture did not land; nothing is returned")
    return _oos_paired_evidence_from_rows(predictions, outcomes.get, include_probabilities=True)


def _capture_section_5a_snapshot_row(cursor, snapshot: Mapping[str, Any]) -> bool:
    """Record the canonical snapshot and its digests, once, after the raw capture."""

    cursor.execute(
        """
        UPDATE public.section_5a_evaluation_seal
        SET snapshot_payload = %(snapshot_payload)s::jsonb,
            evidence_snapshot_id = %(evidence_snapshot_id)s,
            result_inputs_digest = %(result_inputs_digest)s,
            state = 'SEALED_RAW_CAPTURED',
            updated_at_utc = now()
        WHERE seal_id = 'SINGLETON'
          AND state = 'CLAIMED'
          AND raw_evidence IS NOT NULL
          AND snapshot_payload IS NULL
          AND evaluator_pin_digest = %(evaluator_pin_digest)s
        RETURNING seal_id
        """,
        {
            "snapshot_payload": _canonical_text(snapshot),
            "evidence_snapshot_id": snapshot["evidence_snapshot_id"],
            "result_inputs_digest": snapshot["result_inputs_digest"],
            "evaluator_pin_digest": snapshot["evaluator_pin_digest"],
        },
    )
    return cursor.fetchone() is not None


def _fetch_section_5a_seal_row(cursor):
    cursor.execute(
        """
        SELECT seal_id, sealed_at_utc, evidence_snapshot_id, result_inputs_digest,
               evaluator_pin_digest, contract_instants, run_provenance, snapshot_payload,
               raw_evidence, state, state_detail
        FROM public.section_5a_evaluation_seal
        WHERE seal_id = 'SINGLETON'
        """
    )
    row = cursor.fetchone()
    if row is None:
        return None
    columns = (
        "seal_id", "sealed_at_utc", "evidence_snapshot_id", "result_inputs_digest",
        "evaluator_pin_digest", "contract_instants", "run_provenance", "snapshot_payload",
        "raw_evidence", "state", "state_detail",
    )
    seal = dict(zip(columns, row, strict=True))
    for column in ("contract_instants", "run_provenance", "snapshot_payload", "raw_evidence"):
        seal[column] = _decode_json_column(seal[column])
    raw = seal.pop("raw_evidence")
    if isinstance(raw, Mapping):
        seal["captured_rows"] = _oos_paired_evidence_from_rows(
            raw.get("predictions", ()),
            dict(raw.get("outcomes", {})).get,
            include_probabilities=True,
        )
    return seal


def _advance_section_5a_seal_state_row(cursor, state: str, detail: str) -> bool:
    cursor.execute(
        """
        UPDATE public.section_5a_evaluation_seal
        SET state = %(state)s, state_detail = %(detail)s, updated_at_utc = now()
        WHERE seal_id = 'SINGLETON'
        RETURNING seal_id
        """,
        {"state": state, "detail": detail},
    )
    return cursor.fetchone() is not None


def _fetch_oos_t0_row(cursor):
    cursor.execute(
        """
        WITH qualifying_pairs AS (
          SELECT run_id, normalized_symbol, timeframe, reference_close_utc
          FROM public.predictions
          WHERE run_id ~ '^oosb-[0-9a-f]{32}$'
          GROUP BY run_id, normalized_symbol, timeframe, reference_close_utc
          HAVING count(*) = 2
             AND count(*) FILTER (
               WHERE right(prediction_id, 9) = ':BASELINE'
                 AND methodology_version = 'heuristic-v1-wave4b0'
             ) = 1
             AND count(*) FILTER (
               WHERE right(prediction_id, 10) = ':CANDIDATE'
                 AND methodology_version = 'distributional-v1'
             ) = 1
        )
        SELECT min(reference_close_utc) AS t0
        FROM qualifying_pairs
        """
    )
    return cursor.fetchone()


def _insert_prediction(
    cursor,
    row: Mapping[str, Any],
    *,
    reject_conflict: bool = False,
) -> None:
    conflict_clause = "" if reject_conflict else "ON CONFLICT (prediction_id) DO NOTHING"
    cursor.execute(
        f"""
        INSERT INTO predictions (
          prediction_id, run_id, operator_id, symbol, normalized_symbol,
          timeframe, horizon_bars, predicted_at_utc, reference_close_utc,
          reference_price, horizon_end_utc, p_up_frac, p_down_frac,
          p_timeout_frac, decision_band_frac, model_version, methodology_version,
          calibration_status, reliability_status, epistemic_sufficiency,
          gate_action, data_source, is_live_data, cross_provider_state,
          prediction_origin
        )
        VALUES (
          %(prediction_id)s, %(run_id)s, %(operator_id)s, %(symbol)s,
          %(normalized_symbol)s, %(timeframe)s, %(horizon_bars)s,
          %(predicted_at_utc)s, %(reference_close_utc)s, %(reference_price)s,
          %(horizon_end_utc)s, %(p_up_frac)s, %(p_down_frac)s,
          %(p_timeout_frac)s, %(decision_band_frac)s, %(model_version)s,
          %(methodology_version)s, %(calibration_status)s,
          %(reliability_status)s, %(epistemic_sufficiency)s, %(gate_action)s,
          %(data_source)s, %(is_live_data)s, %(cross_provider_state)s,
          %(prediction_origin)s
        )
        {conflict_clause}
        """,
        dict(row),
    )


def _insert_feature_snapshot(
    cursor, row: Mapping[str, Any]
) -> FeatureSnapshotWriteStatus:
    cursor.execute(
        """
        INSERT INTO public.prediction_feature_snapshots (
          prediction_id, run_id, symbol, normalized_symbol, timeframe,
          prediction_as_of_utc, reference_close_utc, quant_v2_schema_version,
          feature_methodology_version, influence_mode, no_lookahead_assertion,
          block_status, feature_count, degraded_count, provider_signature,
          snapshot_payload, snapshot_hash
        )
        VALUES (
          %(prediction_id)s, %(run_id)s, %(symbol)s, %(normalized_symbol)s,
          %(timeframe)s, %(prediction_as_of_utc)s, %(reference_close_utc)s,
          %(quant_v2_schema_version)s, %(feature_methodology_version)s,
          %(influence_mode)s, %(no_lookahead_assertion)s, %(block_status)s,
          %(feature_count)s, %(degraded_count)s, %(provider_signature)s,
          %(snapshot_payload)s::jsonb, %(snapshot_hash)s
        )
        ON CONFLICT (prediction_id) DO NOTHING
        RETURNING snapshot_hash
        """,
        dict(row),
    )
    inserted = cursor.fetchone()
    if inserted is not None:
        return FeatureSnapshotWriteStatus.INSERTED
    cursor.execute(
        """
        SELECT snapshot_hash
        FROM public.prediction_feature_snapshots
        WHERE prediction_id = %(prediction_id)s
        """,
        {"prediction_id": row.get("prediction_id")},
    )
    existing = cursor.fetchone()
    stored_hash = _snapshot_hash_from_db_row(existing)
    incoming_hash = str(row.get("snapshot_hash", ""))
    if stored_hash and stored_hash == incoming_hash:
        return FeatureSnapshotWriteStatus.IDENTICAL_DUPLICATE
    if stored_hash:
        return FeatureSnapshotWriteStatus.CONFLICT
    return FeatureSnapshotWriteStatus.UNAVAILABLE


def _insert_derivatives_snapshot(
    cursor, row: Mapping[str, Any]
) -> DerivativesSnapshotWriteStatus:
    cursor.execute(
        """
        INSERT INTO public.prediction_derivatives_snapshots (
          prediction_id, run_id, normalized_symbol, derivatives_schema_version,
          derivatives_methodology_version, influence_mode, decision_influence_frac,
          block_status, core_prediction_as_of_utc, observation_as_of_utc,
          snapshot_payload, snapshot_hash
        )
        VALUES (
          %(prediction_id)s, %(run_id)s, %(normalized_symbol)s,
          %(derivatives_schema_version)s, %(derivatives_methodology_version)s,
          %(influence_mode)s, %(decision_influence_frac)s, %(block_status)s,
          %(core_prediction_as_of_utc)s, %(observation_as_of_utc)s,
          %(snapshot_payload)s::jsonb, %(snapshot_hash)s
        )
        ON CONFLICT (prediction_id) DO NOTHING
        RETURNING snapshot_hash
        """,
        dict(row),
    )
    inserted = cursor.fetchone()
    if inserted is not None:
        return DerivativesSnapshotWriteStatus.INSERTED
    cursor.execute(
        """
        SELECT snapshot_hash
        FROM public.prediction_derivatives_snapshots
        WHERE prediction_id = %(prediction_id)s
        """,
        {"prediction_id": row.get("prediction_id")},
    )
    existing = cursor.fetchone()
    stored_hash = _snapshot_hash_from_db_row(existing)
    incoming_hash = str(row.get("snapshot_hash", ""))
    if stored_hash and stored_hash == incoming_hash:
        return DerivativesSnapshotWriteStatus.IDENTICAL_DUPLICATE
    if stored_hash:
        return DerivativesSnapshotWriteStatus.CONFLICT
    return DerivativesSnapshotWriteStatus.UNAVAILABLE


def _snapshot_hash_from_db_row(row: Any) -> str:
    if isinstance(row, Mapping):
        return str(row.get("snapshot_hash", ""))
    if isinstance(row, (tuple, list)) and row:
        return str(row[0])
    return ""


def _rest_returned_inserted_snapshot(value: Any) -> bool:
    if isinstance(value, Mapping):
        return bool(value.get("snapshot_hash"))
    return bool(
        isinstance(value, list)
        and value
        and isinstance(value[0], Mapping)
        and value[0].get("snapshot_hash")
    )


def _execute_due_prediction_query(cursor, now_utc: Any, limit: int) -> None:
    cursor.execute(
        """
        SELECT p.prediction_id, p.run_id, p.operator_id, p.symbol, p.normalized_symbol,
               p.timeframe, p.horizon_bars, p.predicted_at_utc, p.reference_close_utc,
               p.reference_price, p.horizon_end_utc, p.p_up_frac, p.p_down_frac,
               p.p_timeout_frac, p.decision_band_frac, p.model_version,
               p.methodology_version, p.calibration_status, p.reliability_status,
               p.epistemic_sufficiency, p.gate_action, p.data_source, p.is_live_data,
               p.cross_provider_state
        FROM public.predictions p
        LEFT JOIN public.prediction_outcomes o
          ON o.prediction_id = p.prediction_id
        WHERE o.prediction_id IS NULL
          AND p.is_live_data = true
          AND p.horizon_end_utc < %(now_utc)s
        ORDER BY p.horizon_end_utc ASC
        LIMIT %(limit)s
        """,
        {"now_utc": now_utc, "limit": limit},
    )


def _fetch_due_prediction_rows(cursor, now_utc: Any, limit: int):
    _execute_due_prediction_query(cursor, now_utc, limit)
    return cursor.fetchall()


def _prediction_row_from_db(row) -> dict:
    keys = (
        "prediction_id",
        "run_id",
        "operator_id",
        "symbol",
        "normalized_symbol",
        "timeframe",
        "horizon_bars",
        "predicted_at_utc",
        "reference_close_utc",
        "reference_price",
        "horizon_end_utc",
        "p_up_frac",
        "p_down_frac",
        "p_timeout_frac",
        "decision_band_frac",
        "model_version",
        "methodology_version",
        "calibration_status",
        "reliability_status",
        "epistemic_sufficiency",
        "gate_action",
        "data_source",
        "is_live_data",
        "cross_provider_state",
    )
    if isinstance(row, Mapping):
        return {
            key: value.isoformat() if hasattr(value, "isoformat") else value
            for key, value in row.items()
        }
    return {
        key: value.isoformat() if hasattr(value, "isoformat") else value
        for key, value in zip(keys, row, strict=True)
    }


def _execute_calibration_query(
    cursor,
    *,
    timeframe: str | None,
    symbol: str | None,
    normalized_symbol: str | None,
    model_version: str | None,
    methodology_version: str | None,
    since: Any | None,
    until: Any | None,
    limit: int | None,
    prediction_origin: str,
) -> None:
    clauses = [
        "p.is_live_data = true",
        "o.is_live_data = true",
        "o.realized_label IN ('UP', 'DOWN', 'TIMEOUT')",
        "coalesce(p.prediction_origin, 'USER_REQUESTED') = %(prediction_origin)s",
    ]
    params: dict[str, Any] = {"prediction_origin": prediction_origin}
    for key, value, column in (
        ("timeframe", timeframe, "p.timeframe"),
        ("symbol", symbol, "p.symbol"),
        ("normalized_symbol", normalized_symbol, "p.normalized_symbol"),
        ("model_version", model_version, "p.model_version"),
        ("methodology_version", methodology_version, "p.methodology_version"),
    ):
        if value is not None:
            clauses.append(f"{column} = %({key})s")
            params[key] = value
    if since is not None:
        clauses.append("o.outcome_close_utc >= %(since)s")
        params["since"] = since
    if until is not None:
        clauses.append("o.outcome_close_utc <= %(until)s")
        params["until"] = until
    limit_clause = ""
    if limit is not None:
        limit_clause = "\n        LIMIT %(limit)s"
        params["limit"] = max(0, int(limit))
    cursor.execute(
        f"""
        SELECT p.prediction_id, p.run_id, p.operator_id, p.symbol, p.normalized_symbol,
               p.timeframe, p.horizon_bars, p.predicted_at_utc, p.reference_close_utc,
               p.reference_price, p.horizon_end_utc, p.p_up_frac, p.p_down_frac,
               p.p_timeout_frac, p.decision_band_frac, p.model_version,
               p.methodology_version, p.calibration_status, p.reliability_status,
               p.epistemic_sufficiency, p.gate_action, p.data_source, p.is_live_data,
               p.cross_provider_state, o.resolved_at_utc, o.outcome_close_utc,
               o.outcome_reference_price, o.terminal_return_frac, o.realized_label,
               o.max_favorable_frac, o.max_adverse_frac, o.candles_observed,
               o.resolver_version, o.data_source, o.is_live_data
        FROM public.predictions p
        JOIN public.prediction_outcomes o
          ON o.prediction_id = p.prediction_id
        WHERE {" AND ".join(clauses)}
        ORDER BY o.outcome_close_utc ASC{limit_clause}
        """,
        params,
    )


def _calibration_row_from_db(row) -> dict:
    keys = _calibration_row_keys()
    if isinstance(row, Mapping):
        return {
            key: value.isoformat() if hasattr(value, "isoformat") else value
            for key, value in row.items()
        }
    return {
        key: value.isoformat() if hasattr(value, "isoformat") else value
        for key, value in zip(keys, row, strict=True)
    }


def _calibration_row_from_parts(prediction: Mapping[str, Any], outcome: Mapping[str, Any]) -> dict:
    return {
        "prediction_id": prediction.get("prediction_id"),
        "run_id": prediction.get("run_id"),
        "operator_id": prediction.get("operator_id"),
        "symbol": prediction.get("symbol"),
        "normalized_symbol": prediction.get("normalized_symbol"),
        "timeframe": prediction.get("timeframe"),
        "horizon_bars": prediction.get("horizon_bars"),
        "predicted_at_utc": prediction.get("predicted_at_utc"),
        "reference_close_utc": prediction.get("reference_close_utc"),
        "reference_price": prediction.get("reference_price"),
        "horizon_end_utc": prediction.get("horizon_end_utc"),
        "p_up_frac": prediction.get("p_up_frac"),
        "p_down_frac": prediction.get("p_down_frac"),
        "p_timeout_frac": prediction.get("p_timeout_frac"),
        "decision_band_frac": prediction.get("decision_band_frac"),
        "model_version": prediction.get("model_version"),
        "methodology_version": prediction.get("methodology_version"),
        "calibration_status": prediction.get("calibration_status"),
        "reliability_status": prediction.get("reliability_status"),
        "epistemic_sufficiency": prediction.get("epistemic_sufficiency"),
        "gate_action": prediction.get("gate_action"),
        "prediction_data_source": prediction.get("data_source"),
        "prediction_is_live_data": prediction.get("is_live_data"),
        "cross_provider_state": prediction.get("cross_provider_state"),
        "prediction_origin": prediction.get(
            "prediction_origin", DEFAULT_PREDICTION_ORIGIN
        ),
        "resolved_at_utc": outcome.get("resolved_at_utc"),
        "outcome_close_utc": outcome.get("outcome_close_utc"),
        "outcome_reference_price": outcome.get("outcome_reference_price"),
        "terminal_return_frac": outcome.get("terminal_return_frac"),
        "realized_label": outcome.get("realized_label"),
        "max_favorable_frac": outcome.get("max_favorable_frac"),
        "max_adverse_frac": outcome.get("max_adverse_frac"),
        "candles_observed": outcome.get("candles_observed"),
        "resolver_version": outcome.get("resolver_version"),
        "outcome_data_source": outcome.get("data_source"),
        "outcome_is_live_data": outcome.get("is_live_data"),
    }


def _calibration_row_keys() -> tuple[str, ...]:
    return (
        "prediction_id",
        "run_id",
        "operator_id",
        "symbol",
        "normalized_symbol",
        "timeframe",
        "horizon_bars",
        "predicted_at_utc",
        "reference_close_utc",
        "reference_price",
        "horizon_end_utc",
        "p_up_frac",
        "p_down_frac",
        "p_timeout_frac",
        "decision_band_frac",
        "model_version",
        "methodology_version",
        "calibration_status",
        "reliability_status",
        "epistemic_sufficiency",
        "gate_action",
        "prediction_data_source",
        "prediction_is_live_data",
        "cross_provider_state",
        "resolved_at_utc",
        "outcome_close_utc",
        "outcome_reference_price",
        "terminal_return_frac",
        "realized_label",
        "max_favorable_frac",
        "max_adverse_frac",
        "candles_observed",
        "resolver_version",
        "outcome_data_source",
        "outcome_is_live_data",
    )


def _calibration_row_matches(
    row: Mapping[str, Any],
    *,
    timeframe: str | None,
    symbol: str | None,
    normalized_symbol: str | None,
    model_version: str | None,
    methodology_version: str | None,
    prediction_origin: str,
    since: Any | None,
    until: Any | None,
) -> bool:
    if row.get("prediction_is_live_data") is not True:
        return False
    if row.get("outcome_is_live_data") is not True:
        return False
    if row.get("realized_label") not in {"UP", "DOWN", "TIMEOUT"}:
        return False
    if not _prediction_origin_matches(row, prediction_origin):
        return False
    for expected, key in (
        (timeframe, "timeframe"),
        (symbol, "symbol"),
        (normalized_symbol, "normalized_symbol"),
        (model_version, "model_version"),
        (methodology_version, "methodology_version"),
    ):
        if expected is not None and row.get(key) != expected:
            return False
    if since is not None and _timestamp_before(row.get("outcome_close_utc"), since):
        return False
    if until is not None and _timestamp_before(until, row.get("outcome_close_utc")):
        return False
    return True


_VALIDATION_ROW_KEYS = (
    "prediction_id",
    "run_id",
    "normalized_symbol",
    "symbol",
    "timeframe",
    "predicted_at_utc",
    "reference_close_utc",
    "horizon_end_utc",
    "horizon_bars",
    "p_up_frac",
    "p_down_frac",
    "p_timeout_frac",
    "model_version",
    "methodology_version",
    "prediction_is_live_data",
    "realized_label",
    "terminal_return_frac",
    "resolver_version",
    "outcome_is_live_data",
    "quant_v2_schema_version",
    "feature_methodology_version",
    "block_status",
    "no_lookahead_assertion",
    "provider_signature",
    "snapshot_payload",
)

_VALIDATION_COVERAGE_KEYS = (
    "live_predictions_all_time",
    "live_predictions_eligible_era",
    "snapshots_all_time",
    "snapshots_eligible_era",
    "resolved_outcomes_eligible_era",
    "snapshot_outcome_joins_eligible_era",
    "predictions_missing_snapshot_eligible_era",
    "snapshots_missing_outcome_eligible_era",
    "first_snapshot_as_of_utc",
    "latest_snapshot_as_of_utc",
)


def _execute_feature_snapshot_coverage_query(
    cursor,
    *,
    feature_methodology_version: str,
    timeframe: str | None,
    since: datetime | None,
    until: datetime | None,
    prediction_origin: str,
) -> None:
    cursor.execute(
        """
        WITH matching_snapshots AS (
          SELECT s.prediction_id, s.timeframe, s.prediction_as_of_utc
          FROM public.prediction_feature_snapshots s
          JOIN public.predictions p ON p.prediction_id = s.prediction_id
          WHERE s.feature_methodology_version = %(feature_methodology_version)s
            AND coalesce(p.prediction_origin, 'USER_REQUESTED') = %(prediction_origin)s
            AND (%(timeframe)s IS NULL OR s.timeframe = %(timeframe)s)
            AND (%(until)s IS NULL OR s.prediction_as_of_utc <= %(until)s)
        ),
        era AS (
          SELECT COALESCE(%(since)s, MIN(prediction_as_of_utc)) AS era_start
          FROM matching_snapshots
        ),
        live_predictions AS (
          SELECT p.prediction_id, p.predicted_at_utc
          FROM public.predictions p
          WHERE p.is_live_data = true
            AND coalesce(p.prediction_origin, 'USER_REQUESTED') = %(prediction_origin)s
            AND (%(timeframe)s IS NULL OR p.timeframe = %(timeframe)s)
            AND (%(until)s IS NULL OR p.predicted_at_utc <= %(until)s)
        ),
        eligible_predictions AS (
          SELECT p.prediction_id, p.predicted_at_utc
          FROM live_predictions p CROSS JOIN era
          WHERE era.era_start IS NOT NULL
            AND p.predicted_at_utc >= era.era_start
        ),
        eligible_snapshots AS (
          SELECT s.prediction_id, s.prediction_as_of_utc
          FROM matching_snapshots s CROSS JOIN era
          WHERE era.era_start IS NOT NULL
            AND s.prediction_as_of_utc >= era.era_start
        ),
        eligible_outcomes AS (
          SELECT p.prediction_id
          FROM eligible_predictions p
          JOIN public.prediction_outcomes o ON o.prediction_id = p.prediction_id
          WHERE o.is_live_data = true
            AND o.realized_label IN ('UP', 'DOWN', 'TIMEOUT')
        )
        SELECT
          (SELECT COUNT(*) FROM live_predictions) AS live_predictions_all_time,
          (SELECT COUNT(*) FROM eligible_predictions) AS live_predictions_eligible_era,
          (SELECT COUNT(*) FROM matching_snapshots) AS snapshots_all_time,
          (SELECT COUNT(*) FROM eligible_snapshots) AS snapshots_eligible_era,
          (SELECT COUNT(*) FROM eligible_outcomes) AS resolved_outcomes_eligible_era,
          (SELECT COUNT(*) FROM eligible_snapshots s
             JOIN eligible_outcomes o ON o.prediction_id = s.prediction_id)
            AS snapshot_outcome_joins_eligible_era,
          (SELECT COUNT(*) FROM eligible_predictions p
             LEFT JOIN eligible_snapshots s ON s.prediction_id = p.prediction_id
             WHERE s.prediction_id IS NULL)
            AS predictions_missing_snapshot_eligible_era,
          (SELECT COUNT(*) FROM eligible_snapshots s
             LEFT JOIN eligible_outcomes o ON o.prediction_id = s.prediction_id
             WHERE o.prediction_id IS NULL)
            AS snapshots_missing_outcome_eligible_era,
          (SELECT MIN(prediction_as_of_utc) FROM matching_snapshots)
            AS first_snapshot_as_of_utc,
          (SELECT MAX(prediction_as_of_utc) FROM matching_snapshots)
            AS latest_snapshot_as_of_utc
        """,
        {
            "feature_methodology_version": feature_methodology_version,
            "timeframe": timeframe,
            "since": since,
            "until": until,
            "prediction_origin": prediction_origin,
        },
    )


def _execute_feature_snapshot_validation_query(
    cursor,
    *,
    feature_methodology_version: str,
    timeframe: str | None,
    since: datetime | None,
    until: datetime | None,
    limit: int,
    prediction_origin: str,
) -> None:
    cursor.execute(
        """
        SELECT p.prediction_id, p.run_id, p.normalized_symbol, p.symbol,
               p.timeframe, p.predicted_at_utc, p.reference_close_utc,
               p.horizon_end_utc, p.horizon_bars, p.p_up_frac, p.p_down_frac,
               p.p_timeout_frac, p.model_version, p.methodology_version,
               p.is_live_data AS prediction_is_live_data, o.realized_label,
               o.terminal_return_frac, o.resolver_version,
               o.is_live_data AS outcome_is_live_data, s.quant_v2_schema_version,
               s.feature_methodology_version, s.block_status,
               s.no_lookahead_assertion, s.provider_signature, s.snapshot_payload
        FROM public.prediction_feature_snapshots s
        JOIN public.predictions p ON p.prediction_id = s.prediction_id
        JOIN public.prediction_outcomes o ON o.prediction_id = s.prediction_id
        WHERE p.is_live_data = true
          AND o.is_live_data = true
          AND o.realized_label IN ('UP', 'DOWN', 'TIMEOUT')
          AND s.feature_methodology_version = %(feature_methodology_version)s
          AND coalesce(p.prediction_origin, 'USER_REQUESTED') = %(prediction_origin)s
          AND (%(timeframe)s IS NULL OR p.timeframe = %(timeframe)s)
          AND (%(since)s IS NULL OR p.predicted_at_utc >= %(since)s)
          AND (%(until)s IS NULL OR p.predicted_at_utc <= %(until)s)
        ORDER BY p.predicted_at_utc ASC, p.prediction_id ASC
        LIMIT %(limit)s
        """,
        {
            "feature_methodology_version": feature_methodology_version,
            "timeframe": timeframe,
            "since": since,
            "until": until,
            "limit": _validation_limit(limit),
            "prediction_origin": prediction_origin,
        },
    )


def _validation_coverage_from_db(row: Any) -> dict[str, Any]:
    if row is None:
        return {key: None if key.endswith("_utc") else 0 for key in _VALIDATION_COVERAGE_KEYS}
    if isinstance(row, Mapping):
        values = {key: row.get(key) for key in _VALIDATION_COVERAGE_KEYS}
    else:
        values = dict(zip(_VALIDATION_COVERAGE_KEYS, row, strict=True))
    return {
        key: (
            value.isoformat() if value is not None and key.endswith("_utc") else value
        )
        for key, value in values.items()
    }


def _validation_row_from_db(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        values = {key: row.get(key) for key in _VALIDATION_ROW_KEYS}
    else:
        values = dict(zip(_VALIDATION_ROW_KEYS, row, strict=True))
    payload = values.get("snapshot_payload")
    if isinstance(payload, str):
        payload = json.loads(payload)
    values["snapshot_payload"] = deepcopy(payload)
    return {
        key: value.isoformat() if hasattr(value, "isoformat") else value
        for key, value in values.items()
    }


def _validation_row_from_parts(
    prediction: Mapping[str, Any],
    outcome: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "prediction_id": prediction.get("prediction_id"),
        "run_id": prediction.get("run_id"),
        "normalized_symbol": prediction.get("normalized_symbol"),
        "symbol": prediction.get("symbol"),
        "timeframe": prediction.get("timeframe"),
        "predicted_at_utc": prediction.get("predicted_at_utc"),
        "reference_close_utc": prediction.get("reference_close_utc"),
        "horizon_end_utc": prediction.get("horizon_end_utc"),
        "horizon_bars": prediction.get("horizon_bars"),
        "p_up_frac": prediction.get("p_up_frac"),
        "p_down_frac": prediction.get("p_down_frac"),
        "p_timeout_frac": prediction.get("p_timeout_frac"),
        "model_version": prediction.get("model_version"),
        "methodology_version": prediction.get("methodology_version"),
        "prediction_is_live_data": prediction.get("is_live_data"),
        "realized_label": outcome.get("realized_label"),
        "terminal_return_frac": outcome.get("terminal_return_frac"),
        "resolver_version": outcome.get("resolver_version"),
        "outcome_is_live_data": outcome.get("is_live_data"),
        "quant_v2_schema_version": snapshot.get("quant_v2_schema_version"),
        "feature_methodology_version": snapshot.get("feature_methodology_version"),
        "block_status": snapshot.get("block_status"),
        "no_lookahead_assertion": snapshot.get("no_lookahead_assertion"),
        "provider_signature": snapshot.get("provider_signature"),
        "snapshot_payload": deepcopy(snapshot.get("snapshot_payload")),
    }


def _prediction_row_with_origin(row: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["prediction_origin"] = validate_prediction_origin(
        row.get("prediction_origin", DEFAULT_PREDICTION_ORIGIN)
    )
    if _is_oos_arm_prediction_id(normalized.get("prediction_id")) and (
        normalized["prediction_origin"] != "SCHEDULED_SHADOW_EVIDENCE"
    ):
        raise ValueError("OOS arm predictions require shadow-evidence origin.")
    return normalized


def _is_oos_arm_prediction_id(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and re.fullmatch(
            r"oosb-[0-9a-f]{32}:(?:15m|1H|4H|1D|1W|1M):(BASELINE|CANDIDATE)",
            value,
        )
    )


def _is_oos_run_id(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and re.fullmatch(r"oosb-[0-9a-f]{32}", value)
    )


OOS_BASELINE_METHODOLOGY = "heuristic-v1-wave4b0"
OOS_CANDIDATE_METHODOLOGY = "distributional-v1"
OOS_PROBABILITY_FIELDS = ("p_up_frac", "p_down_frac", "p_timeout_frac")
OOS_EXPECTED_ORIGIN = "SCHEDULED_SHADOW_EVIDENCE"


def _oos_qualifying_pairs(rows) -> list[dict[str, Any]]:
    """Return every Tier-1 qualifying OOS pair (V1_QUANT_CONTRACT §5A.4).

    THIS IS THE SINGLE DEFINITION OF TIER-1 ELIGIBILITY.  ``fetch_oos_t0`` derives T0
    from it and the paired-evidence read analyses exactly the same population, so the
    analysed set can never drift from the set that fixed T0.  Do not add a second
    qualification rule anywhere.
    """

    groups: dict[tuple[object, object, object, object], list[Mapping[str, Any]]] = {}
    for raw_row in rows:
        if not isinstance(raw_row, Mapping) or not _is_oos_run_id(raw_row.get("run_id")):
            continue
        key = (
            raw_row.get("run_id"),
            raw_row.get("normalized_symbol"),
            raw_row.get("timeframe"),
            raw_row.get("reference_close_utc"),
        )
        groups.setdefault(key, []).append(raw_row)

    pairs: list[dict[str, Any]] = []
    for key, pair_rows in groups.items():
        if len(pair_rows) != 2 or key[3] is None:
            continue
        baseline = [
            row
            for row in pair_rows
            if _oos_arm(row) == "BASELINE"
            and row.get("methodology_version") == OOS_BASELINE_METHODOLOGY
        ]
        candidate = [
            row
            for row in pair_rows
            if _oos_arm(row) == "CANDIDATE"
            and row.get("methodology_version") == OOS_CANDIDATE_METHODOLOGY
        ]
        if len(baseline) != 1 or len(candidate) != 1:
            continue
        pairs.append(
            {
                "run_id": key[0],
                "normalized_symbol": key[1],
                "timeframe": key[2],
                "reference_close_utc": _to_utc_datetime(key[3]),
                "baseline": baseline[0],
                "candidate": candidate[0],
            }
        )
    return pairs


def _oos_paired_evidence_from_rows(
    prediction_rows,
    outcome_for,
    *,
    include_probabilities: bool,
) -> list[dict[str, Any]]:
    """Project Tier-1 pairs into flat evidence rows, in a deterministic order.

    ``include_probabilities`` is a STRUCTURAL SAFETY BOUNDARY, not a convenience.  When
    it is ``False`` no probability reaches the caller at all, so no Brier, ``d`` or ECE
    is computable from what a readiness run holds
    (``docs/SECTION_5A_EVALUATION_PREREGISTRATION.md`` §1).
    """

    evidence: list[dict[str, Any]] = []
    for pair in _oos_qualifying_pairs(prediction_rows):
        row: dict[str, Any] = {
            "run_id": pair["run_id"],
            "normalized_symbol": pair["normalized_symbol"],
            "timeframe": pair["timeframe"],
            "reference_close_utc": pair["reference_close_utc"],
        }
        for arm_name in ("baseline", "candidate"):
            arm_row = pair[arm_name]
            prediction_id = str(arm_row.get("prediction_id", ""))
            outcome = outcome_for(prediction_id)
            row[f"{arm_name}_prediction_id"] = prediction_id
            row[f"{arm_name}_predicted_at_utc"] = arm_row.get("predicted_at_utc")
            row[f"{arm_name}_horizon_end_utc"] = arm_row.get("horizon_end_utc")
            row[f"{arm_name}_prediction_origin"] = arm_row.get("prediction_origin")
            row[f"{arm_name}_realized_label"] = (
                outcome.get("realized_label") if isinstance(outcome, Mapping) else None
            )
            if include_probabilities:
                for field in OOS_PROBABILITY_FIELDS:
                    row[f"{arm_name}_{field}"] = arm_row.get(field)
        evidence.append(row)

    evidence.sort(
        key=lambda item: (
            str(item["timeframe"]),
            str(item["normalized_symbol"]),
            item["reference_close_utc"],
            str(item["run_id"]),
        )
    )
    return evidence


def _oos_origin_anomalies_from_rows(rows) -> int:
    """Count OOS-namespace rows whose origin is not the expected shadow origin.

    Reported, never filtered: none of the existing OOS queries predicates on origin, and
    adding one now would silently change the population that fixed T0
    (pre-registration §4.3).
    """

    return sum(
        1
        for row in rows
        if isinstance(row, Mapping)
        and _is_oos_run_id(row.get("run_id"))
        and row.get("prediction_origin") != OOS_EXPECTED_ORIGIN
    )


OOS_DIAGNOSTIC_FEATURES = {
    "regime": "quant_v2.regime_2state",
    "realized_vol": "quant_v2.realized_volatility",
    "trend_mtf": "quant_v2.trend_mtf",
    "volume_anomaly": "quant_v2.volume_anomaly",
}


def _oos_feature_diagnostics_from_rows(prediction_rows, snapshot_for) -> list[dict]:
    """Return the four persisted quant_v2 values per OOS prediction (§5A.10).

    Diagnostics only.  A missing feature yields ``None`` and never raises: a diagnostic
    must not be able to break, let alone gate, an evaluation.
    """

    diagnostics: list[dict[str, Any]] = []
    for row in prediction_rows:
        if not isinstance(row, Mapping) or not _is_oos_run_id(row.get("run_id")):
            continue
        prediction_id = str(row.get("prediction_id", ""))
        timeframe = row.get("timeframe")
        entry: dict[str, Any] = {
            "prediction_id": prediction_id,
            "normalized_symbol": row.get("normalized_symbol"),
            "timeframe": timeframe,
            "reference_close_utc": row.get("reference_close_utc"),
        }
        snapshot = snapshot_for(prediction_id)
        payload = snapshot.get("snapshot_payload") if isinstance(snapshot, Mapping) else None
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (TypeError, ValueError):
                payload = None
        features = payload.get("features") if isinstance(payload, Mapping) else None
        by_id: dict[str, Any] = {}
        if isinstance(features, list):
            for feature in features:
                if isinstance(feature, Mapping) and feature.get("feature_id") is not None:
                    by_id[str(feature["feature_id"])] = feature.get("raw_value")
        for name, prefix in OOS_DIAGNOSTIC_FEATURES.items():
            entry[name] = by_id.get(f"{prefix}:{timeframe}")
        diagnostics.append(entry)

    diagnostics.sort(key=lambda item: str(item["prediction_id"]))
    return diagnostics


def _oos_t0_from_rows(rows) -> datetime | None:
    return min(
        (pair["reference_close_utc"] for pair in _oos_qualifying_pairs(rows)),
        default=None,
    )


def _oos_arm(row: Mapping[str, Any]) -> str | None:
    """Derive the arm from the prediction_id suffix ONLY (finding G7).

    The Postgres qualifier can see nothing but prediction_id, so an arm read from any other
    field would let the in-memory and Postgres paths admit different populations — silently,
    and in exactly the rows that decide the answer. There is no second source of arm.
    """

    prediction_id = row.get("prediction_id")
    if isinstance(prediction_id, str):
        suffix = prediction_id.rsplit(":", maxsplit=1)[-1]
        if suffix in {"BASELINE", "CANDIDATE"}:
            return suffix
    return None


def _first_db_value(row: Any) -> Any:
    if isinstance(row, Mapping):
        return next(iter(row.values()), None)
    if isinstance(row, (tuple, list)):
        return row[0] if row else None
    return row


def _same_timestamp(left: Any, right: Any) -> bool:
    try:
        return _to_utc_datetime(left) == _to_utc_datetime(right)
    except (TypeError, ValueError):
        return False


def _prediction_origin_matches(
    row: Mapping[str, Any] | None,
    expected_origin: str,
) -> bool:
    if row is None:
        return False
    try:
        actual = validate_prediction_origin(
            row.get("prediction_origin", DEFAULT_PREDICTION_ORIGIN)
        )
    except ValueError:
        return False
    return actual == expected_origin


def _validation_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("Validation row limit must be a positive integer.")
    return min(limit, 50_000)


def _validation_live_outcome(row: Mapping[str, Any] | None) -> bool:
    return bool(
        row
        and row.get("is_live_data") is True
        and row.get("realized_label") in {"UP", "DOWN", "TIMEOUT"}
    )


def _validation_at_or_after(value: Any, lower: Any | None) -> bool:
    if lower is None:
        return False
    try:
        return _to_utc_datetime(value) >= _to_utc_datetime(lower)
    except (TypeError, ValueError):
        return False


def _validation_within_upper_bound(value: Any, upper: Any | None) -> bool:
    if upper is None:
        return True
    try:
        return _to_utc_datetime(value) <= _to_utc_datetime(upper)
    except (TypeError, ValueError):
        return False


def _validation_in_window(value: Any, lower: Any | None, upper: Any | None) -> bool:
    if lower is not None and not _validation_at_or_after(value, lower):
        return False
    return _validation_within_upper_bound(value, upper)


def _postgres_error_message(operation: str, phase: str, exc: Exception) -> str:
    message = _sanitize_postgres_error(str(exc))
    return f"SUPABASE_POSTGRES {operation} failed: {type(exc).__name__} [{phase}] {message}"


def _sanitize_postgres_error(message: str) -> str:
    compact = " ".join(str(message).split())
    compact = re.sub(r"(?i)\b(?:postgresql|postgres)://\S+", "<redacted-postgres-url>", compact)
    compact = re.sub(
        r"(?i)\b(password|apikey|authorization|bearer)\b\s*[:=]\s*\S+",
        r"\1=<redacted>",
        compact,
    )
    return (compact or "no detail")[:200]


def _iso_for_query(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _timestamp_before(left: Any, right: Any) -> bool:
    try:
        return _to_utc_datetime(left) < _to_utc_datetime(right)
    except (TypeError, ValueError):
        return False


def _to_utc_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise TypeError("Unsupported timestamp value.")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _postgrest_csv(values: list[str]) -> str:
    return ",".join(f'"{value}"' for value in values)


def build_persistence_repository(settings: Settings) -> PersistenceRepository:
    if settings.supabase_url and settings.supabase_service_role_key:
        return SupabaseRestRepository(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    if settings.supabase_db_url:
        return SupabasePersistenceRepository(settings.supabase_db_url)
    return InMemoryPersistenceRepository()


def build_operator_repository(settings: Settings) -> PersistenceRepository:
    """Build repository for operator/reporting jobs, preferring direct Postgres."""

    if settings.supabase_db_url:
        return SupabasePersistenceRepository(settings.supabase_db_url)
    if settings.supabase_url and settings.supabase_service_role_key:
        return SupabaseRestRepository(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    return InMemoryPersistenceRepository()
