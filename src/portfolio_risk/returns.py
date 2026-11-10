"""Return calculations.

Conventions
-----------
* Returns are simple (arithmetic) period returns expressed as decimals: 0.01 is one percent.
* A return series with ``n`` observations is derived from ``n + 1`` prices.
* Portfolio returns assume constant weights, that is, rebalancing to the target weights
  every period. Buy-and-hold drift is not modelled.
"""

from __future__ import annotations

import math
from collections.abc import Hashable

import numpy as np
import pandas as pd

from portfolio_risk._checks import finite_values
from portfolio_risk.errors import DataValidationError


def to_period_rate(annual_rate: float, periods_per_year: int) -> float:
    """Convert an annual rate to a per-period rate by geometric de-compounding.

    ``(1 + annual) ** (1 / periods_per_year) - 1``.
    """
    return float((1.0 + annual_rate) ** (1.0 / periods_per_year) - 1.0)


def simple_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Simple returns ``P_t / P_{t-1} - 1``. The first row, which has no predecessor, is dropped."""
    return (prices / prices.shift(1) - 1.0).iloc[1:]


def portfolio_returns(asset_returns: pd.DataFrame, weights: pd.Series) -> pd.Series:
    """Weighted sum of asset returns, ``r_p = w' r``, for constant weights.

    Only the columns named in ``weights`` are used, in the order of ``weights.index``.
    """
    missing = [name for name in weights.index if name not in asset_returns.columns]
    if missing:
        raise DataValidationError(f"No return series for weighted assets: {missing}.")
    matrix = asset_returns.loc[:, list(weights.index)].to_numpy(dtype=np.float64)
    combined = matrix @ weights.to_numpy(dtype=np.float64)
    return pd.Series(combined, index=asset_returns.index, name="portfolio")


def wealth_index(returns: pd.Series, start: Hashable, initial: float = 1.0) -> pd.Series:
    """Cumulative value of ``initial`` invested at ``start`` and compounded by ``returns``.

    The result has ``len(returns) + 1`` points: the initial value labelled ``start`` followed
    by the value after each return.
    """
    values = finite_values(returns, minimum=1, statistic="Wealth index")
    levels = initial * np.cumprod(1.0 + values)
    index = pd.Index([start, *returns.index])
    return pd.Series(np.concatenate(([initial], levels)), index=index, name="wealth")


def total_return(returns: pd.Series) -> float:
    """Compounded return over the whole sample, ``prod(1 + r) - 1``."""
    values = finite_values(returns, minimum=1, statistic="Total return")
    return float(np.expm1(np.log1p(values).sum()))


def annualised_return(returns: pd.Series, periods_per_year: int) -> float:
    """Compound annual growth rate, ``prod(1 + r) ** (periods_per_year / n) - 1``."""
    values = finite_values(returns, minimum=1, statistic="Annualised return")
    log_growth = float(np.log1p(values).sum())
    return math.expm1(log_growth * periods_per_year / values.size)
