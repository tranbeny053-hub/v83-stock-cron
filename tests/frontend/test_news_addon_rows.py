"""A run with news analysis on, live and reopened: the News Add-on "State" row and the News
Authority "Provider status" row (the release-prep review's minors MINOR-A and MINOR-B).

No golden pins such a run: every whole-screen scenario is METRICS_ONLY. These are pinned here, over
the real backend's own answers (the app, through its test client, in fixture mode, with news
providers that answer without the network) rendered by the real app.js on the DOM stand-in:
- live: the analysis as POST /v1/analyze answers it, beside its detail (GET /v1/analyze/detail);
- reopened from this process: the row GET /v1/runs lists, beside the detail the route answers;
- reopened from a durable store: a stand-in serving what a save writes (sanitize_for_export of the
  run's detail view, analysis_service.schedule_best_effort_persist) after a JSON round trip, read
  through the same two routes by an app that does not hold the run.

MINOR-A. A reopened run's history row carries no news add-on state, so its "State" row read
"UNAVAILABLE" while the same screen shows the stored state's status. It now reads that status: the
state detail/builder.py stores is the analysis's own `news_addon_state`, the object the live row
reads, and utils/sanitize.py leaves its `status` alone. A live screen is unchanged.

MINOR-B. The live "Provider status" row joined a list of objects as text: "[object Object]". It now
shows the list whole, as the detail tables show one: the fold with its size, over its JSON. The
reopened row stays "n/a": the stored list has each provider's `last_failure_error_code` masked by
sanitize_for_export (owner ruling H3 keeps the sanitizer as it is), so it is not a copy of the list
the live row reads.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from typing import Any

import fullscreen_goldens as goldens
import pytest
from fastapi.testclient import TestClient

from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import dev_limiter, hash_code, session_limiter
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.news.adapters.common import NewsProviderError
from crypto_probability_engine.persistence.repository import InMemoryPersistenceRepository
from crypto_probability_engine.utils.sanitize import sanitize_for_export

harness = goldens.harness

ACCESS_CODE = "operator-test-code"
AUTHORITY = "News Authority / Macro & Micro Context"
DISABLED = "News analysis disabled for this run."
OBJECT_TEXT = "[object Object]"
MASKED = "set (****)"


class _Source:
    """A configured news provider that answers with no items, or fails with `error`."""

    def __init__(self, name: str, error: Exception | None = None) -> None:
        self.name = name
        self._error = error

    def is_configured(self) -> bool:
        return True

    def fetch_items(self, symbol: str) -> tuple:
        if self._error is not None:
            raise self._error
        return ()

    def fetch_macro_observations(self) -> tuple:
        return ()


def _rate_limited() -> NewsProviderError:
    return NewsProviderError(
        "RATE_LIMITED",
        "gdelt: rate limited",
        provider="gdelt",
        http_status=429,
        error_code="RATE_LIMITED",
        error_type="RATE_LIMIT",
        operation="GET /api/v2/doc/doc",
        retry_after_seconds=60,
    )


# scenario -> (the analysis mode, the news providers it is served by)
SCENARIOS: dict[str, tuple[str, Any]] = {
    "provider_ok": ("NEWS_ADDON", lambda: [_Source("fred")]),
    "provider_fails": ("NEWS_ADDON", lambda: [_Source("fred"), _Source("gdelt", _rate_limited())]),
    "no_providers": ("NEWS_ADDON", lambda: []),
    "metrics_only": ("METRICS_ONLY", lambda: [_Source("fred")]),
}
# What each analysis's news add-on state says, so the scenarios are what they claim to be.
STATUSES = {
    "provider_ok": "OK",
    "provider_fails": "DEGRADED",
    "no_providers": "UNAVAILABLE",
    "metrics_only": "DISABLED_METRICS_ONLY",
}


class _DurableStore(InMemoryPersistenceRepository):
    """A durable store's stand-in, holding one run: its summary as a save writes it, and its
    detail as a save writes it (sanitize_for_export of the detail view) read back from JSON."""

    def __init__(self, payload: dict) -> None:
        super().__init__()
        self._summary = analysis_service._run_summary(payload)  # noqa: SLF001
        written = json.dumps(sanitize_for_export(copy.deepcopy(payload["detail_view"])))
        self._detail = json.loads(written)

    def persistence_status(self) -> str:
        return "OK"

    def recent_runs_for_origin(self, limit: int, *, prediction_origin: str) -> list[dict]:
        return [dict(self._summary)]

    def run_ids_with_detail(self, run_ids: Any, *, prediction_origin: str) -> set[str]:
        return {self._summary["run_id"]} & set(run_ids)

    def get_run_detail(self, run_id: str, *, prediction_origin: str) -> dict | None:
        return copy.deepcopy(self._detail) if run_id == self._summary["run_id"] else None


def _signed_in(repository: InMemoryPersistenceRepository | None = None) -> TestClient:
    session_limiter.reset()
    dev_limiter.reset()
    settings = Settings(
        access_code_hash=hash_code(ACCESS_CODE),
        session_signing_key="test-signing-key",
        session_cookie_secure=False,
        data_mode="fixture",
    )
    client = TestClient(create_app(settings), raise_server_exceptions=False)
    if repository is not None:
        client.app.state.persistence_repository = repository
    assert client.post("/v1/auth/login", json={"code": ACCESS_CODE}).status_code == 200
    return client


def _ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def _read_back(client: TestClient, run_id: str, source: str) -> dict:
    """The run as the screen reopens it: its Recent row, and the detail the route answers."""

    listing = _ok(client.get("/v1/runs"))
    assert listing["source"] == source
    (row,) = [row for row in listing["runs"] if row["run_id"] == run_id]
    assert row["detail_available"] is True
    return {"row": row, "detail": _ok(client.get(f"/v1/analyze/detail/{run_id}"))}


@pytest.fixture(scope="module")
def answers() -> Iterator[dict[str, dict]]:
    """Each scenario's live analysis and its two reopened runs, as the routes answer them."""

    found: dict[str, dict] = {}
    with pytest.MonkeyPatch.context() as patch:
        for name, (mode, sources) in SCENARIOS.items():
            patch.setattr(
                "crypto_probability_engine.news.contract.build_live_news_sources",
                lambda settings, sources=sources: sources(),
            )
            client = _signed_in()
            body = {"symbol": "BTC/USDT", "timeframe": "1H", "analysis_mode": mode}
            live = _ok(client.post("/v1/analyze", json=body))
            run_id = live["run_id"]
            found[name] = {
                "live": {"row": live, "detail": _ok(client.get(f"/v1/analyze/detail/{run_id}"))},
                "in_process": _read_back(client, run_id, "in_process"),
                "durable": _read_back(_signed_in(_DurableStore(live)), run_id, "durable"),
            }
    yield found


# The ways a screen is shown: the live analysis, and the run reopened from either store.
VIEWS = ("live", "in_process", "durable")


def _without_view(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if key != "decision_view"}


@pytest.fixture(scope="module")
def screens(answers: dict[str, dict]) -> dict[str, list[str]]:
    """Every screen as the real app.js renders it: "<scenario>.<view>" -> its visible texts. The
    goldens' renderer draws each one as a detail panel over the row and detail it is given."""

    panels = {f"{name}.{view}": answers[name][view] for name in SCENARIOS for view in VIEWS}
    live = answers["provider_ok"]["live"]
    # A live analysis whose response carries no news add-on state, beside a detail that holds
    # one: its State row reads its own response only, never the detail's state.
    stateless = copy.deepcopy(live["row"])
    stateless.pop("news_addon_state")
    panels["live_without_state"] = {"row": stateless, "detail": live["detail"]}
    # A reopened run's row that carries its own state (another status): the row's own value wins.
    own = _without_view(live["row"])
    own["news_addon_state"] = {**own["news_addon_state"], "status": "OWN_STATUS"}
    panels["reopened_with_own_state"] = {
        "row": own,
        "detail": answers["provider_ok"]["durable"]["detail"],
    }
    # A stored record without its news add-on state, or without its news block.
    durable = answers["provider_fails"]["durable"]
    for lost, change in (
        ("state_lost", lambda detail: detail["news_detail"].pop("news_addon_state")),
        ("news_lost", lambda detail: detail.pop("news_detail")),
    ):
        detail = copy.deepcopy(durable["detail"])
        change(detail)
        panels[lost] = {"row": durable["row"], "detail": detail}
    rendered = goldens.render({}, panels)["screens"]
    return {name: surfaces["history"] for name, surfaces in rendered.items()}


def _row(texts: list[str], label: str) -> str:
    if label == "State":
        return harness._value(harness._between(texts, "News Add-on", AUTHORITY), label)
    return harness._value(harness._between(texts, AUTHORITY, "Debug / Raw JSON"), label)


def _provider_block(texts: list[str]) -> tuple[str, list[dict]]:
    """The Provider status row's fold: its summary, and the list its JSON holds."""

    part = harness._between(texts, AUTHORITY, "Debug / Raw JSON")
    index = part.index("Provider status")
    return part[index + 1], json.loads(part[index + 2])


def test_the_scenarios_are_what_they_claim_to_be(answers: dict[str, dict]) -> None:
    for name, (mode, _) in SCENARIOS.items():
        live = answers[name]["live"]
        assert live["row"]["analysis_mode"] == mode, name
        assert "decision_view" in live["row"], name
        state = live["row"]["news_addon_state"]
        assert state["status"] == STATUSES[name], name
        for view in ("in_process", "durable"):
            reopened = answers[name][view]
            # The history row carries no news add-on state; its stored record does.
            assert "news_addon_state" not in reopened["row"], (name, view)
            assert reopened["row"]["analysis_mode"] == mode, (name, view)
            stored = reopened["detail"]["news_detail"]["news_addon_state"]
            assert stored["status"] == state["status"], (name, view)
    providers = {
        name: [
            item["provider"]
            for item in answers[name]["live"]["row"]["news_addon_state"]["provider_status"]
        ]
        for name in SCENARIOS
    }
    assert providers == {
        "provider_ok": ["fred"],
        "provider_fails": ["fred", "gdelt"],
        "no_providers": [],
        "metrics_only": [],
    }


def test_the_stored_provider_list_is_not_a_copy_of_the_live_one(answers: dict[str, dict]) -> None:
    """Why the reopened Provider status row stays "n/a": the record's list is the sanitized one.
    The in-process detail is the run's own; the durable one has the failure's code masked."""

    def failed(view: str) -> dict:
        found = answers["provider_fails"][view]
        if view == "live":
            state = found["row"]["news_addon_state"]
        else:
            state = found["detail"]["news_detail"]["news_addon_state"]
        (item,) = [item for item in state["provider_status"] if item["provider"] == "gdelt"]
        return item

    assert failed("live")["last_failure_error_code"] == "RATE_LIMITED"
    assert failed("in_process")["last_failure_error_code"] == "RATE_LIMITED"
    assert failed("durable")["last_failure_error_code"] == MASKED
    # Everything else the state holds is kept: its status is the live row's own.
    for name in SCENARIOS:
        live = answers[name]["live"]["row"]["news_addon_state"]
        stored = answers[name]["durable"]["detail"]["news_detail"]["news_addon_state"]
        assert stored["status"] == live["status"], name
        assert stored == sanitize_for_export(live), name


def test_a_reopened_runs_state_row_reads_its_stored_status(screens: dict[str, list[str]]) -> None:
    """MINOR-A. With news analysis on, the reopened run reads the stored state's status, from
    either store, as the live screen reads its own; a METRICS_ONLY run still says it was off."""

    for name, status in STATUSES.items():
        expected = DISABLED if name == "metrics_only" else status
        for view in VIEWS:
            assert _row(screens[f"{name}.{view}"], "State") == expected, (name, view)
    # The fix is seen, not a default: a status other than the fallback's own.
    assert _row(screens["provider_fails.durable"], "State") == "DEGRADED"
    assert _row(screens["provider_ok.in_process"], "State") == "OK"
    # A live screen reads its own response only: without a state there it is as before.
    assert _row(screens["live_without_state"], "State") == "UNAVAILABLE"
    # A reopened row's own value wins; a record without the state reads as before.
    assert _row(screens["reopened_with_own_state"], "State") == "OWN_STATUS"
    for lost in ("state_lost", "news_lost"):
        assert _row(screens[lost], "State") == "UNAVAILABLE", lost


def test_the_live_provider_status_row_shows_the_backends_list_whole(
    answers: dict[str, dict], screens: dict[str, list[str]]
) -> None:
    """MINOR-B. The live row shows the list as the detail tables show one: the fold with its
    size, over its JSON, every field the backend gives (a failure's code included); no words of
    the frontend's own. A run with no providers reads "none". The fold names its size as the
    shared fold does (F-4): one provider is "1 item", two are "2 items"."""

    for name, size in (("provider_ok", "1 item"), ("provider_fails", "2 items")):
        listed = answers[name]["live"]["row"]["news_addon_state"]["provider_status"]
        summary, shown = _provider_block(screens[f"{name}.live"])
        assert summary == size, name
        assert len(listed) == int(size.split()[0]), name
        assert shown == listed, name
    _, shown = _provider_block(screens["provider_fails.live"])
    (failed,) = [item for item in shown if item["provider"] == "gdelt"]
    assert (failed["status"], failed["last_failure_error_code"]) == ("UNAVAILABLE", "RATE_LIMITED")
    assert _row(screens["no_providers.live"], "Provider status") == "none"
    assert _row(screens["metrics_only.live"], "Provider status") == "none"


def test_a_reopened_runs_provider_status_row_stays_not_available(
    screens: dict[str, list[str]],
) -> None:
    """The stored list is not read (owner ruling H3): the reopened row reads "n/a"."""

    for name in SCENARIOS:
        for view in ("in_process", "durable"):
            assert _row(screens[f"{name}.{view}"], "Provider status") == "n/a", (name, view)
    for name in ("live_without_state", "state_lost", "news_lost"):
        assert _row(screens[name], "Provider status") == "n/a", name


def test_no_screen_prints_an_object_as_text(screens: dict[str, list[str]]) -> None:
    for name, texts in screens.items():
        assert not [text for text in texts if OBJECT_TEXT in text], name


def test_a_rows_json_reads_from_the_left() -> None:
    """The value column is right-aligned; the JSON a row shows whole is not, so its indentation
    reads as JSON (frontend/styles.css)."""

    css = (harness.ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")
    rule = css.split(".detail-kv dd pre {", 1)[1].split("}", 1)[0]
    assert "text-align: left;" in rule
