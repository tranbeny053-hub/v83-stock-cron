from __future__ import annotations

import pytest

from scripts import news_live_smoke


class _Settings:
    news_live_smoke_enabled = True


def _blocks(*, status: str, configured_source_count: int) -> dict:
    return {
        "news_addon_state": {
            "status": status,
            "configured_source_count": configured_source_count,
            "news_influence_frac": 0.0,
            "influence_mode": "ADVISORY_DISPLAY_ONLY",
            "provider_status": [],
        }
    }


@pytest.mark.parametrize("configured_source_count", [0, 2])
def test_enabled_smoke_fails_when_news_is_unavailable(
    monkeypatch,
    capsys,
    configured_source_count: int,
) -> None:
    monkeypatch.setattr(news_live_smoke.Settings, "from_env", lambda: _Settings())
    monkeypatch.setattr(
        news_live_smoke,
        "build_news_blocks",
        lambda **_kwargs: _blocks(
            status="UNAVAILABLE",
            configured_source_count=configured_source_count,
        ),
    )

    assert news_live_smoke.main() == 1
    assert capsys.readouterr().out == (
        "FAIL: news smoke found no available provider "
        f"(configured={configured_source_count}).\n"
    )


def test_enabled_smoke_passes_when_news_is_available(monkeypatch, capsys) -> None:
    monkeypatch.setattr(news_live_smoke.Settings, "from_env", lambda: _Settings())
    monkeypatch.setattr(
        news_live_smoke,
        "build_news_blocks",
        lambda **_kwargs: _blocks(status="DEGRADED", configured_source_count=2),
    )

    assert news_live_smoke.main() == 0
    assert capsys.readouterr().out.startswith(
        "PASS: news smoke completed status=DEGRADED providers=2\n"
    )
