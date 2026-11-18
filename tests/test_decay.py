"""Alpha decay: rolling statistics checked by hand, z-score orientation, ratings and limits.

The hand-worked window is r = [+10%, -5%, +2%, -1%, +3%] with 5 periods a year:
growth 1.1 * 0.95 * 1.02 * 0.99 * 1.03 = 1.08689823; mean 1.8%; sample standard deviation
sqrt(0.01228 / 4) = 5.5406%; levels 1, 1.1, 1.045, 1.0659, 1.055241, 1.0868982 against a peak
of 1.1 give drawdowns 0, 0, -5%, -3.1%, -4.069%, -1.1911%.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from portfolio_risk.decay import (
    METRICS,
    alpha_decay,
    metric_by_key,
    parse_windows,
    rate,
    rolling_values,
)
from portfolio_risk.errors import ConfigurationError, InsufficientDataError

R = pd.Series([0.10, -0.05, 0.02, -0.01, 0.03], index=pd.bdate_range("2024-01-01", periods=5))


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("ann_return", 0.08689823),  # growth ** (5 / 5) - 1
        ("volatility", 0.0554064 * np.sqrt(5)),
        ("downside", np.sqrt(0.0025 + 0.0001)),  # sqrt(mean(min(r, 0)^2) * 5) = sqrt(0.0026)
        ("max_dd", -0.05),
        ("mean_dd", -(0.05 + 0.031 + 0.040690 + 0.011911) / 6),  # six levels incl. the start
        ("win_rate", 0.6),  # three of five days are positive
        ("var95", 0.042),  # 5% quantile of the sorted returns: -0.05 + 0.2 * 0.04
        ("es95", 0.05),  # only -5% is at or below the 5% quantile
        ("payoff", 0.05 / 0.03),  # average win 5%, average loss 3%
        ("sharpe", 0.018 / 0.0554064 * np.sqrt(5)),
    ],
)
def test_each_statistic_matches_the_hand_calculation(key: str, expected: float) -> None:
    value = float(rolling_values(R, metric_by_key(key), 5, 5).iloc[0])
    assert value == pytest.approx(expected, rel=2e-4, abs=1e-9)


def test_every_metric_is_covered_by_the_hand_calculation() -> None:
    assert {m.key for m in METRICS} == {
        "ann_return", "volatility", "downside", "max_dd", "mean_dd",
        "win_rate", "var95", "es95", "payoff", "sharpe",
    }  # fmt: skip


def test_rolling_values_are_labelled_by_the_last_date_of_each_window() -> None:
    series = rolling_values(R, metric_by_key("win_rate"), 3, 5)
    assert list(series.index) == list(R.index[2:])
    assert series.tolist() == pytest.approx([2 / 3, 1 / 3, 2 / 3])


def test_risk_free_rate_lowers_the_sharpe_ratio() -> None:
    sharpe = metric_by_key("sharpe")
    assert float(rolling_values(R, sharpe, 5, 5, 0.5).iloc[0]) < float(
        rolling_values(R, sharpe, 5, 5, 0.0).iloc[0]
    )


# ----------------------------------------------------------------------- ratings


@pytest.mark.parametrize(
    ("z", "expected"),
    [
        (2.0, "Excellent"), (1.0, "Excellent"), (0.99, "Good"), (-0.5, "Good"),
        (-0.51, "Warning"), (-1.5, "Warning"), (-1.51, "Critical"),
    ],
)  # fmt: skip
def test_rating_bands(z: float, expected: str) -> None:
    assert rate(z) == expected


def returns_with_last_block(sigma_last: float, rows: int = 420, last: int = 21) -> pd.Series:
    rng = np.random.default_rng(7)
    calm = rng.normal(0.0005, 0.005, rows - last)
    final = rng.normal(0.0005, sigma_last, last)
    return pd.Series(
        np.concatenate([calm, final]), index=pd.bdate_range("2021-01-01", periods=rows)
    )


def test_a_volatile_final_window_is_flagged_and_a_calm_one_is_not() -> None:
    wild = alpha_decay(returns_with_last_block(0.04), periods_per_year=252, windows=(21,))
    calm = alpha_decay(returns_with_last_block(0.001), periods_per_year=252, windows=(21,))
    for key in ("volatility", "downside", "var95", "es95"):
        assert wild.cell(key, 21).rating == "Critical", key
        assert wild.cell(key, 21).z < -1.5
        assert calm.cell("volatility", 21).rating == "Excellent"
    # orientation: lower volatility than usual must give a POSITIVE score
    assert calm.cell("volatility", 21).z > 1.0
    assert wild.cell("volatility", 21).percentile < 0.05
    assert calm.cell("volatility", 21).percentile > 0.95


def test_latest_window_is_compared_only_with_earlier_windows() -> None:
    series = returns_with_last_block(0.01, rows=100)
    report = alpha_decay(series, periods_per_year=252, windows=(21,), min_history=10)
    assert report.cell("volatility", 21).n_history == 100 - 21 + 1 - 1  # windows minus the latest
    assert report.as_of == series.index[-1]


def test_history_statistics_exclude_the_latest_window() -> None:
    series = returns_with_last_block(0.01)
    cell = alpha_decay(series, periods_per_year=252, windows=(21,)).cell("volatility", 21)
    all_windows = rolling_values(series, metric_by_key("volatility"), 21, 252)
    assert cell.latest == pytest.approx(float(all_windows.iloc[-1]))
    assert cell.history_mean == pytest.approx(float(all_windows.iloc[:-1].mean()))
    assert cell.history_std == pytest.approx(float(all_windows.iloc[:-1].std(ddof=1)))


def test_summary_counts_are_consistent() -> None:
    report = alpha_decay(returns_with_last_block(0.02), periods_per_year=252)
    assert len(report.cells) == 3 * len(METRICS)
    assert sum(report.counts().values()) == len(report.cells)
    assert report.healthy <= report.rated <= len(report.cells)


# ------------------------------------------------------------------ edge cases


def test_too_little_data_is_refused() -> None:
    with pytest.raises(InsufficientDataError, match="needs at least"):
        alpha_decay(returns_with_last_block(0.01, rows=40), periods_per_year=252, windows=(21,))


def test_a_window_longer_than_the_history_is_reported_not_crashed() -> None:
    report = alpha_decay(
        returns_with_last_block(0.01, rows=100), periods_per_year=252, windows=(21, 500)
    )
    assert report.cell("volatility", 500).rating == "Insufficient history"
    assert report.cell("volatility", 21).rating != "Insufficient history"


def test_not_enough_earlier_windows_gives_no_rating() -> None:
    # 60 returns: a 21-period window has 39 earlier windows, a 50-period window only 10
    report = alpha_decay(
        returns_with_last_block(0.01, rows=60), periods_per_year=252, windows=(21, 50)
    )
    assert report.cell("volatility", 21).rating != "Insufficient history"
    assert report.cell("volatility", 50).rating == "Insufficient history"
    assert report.cell("volatility", 50).n_history == 10


def test_a_statistic_that_never_changes_scores_zero() -> None:
    flat = pd.Series(0.001, index=pd.bdate_range("2021-01-01", periods=120))
    cell = alpha_decay(flat, periods_per_year=252, windows=(21,)).cell("win_rate", 21)
    assert cell.z == 0.0
    assert cell.rating == "Good"


def test_payoff_ratio_is_undefined_when_the_window_has_no_losses() -> None:
    up = pd.Series(0.001, index=pd.bdate_range("2021-01-01", periods=120))
    cell = alpha_decay(up, periods_per_year=252, windows=(21,)).cell("payoff", 21)
    assert cell.rating == "Insufficient history"


def test_missing_values_are_dropped_before_windows_are_formed() -> None:
    series = returns_with_last_block(0.01)
    series.iloc[10] = np.nan
    assert alpha_decay(series, periods_per_year=252, windows=(21,)).observations == len(series) - 1


def test_window_parsing() -> None:
    assert parse_windows("63, 21;126, 21") == (21, 63, 126)
    for bad in ("", "abc", "2", "21,63,126,252,504,756,1000"):
        with pytest.raises(ConfigurationError):
            parse_windows(bad)
