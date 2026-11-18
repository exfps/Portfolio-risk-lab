"""Tearsheet statistics against hand calculations.

Fixture: 40 business days from 2024-01-01 alternating +2%, -1%, +2%, ... (20 of each), with
40 periods per year so the 40 returns span exactly one year. Then, by hand:

* growth = (1.02 * 0.99) ** 20, and CAGR equals the total return;
* the deepest drawdown is 0.99 - 1 = -1% (every dip is recovered by the next gain);
* wins average 2%, losses average 1%: payoff 2, profit factor 2 (0.40 / 0.20), win rate 50%;
* the 5% quantile is -1%, so VaR and expected shortfall are both 1%;
* the two-point distribution is symmetric, so skewness is zero;
* standard deviation is 0.015 * sqrt(40 / 39).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from portfolio_risk.drawdown import drawdown_periods
from portfolio_risk.errors import ConfigurationError, InsufficientDataError
from portfolio_risk.tearsheet import (
    RELATIVE_ROWS,
    ROWS,
    calendar_years,
    monthly_table,
    rolling_statistic,
    series_metrics,
    tearsheet_table,
)

INDEX = pd.bdate_range("2024-01-01", periods=40)
ALTERNATING = pd.Series(np.tile([0.02, -0.01], 20), index=INDEX)
GROWTH = (1.02 * 0.99) ** 20


def test_each_statistic_matches_the_hand_calculation() -> None:
    m = series_metrics(ALTERNATING, 40, 0.0, 0.0)
    assert m["total_return"] == pytest.approx(GROWTH - 1)
    assert m["cagr"] == pytest.approx(GROWTH - 1)
    assert m["volatility"] == pytest.approx(0.015 * math.sqrt(40 / 39) * math.sqrt(40))
    assert m["max_dd"] == pytest.approx(-0.01)
    assert m["calmar"] == pytest.approx((GROWTH - 1) / 0.01)
    assert m["var95"] == pytest.approx(0.01)
    assert m["es95"] == pytest.approx(0.01)
    assert m["skew"] == pytest.approx(0.0, abs=1e-9)
    assert m["best"] == pytest.approx(0.02)
    assert m["worst"] == pytest.approx(-0.01)
    assert m["win_rate"] == pytest.approx(0.5)
    assert m["payoff"] == pytest.approx(2.0)
    assert m["profit_factor"] == pytest.approx(2.0)
    assert m["sharpe"] == pytest.approx(0.005 / (0.015 * math.sqrt(40 / 39)) * math.sqrt(40))


def test_monthly_statistics() -> None:
    # January has 23 business days (12 gains, 11 losses); February's 17 start with a loss.
    jan = 1.02**12 * 0.99**11 - 1
    feb = 1.02**8 * 0.99**9 - 1
    m = series_metrics(ALTERNATING, 40, 0.0, 0.0)
    assert m["best_month"] == pytest.approx(max(jan, feb))
    assert m["worst_month"] == pytest.approx(min(jan, feb))
    assert m["positive_months"] == pytest.approx(0.5 if min(jan, feb) < 0 < max(jan, feb) else 1.0)

    grid = monthly_table(ALTERNATING)
    assert list(grid.index) == [2024]
    assert grid.loc[2024, "Jan"] == pytest.approx(jan)
    assert grid.loc[2024, "Feb"] == pytest.approx(feb)
    assert grid.loc[2024, "Year"] == pytest.approx(GROWTH - 1)
    assert grid.loc[2024].drop(["Jan", "Feb", "Year"]).isna().all()


def test_the_year_column_compounds_months_across_years() -> None:
    index = pd.bdate_range("2023-11-01", periods=90)
    grid = monthly_table(pd.Series(0.001, index=index))
    assert list(grid.index) == [2023, 2024]
    assert grid.loc[2023, "Year"] == pytest.approx((1.001) ** 43 - 1)  # 22 Nov + 21 Dec days
    years = calendar_years({"x": pd.Series(0.001, index=index)})
    assert years["x"].to_numpy() == pytest.approx(grid["Year"].to_numpy())


def test_benchmark_relative_rows() -> None:
    bench = ALTERNATING.copy()
    twice = bench * 2.0
    table = tearsheet_table(
        {"Portfolio": twice, "Benchmark": bench},
        periods_per_year=40,
        benchmark="Benchmark",
    )
    assert list(table.index) == [r.key for r in ROWS] + [r.key for r in RELATIVE_ROWS]
    assert table.loc["beta", "Portfolio"] == pytest.approx(2.0)
    assert table.loc["alpha", "Portfolio"] == pytest.approx(0.0, abs=1e-12)
    assert table.loc["correlation", "Portfolio"] == pytest.approx(1.0)
    assert table["Benchmark"].loc[[r.key for r in RELATIVE_ROWS]].isna().all()
    totals = table.loc["total_return"].to_numpy(dtype=float)
    assert totals[0] > totals[1]


def test_without_a_benchmark_only_the_standard_rows_appear() -> None:
    table = tearsheet_table({"A": ALTERNATING}, periods_per_year=40)
    assert list(table.index) == [r.key for r in ROWS]


def test_no_losses_make_the_ratios_undefined_rather_than_infinite() -> None:
    up = pd.Series(0.001, index=INDEX)
    m = series_metrics(up, 40, 0.0, 0.0)
    assert math.isnan(m["payoff"])
    assert math.isnan(m["profit_factor"])
    assert math.isnan(m["calmar"])
    assert m["win_rate"] == 1.0


def test_drawdown_episodes() -> None:
    levels = pd.Series(
        [1.0, 1.1, 0.99, 1.0, 1.2, 1.14, 1.2, 1.1, 1.14],
        index=pd.bdate_range("2024-01-01", periods=9),
    )
    episodes = drawdown_periods(levels)
    assert len(episodes) == 3
    first = episodes.iloc[0]  # 1.1 -> 0.99 is the deepest: -10%, recovered at 1.2
    assert first["depth"] == pytest.approx(0.99 / 1.1 - 1)
    assert first["start"] == levels.index[1]
    assert first["trough"] == levels.index[2]
    assert first["end"] == levels.index[4]
    assert first["periods"] == 3
    assert bool(first["recovered"])
    assert episodes["depth"].is_monotonic_increasing  # deepest first
    open_ = episodes.iloc[1]  # 1.2 -> 1.1 -> 1.14 never regains 1.2: -8.3%
    assert open_["depth"] == pytest.approx(1.1 / 1.2 - 1)
    assert not bool(open_["recovered"])
    assert pd.isna(open_["end"])
    assert open_["periods"] == 2
    assert episodes.iloc[2]["depth"] == pytest.approx(1.14 / 1.2 - 1)


def test_a_series_that_never_falls_has_no_episodes() -> None:
    levels = pd.Series([1.0, 1.1, 1.2], index=pd.bdate_range("2024-01-01", periods=3))
    assert drawdown_periods(levels).empty


def test_drawdown_periods_limit() -> None:
    levels = pd.Series(
        np.tile([1.0, 0.9], 20) * np.repeat(np.arange(1, 21) * 0.1 + 1, 2),
        index=pd.bdate_range("2024-01-01", periods=40),
    )
    assert len(drawdown_periods(levels, limit=3)) == 3


def test_rolling_statistics() -> None:
    r = pd.Series(
        [0.10, -0.05, 0.02, -0.01, 0.03] * 4, index=pd.bdate_range("2024-01-01", periods=20)
    )
    vol = rolling_statistic(r, "volatility", 5, periods_per_year=5)
    assert vol.iloc[4] == pytest.approx(0.0554064 * math.sqrt(5), rel=2e-4)
    assert vol.iloc[:4].isna().all()
    sharpe = rolling_statistic(r, "sharpe", 5, periods_per_year=5)
    assert sharpe.iloc[4] == pytest.approx(0.018 / 0.0554064 * math.sqrt(5), rel=2e-4)
    beta = rolling_statistic(r * 2, "beta", 5, periods_per_year=5, benchmark=r)
    assert beta.dropna().to_numpy() == pytest.approx(2.0)


def test_input_validation() -> None:
    with pytest.raises(InsufficientDataError):
        series_metrics(ALTERNATING.iloc[:10], 40, 0.0, 0.0)
    with pytest.raises(ConfigurationError):
        tearsheet_table({}, periods_per_year=40)
    with pytest.raises(ConfigurationError, match="not among"):
        tearsheet_table({"A": ALTERNATING}, periods_per_year=40, benchmark="B")
    with pytest.raises(ConfigurationError):
        rolling_statistic(ALTERNATING, "volatility", 2, periods_per_year=40)
    with pytest.raises(ConfigurationError):
        rolling_statistic(ALTERNATING, "beta", 10, periods_per_year=40)
    with pytest.raises(ConfigurationError):
        rolling_statistic(ALTERNATING, "nonsense", 10, periods_per_year=40)
    with pytest.raises(InsufficientDataError):
        rolling_statistic(ALTERNATING, "volatility", 40, periods_per_year=40)
