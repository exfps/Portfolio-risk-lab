"""Risk and outcome statistics computed per simulated path and across paths.

Per-path statistics (maximum drawdown, volatility, longest underwater spell) describe one
possible future; across-path statistics (percentiles, VaR) describe the distribution of
outcomes. They answer different questions and are never mixed.

Conventions
-----------
* VaR and expected shortfall are losses over the whole horizon, reported as positive numbers
  in return units: 0.15 means a 15% loss. They are not annualised.
* Drawdowns are negative fractions: -0.25 means 25% below the previous peak.
* All statistics describe the model's simulated paths, not forecasts.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

from portfolio_risk.simulation.engine import SimulationConfig

Array = npt.NDArray[np.float64]
PERCENTILES = (5, 10, 25, 50, 75, 90, 95)
BAND_QUANTILES = (0.05, 0.25, 0.50, 0.75, 0.95)
_BLOCK = 500


@dataclass(frozen=True)
class Summary:
    ending_mean: float
    ending_percentiles: dict[int, float]
    cagr_p05: float
    cagr_median: float
    cagr_p95: float
    volatility_median: float
    prob_loss: float
    var_95: float
    var_99: float
    es_95: float
    es_99: float
    max_drawdown_median: float
    max_drawdown_worst_5pct: float
    prob_bust: float
    prob_target_end: float
    prob_target_touch: float
    longest_drawdown_median: float
    longest_drawdown_p95: float


@dataclass(frozen=True)
class PathStats:
    """One value per simulated path."""

    ending: Array
    cagr: Array
    max_drawdown: Array
    volatility: Array
    longest_drawdown: Array
    peak: Array


@dataclass(frozen=True)
class SimulationResult:
    model: str
    window: str
    warnings: tuple[str, ...]
    config: SimulationConfig
    summary: Summary
    paths: PathStats
    bands: pd.DataFrame
    worst_paths: Array


def var_es(horizon_returns: Array, confidence: float) -> tuple[float, float]:
    """Value at Risk and expected shortfall of horizon returns, as positive losses."""
    cutoff = float(np.quantile(horizon_returns, 1.0 - confidence))
    tail = horizon_returns[horizon_returns <= cutoff]
    return -cutoff, -float(tail.mean())


def longest_underwater(drawdown: npt.NDArray[np.float64]) -> npt.NDArray[np.int64]:
    """Length, in periods, of the longest spell below the previous peak, per path."""
    under = drawdown < 0.0
    position = np.arange(under.shape[1])
    last_clear = np.maximum.accumulate(np.where(under, -1, position), axis=1)
    return np.asarray((np.where(under, position - last_clear, 0)).max(axis=1), dtype=np.int64)


def _path_stats(values: npt.NDArray[np.float32], config: SimulationConfig) -> PathStats:
    ending, cagr, mdd, vol, longest, peak = [], [], [], [], [], []
    years = config.horizon_years
    for lo in range(0, len(values), _BLOCK):
        block = values[lo : lo + _BLOCK].astype(np.float64)
        end = block[:, -1].copy()  # a view would keep the whole block alive
        running = np.maximum.accumulate(block, axis=1)
        drawdown = block / running - 1.0
        prior = block[:, :-1]
        steps = np.divide(block[:, 1:], prior, out=np.ones_like(prior), where=prior > 0) - 1.0
        ending.append(end)
        cagr.append((end / config.initial_value) ** (1.0 / years) - 1.0)
        mdd.append(drawdown.min(axis=1))
        vol.append(steps.std(axis=1, ddof=1) * np.sqrt(config.periods_per_year))
        longest.append(longest_underwater(drawdown).astype(np.float64))
        peak.append(running[:, -1].copy())
    return PathStats(*(np.concatenate(part) for part in (ending, cagr, mdd, vol, longest, peak)))


def summarise(
    values: npt.NDArray[np.float32], config: SimulationConfig
) -> tuple[Summary, PathStats]:
    stats = _path_stats(values, config)
    start = config.initial_value
    horizon = stats.ending / start - 1.0
    var95, es95 = var_es(horizon, 0.95)
    var99, es99 = var_es(horizon, 0.99)
    q = np.quantile
    target_value = start * (1.0 + config.target_return)
    summary = Summary(
        ending_mean=float(stats.ending.mean()),
        ending_percentiles={p: float(q(stats.ending, p / 100)) for p in PERCENTILES},
        cagr_p05=float(q(stats.cagr, 0.05)),
        cagr_median=float(q(stats.cagr, 0.5)),
        cagr_p95=float(q(stats.cagr, 0.95)),
        volatility_median=float(np.median(stats.volatility)),
        prob_loss=float((stats.ending < start).mean()),
        var_95=var95,
        var_99=var99,
        es_95=es95,
        es_99=es99,
        max_drawdown_median=float(np.median(stats.max_drawdown)),
        max_drawdown_worst_5pct=float(q(stats.max_drawdown, 0.05)),
        prob_bust=float((stats.max_drawdown <= -config.bust_drawdown).mean()),
        prob_target_end=float((stats.ending >= target_value).mean()),
        prob_target_touch=float((stats.peak >= target_value).mean()),
        longest_drawdown_median=float(np.median(stats.longest_drawdown)),
        longest_drawdown_p95=float(q(stats.longest_drawdown, 0.95)),
    )
    return summary, stats


MAX_BAND_POINTS = 300


def band_columns(n_columns: int) -> npt.NDArray[np.intp]:
    """Evenly spaced columns to plot, always including the first and the last.

    A chart cannot show more than a few hundred points, so computing percentiles for every
    daily step of a ten-year path only costs time and memory.
    """
    if n_columns <= MAX_BAND_POINTS:
        return np.arange(n_columns)
    picks = np.linspace(0, n_columns - 1, MAX_BAND_POINTS).round().astype(np.intp)
    return np.unique(picks)


def fan_bands(values: npt.NDArray[np.float32], config: SimulationConfig) -> pd.DataFrame:
    """Percentile bands of portfolio value over time, indexed in years (thinned for charts)."""
    columns = band_columns(values.shape[1])
    bands = np.quantile(values[:, columns], BAND_QUANTILES, axis=0)
    index = columns / config.periods_per_year
    return pd.DataFrame(
        bands.T,
        index=pd.Index(index, name="years"),
        columns=[f"p{int(x * 100):02d}" for x in BAND_QUANTILES],
    )
