"""Benchmark-relative statistics."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from portfolio_risk._checks import finite_values, is_constant
from portfolio_risk.errors import DataValidationError


@dataclass(frozen=True, slots=True)
class BenchmarkStats:
    """Portfolio versus benchmark.

    ``beta`` and ``alpha_annualised`` come from an OLS regression of portfolio excess returns
    on benchmark excess returns. ``alpha_annualised`` is the per-period intercept multiplied
    by ``periods_per_year`` (Jensen's alpha, arithmetic annualisation).
    ``tracking_error`` is the annualised standard deviation of active returns ``r_p - r_b``.
    ``information_ratio`` is annualised mean active return divided by tracking error.
    """

    beta: float
    alpha_annualised: float
    correlation: float
    r_squared: float
    active_return_annualised: float
    tracking_error: float
    information_ratio: float


def benchmark_statistics(
    portfolio: pd.Series,
    benchmark: pd.Series,
    risk_free_per_period: float,
    periods_per_year: int,
) -> BenchmarkStats:
    if not portfolio.index.equals(benchmark.index):
        raise DataValidationError("Portfolio and benchmark returns must share the same dates.")
    p = finite_values(portfolio, minimum=3, statistic="Benchmark statistics")
    b = finite_values(benchmark, minimum=3, statistic="Benchmark statistics")
    if is_constant(b):
        raise DataValidationError(
            "The benchmark has constant returns (zero variance); beta is undefined."
        )

    excess_p = p - risk_free_per_period
    excess_b = b - risk_free_per_period
    covariance = float(np.cov(excess_p, excess_b, ddof=1)[0, 1])
    beta = covariance / float(excess_b.var(ddof=1))
    alpha_per_period = float(excess_p.mean()) - beta * float(excess_b.mean())

    correlation = math.nan if is_constant(p) else float(np.corrcoef(p, b)[0, 1])

    active = p - b
    active_return = float(active.mean()) * periods_per_year
    if is_constant(active):
        tracking_error = 0.0
        information_ratio = math.nan
    else:
        tracking_error = float(active.std(ddof=1)) * math.sqrt(periods_per_year)
        information_ratio = active_return / tracking_error

    return BenchmarkStats(
        beta=beta,
        alpha_annualised=alpha_per_period * periods_per_year,
        correlation=correlation,
        r_squared=correlation**2,
        active_return_annualised=active_return,
        tracking_error=tracking_error,
        information_ratio=information_ratio,
    )
