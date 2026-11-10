"""Correlation, concentration and risk decomposition.

Weights are assumed to be long-only and to sum to one. Both properties are enforced by
``portfolio_risk.io.validation.validate_weights`` before analysis.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from portfolio_risk._checks import is_constant
from portfolio_risk.errors import DataValidationError


def correlation_matrix(asset_returns: pd.DataFrame) -> pd.DataFrame:
    """Pearson correlation of asset returns. Raises if any series is constant."""
    for name in asset_returns.columns:
        if is_constant(asset_returns[name].to_numpy(dtype=np.float64)):
            raise DataValidationError(
                f"{name!r} has constant returns (zero variance); its correlation is undefined."
            )
    return asset_returns.corr()


def covariance_matrix(asset_returns: pd.DataFrame) -> pd.DataFrame:
    """Sample covariance (``ddof=1``) of per-period asset returns."""
    return asset_returns.cov()


def herfindahl_hirschman_index(weights: pd.Series) -> float:
    """Concentration index ``sum(w_i ** 2)``. Ranges from ``1 / N`` (equal weights) to 1."""
    values = weights.to_numpy(dtype=np.float64)
    return float(np.sum(values**2))


def effective_number_of_positions(weights: pd.Series) -> float:
    """Inverse of the HHI: the number of equally weighted positions with the same concentration."""
    return 1.0 / herfindahl_hirschman_index(weights)


def risk_contributions(covariance: pd.DataFrame, weights: pd.Series) -> pd.Series:
    """Each asset's share of portfolio variance (Euler decomposition).

    ``RC_i = w_i * (Sigma w)_i / (w' Sigma w)``. The shares sum to one. They can be negative
    for an asset that diversifies the rest of the portfolio.
    """
    names = list(weights.index)
    sigma = covariance.loc[names, names].to_numpy(dtype=np.float64)
    w = weights.to_numpy(dtype=np.float64)
    marginal = sigma @ w
    variance = float(w @ marginal)
    if not variance > 0.0:
        raise DataValidationError("Portfolio variance is zero; risk contributions are undefined.")
    return pd.Series(w * marginal / variance, index=weights.index, name="risk_contribution")
