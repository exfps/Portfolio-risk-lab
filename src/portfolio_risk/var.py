"""Value at Risk (VaR) and Conditional VaR (CVaR, also called expected shortfall).

Conventions
-----------
* Results are reported as **positive losses** in return units: 0.02 means a 2% loss.
  A negative value means the quantile itself is a gain.
* The horizon is one observation period. No square-root-of-time scaling is applied.
* ``confidence`` is the probability that the loss will not exceed VaR, e.g. 0.95.
"""

from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd

from portfolio_risk._checks import check_confidence, finite_values

_STANDARD_NORMAL = NormalDist()


def _tail_quantile(values: np.ndarray, confidence: float) -> float:
    """Return-space quantile at probability ``1 - confidence`` with linear interpolation."""
    return float(np.quantile(values, 1.0 - confidence, method="linear"))


def historical_var(returns: pd.Series, confidence: float) -> float:
    """Empirical VaR: the negated ``1 - confidence`` quantile of observed returns."""
    check_confidence(confidence)
    values = finite_values(returns, minimum=2, statistic="Historical VaR")
    return -_tail_quantile(values, confidence)


def historical_cvar(returns: pd.Series, confidence: float) -> float:
    """Empirical CVaR: the negated mean of all returns at or below the quantile."""
    check_confidence(confidence)
    values = finite_values(returns, minimum=2, statistic="Historical CVaR")
    quantile = _tail_quantile(values, confidence)
    return -float(values[values <= quantile].mean())


def parametric_var(returns: pd.Series, confidence: float) -> float:
    """Normal VaR: ``-mu + sigma * z`` where ``z`` is the standard normal quantile."""
    check_confidence(confidence)
    values = finite_values(returns, minimum=2, statistic="Parametric VaR")
    z = _STANDARD_NORMAL.inv_cdf(confidence)
    return -float(values.mean()) + float(values.std(ddof=1)) * z


def parametric_cvar(returns: pd.Series, confidence: float) -> float:
    """Normal CVaR: ``-mu + sigma * phi(z) / (1 - confidence)``."""
    check_confidence(confidence)
    values = finite_values(returns, minimum=2, statistic="Parametric CVaR")
    z = _STANDARD_NORMAL.inv_cdf(confidence)
    tail_mean = _STANDARD_NORMAL.pdf(z) / (1.0 - confidence)
    return -float(values.mean()) + float(values.std(ddof=1)) * tail_mean
