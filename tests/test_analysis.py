"""End-to-end analysis: a two-asset portfolio worked by hand, plus the bundled sample."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from portfolio_risk import AnalysisConfig, analyse, load_prices, load_weights
from portfolio_risk.errors import DataValidationError, InsufficientDataError
from portfolio_risk.sample_data import generate_sample_prices, sample_weights

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def two_asset_prices(*, with_benchmark: bool = False) -> pd.DataFrame:
    """Three weekly returns each. A: +10%, -10%, +10%. B: +2%, +1%, +3%."""
    index = pd.date_range("2024-01-05", periods=4, freq="W-FRI", name="date")
    frame = pd.DataFrame(
        {"A": [100.0, 110.0, 99.0, 108.9], "B": [100.0, 102.0, 103.02, 106.1106]},
        index=index,
    )
    if with_benchmark:
        frame["IDX"] = [100.0, 101.0, 100.0, 103.0]
    return frame


CONFIG = AnalysisConfig(periods_per_year=52, min_observations=3)
WEIGHTS = pd.Series({"A": 0.5, "B": 0.5})


def test_hand_worked_two_asset_portfolio() -> None:
    result = analyse(two_asset_prices(), WEIGHTS, CONFIG)
    # Portfolio returns: 0.5 * A + 0.5 * B = [0.06, -0.045, 0.065].
    assert result.portfolio_returns.tolist() == pytest.approx([0.06, -0.045, 0.065])
    assert result.observations == 3
    # Wealth: 1.06, 1.06 * 0.955 = 1.0123, 1.0123 * 1.065 = 1.0780995.
    assert result.wealth.tolist() == pytest.approx([1.0, 1.06, 1.0123, 1.0780995])
    assert result.performance.total_return == pytest.approx(0.0780995)
    # Drawdown: peak 1.06 -> trough 1.0123 = 0.955 - 1 = -4.5%, regained on the last date.
    drawdown = result.performance.drawdown
    assert drawdown.max_drawdown == pytest.approx(-0.045)
    assert drawdown.recovery == result.wealth.index[-1]
    assert drawdown.longest_duration_periods == 2
    # Volatility: sum of squares 0.0036 + 0.002025 + 0.004225 = 0.00985; n * mean**2 =
    # 3 * (0.08 / 3) ** 2 = 0.0064 / 3. Sum of squared deviations = 0.00985 - 0.0064 / 3,
    # sample variance is that over n - 1 = 2; scaled by sqrt(52).
    expected_vol = math.sqrt((0.00985 - 0.0064 / 3) / 2) * math.sqrt(52)
    assert result.performance.annualised_volatility == pytest.approx(expected_vol)
    assert result.hhi == pytest.approx(0.5)
    assert result.effective_positions == pytest.approx(2.0)
    assert result.risk_contribution.sum() == pytest.approx(1.0)
    # Three observations is far below the recommended minimum, and that is the only warning.
    assert len(result.warnings) == 1
    assert result.warnings[0].startswith("Only 3 observations")


def test_asset_table_and_correlation_shapes() -> None:
    result = analyse(two_asset_prices(), WEIGHTS, CONFIG)
    assert list(result.asset_table.columns) == [
        "weight",
        "annualised_return",
        "annualised_volatility",
        "max_drawdown",
        "risk_contribution",
    ]
    assert result.asset_table.loc["A", "max_drawdown"] == pytest.approx(-0.10)
    assert result.asset_table.loc["B", "max_drawdown"] == 0.0
    assert result.correlation.shape == (2, 2)


def test_benchmark_is_optional_and_excluded_from_the_portfolio() -> None:
    without = analyse(two_asset_prices(), WEIGHTS, CONFIG)
    with_benchmark = analyse(
        two_asset_prices(with_benchmark=True), WEIGHTS, CONFIG, benchmark="IDX"
    )
    assert without.benchmark is None
    assert with_benchmark.benchmark is not None
    assert with_benchmark.portfolio_returns.tolist() == without.portfolio_returns.tolist()
    assert list(with_benchmark.correlation.columns) == ["A", "B"]


def test_zero_weight_asset_stays_in_the_correlation_matrix() -> None:
    result = analyse(two_asset_prices(), pd.Series({"A": 1.0, "B": 0.0}), CONFIG)
    assert result.correlation.shape == (2, 2)
    assert result.risk_contribution["B"] == pytest.approx(0.0)


def test_weights_that_do_not_sum_to_one_are_rejected_or_rescaled_with_a_note() -> None:
    with pytest.raises(DataValidationError, match="not 1"):
        analyse(two_asset_prices(), pd.Series({"A": 1.0, "B": 1.0}), CONFIG)
    result = analyse(
        two_asset_prices(), pd.Series({"A": 1.0, "B": 1.0}), CONFIG, normalise_weights=True
    )
    assert result.weights.tolist() == [0.5, 0.5]
    assert any("rescaled" in note for note in result.warnings)


def test_frequency_mismatch_is_reported() -> None:
    result = analyse(
        two_asset_prices(), WEIGHTS, AnalysisConfig(periods_per_year=252, min_observations=3)
    )
    assert any("52 periods per year" in note for note in result.warnings)


def test_too_little_data_is_rejected() -> None:
    with pytest.raises(InsufficientDataError):
        analyse(two_asset_prices(), WEIGHTS, AnalysisConfig(periods_per_year=52))


def test_var_table_has_one_row_per_confidence_level() -> None:
    result = analyse(two_asset_prices(), WEIGHTS, CONFIG)
    assert [row.confidence for row in result.var] == [0.95, 0.99]
    for row in result.var:
        assert row.historical_cvar >= row.historical_var
        assert row.parametric_cvar >= row.parametric_var


# -- bundled sample ----------------------------------------------------------------------------


def test_committed_example_files_match_the_generator() -> None:
    generated = generate_sample_prices()
    committed = load_prices(EXAMPLES / "sample_prices_synthetic.csv")
    assert committed.shape == generated.shape
    assert np.allclose(committed.to_numpy(), generated.to_numpy(), atol=5e-5)
    weights = load_weights(EXAMPLES / "sample_weights_synthetic.csv")
    assert weights.equals(sample_weights().rename("weight").rename_axis("ticker"))


def test_sample_generation_is_deterministic() -> None:
    assert generate_sample_prices().equals(generate_sample_prices())
    assert not generate_sample_prices(seed=1).equals(generate_sample_prices(seed=2))


def test_sample_analysis_snapshot() -> None:
    """Pins the numbers quoted in the README. These come from synthetic data."""
    result = analyse(
        load_prices(EXAMPLES / "sample_prices_synthetic.csv"),
        load_weights(EXAMPLES / "sample_weights_synthetic.csv"),
        benchmark="SYN_BENCH",
    )
    performance = result.performance
    assert result.observations == 756
    assert result.warnings == ()
    assert performance.total_return == pytest.approx(0.2266, abs=5e-5)
    assert performance.cagr == pytest.approx(0.0705, abs=5e-5)
    assert performance.annualised_volatility == pytest.approx(0.1030, abs=5e-5)
    assert performance.sharpe_ratio == pytest.approx(0.713, abs=5e-4)
    assert performance.drawdown.max_drawdown == pytest.approx(-0.1165, abs=5e-5)
    assert performance.drawdown.recovery == pd.Timestamp("2023-11-15")
    assert result.var[0].historical_var == pytest.approx(0.0100, abs=5e-5)
    assert result.benchmark is not None
    assert result.benchmark.beta == pytest.approx(0.939, abs=5e-4)
