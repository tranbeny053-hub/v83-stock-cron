"""One call of POST /v1/automation/radar-evidence, fail closed at every step.

Order: kill switch; human session refused; machine credential; strict request; ledger
reservation (idempotency: replay, conflict, in progress); quota; concurrency; the isolated
analysis under a server-side deadline; the pinned radar_evidence.v1 body; the ledger record.
Evidence is returned only after it is recorded; anything else is a catalogued error with no
partial evidence. The service never raises and never echoes a credential or a request field.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from concurrent.futures import Executor, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from crypto_probability_engine.api.analysis_service import analyze_request_isolated
from crypto_probability_engine.api.auth import DEV_SESSION_COOKIE, SESSION_COOKIE
from crypto_probability_engine.api.schemas import AnalysisMode, AnalysisRequest, AssetClass
from crypto_probability_engine.automation.config import (
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
    error_status,
    parse_request,
)
from crypto_probability_engine.automation.credentials import (
    CredentialRefusal,
    MachinePrincipal,
    authenticate,
)
from crypto_probability_engine.automation.ledger import (
    AutomationLedger,
    LedgerUnavailable,
    Outcome,
    ReservationKind,
)
from crypto_probability_engine.automation.quota import (
    CONCURRENCY_RETRY_AFTER_SECONDS,
    ConcurrencyGate,
    evaluate_quota,
)
from crypto_probability_engine.config.build_info import build_info_payload
from crypto_probability_engine.config.settings import Settings

HUMAN_SESSION_COOKIES = (SESSION_COOKIE, DEV_SESSION_COOKIE)
# Time kept back from the deadline to build, validate and record the body.
RESPONSE_MARGIN_SECONDS = 0.5
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
        analyzer: Callable[[RadarEvidenceRequest], dict[str, Any]] | None = None,
        config_loader: Callable[[], AutomationConfig] | None = None,
        clock: Callable[[], datetime] | None = None,
        build_info: Callable[[], dict[str, Any]] | None = None,
        executor: Executor | None = None,
        concurrency: ConcurrencyGate | None = None,
    ) -> None:
        self._ledger = ledger
        self._analyzer = analyzer or (lambda req: run_isolated_analysis(req, settings=settings))
        self._config_loader = config_loader or (lambda: load_config(os.environ))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._build_info = build_info or build_info_payload
        self._executor = executor or ThreadPoolExecutor(
            max_workers=MAX_CONCURRENT_ANALYSES, thread_name_prefix="ucpe-automation"
        )
        self._concurrency = concurrency or ConcurrencyGate(MAX_CONCURRENT_ANALYSES)

    def handle(
        self, *, credential: str | None, cookies: Mapping[str, str], body: bytes
    ) -> AutomationResult:
        try:
            return self._handle(credential=credential, cookies=cookies, body=body)
        except Exception:
            return _error(ErrorCode.ANALYSIS_FAILED)

    def _handle(
        self, *, credential: str | None, cookies: Mapping[str, str], body: bytes
    ) -> AutomationResult:
        config = self._config_loader()
        if not config.enabled:
            return _error(ErrorCode.AUTOMATION_DISABLED)
        if config.problems:
            return _error(ErrorCode.NOT_CONFIGURED)
        if any(name in cookies for name in HUMAN_SESSION_COOKIES):
            return _error(ErrorCode.HUMAN_SESSION_REFUSED)
        received = self._clock()
        principal = authenticate(credential, config.credentials, now=received)
        if principal is CredentialRefusal.MISSING:
            return _error(ErrorCode.CREDENTIAL_REQUIRED)
        if not isinstance(principal, MachinePrincipal):
            return _error(ErrorCode.CREDENTIAL_INVALID)
        try:
            request = parse_request(body)
        except ContractError as refusal:
            return _error(refusal.code)
        build_info = self._build_info()
        try:
            reservation = self._ledger.reserve(
                credential_id=principal.credential_id,
                client_request_id=request.client_request_id,
                request_fingerprint=request.fingerprint,
                release_id=str(build_info["release_id"]),
                deadline_ms=request.deadline_ms,
                now=received,
            )
        except LedgerUnavailable:
            return _error(ErrorCode.LEDGER_UNAVAILABLE)
        if reservation.kind is ReservationKind.CONFLICT:
            return _error(ErrorCode.IDEMPOTENCY_CONFLICT)
        if reservation.kind is ReservationKind.IN_PROGRESS:
            return _error(ErrorCode.REQUEST_IN_PROGRESS)
        if reservation.kind is ReservationKind.REPLAY:
            return _replay(reservation.entry)
        if reservation.kind is ReservationKind.ABANDONED:
            return self._finish(principal, request, ErrorCode.DEADLINE_EXCEEDED)
        quota = evaluate_quota(
            reservation, per_5min=config.quota_per_5min, per_day=config.quota_per_day, now=received
        )
        if not quota.allowed:
            return self._finish(
                principal, request, ErrorCode.QUOTA_EXCEEDED, quota.retry_after_seconds
            )
        if not self._concurrency.try_acquire():
            return self._finish(
                principal, request, ErrorCode.CONCURRENCY_LIMIT, CONCURRENCY_RETRY_AFTER_SECONDS
            )
        return self._analyze(principal, request, build_info, received)

    def _analyze(
        self,
        principal: MachinePrincipal,
        request: RadarEvidenceRequest,
        build_info: dict[str, Any],
        received: datetime,
    ) -> AutomationResult:
        deadline_seconds = request.deadline_ms / 1000
        remaining = deadline_seconds - _elapsed(received, self._clock()) - RESPONSE_MARGIN_SECONDS
        if remaining <= 0:
            self._concurrency.release()
            return self._finish(principal, request, ErrorCode.DEADLINE_EXCEEDED)
        try:
            future = self._executor.submit(self._analyzer, request)
        except Exception:
            self._concurrency.release()
            return self._finish(principal, request, ErrorCode.ANALYSIS_FAILED)
        # The slot is freed when the analysis thread really ends, not when the caller gives up.
        future.add_done_callback(lambda _future: self._concurrency.release())
        try:
            analysis = future.result(timeout=remaining)
        except FutureTimeout:
            return self._finish(principal, request, ErrorCode.DEADLINE_EXCEEDED)
        except Exception as exc:  # the analysis refused or failed: never partial evidence
            return self._finish(principal, request, _analysis_error(exc))
        issued = self._clock()
        if _elapsed(received, issued) > deadline_seconds:
            return self._finish(principal, request, ErrorCode.DEADLINE_EXCEEDED)
        try:
            evidence = build_radar_evidence(
                analysis,
                request=request,
                build_info=build_info,
                issued_at_utc=_iso(issued),
            )
        except ContractError as violation:
            return self._finish(principal, request, violation.code)
        try:
            self._ledger.complete(
                credential_id=principal.credential_id,
                client_request_id=request.client_request_id,
                outcome=Outcome(
                    outcome_code="SUCCEEDED",
                    http_status=200,
                    response_body=evidence,
                    run_id=evidence["run_id"],
                    analysis_hash=evidence["analysis_hash"],
                    evidence_hash=evidence["evidence_hash"],
                ),
                now=issued,
            )
        except LedgerUnavailable:
            return _error(ErrorCode.LEDGER_UNAVAILABLE)
        return AutomationResult(200, evidence, {"Cache-Control": "no-store"})

    def _finish(
        self,
        principal: MachinePrincipal,
        request: RadarEvidenceRequest,
        code: ErrorCode,
        retry_after_seconds: int | None = None,
    ) -> AutomationResult:
        """Record a refusal against the reserved key, then answer it."""

        body = error_body(code, retry_after_seconds)
        try:
            self._ledger.complete(
                credential_id=principal.credential_id,
                client_request_id=request.client_request_id,
                outcome=Outcome(
                    outcome_code=code.value, http_status=error_status(code), response_body=body
                ),
                now=self._clock(),
            )
        except LedgerUnavailable:
            return _error(ErrorCode.LEDGER_UNAVAILABLE)
        return _error(code, retry_after_seconds)


def _error(code: ErrorCode, retry_after_seconds: int | None = None) -> AutomationResult:
    headers = {"Cache-Control": "no-store"}
    if retry_after_seconds is not None:
        headers["Retry-After"] = str(retry_after_seconds)
    return AutomationResult(error_status(code), error_body(code, retry_after_seconds), headers)


def _replay(entry: Any) -> AutomationResult:
    body = entry.response_body if entry is not None else None
    status = entry.http_status if entry is not None else None
    if not isinstance(body, dict) or not isinstance(status, int):
        return _error(ErrorCode.LEDGER_UNAVAILABLE)
    headers = {"Cache-Control": "no-store", "Idempotent-Replay": "true"}
    retry_after = (body.get("error") or {}).get("retry_after_seconds") if status != 200 else None
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


def _elapsed(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds()


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
