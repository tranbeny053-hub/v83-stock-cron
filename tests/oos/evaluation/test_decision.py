"""The §5A acceptance decision, including a genuine PASS and every fail-closed edge."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from crypto_probability_engine.oos.evaluation import decision
from crypto_probability_engine.oos.evaluation.admission import admit
from tests.oos.evaluation.conftest import (
    T0,
    T_CLOSE,
    daily_4h_evidence,
    evidence_row,
)


def _evaluate(rows, timeframe: str = "4H"):
    return decision.evaluate_timeframe(
        timeframe, admit(rows, t0=T0, t_close=T_CLOSE), t0=T0, t_close=T_CLOSE
    )


# --- the evaluator must be ABLE to pass, or every negative test below is vacuous ---


def test_a_genuinely_better_candidate_reaches_PASS() -> None:
    result = _evaluate(daily_4h_evidence())
    assert result.state == decision.PASS, result.reason
    assert result.a_holds and result.b_holds
    assert [c.usable_windows for c in result.coarsenings] == [11, 7, 5]
    assert all(c.holds for c in result.coarsenings)


def test_pass_authorizes_only_covered_symbols_that_clear_C() -> None:
    result = _evaluate(daily_4h_evidence())
    assert result.authorized_cells == ("BTC/USDT|4H",)
    assert result.per_symbol["ETH/USDT"].covered is False


def test_a_worse_candidate_is_NOT_PASS() -> None:
    rows = daily_4h_evidence(candidate_ups=[0.40, 0.41, 0.39, 0.42, 0.38])
    result = _evaluate(rows)
    assert result.state == decision.NOT_PASS
    assert not result.a_holds


# --- fail-closed edges, each pinned by the pre-registration ---


def test_zero_admitted_pairs_is_NOT_PASS_decided_before_A_or_B() -> None:
    result = _evaluate([])
    assert result.state == decision.NOT_PASS
    assert result.reason == "no Tier-2 admitted pairs in this timeframe"
    assert result.coarsenings == ()
    assert result.b1_holds is False, "B must never affirm on absent evidence"


def test_a1_fails_closed_below_two_windows() -> None:
    holds, boundary = decision.a1([-1.0])
    assert holds is False and boundary is None


def test_a1_fails_closed_on_zero_dispersion() -> None:
    """t is undefined with s == 0; a strict guard may only err toward NOT PASS."""

    holds, boundary = decision.a1([-0.5, -0.5, -0.5, -0.5, -0.5])
    assert holds is False and boundary is None


def test_a2_ties_are_non_negative_and_remain_in_k() -> None:
    holds, boundary, n_neg = decision.a2([-1.0, -1.0, -1.0, -1.0, 0.0])
    assert n_neg == 4
    assert boundary == pytest.approx(6 / 32)
    assert holds is False


def test_a2_reproduces_the_contract_attainability_floor() -> None:
    assert decision.a2([-1.0] * 5)[1] == pytest.approx(0.03125)
    assert decision.a2([-1.0] * 5)[0] is True
    assert decision.a2([-1.0] * 4)[1] == pytest.approx(0.0625)
    assert decision.a2([-1.0] * 4)[0] is False


def test_A_requires_all_three_coarsenings() -> None:
    result = _evaluate(daily_4h_evidence())
    for index in range(len(result.coarsenings)):
        weakened = list(result.coarsenings)
        weakened[index] = decision.CoarseningResult(
            coarsening=weakened[index].coarsening,
            k_pre_drop=weakened[index].k_pre_drop,
            usable_windows=weakened[index].usable_windows,
            dropped_windows=weakened[index].dropped_windows,
            a1_holds=False,
            a1_boundary_statistic=0.9,
            a2_holds=True,
            a2_boundary_statistic=0.01,
            a2_negative_windows=0,
        )
        assert not all(c.holds for c in weakened)


def test_zero_dispersion_at_one_coarsening_alone_blocks_PASS() -> None:
    """A candidate winning by an IDENTICAL margin in every c=4 window still cannot PASS.

    A1 needs a dispersion estimate and there is none, so it fails closed at c=4 even
    though c=1 and c=2 clear comfortably and every window favours the candidate. This
    is the §5 fail-closed rule doing real work, not a theoretical branch.
    """

    rows = daily_4h_evidence(candidate_ups=[0.60, 0.61, 0.59, 0.62, 0.58])
    result = _evaluate(rows)
    by_c = {c.coarsening: c for c in result.coarsenings}
    assert by_c[1].a1_holds and by_c[2].a1_holds
    assert by_c[4].a1_holds is False
    assert by_c[4].a1_boundary_statistic is None
    assert by_c[4].a2_holds is True and by_c[4].a2_negative_windows == 5
    assert result.state == decision.NOT_PASS


def test_probability_invariant_breach_is_an_observable_FAIL() -> None:
    row = evidence_row(T0)
    row["candidate_p_up_frac"] = 0.99  # sum now far from 1.0
    result = _evaluate([row])
    assert result.state == decision.FAIL
    breach = [c for c in result.fail_checks if c.status == decision.OBSERVABLE_BREACH]
    assert breach and breach[0].name == "probability_triplet_sums_to_one"


def test_unobservable_fail_checks_are_declared_not_assumed_clean() -> None:
    result = _evaluate(daily_4h_evidence())
    unobservable = {
        check.name for check in result.fail_checks if check.status == decision.NOT_OBSERVABLE
    }
    assert unobservable == {
        "hard_gate_not_overridden_by_score_or_news",
        "gated_when_evidence_is_thin",
        "no_sentiment_only_action",
    }
    assert all(
        "none of which is persisted" in check.detail
        for check in result.fail_checks
        if check.status == decision.NOT_OBSERVABLE
    )


def test_readiness_projection_cannot_be_scored() -> None:
    """A row with no probabilities must raise, never silently score as zero."""

    rows = [evidence_row(T0 + timedelta(days=d), with_probabilities=False) for d in range(22)]
    with pytest.raises(KeyError, match="no probabilities"):
        _evaluate(rows)


def test_output_never_claims_statistical_significance() -> None:
    result = _evaluate(daily_4h_evidence())
    rendered = json.dumps(
        {
            "state": result.state,
            "reason": result.reason,
            "coarsenings": [c.__dict__ for c in result.coarsenings],
        }
    ).lower()
    assert "significant" not in rendered
    assert "p_value" not in rendered and "p-value" not in rendered
    assert "boundary_statistic" in rendered
