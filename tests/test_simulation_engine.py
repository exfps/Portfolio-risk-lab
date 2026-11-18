"""Portfolio aggregation, rebalancing, costs, per-path statistics and end-to-end runs.

Expected values in the rebalancing tests are worked out by hand in the comments.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
import pytest

from portfolio_risk.errors import ConfigurationError, DataValidationError
from portfolio_risk.simulation import Gaussian, SimulationConfig, engine, make_model, run_simulation
from portfolio_risk.simulation.analytics import longest_underwater, summarise, var_es


class Fixed:
    """A model that returns the same chosen returns on every path."""

    name = "fixed"

    def __init__(self, steps: list[list[float]]) -> None:
        self.steps = np.array(steps, dtype=np.float64)

    def fit(self, returns: pd.DataFrame) -> Fixed:
        return self

    def simulate(
        self, n_paths: int, n_periods: int, rng: np.random.Generator
    ) -> npt.NDArray[np.float64]:
        return np.broadcast_to(
            self.steps[:n_periods], (n_paths, n_periods, self.steps.shape[1])
        ).copy()


def final_value(rebalancing: str, cost: float) -> float:
    # Asset A gains 10% in both periods, asset B is flat. Start 100 split 50/50.
    config = SimulationConfig(
        n_paths=10,
        horizon_years=2 / 252,
        rebalancing=rebalancing,
        transaction_cost=cost,
        initial_value=100.0,
    )
    assert config.n_periods == 2
    model = Fixed([[0.10, 0.0], [0.10, 0.0]])
    values = engine.simulate_values(model, np.array([0.5, 0.5]), config)
    return float(values[0, -1])


def test_buy_and_hold_lets_weights_drift() -> None:
    # 50 -> 55 -> 60.5 for A, B stays 50: 110.5
    assert final_value("never", 0.0) == pytest.approx(110.5)


def test_rebalancing_without_cost() -> None:
    # After period 1: 55 + 50 = 105, reset to 52.5 each. Period 2: 57.75 + 52.5 = 110.25
    assert final_value("every period", 0.0) == pytest.approx(110.25)


def test_rebalancing_charges_cost_on_traded_value() -> None:
    # Trade = |52.5-55| + |52.5-50| = 5; cost 1% of 5 = 0.05; value 104.95 -> 52.475 each.
    # Period 2: 52.475 * 1.1 + 52.475 = 110.1975
    assert final_value("every period", 0.01) == pytest.approx(110.1975, abs=1e-4)


def test_no_rebalance_trade_at_the_final_period() -> None:
    config = SimulationConfig(
        n_paths=10, horizon_years=1 / 252, transaction_cost=0.05, initial_value=100.0
    )
    values = engine.simulate_values(Fixed([[0.1, 0.0]]), np.array([0.5, 0.5]), config)
    assert values[0, -1] == pytest.approx(105.0)  # one period, nothing to rebalance for


@pytest.mark.parametrize(
    ("frequency", "monthly", "quarterly", "annually"),
    [("daily", 21, 63, 252), ("weekly", 4, 13, 52), ("monthly", 1, 3, 12)],
)
def test_rebalance_intervals_follow_the_frequency(
    frequency: str, monthly: int, quarterly: int, annually: int
) -> None:
    def every(choice: str) -> int | None:
        config = SimulationConfig(frequency=frequency, rebalancing=choice)
        return config.rebalance_every

    assert (every("monthly"), every("quarterly"), every("annually")) == (
        monthly,
        quarterly,
        annually,
    )
    assert every("never") is None
    assert every("every period") == 1


def test_horizon_is_converted_to_periods() -> None:
    assert SimulationConfig(horizon_years=5).n_periods == 1260
    assert SimulationConfig(horizon_years=3, frequency="weekly").n_periods == 156
    assert SimulationConfig(horizon_years=10, frequency="monthly").n_periods == 120


@pytest.mark.parametrize(
    "bad",
    [
        {"n_paths": 5},
        {"frequency": "hourly"},
        {"rebalancing": "sometimes"},
        {"transaction_cost": 0.5},
        {"initial_value": 0},
        {"bust_drawdown": 1.0},
        {"target_return": 0},
        {"horizon_years": 0},
    ],
)
def test_configuration_is_validated(bad: dict[str, Any]) -> None:
    with pytest.raises(ConfigurationError):
        SimulationConfig(**bad)


def test_weights_must_match_assets_sum_to_one_and_not_be_negative() -> None:
    names = ["A", "B"]
    good = pd.Series({"A": 0.4, "B": 0.6})
    np.testing.assert_allclose(engine.check_weights(good, names), [0.4, 0.6])
    for bad in (
        pd.Series({"A": 0.4, "B": 0.5}),
        pd.Series({"A": 1.2, "B": -0.2}),
        pd.Series({"A": 1.0}),
        pd.Series({"A": 0.5, "B": 0.5, "C": 0.0}),
    ):
        with pytest.raises(DataValidationError):
            engine.check_weights(bad, names)


# ------------------------------------------------------------ frequency conversion


def test_daily_returns_compound_into_weekly_returns_and_partial_weeks_are_dropped() -> None:
    index = pd.bdate_range("2021-01-08", periods=11)  # a Friday, then two full weeks
    daily = pd.DataFrame({"A": 0.01}, index=index)
    weekly = engine.to_frequency(daily, 252, "weekly")
    assert len(weekly) == 2
    np.testing.assert_allclose(weekly["A"], 1.01**5 - 1.0)


def test_frequency_cannot_be_increased() -> None:
    weekly = pd.DataFrame({"A": 0.01}, index=pd.date_range("2021-01-01", periods=10, freq="W-FRI"))
    with pytest.raises(ConfigurationError, match="not possible"):
        engine.to_frequency(weekly, 52, "daily")
    assert engine.to_frequency(weekly, 52, "weekly") is weekly


# ----------------------------------------------------------------------- analytics


def test_value_at_risk_and_expected_shortfall_by_hand() -> None:
    returns = np.linspace(-0.5, 0.5, 101)  # -0.50, -0.49, ... 0.50
    var, es = var_es(returns, 0.95)
    assert var == pytest.approx(0.45)  # the 5% quantile is -0.45
    assert es == pytest.approx(0.475)  # mean of -0.50 ... -0.45 is -0.475


def test_longest_underwater_spell_by_hand() -> None:
    value = np.array([[100.0, 120.0, 90.0, 110.0, 130.0], [100.0, 99.0, 98.0, 97.0, 96.0]])
    drawdown = value / np.maximum.accumulate(value, axis=1) - 1.0
    assert longest_underwater(drawdown).tolist() == [2, 4]


def test_path_statistics_by_hand() -> None:
    values = np.array(
        [
            [100.0, 120.0, 90.0, 110.0, 130.0],  # max drawdown 90/120 - 1 = -25%
            [100.0, 160.0, 120.0, 120.0, 120.0],  # touches 160 but ends at 120
            [100.0, 110.0, 121.0, 133.1, 146.41],  # steady 10% growth, no drawdown
        ],
        dtype=np.float32,
    )
    config = SimulationConfig(
        n_paths=10,
        horizon_years=1.0,
        frequency="monthly",
        bust_drawdown=0.2,
        target_return=0.5,
        initial_value=100.0,
    )
    summary, paths = summarise(values, config)
    np.testing.assert_allclose(paths.cagr, [0.30, 0.20, 0.4641], rtol=1e-5)
    np.testing.assert_allclose(paths.max_drawdown, [-0.25, -0.25, 0.0], atol=1e-6)
    assert paths.volatility[2] == pytest.approx(0.0, abs=1e-5)
    assert summary.prob_bust == pytest.approx(2 / 3)  # paths 1 and 2 fall 25%
    assert summary.prob_target_end == 0.0  # nobody ends at or above 150
    assert summary.prob_target_touch == pytest.approx(1 / 3)  # only the path that peaks at 160
    assert summary.prob_loss == 0.0
    assert summary.ending_mean == pytest.approx((130 + 120 + 146.41) / 3, rel=1e-5)


# -------------------------------------------------------------------- end to end


def history(rows: int = 600, seed: int = 2) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    data = rng.multivariate_normal(
        [0.0004, 0.0002], np.array([[1.0, 0.5], [0.5, 1.5]]) * 1e-4, size=rows
    )
    return pd.DataFrame(data, index=pd.bdate_range("2019-01-01", periods=rows), columns=["A", "B"])


WEIGHTS = pd.Series({"A": 0.6, "B": 0.4})


def test_zero_drift_single_asset_has_expected_ending_value_equal_to_the_start() -> None:
    # With mean-zero independent returns, E[product of (1 + r)] = 1 exactly.
    config = SimulationConfig(n_paths=20_000, horizon_years=1.0, seed=5)
    result = run_simulation(history()[["A"]], pd.Series({"A": 1.0}), Gaussian("zero"), config)
    assert result.summary.ending_mean == pytest.approx(config.initial_value, rel=0.004)


def test_single_asset_is_unaffected_by_rebalancing_choice() -> None:
    returns = history()[["A"]]
    one = pd.Series({"A": 1.0})
    ends = {
        choice: run_simulation(
            returns,
            one,
            Gaussian(),
            SimulationConfig(n_paths=50, horizon_years=1.0, seed=1, rebalancing=choice),
        ).summary.ending_mean
        for choice in ("never", "every period", "annually")
    }
    assert len(set(ends.values())) == 1


def test_same_seed_reproduces_and_result_is_self_consistent() -> None:
    config = SimulationConfig(n_paths=300, horizon_years=1.0, seed=9)
    a = run_simulation(history(), WEIGHTS, make_model("student_t"), config)
    b = run_simulation(history(), WEIGHTS, make_model("student_t"), config)
    np.testing.assert_array_equal(a.paths.ending, b.paths.ending)
    s = a.summary
    p = s.ending_percentiles
    assert p[5] <= p[25] <= p[50] <= p[75] <= p[95]
    assert s.var_99 >= s.var_95
    assert s.es_95 >= s.var_95
    assert s.es_99 >= s.var_99
    assert a.bands.shape == (253, 5)
    assert a.bands.iloc[0].tolist() == [config.initial_value] * 5
    assert (a.bands["p05"] <= a.bands["p50"]).all()
    assert a.worst_paths.shape == (20, 253)
    assert a.worst_paths[:, -1].max() <= np.sort(a.paths.ending)[19] + 1e-6
    assert "600 observations" in a.window


def test_chunking_does_not_change_shape_or_reproducibility(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "_CHUNK_BUDGET", 400)  # forces many small chunks
    config = SimulationConfig(n_paths=45, horizon_years=10 / 252, seed=3)
    a = run_simulation(history(), WEIGHTS, Gaussian(), config)
    b = run_simulation(history(), WEIGHTS, Gaussian(), config)
    assert a.paths.ending.shape == (45,)
    np.testing.assert_array_equal(a.paths.ending, b.paths.ending)


def test_weekly_simulation_from_daily_history() -> None:
    config = SimulationConfig(n_paths=100, horizon_years=2.0, frequency="weekly", seed=4)
    result = run_simulation(
        history(), WEIGHTS, make_model("block_bootstrap", block_length=4), config
    )
    assert result.bands.shape == (105, 5)


def test_too_little_history_is_refused_after_conversion() -> None:
    monthly = SimulationConfig(n_paths=50, horizon_years=1.0, frequency="monthly")
    with pytest.raises(Exception, match="at least"):
        run_simulation(history(), WEIGHTS, Gaussian(), monthly)


def test_chart_bands_are_thinned_but_keep_both_ends() -> None:
    from portfolio_risk.simulation.analytics import MAX_BAND_POINTS, band_columns  # noqa: PLC0415

    short = band_columns(253)
    assert short.tolist() == list(range(253))
    long = band_columns(2521)
    assert len(long) <= MAX_BAND_POINTS
    assert long[0] == 0
    assert long[-1] == 2520
    assert (np.diff(long) > 0).all()
