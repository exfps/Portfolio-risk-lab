"""Run a fitted return model through a portfolio with rebalancing and transaction costs."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

from portfolio_risk.errors import ConfigurationError, DataValidationError
from portfolio_risk.simulation.models import ReturnModel
from portfolio_risk.simulation.prepare import PreparedReturns, prepare_returns

Array = npt.NDArray[np.float64]
FREQUENCIES = {"daily": 252, "weekly": 52, "monthly": 12}
REBALANCING = ("never", "every period", "monthly", "quarterly", "annually")
_CHUNK_BUDGET = 2_000_000  # simulated return values held in memory at once


@dataclass(frozen=True)
class SimulationConfig:
    """Assumptions for one simulation run. All of them appear in the report."""

    n_paths: int = 10_000
    horizon_years: float = 5.0
    frequency: str = "daily"
    seed: int | None = None
    rebalancing: str = "every period"
    transaction_cost: float = 0.0  # fraction of traded value; 0.001 is 10 basis points
    initial_value: float = 100_000.0
    bust_drawdown: float = 0.25  # a path "busts" if it ever falls this far below its peak
    target_return: float = 0.50  # the goal: ending value this far above the start

    def __post_init__(self) -> None:
        if not 10 <= self.n_paths <= 200_000:
            raise ConfigurationError(f"n_paths must be between 10 and 200000; got {self.n_paths}.")
        if self.frequency not in FREQUENCIES:
            raise ConfigurationError(f"frequency must be one of {sorted(FREQUENCIES)}.")
        if self.rebalancing not in REBALANCING:
            raise ConfigurationError(f"rebalancing must be one of {list(REBALANCING)}.")
        if not self.horizon_years > 0 or self.n_periods < 1:
            raise ConfigurationError("The horizon must cover at least one period.")
        if not 0.0 <= self.transaction_cost <= 0.1:
            raise ConfigurationError("transaction_cost must be between 0 and 0.1 (10%).")
        if not self.initial_value > 0:
            raise ConfigurationError("initial_value must be positive.")
        if not 0.0 < self.bust_drawdown < 1.0:
            raise ConfigurationError("bust_drawdown must be between 0 and 1.")
        if not self.target_return > 0:
            raise ConfigurationError("target_return must be positive.")

    @property
    def periods_per_year(self) -> int:
        return FREQUENCIES[self.frequency]

    @property
    def n_periods(self) -> int:
        return round(self.horizon_years * self.periods_per_year)

    @property
    def rebalance_every(self) -> int | None:
        """Rebalance interval in periods, or None for buy-and-hold."""
        ppy = self.periods_per_year
        monthly = max(1, round(ppy / 12))
        return {
            "never": None,
            "every period": 1,
            "monthly": monthly,
            "quarterly": max(1, round(ppy / 4)),
            "annually": ppy,
        }[self.rebalancing]


def to_frequency(returns: pd.DataFrame, source_periods_per_year: int, target: str) -> pd.DataFrame:
    """Compound returns to the simulation frequency (daily to weekly or monthly).

    Partial periods at the edges of the history are dropped, because a three-day "week"
    would understate that period's variance.
    """
    if target not in FREQUENCIES:
        raise ConfigurationError(f"frequency must be one of {sorted(FREQUENCIES)}.")
    wanted = FREQUENCIES[target]
    if source_periods_per_year == wanted:
        return returns
    if source_periods_per_year < wanted:
        raise ConfigurationError(
            f"The history has {source_periods_per_year} periods a year, so a {target} "
            "simulation is not possible. Choose a lower frequency."
        )
    if not isinstance(returns.index, pd.DatetimeIndex):
        raise DataValidationError("Converting frequency needs a date index.")
    rule = "W-FRI" if target == "weekly" else "ME"
    grouped = returns.resample(rule)
    compounded = (1.0 + returns).groupby(pd.Grouper(freq=rule)).prod() - 1.0
    counts = grouped.size()
    keep = counts >= 0.6 * counts.median()
    return compounded.loc[keep.to_numpy()]


def check_weights(weights: pd.Series, assets: list[str]) -> Array:
    """Return weights as an array in ``assets`` order after checking they are usable."""
    missing = [a for a in assets if a not in weights.index]
    if missing or len(weights) != len(assets):
        raise DataValidationError("Weights must name exactly the assets that have returns.")
    values = weights.loc[assets].to_numpy(dtype=np.float64)
    if not np.isfinite(values).all() or (values < 0).any():
        raise DataValidationError("Simulation weights must be finite and not negative.")
    if abs(values.sum() - 1.0) > 1e-6:
        raise DataValidationError(f"Weights must sum to 1; they sum to {values.sum():.6f}.")
    return values


def _grow(returns: Array, weights: Array, config: SimulationConfig) -> Array:
    """Portfolio value paths ``(paths, periods + 1)`` for one chunk of simulated returns."""
    paths, periods, _ = returns.shape
    every = config.rebalance_every
    holdings = np.tile(config.initial_value * weights, (paths, 1))
    value = np.empty((paths, periods + 1))
    value[:, 0] = config.initial_value
    for t in range(periods):
        holdings *= 1.0 + returns[:, t, :]
        total = holdings.sum(axis=1)
        if every is not None and (t + 1) % every == 0 and t + 1 < periods:
            target = total[:, None] * weights
            traded = np.abs(target - holdings).sum(axis=1)
            total = total - config.transaction_cost * traded
            holdings = total[:, None] * weights
        value[:, t + 1] = total
    return value


def simulate_values(
    model: ReturnModel, weights: Array, config: SimulationConfig
) -> npt.NDArray[np.float32]:
    """Simulate portfolio value paths in memory-bounded chunks.

    Values are stored as float32 (about 50 MB for 10,000 daily paths over five years);
    all arithmetic is done in float64. Results depend on the seed, the inputs and the chunk
    size, and the chunk size is a fixed function of the horizon and asset count.
    """
    periods = config.n_periods
    chunk = max(1, _CHUNK_BUDGET // (periods * len(weights)))
    count = -(-config.n_paths // chunk)
    seeds = np.random.SeedSequence(config.seed).spawn(count)
    out = np.empty((config.n_paths, periods + 1), dtype=np.float32)
    for k, seed in enumerate(seeds):
        lo, hi = k * chunk, min((k + 1) * chunk, config.n_paths)
        rng = np.random.default_rng(seed)
        draws = model.simulate(hi - lo, periods, rng)
        out[lo:hi] = _grow(draws, weights, config)
    return out


def prepare_for_simulation(
    returns: pd.DataFrame, config: SimulationConfig, *, source_periods_per_year: int = 252
) -> PreparedReturns:
    """Convert to the simulation frequency, then validate."""
    return prepare_returns(to_frequency(returns, source_periods_per_year, config.frequency))
