from __future__ import annotations

import pytest

from crypto_probability_engine.detail.frontend_display import build_frontend_display


def _quant_result(hard_blocks: list[str] | None = None) -> dict:
    gate_result = {
        "action": "BLOCKED",
        "hard_gate_passed": False,
    }
    if hard_blocks is not None:
        gate_result["hard_blocks"] = hard_blocks
    return {
        "probability_state": {
            "horizons": {
                "H_primary": {
                    "p_up_frac": 0.4,
                    "p_down_frac": 0.3,
                    "p_timeout_frac": 0.3,
                }
            }
        },
        "score_stack": {"total_score": 50.0, "disposition": "WATCH"},
        "gate_result": gate_result,
        "execution_realism": {"warnings": []},
    }


def _display(
    hard_blocks: list[str] | None = None,
    skill_evidence: dict | None = None,
) -> dict:
    return build_frontend_display(
        _quant_result(hard_blocks),
        {"news_addon_state": {"warnings": []}},
        "METRICS_ONLY",
        {"warnings": []},
        {
            "timeframe_label": "One hour",
            "horizon_label": "Four bars",
            "horizon_bars": 4,
            "horizon_approx_label": "About four hours",
            "probability_explanation": "Test explanation.",
            "uncalibrated_banner": "Test banner.",
            "model_readiness_label": "Test readiness.",
        },
        skill_evidence=skill_evidence,
    )


def _skill_detail(skill_evidence: dict | None) -> str:
    display = _display(["SKILL_NOT_DEMONSTRATED"], skill_evidence)
    return display["blocking_reasons"][0]["detail"]


def test_skill_verdicts_have_distinguishable_details() -> None:
    details = {
        _skill_detail({"verdict": "INSUFFICIENT_EVIDENCE", "n": 12}),
        _skill_detail(
            {
                "verdict": "NO_DEMONSTRATED_SKILL",
                "n": 100,
                "observed_directional_rate": 0.58,
            }
        ),
        _skill_detail({"verdict": "DEMONSTRATED_SKILL", "n": 100}),
    }

    assert len(details) == 3


def test_insufficient_evidence_copy_only_states_what_is_known() -> None:
    detail = _skill_detail({"verdict": "INSUFFICIENT_EVIDENCE", "n": 0})

    assert "not been evaluated" in detail
    assert "0" in detail
    for forbidden in (
        "accumulat",
        "arriv",
        "on track",
        "keep using",
        "wait",
        "growing",
        "healthy",
    ):
        assert forbidden not in detail.lower()


def test_no_demonstrated_skill_copy_is_precise_about_accuracy() -> None:
    detail = _skill_detail(
        {
            "verdict": "NO_DEMONSTRATED_SKILL",
            "n": 100,
            "observed_directional_rate": 0.59,
        }
    )

    assert "59.0%" in detail
    assert "did not clear the required evidence threshold" in detail
    assert "This is not a finding that accuracy is at or below 50%." in detail
    assert "no better than chance" not in detail
    assert "coin flip" not in detail


@pytest.mark.parametrize(
    "skill_evidence",
    [
        None,
        {"n": 100, "observed_directional_rate": 0.6},
        {
            "verdict": "NO_DEMONSTRATED_SKILL",
            "n": 100,
            "observed_directional_rate": None,
        },
    ],
)
def test_incomplete_skill_evidence_produces_detail(skill_evidence: dict | None) -> None:
    assert isinstance(_skill_detail(skill_evidence), str)


@pytest.mark.parametrize("hard_blocks", [None, []])
def test_no_hard_blocks_produces_no_blocking_reasons(
    hard_blocks: list[str] | None,
) -> None:
    assert _display(hard_blocks)["blocking_reasons"] == []


def test_unknown_hard_block_is_preserved() -> None:
    reason = _display(["NEW_HARD_BLOCK"])["blocking_reasons"][0]

    assert reason["code"] == "NEW_HARD_BLOCK"
    assert reason["headline"] == "NEW_HARD_BLOCK"
    assert "description is unavailable" in reason["detail"]


def test_raw_reason_fields_are_unchanged() -> None:
    hard_blocks = ["PROVIDER_DEGRADED", "SKILL_NOT_DEMONSTRATED"]
    display = _display(hard_blocks)

    assert display["key_reasons"] == hard_blocks
    assert display["invalidation_conditions"] == hard_blocks


def test_every_known_hard_block_has_operator_copy() -> None:
    codes = [
        "KILL_SWITCH",
        "SHELTER_MODE_BLOCK",
        "PROVIDER_DEGRADED",
        "EPISTEMIC_VOID",
        "LIQUIDITY_NOT_VIABLE",
        "TAIL_RISK_BREACH",
        "EXECUTION_COST_TOO_HIGH",
        "SKILL_NOT_DEMONSTRATED",
    ]

    reasons = _display(codes)["blocking_reasons"]

    assert [reason["code"] for reason in reasons] == codes
    assert all(reason["headline"] and reason["detail"] for reason in reasons)
    assert all(reason["headline"] != reason["code"] for reason in reasons)
