"""Plan §10: the event sink is allowlisted, bounded, flattened, and never raises."""

from __future__ import annotations

import json

import pytest

from crypto_probability_engine.telemetry import events as ev

# Words that would mean a field could carry a secret, a credential or personal data.
FORBIDDEN_WORDS = {"token", "secret", "password", "cookie", "authorization", "header", "headers",
                   "query", "ip", "address", "operator", "credential", "payload", "body", "email",
                   "session", "key", "user", "agent"}


def test_only_allowlisted_events_and_fields_survive() -> None:
    assert ev.sanitize("not_an_event", {"run_id": "r"}) is None
    clean = ev.sanitize("http_request", {"route": "/x", "status": 200, "cookie": "c",
                                         "authorization": "a", "query": "q=1", "client": "1.2.3.4"})
    assert clean == {"event": "http_request", "route": "/x", "status": 200}


def test_values_are_flattened_to_short_scalars() -> None:
    clean = ev.sanitize("persistence_receipt", {
        "run_id": "r" * 500, "duration_ms": 12.34567, "overall": float("nan"),
        "prediction_rows": 3, "error_class": None, "repository": {"nested": "dropped"},
        "feature_snapshot": ["dropped"], "prediction": b"dropped", "background_status": True,
    })
    assert clean is not None
    assert clean["run_id"] == "r" * ev.MAX_TEXT + "..."
    assert clean["duration_ms"] == 12.346
    assert clean["overall"] is None
    assert clean["prediction_rows"] == 3 and clean["background_status"] is True
    assert clean["error_class"] is None
    for dropped in ("repository", "feature_snapshot", "prediction"):
        assert dropped not in clean


def test_the_buffer_is_bounded_and_keeps_the_newest() -> None:
    sink = ev.TelemetrySink(capacity=3)
    for index in range(10):
        sink.record("http_request", {"status": index})
    assert [event["status"] for event in sink.events] == [7, 8, 9]


def test_recording_never_raises_and_keeps_nothing_it_cannot_flatten() -> None:
    class Hostile:
        def __str__(self) -> str:
            raise RuntimeError("no")

    sink = ev.TelemetrySink()
    sink.record("http_request", {"route": Hostile()})
    sink.record("http_request", None)  # type: ignore[arg-type]
    assert list(sink.events) == []


def test_each_event_is_one_sorted_json_line_on_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    sink = ev.TelemetrySink()
    capsys.readouterr()
    sink.record("http_request", {"status": 204, "route": "/v1/x"})
    lines = capsys.readouterr().out.splitlines()
    assert lines == ['{"event":"http_request","route":"/v1/x","status":204}']
    assert json.loads(lines[0])["status"] == 204


def test_emit_records_on_the_process_wide_sink() -> None:
    ev.emit("analysis_completed", run_id="run-emit", symbol="BTC/USDT", cookie="dropped")
    assert ev.EVENTS_SINK.events[-1] == {"event": "analysis_completed", "run_id": "run-emit",
                                         "symbol": "BTC/USDT"}
    assert ev.EVENTS_SINK.events.maxlen == ev.BUFFER_SIZE


def test_no_allowlisted_field_can_name_a_secret_or_personal_data() -> None:
    for field in ev.FIELDS:
        assert not set(field.split("_")) & FORBIDDEN_WORDS, field
