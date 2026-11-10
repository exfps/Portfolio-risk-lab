"""Volatility and risk-adjusted return ratios.

All functions take a series of per-period simple returns. Ratios are annualised by
``sqrt(periods_per_year)``, which assumes returns are serially uncorrelated.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from portfolio_risk._checks import finite_values, is_constant


def annualised_volatility(returns: pd.Series, periods_per_year: int) -> float:
    """Sample standard deviation (``ddof=1``) scaled by ``sqrt(periods_per_year)``."""
    values = finite_values(returns, minimum=2, statistic="Volatility")
    return float(values.std(ddof=1)) * math.sqrt(periods_per_year)


def sharpe_ratio(returns: pd.Series, risk_free_per_period: float, periods_per_year: int) -> float:
    """Annualised Sharpe ratio.

    ``mean(r - rf) / std(r - rf, ddof=1) * sqrt(periods_per_year)``

    Returns NaN when the series is constant, because the ratio is undefined.
    """
    values = finite_values(returns, minimum=2, statistic="Sharpe ratio")
    if is_constant(values):
        return math.nan
    excess = values - risk_free_per_period
    return float(excess.mean() / excess.std(ddof=1)) * math.sqrt(periods_per_year)


def downside_deviation(returns: pd.Series, mar_per_period: float) -> float:
    """Per-period downside deviation relative to a minimum acceptable return (MAR).

    ``sqrt(mean(min(r - MAR, 0) ** 2))`` with the mean taken over *all* observations,
    not only those below the MAR.
    """
    values = finite_values(returns, minimum=2, statistic="Downside deviation")
    shortfall = np.minimum(values - mar_per_period, 0.0)
    return float(np.sqrt(np.mean(shortfall**2)))


def sortino_ratio(returns: pd.Series, mar_per_period: float, periods_per_year: int) -> float:
    """Annualised Sortino ratio.

    ``(mean(r) - MAR) / downside_deviation * sqrt(periods_per_year)``

    Returns NaN when no observation falls below the MAR, because the ratio is undefined.
    """
    values = finite_values(returns, minimum=2, statistic="Sortino ratio")
    deviation = downside_deviation(returns, mar_per_period)
    if deviation == 0.0:
        return math.nan
    return float(values.mean() - mar_per_period) / deviation * math.sqrt(periods_per_year)
