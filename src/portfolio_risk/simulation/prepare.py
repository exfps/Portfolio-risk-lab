"""Validation of the historical returns that feed the simulation models."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from portfolio_risk.errors import DataValidationError, InsufficientDataError

MIN_OBSERVATIONS = 60
SHORT_HISTORY = 252


@dataclass(frozen=True)
class PreparedReturns:
    """Validated simple returns, one column per asset, plus any quality warnings."""

    returns: pd.DataFrame
    warnings: tuple[str, ...]

    @property
    def window(self) -> str:
        """The estimation window, stated in every simulation result."""
        index = self.returns.index
        return f"{index[0]:%Y-%m-%d} to {index[-1]:%Y-%m-%d} ({len(index)} observations)"


def prepare_returns(returns: pd.DataFrame, *, minimum: int = MIN_OBSERVATIONS) -> PreparedReturns:
    """Check that ``returns`` can be used to fit a simulation model.

    Rejects missing or infinite values rather than filling them, because a silent fill would
    change the estimated mean and covariance without the user knowing.
    """
    if returns.shape[1] == 0:
        raise DataValidationError("Simulation needs at least one asset.")
    if len(returns) < minimum:
        raise InsufficientDataError(
            f"Simulation needs at least {minimum} return observations; got {len(returns)}."
        )
    values = returns.to_numpy(dtype=np.float64)
    if not np.isfinite(values).all():
        raise DataValidationError("Returns contain NaN or infinite values; clean them first.")
    if (values <= -1.0).any():
        raise DataValidationError("Returns contain a loss of 100% or more, which is not a price.")
    notes: list[str] = []
    if len(returns) < SHORT_HISTORY:
        notes.append(
            f"Only {len(returns)} observations: estimates of mean and covariance are unreliable."
        )
    constant = [str(c) for c in returns.columns if returns[c].nunique() == 1]
    if constant:
        notes.append(f"Constant return series (no variation): {', '.join(constant)}.")
    return PreparedReturns(returns, tuple(notes))
