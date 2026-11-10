"""Volatility, Sharpe and Sortino against hand-worked examples.

Fixture ``R`` = [0.02, 0.04, 0.06, 0.08, 0.10]:
  mean = 0.06, deviations = [-0.04, -0.02, 0, 0.02, 0.04]
  sum of squares = 0.004, sample variance = 0.004 / 4 = 0.001

Fixture ``S`` = [-0.02, 0.03, 0.03, -0.04, 0.02]:
  mean = 0.02 / 5 = 0.004
  shortfalls below zero = [-0.02, 0, 0, -0.04, 0]
  downside deviation = sqrt((0.0004 + 0.0016) / 5) = sqrt(0.0004) = 0.02
"""

from __future__ import annotations

import math

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from portfolio_risk.errors import InsufficientDataError
from portfolio_risk.risk import (
    annualised_volatility,
    downside_deviation,
    sharpe_ratio,
    sortino_ratio,
)

R = pd.Series([0.02, 0.04, 0.06, 0.08, 0.10])
S = pd.Series([-0.02, 0.03, 0.03, -0.04, 0.02])


def test_annualised_volatility() -> None:
    # sqrt(0.001) * sqrt(4) = sqrt(0.004)
    assert annualised_volatility(R, 4) == pytest.approx(math.sqrt(0.004))


def test_sharpe_ratio_with_risk_free_rate() -> None:
    # excess mean = 0.06 - 0.01 = 0.05; std unchanged = sqrt(0.001)
    # 0.05 / sqrt(0.001) * sqrt(4) = 0.1 / sqrt(0.001) = sqrt(10)
    assert sharpe_ratio(R, 0.01, 4) == pytest.approx(math.sqrt(10))


def test_sharpe_ratio_is_nan_for_constant_returns() -> None:
    assert math.isnan(sharpe_ratio(pd.Series([0.01] * 10), 0.0, 252))


def test_downside_deviation_averages_over_all_observations() -> None:
    assert downside_deviation(S, 0.0) == pytest.approx(0.02)
    # Averaging over the two negative observations only would give sqrt(0.002 / 2) = 0.0316.
    assert downside_deviation(S, 0.0) != pytest.approx(math.sqrt(0.001))


def test_downside_deviation_with_minimum_acceptable_return() -> None:
    # shortfalls vs 0.01: [-0.03, 0, 0, -0.05, 0]; (0.0009 + 0.0025) / 5 = 0.00068
    assert downside_deviation(S, 0.01) == pytest.approx(math.sqrt(0.00068))


def test_sortino_ratio() -> None:
    # (0.004 - 0) / 0.02 * sqrt(4) = 0.4
    assert sortino_ratio(S, 0.0, 4) == pytest.approx(0.4)


def test_sortino_ratio_with_minimum_acceptable_return() -> None:
    expected = (0.004 - 0.01) / math.sqrt(0.00068) * 2
    assert sortino_ratio(S, 0.01, 4) == pytest.approx(expected)


def test_sortino_ratio_is_nan_without_downside() -> None:
    assert math.isnan(sortino_ratio(R, 0.0, 252))


def test_single_observation_is_rejected() -> None:
    with pytest.raises(InsufficientDataError, match="at least 2"):
        annualised_volatility(pd.Series([0.01]), 252)


@given(
    st.lists(st.floats(min_value=-0.5, max_value=0.5), min_size=2, max_size=200),
    st.integers(min_value=1, max_value=365),
)
def test_volatility_is_non_negative_and_scales_with_sqrt_periods(
    values: list[float], periods: int
) -> None:
    returns = pd.Series(values)
    daily = annualised_volatility(returns, 1)
    scaled = annualised_volatility(returns, periods)
    assert daily >= 0.0
    assert scaled == pytest.approx(daily * math.sqrt(periods))
