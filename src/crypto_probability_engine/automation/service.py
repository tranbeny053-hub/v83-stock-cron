"""One call of POST /v1/automation/radar-evidence, fail closed at every step.

Order: kill switch; human session refused; machine credential (read from the database registry on
every call, so a rotation or revocation applies to the next request); strict request; ledger
reservation (idempotency: replay, conflict, in progress; the capacity contract: a full ledger or a
credential past its rolling-day row ceiling refuses a NEW key without recording it); quota;
concurrency; the isolated analysis; the pinned radar_evidence.v1 body, never stored above
``LEDGER_MAX_BODY_BYTES``; the ledger record. The service never raises and never
echoes a credential or a request field.

The deadline is a MONOTONIC budget of ``deadline_ms`` from the moment the request arrived at the
route (before its body was read). The analysis may use it up to ``RECORD_RESERVE_SECONDS`` before
its end; the success is then recorded only if the database clock is still within the deadline
(the ledger checks it inside the recording transaction), and otherwise recorded and answered as
DEADLINE_EXCEEDED. Evidence is returned only after its on-time record commits, so the ledger always
says what the caller was told; network transit after the commit is outside the budget.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from concurrent.futures import Executor, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from crypto_probability_engine.api.analysis_service import analyze_request_isolated
from crypto_probability_engine.api.auth import DEV_SESSION_COOKIE, SESSION_COOKIE
from crypto_probability_engine.api.schemas import AnalysisMode, AnalysisRequest, AssetClass
from crypto_probability_engine.automation.config import (
    LEDGER_MAX_BODY_BYTES,
    LEDGER_ROWS_PER_QUOTA_UNIT,
    MAX_CONCURRENT_ANALYSES,
    AutomationConfig,
    load_config,
)
from crypto_probability_engine.automation.contract import (
    ContractError,
    ErrorCode,
    RadarEvidenceRequest,
    build_radar_evidence,
    error_body,
    error_body_valid,
    error_status,
    parse_request,
    radar_evidence_valid,
    render,
)
from crypto_probability_engine.automation.credentials import (
    CredentialRefusal,
    CredentialRegistry,
    MachinePrincipal,
    RegistryUnavailable,
    authenticate,
)
from crypto_probability_engine.automation.ledger import (
    AutomationLedger,
    LedgerEntry,
    LedgerUnavailable,
    Outcome,
    ReservationKind,
)
from crypto_probability_engine.automation.quota import (
    CONCURRENCY_RETRY_AFTER_SECONDS,
    ConcurrencyGate,
    evaluate_quota,
    throttle_retry_after,
)
from crypto_probability_engine.config.build_info import build_info_payload
from crypto_probability_engine.config.settings import Settings

HUMAN_SESSION_COOKIES = (SESSION_COOKIE, DEV_SESSION_COOKIE)
# Budget kept back from the deadline to build, validate and record the body.
RECORD_RESERVE_SECONDS = 1.0
# Below this much budget left, a success is not even attempted: it is recorded as late.
MIN_RECORD_SECONDS = 0.1
_UPSTREAM_CODES = frozenset(
    {
        "PROVIDER_DEGRADED",
        "DATA_CONFLICT",
        "STALE_CANDLES",
        "INSUFFICIENT_DATA",
        "EXCHANGE_HEALTH_BLOCK",
        "SHELTER_MODE_BLOCK",
    }
)


@dataclass(frozen=True)
class AutomationResult:
    status: int
    body: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class _Call:
    principal: MachinePrincipal
    request: RadarEvidenceRequest
    received_utc: datetime
    budget_end: float  # monotonic seconds
    deadline_at_utc: datetime


def run_isolated_analysis(request: RadarEvidenceRequest, *, settings: Settings) -> dict[str, Any]:
    """The analysis behind one radar-evidence call: METRICS_ONLY spot, fully isolated."""

    return analyze_request_isolated(
        AnalysisRequest(
            symbol=request.symbol,
            timeframe=request.primary_timeframe,
            analysis_mode=AnalysisMode.METRICS_ONLY,
            asset_class=AssetClass.CRYPTO_SPOT,
        ),
        settings=settings,
    )


class RadarEvidenceService:
    def __init__(
        self,
        *,
        settings: Settings,
        ledger: AutomationLedger,
        registry: CredentialRegistry,
        analyzer: Callable[[RadarEvidenceRequest], dict[str, Any]] | None = None,
        config_loader: Callable[[], AutomationConfig] | None = None,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
        build_info: Callable[[], dict[str, Any]] | None = None,
        executor: Executor | None = None,
        concurrency: ConcurrencyGate | None = None,
    ) -> None:
        self._ledger = ledger
        self._registry = registry
        self._analyzer = analyzer or (lambda req: run_isolated_analysis(req, settings=settings))
        self._config_loader = config_loader or (lambda: load_config(os.environ))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._monotonic = monotonic or time.monotonic
        self._build_info = build_info or build_info_payload
        self._executor = executor or ThreadPoolExecutor(
            max_workers=MAX_CONCURRENT_ANALYSES, thread_name_prefix="ucpe-automation"
        )
        self._concurrency = concurrency or ConcurrencyGate(MAX_CONCURRENT_ANALYSES)

    def monotonic_now(self) -> float:
        """The service's own monotonic clock: the route stamps a request's arrival with it."""

        return self._monotonic()

    def handle(
        self,
        *,
        credential: str | None,
        cookies: Mapping[str, str],
        body: bytes,
        arrived_monotonic: float | None = None,
    ) -> AutomationResult:
        try:
            arrived = self._monotonic() if arrived_monotonic is None else arrived_monotonic
            return self._handle(credential=credential, cookies=cookies, body=body, arrived=arrived)
        except Exception:
            return _error(ErrorCode.ANALYSIS_FAILED)

    def _handle(
        self, *, credential: str | None, cookies: Mapping[str, str], body: bytes, arrived: float
    ) -> AutomationResult:
        config = self._config_loader()
        if not config.enabled:
            return _error(ErrorCode.AUTOMATION_DISABLED)
        if config.problems:
            return _error(ErrorCode.NOT_CONFIGURED)
        if any(name in cookies for name in HUMAN_SESSION_COOKIES):
            return _error(ErrorCode.HUMAN_SESSION_REFUSED)
        received = self._clock()
        try:
            principal = authenticate(credential, self._registry, now=received)
        except RegistryUnavailable:  # the registry lives in the ledger's database: fail closed
            return _error(ErrorCode.LEDGER_UNAVAILABLE)
        if principal is CredentialRefusal.MISSING:
            return _error(ErrorCode.CREDENTIAL_REQUIRED)
        if not isinstance(principal, MachinePrincipal):
            return _error(ErrorCode.CREDENTIAL_INVALID)
        try:
            request = parse_request(body)
        except ContractError as refusal:
            return _error(refusal.code)
        budget_end = arrived + request.deadline_ms / 1000
        call = _Call(
            principal=principal,
            request=request,
            received_utc=received,
            budget_end=budget_end,
            deadline_at_utc=received + timedelta(seconds=budget_end - self._monotonic()),
        )
        build_info = self._build_info()
        try:
            reservation = self._ledger.reserve(
                credential_id=principal.credential_id,
                client_request_id=request.client_request_id,
                request_fingerprint=request.fingerprint,
                release_id=str(build_info["release_id"]),
                deadline_ms=request.deadline_ms,
                now=received,
                max_rows_per_day=LEDGER_ROWS_PER_QUOTA_UNIT * config.quota_per_day,
            )
        except LedgerUnavailable:
            return _error(ErrorCode.LEDGER_UNAVAILABLE)
        if reservation.kind is ReservationKind.FULL:  # the capacity contract: nothing was written
            return _error(ErrorCode.LEDGER_UNAVAILABLE)
        if reservation.kind is ReservationKind.THROTTLED:  # nothing was written
            return _error(ErrorCode.QUOTA_EXCEEDED, throttle_retry_after(reservation, received))
        if reservation.kind is ReservationKind.CONFLICT:
            return _error(ErrorCode.IDEMPOTENCY_CONFLICT)
        if reservation.kind is ReservationKind.IN_PROGRESS:
            return _error(ErrorCode.REQUEST_IN_PROGRESS)
        if reservation.kind is ReservationKind.REPLAY:
            return _replay(reservation.entry)
        if reservation.kind is ReservationKind.ABANDONED:
            return self._finish(call, ErrorCode.DEADLINE_EXCEEDED)
        quota = evaluate_quota(
            reservation, per_5min=config.quota_per_5min, per_day=config.quota_per_day, now=received
        )
        if not quota.allowed:
            return self._finish(call, ErrorCode.QUOTA_EXCEEDED, quota.retry_after_seconds)
        if not self._concurrency.try_acquire():
            return self._finish(call, ErrorCode.CONCURRENCY_LIMIT, CONCURRENCY_RETRY_AFTER_SECONDS)
        return self._analyze(call, build_info)

    def _analyze(self, call: _Call, build_info: dict[str, Any]) -> AutomationResult:
        remaining = call.budget_end - self._monotonic() - RECORD_RESERVE_SECONDS
        if remaining <= 0:
            self._concurrency.release()
            return self._finish(call, ErrorCode.DEADLINE_EXCEEDED)
        try:
            future = self._executor.submit(self._analyzer, call.request)
        except Exception:
            self._concurrency.release()
            return self._finish(call, ErrorCode.ANALYSIS_FAILED)
        # The slot is freed when the analysis thread really ends, not when the caller gives up.
        future.add_done_callback(lambda _future: self._concurrency.release())
        try:
            analysis = future.result(timeout=remaining)
        except FutureTimeout:
            return self._finish(call, ErrorCode.DEADLINE_EXCEEDED)
        except Exception as exc:  # the analysis refused or failed: never partial evidence
            return self._finish(call, _analysis_error(exc))
        try:
            evidence = build_radar_evidence(
                analysis,
                request=call.request,
                build_info=build_info,
                issued_at_utc=_iso(self._clock()),
            )
        except ContractError as refusal:
            return self._finish(call, refusal.code)
        if len(render(evidence)) > LEDGER_MAX_BODY_BYTES:  # the capacity contract: never stored
            return self._finish(call, ErrorCode.CONTRACT_VIOLATION)
        record_budget = call.budget_end - self._monotonic()
        if record_budget < MIN_RECORD_SECONDS:
            return self._finish(call, ErrorCode.DEADLINE_EXCEEDED)
        late = error_body(ErrorCode.DEADLINE_EXCEEDED)
        try:
            on_time = self._ledger.complete_success(
                credential_id=call.principal.credential_id,
                client_request_id=call.request.client_request_id,
                outcome=Outcome(
                    outcome_code="SUCCEEDED",
                    http_status=200,
                    response_body=evidence,
                    run_id=evidence["run_id"],
                    analysis_hash=evidence["analysis_hash"],
                    evidence_hash=evidence["evidence_hash"],
                ),
                late_outcome=Outcome(
                    outcome_code=ErrorCode.DEADLINE_EXCEEDED.value,
                    http_status=error_status(ErrorCode.DEADLINE_EXCEEDED),
                    response_body=late,
                ),
                deadline_at_utc=call.deadline_at_utc,
                now=self._clock(),
                timeout_seconds=record_budget,
            )
        except LedgerUnavailable:
            return _error(ErrorCode.LEDGER_UNAVAILABLE)
        if not on_time:
            return _error(ErrorCode.DEADLINE_EXCEEDED)
        return AutomationResult(200, evidence, {"Cache-Control": "no-store"})

    def _finish(
        self, call: _Call, code: ErrorCode, retry_after_seconds: int | None = None
    ) -> AutomationResult:
        """Record a refusal against the reserved key, then answer it."""

        body = error_body(code, retry_after_seconds)
        try:
            self._ledger.complete(
                credential_id=call.principal.credential_id,
                client_request_id=call.request.client_request_id,
                outcome=Outcome(
                    outcome_code=code.value, http_status=error_status(code), response_body=body
                ),
                now=self._clock(),
            )
        except LedgerUnavailable:
            return _error(ErrorCode.LEDGER_UNAVAILABLE)
        return _error(code, retry_after_seconds)


def _error(code: ErrorCode, retry_after_seconds: int | None = None) -> AutomationResult:
    body = error_body(code, retry_after_seconds)
    if not error_body_valid(body):  # a fixed catalogue: never expected, but never sent unchecked
        body = error_body(ErrorCode.ANALYSIS_FAILED)
        code, retry_after_seconds = ErrorCode.ANALYSIS_FAILED, None
    headers = {"Cache-Control": "no-store"}
    if retry_after_seconds is not None:
        headers["Retry-After"] = str(retry_after_seconds)
    return AutomationResult(error_status(code), body, headers)


def _replay(entry: LedgerEntry | None) -> AutomationResult:
    """The stored outcome, re-validated against its schema before it is sent again."""

    body = entry.response_body if entry is not None else None
    status = entry.http_status if entry is not None else None
    if not isinstance(body, dict) or not isinstance(status, int):
        return _error(ErrorCode.LEDGER_UNAVAILABLE)
    valid = radar_evidence_valid(body) if status == 200 else error_body_valid(body)
    if not valid:
        return _error(ErrorCode.LEDGER_UNAVAILABLE)
    headers = {"Cache-Control": "no-store", "Idempotent-Replay": "true"}
    retry_after = body["error"]["retry_after_seconds"] if status != 200 else None
    if isinstance(retry_after, int):
        headers["Retry-After"] = str(retry_after)
    return AutomationResult(status, body, headers)


def _analysis_error(exc: Exception) -> ErrorCode:
    detail = getattr(exc, "detail", None)
    code = None
    if isinstance(detail, dict):
        code = (detail.get("error") or {}).get("code")
    code = getattr(code, "value", code)
    if code == "INVALID_SYMBOL":
        return ErrorCode.UNSUPPORTED_SYMBOL
    if code in _UPSTREAM_CODES:
        return ErrorCode.UPSTREAM_UNAVAILABLE
    return ErrorCode.ANALYSIS_FAILED


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
