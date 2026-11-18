"""Classic tearsheet statistics: side-by-side metrics, calendar returns and rolling series.

Everything here works on per-period simple returns and returns plain pandas objects. The
metric definitions follow the rest of the package (sample standard deviation, annualised by
``sqrt(periods_per_year)``; VaR and expected shortfall are historical, as positive losses).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from portfolio_risk import drawdown, returns, risk
from portfolio_risk.benchmark import benchmark_statistics
from portfolio_risk.errors import ConfigurationError, DataValidationError, InsufficientDataError

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MIN_OBSERVATIONS = 30


@dataclass(frozen=True, slots=True)
class Row:
    key: str
    label: str
    fmt: str  # "pct", "pct2", "ratio" or "int"


ROWS: tuple[Row, ...] = (
    Row("total_return", "Total return", "pct"),
    Row("cagr", "Annualised return (CAGR)", "pct"),
    Row("volatility", "Annualised volatility", "pct"),
    Row("sharpe", "Sharpe ratio", "ratio"),
    Row("sortino", "Sortino ratio", "ratio"),
    Row("calmar", "Calmar ratio", "ratio"),
    Row("max_dd", "Maximum drawdown", "pct"),
    Row("longest_dd", "Longest drawdown (periods)", "int"),
    Row("var95", "Value at Risk 95% (one period)", "pct2"),
    Row("es95", "Expected shortfall 95% (one period)", "pct2"),
    Row("skew", "Skewness", "ratio"),
    Row("kurtosis", "Excess kurtosis", "ratio"),
    Row("best", "Best period", "pct"),
    Row("worst", "Worst period", "pct"),
    Row("win_rate", "Positive periods", "pct"),
    Row("payoff", "Payoff ratio (average win / average loss)", "ratio"),
    Row("profit_factor", "Profit factor (total gains / total losses)", "ratio"),
    Row("best_month", "Best month", "pct"),
    Row("worst_month", "Worst month", "pct"),
    Row("positive_months", "Positive months", "pct"),
)
RELATIVE_ROWS: tuple[Row, ...] = (
    Row("beta", "Beta to benchmark", "ratio"),
    Row("alpha", "Alpha to benchmark (annualised)", "pct"),
    Row("correlation", "Correlation with benchmark", "ratio"),
    Row("tracking_error", "Tracking error", "pct"),
    Row("information_ratio", "Information ratio", "ratio"),
)


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 0.0 else math.nan


def monthly_returns(series: pd.Series) -> pd.Series:
    """Compound the per-period returns inside each calendar month (index: month end)."""
    grouped = (1.0 + series).groupby(pd.DatetimeIndex(series.index).to_period("M")).prod() - 1.0
    return grouped


def series_metrics(
    series: pd.Series, periods_per_year: int, rf_per_period: float, mar_per_period: float
) -> dict[str, float]:
    """Every row of :data:`ROWS` for one return series."""
    clean = series.dropna()
    if len(clean) < MIN_OBSERVATIONS:
        raise InsufficientDataError(
            f"A tearsheet needs at least {MIN_OBSERVATIONS} returns; got {len(clean)}."
        )
    values = clean.to_numpy(dtype=float)
    wealth = returns.wealth_index(clean, start=clean.index[0])
    summary = drawdown.summarise_drawdowns(wealth)
    cagr = returns.annualised_return(clean, periods_per_year)
    wins, losses = values[values > 0.0], values[values < 0.0]
    cut = float(np.quantile(values, 0.05))
    monthly = monthly_returns(clean).to_numpy(dtype=float)
    return {
        "total_return": returns.total_return(clean),
        "cagr": cagr,
        "volatility": risk.annualised_volatility(clean, periods_per_year),
        "sharpe": risk.sharpe_ratio(clean, rf_per_period, periods_per_year),
        "sortino": risk.sortino_ratio(clean, mar_per_period, periods_per_year),
        "calmar": _ratio(cagr, -summary.max_drawdown),
        "max_dd": summary.max_drawdown,
        "longest_dd": float(summary.longest_duration_periods),
        "var95": -cut,
        "es95": -float(values[values <= cut].mean()),
        "skew": float(np.asarray(clean.skew())),
        "kurtosis": float(np.asarray(clean.kurt())),
        "best": float(values.max()),
        "worst": float(values.min()),
        "win_rate": float((values > 0.0).mean()),
        "payoff": _ratio(
            float(wins.mean()) if wins.size else math.nan,
            -float(losses.mean()) if losses.size else 0.0,
        ),
        "profit_factor": _ratio(float(wins.sum()), -float(losses.sum())),
        "best_month": float(monthly.max()),
        "worst_month": float(monthly.min()),
        "positive_months": float((monthly > 0.0).mean()),
    }


def tearsheet_table(
    named: Mapping[str, pd.Series],
    *,
    periods_per_year: int,
    rf_per_period: float = 0.0,
    mar_per_period: float = 0.0,
    benchmark: str | None = None,
) -> pd.DataFrame:
    """Rows are statistics, columns are the named series (all on the same dates).

    With ``benchmark`` (one of the names) the relative rows are added; they are blank in the
    benchmark's own column.
    """
    if not named:
        raise ConfigurationError("Give at least one return series.")
    if benchmark is not None and benchmark not in named:
        raise ConfigurationError(f"Benchmark {benchmark!r} is not among the series.")
    frame = pd.DataFrame(
        {
            name: series_metrics(s, periods_per_year, rf_per_period, mar_per_period)
            for name, s in named.items()
        }
    )
    frame = frame.loc[[r.key for r in ROWS]]
    if benchmark is None:
        return frame
    blank = dict.fromkeys((r.key for r in RELATIVE_ROWS), math.nan)
    relative: dict[str, dict[str, float]] = {}
    for name, s in named.items():
        values = dict(blank)
        if name != benchmark:
            try:
                stats = benchmark_statistics(s, named[benchmark], rf_per_period, periods_per_year)
            except DataValidationError:
                pass
            else:
                values = {
                    "beta": stats.beta,
                    "alpha": stats.alpha_annualised,
                    "correlation": stats.correlation,
                    "tracking_error": stats.tracking_error,
                    "information_ratio": stats.information_ratio,
                }
        relative[name] = values
    return pd.concat([frame, pd.DataFrame(relative)])


def monthly_table(series: pd.Series) -> pd.DataFrame:
    """Calendar grid: one row per year, columns Jan to Dec and the compounded year."""
    monthly = monthly_returns(series.dropna())
    periods = pd.PeriodIndex(monthly.index)
    grid = pd.DataFrame(np.nan, index=sorted(set(periods.year)), columns=list(MONTHS))
    for year, month, value in zip(periods.year, periods.month, monthly.to_numpy(), strict=True):
        grid.loc[year, MONTHS[month - 1]] = float(value)
    yearly = (1.0 + monthly).groupby(periods.year).prod() - 1.0
    grid["Year"] = yearly
    return grid


def calendar_years(named: Mapping[str, pd.Series]) -> pd.DataFrame:
    """Compounded return per calendar year, one column per series. Partial years are included."""
    out = {}
    for name, series in named.items():
        clean = series.dropna()
        years = pd.DatetimeIndex(clean.index).year
        out[name] = (1.0 + clean).groupby(years).prod() - 1.0
    return pd.DataFrame(out)


def rolling_statistic(
    series: pd.Series,
    kind: str,
    window: int,
    *,
    periods_per_year: int,
    rf_per_period: float = 0.0,
    benchmark: pd.Series | None = None,
) -> pd.Series:
    """Rolling ``volatility``, ``sharpe`` or ``beta`` (needs ``benchmark``) over a window."""
    if window < 5:
        raise ConfigurationError("The rolling window must be at least 5 periods.")
    clean = series.dropna()
    if len(clean) < window + 1:
        raise InsufficientDataError(
            f"Need more than {window} returns for a {window}-period window."
        )
    roll = clean.rolling(window)
    if kind == "volatility":
        return roll.std(ddof=1) * math.sqrt(periods_per_year)
    if kind == "sharpe":
        excess = clean - rf_per_period
        spread = excess.rolling(window)
        std = spread.std(ddof=1).replace(0.0, np.nan)
        return spread.mean() / std * math.sqrt(periods_per_year)
    if kind == "beta":
        if benchmark is None:
            raise ConfigurationError("Rolling beta needs a benchmark.")
        other = benchmark.reindex(clean.index)
        variance = other.rolling(window).var(ddof=1).replace(0.0, np.nan)
        return clean.rolling(window).cov(other) / variance
    raise ConfigurationError(f"Unknown rolling statistic {kind!r}.")
