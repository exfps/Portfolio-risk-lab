"""Small argument checks shared by the metric modules."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pandas as pd

from portfolio_risk.errors import ConfigurationError, DataValidationError, InsufficientDataError


def finite_values(returns: pd.Series, *, minimum: int, statistic: str) -> npt.NDArray[np.float64]:
    """Return ``returns`` as a float array after checking length and finiteness."""
    values = returns.to_numpy(dtype=np.float64)
    if values.size < minimum:
        raise InsufficientDataError(
            f"{statistic} needs at least {minimum} observations; got {values.size}."
        )
    if not np.isfinite(values).all():
        raise DataValidationError(f"{statistic} received NaN or infinite returns.")
    return values


def is_constant(values: npt.NDArray[np.float64]) -> bool:
    """True when every element is identical. Exact comparison: no tolerance is applied."""
    return bool(values.min() == values.max())


def check_confidence(confidence: float) -> None:
    if not 0.5 < confidence < 1.0:
        raise ConfigurationError(
            f"Confidence level must be strictly between 0.5 and 1; got {confidence}."
        )
