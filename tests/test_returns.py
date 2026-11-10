"""Return calculations against hand-worked examples.

Prices 100, 110, 99, 108.9 give returns +10%, -10%, +10%. Compounded:
1.10 * 0.90 * 1.10 = 1.089, so the total return is 8.9%.
"""

from __future__ import annotations

import pandas as pd
import pytest

from portfolio_risk.errors import DataValidationError, InsufficientDataError
from portfolio_risk.returns import (
    annualised_return,
    portfolio_returns,
    simple_returns,
    to_period_rate,
    total_return,
    wealth_index,
)

DATES = pd.bdate_range("2024-01-01", periods=4)
PRICES = pd.DataFrame({"A": [100.0, 110.0, 99.0, 108.9]}, index=DATES)


def test_simple_returns_drop_first_row_and_match_hand_values() -> None:
    result = simple_returns(PRICES)
    assert list(result.index) == list(DATES[1:])
    assert result["A"].tolist() == pytest.approx([0.10, -0.10, 0.10])


def test_total_return_compounds() -> None:
    returns = simple_returns(PRICES)["A"]
    assert total_return(returns) == pytest.approx(0.089)


def test_annualised_return_uses_geometric_scaling() -> None:
    returns = simple_returns(PRICES)["A"]
    # Three observations. With 3 periods per year the sample is exactly one year.
    assert annualised_return(returns, 3) == pytest.approx(0.089)
    # With 6 periods per year the sample is half a year: 1.089 ** 2 - 1.
    assert annualised_return(returns, 6) == pytest.approx(0.185921)


def test_to_period_rate_decompounds() -> None:
    assert to_period_rate(0.21, 2) == pytest.approx(0.10)
    assert to_period_rate(0.0, 252) == 0.0


def test_portfolio_returns_is_weighted_sum_in_weight_order() -> None:
    asset_returns = pd.DataFrame(
        {"A": [0.10, -0.10, 0.10], "B": [0.02, 0.02, 0.02]}, index=DATES[1:]
    )
    weights = pd.Series({"B": 0.5, "A": 0.5})
    result = portfolio_returns(asset_returns, weights)
    assert result.tolist() == pytest.approx([0.06, -0.04, 0.06])
    assert result.name == "portfolio"


def test_portfolio_returns_rejects_unknown_asset() -> None:
    asset_returns = pd.DataFrame({"A": [0.01, 0.02]})
    with pytest.raises(DataValidationError, match="'C'"):
        portfolio_returns(asset_returns, pd.Series({"A": 0.5, "C": 0.5}))


def test_wealth_index_has_initial_point_at_start_label() -> None:
    returns = simple_returns(PRICES)["A"]
    wealth = wealth_index(returns, start=DATES[0])
    assert list(wealth.index) == list(DATES)
    assert wealth.tolist() == pytest.approx([1.0, 1.10, 0.99, 1.089])


def test_wealth_index_scales_with_initial_value() -> None:
    returns = simple_returns(PRICES)["A"]
    assert wealth_index(returns, start=DATES[0], initial=1000.0).iloc[-1] == pytest.approx(1089.0)


def test_non_finite_returns_are_rejected() -> None:
    with pytest.raises(DataValidationError, match="NaN or infinite"):
        total_return(pd.Series([0.01, float("nan")]))


def test_empty_returns_are_rejected() -> None:
    with pytest.raises(InsufficientDataError):
        total_return(pd.Series([], dtype=float))
