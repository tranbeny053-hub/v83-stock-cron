from __future__ import annotations

import ast
import json
from pathlib import Path

import httpx
import pytest

from scripts import manual_smoke, production_smoke

ACCESS_CODE = "access-code-that-must-stay-private"
COOKIE_VALUE = "cookie-that-must-stay-private"
ENABLED = {
    "UCPE_PRODUCTION_SMOKE_ENABLED": "true",
    "UCPE_SMOKE_ACCESS_CODE": ACCESS_CODE,
}


def _unauthorized() -> dict:
    return {
        "detail": {
            "error": {
                "code": "UNAUTHORIZED",
                "message": "Valid session is required.",
                "retry_after_seconds": None,
                "run_id": None,
                "provider_state_snapshot": {},
                "system_status_snapshot": {},
            }
        }
    }


def _calibration() -> dict:
    return {
        "status": "OK",
        "repository": "SUPABASE_POSTGRES",
        "timeframes": [
            {"timeframe": "15m", "reliability_status": "EARLY_DIAGNOSTIC", "sample_count": 37},
            {"timeframe": "1H", "reliability_status": "INSUFFICIENT_SAMPLE", "sample_count": 4},
        ],
    }


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/healthcheck":
        return httpx.Response(200, json={"status": "OK"})
    if path == "/v1/build-info":
        return httpx.Response(200, json={"fingerprint": "UCPE LIVE BUILD fixture"})
    if path == "/":
        return httpx.Response(200, text='<script src="/assets/app.js?v=fixture"></script>')
    if path == "/assets/app.js":
        assert request.url.query == b"v=fixture"
        return httpx.Response(200, text="prob_up_pct prob_down_pct prob_timeout_pct")
    if path in {"/v1/system_status", "/v1/calibration"}:
        return httpx.Response(401, json=_unauthorized())
    raise AssertionError(f"unexpected request: {request.method} {request.url}")


def _run(
    tmp_path: Path,
    handler=_handler,
    *,
    authenticated: bool = False,
    environ=ENABLED,
    extra_args: list[str] | None = None,
) -> int:
    argv = ["--base-url", "https://production.invalid", "--raw-capture-dir", str(tmp_path)]
    if authenticated:
        argv.append("--authenticated")
    if extra_args:
        argv.extend(extra_args)
    return production_smoke.main(
        argv,
        transport=httpx.MockTransport(handler),
        environ=environ,
    )


def test_master_gate_off_refuses_without_request(tmp_path: Path, capsys) -> None:
    requests = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        raise AssertionError("network must not be reached")

    assert _run(tmp_path, handler, environ={}) == 1
    assert requests == 0
    assert "UCPE_PRODUCTION_SMOKE_ENABLED" in capsys.readouterr().out


def test_authenticated_missing_access_code_refuses_without_request(tmp_path: Path, capsys) -> None:
    requests = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        raise AssertionError("network must not be reached")

    env = {"UCPE_PRODUCTION_SMOKE_ENABLED": "true"}
    assert _run(tmp_path, handler, authenticated=True, environ=env) == 1
    assert requests == 0
    output = capsys.readouterr().out
    assert "UCPE_SMOKE_ACCESS_CODE" in output


def test_phase_a_passes_healthy_fixture(tmp_path: Path, capsys) -> None:
    assert _run(tmp_path) == 0
    output = capsys.readouterr().out
    assert "build fingerprint: UCPE LIVE BUILD fixture" in output
    assert output.endswith("PASS: production smoke phases A\n")
    assert (tmp_path / "phase-a-app-js.body").read_bytes() == (
        b"prob_up_pct prob_down_pct prob_timeout_pct"
    )


def test_phase_a_fails_on_stale_served_bundle(tmp_path: Path, capsys) -> None:
    stale = production_smoke.STALE_FRONTEND_MARKERS[0]

    def handler(request: httpx.Request) -> httpx.Response:
        response = _handler(request)
        if request.url.path == "/assets/app.js":
            return httpx.Response(
                200,
                text=f"prob_up_pct prob_down_pct prob_timeout_pct {stale}",
            )
        return response

    assert _run(tmp_path, handler) == 1
    assert capsys.readouterr().out.count("served app.js contains stale marker") == 1


def test_phase_a_fails_if_calibration_is_public(tmp_path: Path, capsys) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/calibration":
            return httpx.Response(200, json=_calibration())
        return _handler(request)

    assert _run(tmp_path, handler) == 1
    output = capsys.readouterr().out
    assert "unauthenticated GET /v1/calibration returned HTTP 200, expected 401" in output
    expected = (
        "production smoke phases A; unauthenticated GET /v1/calibration "
        "returned HTTP 200, expected 401\n"
    )
    assert output.endswith(expected)


def test_phase_a_timeout_names_request_and_default_budget(tmp_path: Path, capsys) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/healthcheck":
            raise httpx.ReadTimeout("private transport detail", request=request)
        return _handler(request)

    assert _run(tmp_path, handler) == 1
    output = capsys.readouterr().out
    assert output.endswith(
        "FAIL: production smoke phases A; GET /healthcheck timed out after 10.0s\n"
    )
    assert output.count("FAIL:") == 1


def test_calibration_timeout_names_request_and_long_budget(tmp_path: Path, capsys) -> None:
    authenticated = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal authenticated
        if request.url.path == "/v1/auth/login":
            authenticated = True
            return httpx.Response(200, json={"ok": True})
        if authenticated and request.url.path == "/v1/system_status":
            return httpx.Response(
                200,
                json={
                    "system": {
                        "persistence_status": "OK",
                        "repository_type": "SUPABASE_POSTGRES",
                    }
                },
            )
        if authenticated and request.url.path == "/v1/calibration":
            raise httpx.ReadTimeout("private transport detail", request=request)
        return _handler(request)

    assert _run(tmp_path, handler, authenticated=True) == 1
    output = capsys.readouterr().out
    assert output.endswith(
        "FAIL: production smoke phases A+B; GET /v1/calibration timed out after 120.0s\n"
    )
    assert output.count("FAIL:") == 1
    assert "private transport detail" not in output


def test_requests_receive_their_configured_per_request_timeouts(tmp_path: Path) -> None:
    authenticated = False
    observed: dict[tuple[str, bool], dict[str, float]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal authenticated
        observed[(request.url.path, authenticated)] = request.extensions["timeout"]
        if request.url.path == "/v1/auth/login":
            authenticated = True
            return httpx.Response(200, json={"ok": True})
        if authenticated and request.url.path == "/v1/system_status":
            return httpx.Response(
                200,
                json={
                    "system": {
                        "persistence_status": "OK",
                        "repository_type": "SUPABASE_POSTGRES",
                    }
                },
            )
        if authenticated and request.url.path == "/v1/calibration":
            return httpx.Response(200, json=_calibration())
        return _handler(request)

    assert (
        _run(
            tmp_path,
            handler,
            authenticated=True,
            extra_args=["--timeout", "3.5", "--calibration-timeout", "45"],
        )
        == 0
    )
    assert set(observed[("/healthcheck", False)].values()) == {3.5}
    assert set(observed[("/v1/calibration", True)].values()) == {45.0}


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--timeout", "0"),
        ("--timeout", "not-a-number"),
        ("--calibration-timeout", "-1"),
        ("--calibration-timeout", "nan"),
    ],
)
def test_invalid_timeout_is_rejected_before_request(
    tmp_path: Path,
    flag: str,
    value: str,
) -> None:
    requests = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        raise AssertionError("network must not be reached")

    with pytest.raises(SystemExit) as exc_info:
        _run(tmp_path, handler, extra_args=[flag, value])
    assert exc_info.value.code != 0
    assert requests == 0


def test_phase_b_prints_only_bounded_diagnostics_and_keeps_secrets_out(
    tmp_path: Path,
    capsys,
) -> None:
    authenticated = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal authenticated
        if request.url.path == "/v1/auth/login":
            assert request.method == "POST"
            assert json.loads(request.content) == {"code": ACCESS_CODE}
            authenticated = True
            return httpx.Response(
                200,
                json={"ok": True},
                headers={
                    "Set-Cookie": (
                        f"ucpe_session={COOKIE_VALUE}; HttpOnly; Max-Age=3600; "
                        "Path=/; SameSite=lax; Secure"
                    )
                },
            )
        if authenticated and request.url.path == "/v1/system_status":
            assert request.headers.get("cookie") == f"ucpe_session={COOKIE_VALUE}"
            return httpx.Response(
                200,
                json={
                    "runtime": {"status": "OK"},
                    "system": {
                        "persistence_status": "OK",
                        "repository_type": "SUPABASE_POSTGRES",
                    },
                },
            )
        if authenticated and request.url.path == "/v1/calibration":
            return httpx.Response(200, json=_calibration())
        return _handler(request)

    assert _run(tmp_path, handler, authenticated=True) == 0
    output = capsys.readouterr().out
    assert "persistence_status=OK repository_type=SUPABASE_POSTGRES" in output
    assert "timeframe=15m calibration_status=EARLY_DIAGNOSTIC sample_count=37" in output
    assert "timeframe=1H calibration_status=INSUFFICIENT_SAMPLE sample_count=4" in output
    assert output.endswith("PASS: production smoke phases A+B\n")
    assert ACCESS_CODE not in output
    assert COOKIE_VALUE not in output
    assert "Set-Cookie" not in output
    captures = b"\n".join(path.read_bytes() for path in sorted(tmp_path.iterdir()))
    assert ACCESS_CODE.encode() not in captures
    assert COOKIE_VALUE.encode() not in captures
    assert b"Set-Cookie" not in captures
    assert b"HttpOnly" not in captures


def test_mocked_session_cookie_matches_the_real_app_cookie_attributes() -> None:
    """The Phase B mock is only meaningful if it scopes the cookie like the real app.

    Without an explicit ``Path``, http.cookiejar derives the path from the login URL
    (``/v1/auth``), so the cookie would never be sent to ``/v1/system_status`` and the smoke
    would pass or fail for reasons production never reproduces.
    """

    from fastapi.testclient import TestClient

    from crypto_probability_engine.api.app import create_app
    from crypto_probability_engine.api.auth import hash_code
    from crypto_probability_engine.config.settings import Settings

    settings = Settings(
        access_code_hash=hash_code("operator-smoke-code"),
        session_signing_key="smoke-signing-key",
        session_cookie_secure=True,
        data_mode="fixture",
    )
    with TestClient(create_app(settings)) as client:
        login = client.post("/v1/auth/login", json={"code": "operator-smoke-code"})
    assert login.status_code == 200, login.text
    set_cookie = login.headers.get("set-cookie")
    assert set_cookie is not None
    assert "Path=/;" in set_cookie or set_cookie.endswith("Path=/")
    assert "HttpOnly" in set_cookie


def test_stale_marker_tuple_matches_manual_smoke() -> None:
    assert production_smoke.STALE_FRONTEND_MARKERS == manual_smoke.STALE_FRONTEND_MARKERS


def test_module_is_read_only_except_single_login() -> None:
    source_path = Path(production_smoke.__file__)
    source = source_path.read_text()
    tree = ast.parse(source)
    writes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"post", "put", "patch", "delete"}
    ]
    assert len(writes) == 1
    assert isinstance(writes[0].func, ast.Attribute) and writes[0].func.attr == "post"
    assert ast.literal_eval(writes[0].args[0]) == "/v1/auth/login"
    forbidden_paths = ("/v1/ana" + "lyze", "/v1/ana" + "lyze_batch")
    assert all(path not in source for path in forbidden_paths)
