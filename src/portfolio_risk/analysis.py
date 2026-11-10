"""Single entry point that turns prices and weights into a complete set of statistics."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from portfolio_risk import drawdown, exposure, returns, risk, var
from portfolio_risk.benchmark import BenchmarkStats, benchmark_statistics
from portfolio_risk.config import AnalysisConfig
from portfolio_risk.drawdown import DrawdownSummary
from portfolio_risk.io.validation import (
    check_columns,
    clean_prices,
    frequency_warnings,
    validate_weights,
)


@dataclass(frozen=True, slots=True)
class PerformanceSummary:
    total_return: float
    cagr: float
    annualised_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    drawdown: DrawdownSummary


@dataclass(frozen=True, slots=True)
class VarEstimate:
    """One-period VaR and CVaR at a single confidence level, as positive losses."""

    confidence: float
    historical_var: float
    historical_cvar: float
    parametric_var: float
    parametric_cvar: float


@dataclass(frozen=True, slots=True, eq=False)
class AnalysisResult:
    config: AnalysisConfig
    start: pd.Timestamp
    end: pd.Timestamp
    observations: int
    weights: pd.Series
    portfolio_returns: pd.Series
    wealth: pd.Series
    drawdowns: pd.Series
    performance: PerformanceSummary
    var: tuple[VarEstimate, ...]
    correlation: pd.DataFrame
    asset_table: pd.DataFrame
    hhi: float
    effective_positions: float
    risk_contribution: pd.Series
    benchmark: BenchmarkStats | None
    warnings: tuple[str, ...]


def analyse(
    prices: pd.DataFrame,
    weights: pd.Series,
    config: AnalysisConfig | None = None,
    benchmark: str | None = None,
    *,
    normalise_weights: bool = False,
) -> AnalysisResult:
    """Analyse a constant-weight portfolio.

    ``prices`` holds one column per weighted asset, plus the ``benchmark`` column if given.
    Weights must be long-only and sum to one unless ``normalise_weights`` is true.
    Raises ``DataValidationError`` for unusable input; recoverable issues are returned in
    ``AnalysisResult.warnings``.
    """
    config = config or AnalysisConfig()
    weights, notes = validate_weights(weights, normalise=normalise_weights)
    check_columns(prices, weights, benchmark)

    wanted = [*weights.index, *([benchmark] if benchmark is not None else [])]
    levels, cleaning_notes = clean_prices(prices[wanted], min_observations=config.min_observations)
    notes += cleaning_notes
    notes += frequency_warnings(pd.DatetimeIndex(levels.index), config.periods_per_year)

    ppy = config.periods_per_year
    period_returns = returns.simple_returns(levels)
    asset_returns = period_returns[list(weights.index)]
    portfolio = returns.portfolio_returns(asset_returns, weights)

    start = pd.Timestamp(levels.index[0])
    wealth = returns.wealth_index(portfolio, start=start)
    covariance = exposure.covariance_matrix(asset_returns)
    contributions = exposure.risk_contributions(covariance, weights)

    performance = PerformanceSummary(
        total_return=returns.total_return(portfolio),
        cagr=returns.annualised_return(portfolio, ppy),
        annualised_volatility=risk.annualised_volatility(portfolio, ppy),
        sharpe_ratio=risk.sharpe_ratio(portfolio, config.risk_free_per_period, ppy),
        sortino_ratio=risk.sortino_ratio(portfolio, config.mar_per_period, ppy),
        drawdown=drawdown.summarise_drawdowns(wealth),
    )

    var_table = tuple(
        VarEstimate(
            confidence=level,
            historical_var=var.historical_var(portfolio, level),
            historical_cvar=var.historical_cvar(portfolio, level),
            parametric_var=var.parametric_var(portfolio, level),
            parametric_cvar=var.parametric_cvar(portfolio, level),
        )
        for level in config.confidence_levels
    )

    asset_table = pd.DataFrame(
        {
            "weight": weights,
            "annualised_return": [
                returns.annualised_return(asset_returns[name], ppy) for name in weights.index
            ],
            "annualised_volatility": [
                risk.annualised_volatility(asset_returns[name], ppy) for name in weights.index
            ],
            "max_drawdown": [
                float(drawdown.drawdown_series(levels[name]).min()) for name in weights.index
            ],
            "risk_contribution": contributions,
        },
        index=weights.index,
    )

    benchmark_stats = (
        benchmark_statistics(portfolio, period_returns[benchmark], config.risk_free_per_period, ppy)
        if benchmark is not None
        else None
    )

    return AnalysisResult(
        config=config,
        start=start,
        end=pd.Timestamp(levels.index[-1]),
        observations=int(np.size(portfolio)),
        weights=weights,
        portfolio_returns=portfolio,
        wealth=wealth,
        drawdowns=drawdown.drawdown_series(wealth),
        performance=performance,
        var=var_table,
        correlation=exposure.correlation_matrix(asset_returns),
        asset_table=asset_table,
        hhi=exposure.herfindahl_hirschman_index(weights),
        effective_positions=exposure.effective_number_of_positions(weights),
        risk_contribution=contributions,
        benchmark=benchmark_stats,
        warnings=tuple(notes),
    )
