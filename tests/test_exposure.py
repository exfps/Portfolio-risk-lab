"""Correlation, concentration and risk contributions against hand-worked examples."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from portfolio_risk.errors import DataValidationError
from portfolio_risk.exposure import (
    correlation_matrix,
    covariance_matrix,
    effective_number_of_positions,
    herfindahl_hirschman_index,
    risk_contributions,
)


def test_hhi_and_effective_positions() -> None:
    weights = pd.Series([0.5, 0.3, 0.2], index=["A", "B", "C"])
    # 0.25 + 0.09 + 0.04
    assert herfindahl_hirschman_index(weights) == pytest.approx(0.38)
    assert effective_number_of_positions(weights) == pytest.approx(1 / 0.38)


def test_equal_weights_give_minimum_concentration() -> None:
    weights = pd.Series([0.25] * 4, index=list("ABCD"))
    assert herfindahl_hirschman_index(weights) == pytest.approx(0.25)
    assert effective_number_of_positions(weights) == pytest.approx(4.0)


def test_single_position_is_fully_concentrated() -> None:
    weights = pd.Series([1.0], index=["A"])
    assert herfindahl_hirschman_index(weights) == 1.0
    assert effective_number_of_positions(weights) == 1.0


def test_correlation_of_perfectly_related_series() -> None:
    base = [0.01, -0.02, 0.03, 0.00, 0.02]
    frame = pd.DataFrame(
        {"A": base, "B": [2 * x for x in base], "C": [-x for x in base]},
    )
    corr = correlation_matrix(frame)
    assert corr.loc["A", "B"] == pytest.approx(1.0)
    assert corr.loc["A", "C"] == pytest.approx(-1.0)
    assert np.allclose(np.diag(corr.to_numpy()), 1.0)


def test_correlation_rejects_constant_series() -> None:
    frame = pd.DataFrame({"A": [0.01, 0.02, 0.03], "FLAT": [0.0, 0.0, 0.0]})
    with pytest.raises(DataValidationError, match="'FLAT'"):
        correlation_matrix(frame)


def test_covariance_matches_hand_calculation() -> None:
    # A = [1, 2, 3], B = [2, 4, 6] (in return units): var(A) = 1, var(B) = 4, cov = 2.
    frame = pd.DataFrame({"A": [0.01, 0.02, 0.03], "B": [0.02, 0.04, 0.06]})
    cov = covariance_matrix(frame)
    assert cov.loc["A", "A"] == pytest.approx(0.0001)
    assert cov.loc["B", "B"] == pytest.approx(0.0004)
    assert cov.loc["A", "B"] == pytest.approx(0.0002)


def test_risk_contributions_uncorrelated_assets() -> None:
    # vol 20% and 10%, uncorrelated, equal weights.
    # Sigma w = [0.02, 0.005]; portfolio variance = 0.5 * 0.02 + 0.5 * 0.005 = 0.0125.
    # Contributions: 0.01 / 0.0125 = 0.8 and 0.0025 / 0.0125 = 0.2.
    cov = pd.DataFrame([[0.04, 0.0], [0.0, 0.01]], index=["A", "B"], columns=["A", "B"])
    result = risk_contributions(cov, pd.Series({"A": 0.5, "B": 0.5}))
    assert result.tolist() == pytest.approx([0.8, 0.2])


def test_risk_contributions_correlated_assets() -> None:
    # Sigma w = [0.5 * 0.04 + 0.5 * 0.01, 0.5 * 0.01 + 0.5 * 0.01] = [0.025, 0.010].
    # Variance = 0.5 * 0.025 + 0.5 * 0.010 = 0.0175.
    # Contributions: 0.0125 / 0.0175 = 5/7 and 0.005 / 0.0175 = 2/7.
    cov = pd.DataFrame([[0.04, 0.01], [0.01, 0.01]], index=["A", "B"], columns=["A", "B"])
    result = risk_contributions(cov, pd.Series({"A": 0.5, "B": 0.5}))
    assert result["A"] == pytest.approx(5 / 7)
    assert result["B"] == pytest.approx(2 / 7)


def test_risk_contributions_follow_weight_order() -> None:
    cov = pd.DataFrame([[0.04, 0.0], [0.0, 0.01]], index=["A", "B"], columns=["A", "B"])
    result = risk_contributions(cov, pd.Series({"B": 0.5, "A": 0.5}))
    assert list(result.index) == ["B", "A"]
    assert result.tolist() == pytest.approx([0.2, 0.8])


def test_zero_variance_portfolio_is_rejected() -> None:
    cov = pd.DataFrame(np.zeros((2, 2)), index=["A", "B"], columns=["A", "B"])
    with pytest.raises(DataValidationError, match="variance is zero"):
        risk_contributions(cov, pd.Series({"A": 0.5, "B": 0.5}))


@given(
    st.lists(
        st.lists(st.floats(min_value=-0.1, max_value=0.1), min_size=4, max_size=4),
        min_size=8,
        max_size=40,
    ),
    st.lists(st.floats(min_value=0.01, max_value=1.0), min_size=4, max_size=4),
)
def test_contributions_sum_to_one_and_hhi_is_bounded(
    rows: list[list[float]], raw_weights: list[float]
) -> None:
    returns = pd.DataFrame(rows, columns=list("ABCD"))
    # A small diagonal keeps the covariance matrix positive definite for degenerate samples.
    cov = covariance_matrix(returns) + np.eye(4) * 1e-6
    weights = pd.Series(raw_weights, index=list("ABCD"))
    weights = weights / weights.sum()
    assert risk_contributions(cov, weights).sum() == pytest.approx(1.0)
    hhi = herfindahl_hirschman_index(weights)
    assert 0.25 - 1e-12 <= hhi <= 1.0 + 1e-12
