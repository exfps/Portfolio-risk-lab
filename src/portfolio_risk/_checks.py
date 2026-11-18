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


#: Spread below which a series is treated as constant. Returns are of order 1e-2, so a spread
#: under 1e-12 is floating-point noise (for example from prices compounding at a fixed rate),
#: and dividing by the resulting standard deviation would give meaningless ratios of 1e13.
CONSTANT_TOLERANCE = 1e-12


def is_constant(values: npt.NDArray[np.float64]) -> bool:
    """True when every element is equal up to floating-point noise (``CONSTANT_TOLERANCE``)."""
    scale = max(1.0, float(np.abs(values).max()))
    return bool(float(np.ptp(values)) <= CONSTANT_TOLERANCE * scale)


def check_confidence(confidence: float) -> None:
    if not 0.5 < confidence < 1.0:
        raise ConfigurationError(
            f"Confidence level must be strictly between 0.5 and 1; got {confidence}."
        )
