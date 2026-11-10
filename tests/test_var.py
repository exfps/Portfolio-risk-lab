"""VaR and CVaR against hand-worked examples.

Historical fixture ``T`` has 20 observations. Sorted, the lowest are -0.10, -0.05, -0.03.
With linear interpolation the p-quantile sits at position p * (n - 1) = p * 19.
  p = 0.05 -> position 0.95, between -0.10 and -0.05: -0.10 + 0.95 * 0.05 = -0.0525
  p = 0.01 -> position 0.19: -0.10 + 0.19 * 0.05 = -0.0905
Only -0.10 lies at or below either quantile, so both CVaRs equal 0.10.

Parametric fixture ``Z`` = [0.01, -0.01, 0.01, -0.01] has mean 0 and sample standard
deviation sqrt(4 * 0.0001 / 3). Standard normal constants (tabulated values):
  z(0.95) = 1.6448536, z(0.99) = 2.3263479
  phi(z) / (1 - c): 2.0627128 at 95%, 2.6652142 at 99%
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from portfolio_risk.errors import ConfigurationError
from portfolio_risk.var import historical_cvar, historical_var, parametric_cvar, parametric_var

TAIL = [-0.10, -0.05, -0.03, -0.02, -0.01, 0.00, 0.01, 0.02, 0.03, 0.04]
UPPER = [0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.11, 0.12, 0.13, 0.14]
T = pd.Series(TAIL + UPPER)

SIGMA_Z = math.sqrt(4 * 0.0001 / 3)
Z = pd.Series([0.01, -0.01, 0.01, -0.01])


def test_historical_var_interpolates_between_order_statistics() -> None:
    assert historical_var(T, 0.95) == pytest.approx(0.0525)
    assert historical_var(T, 0.99) == pytest.approx(0.0905)


def test_historical_cvar_averages_the_tail() -> None:
    assert historical_cvar(T, 0.95) == pytest.approx(0.10)
    assert historical_cvar(T, 0.99) == pytest.approx(0.10)


def test_historical_cvar_with_several_tail_observations() -> None:
    # 101 evenly spaced returns from -0.05 to 0.05. The 5% quantile is the 6th smallest,
    # -0.045. The tail is -0.05 ... -0.045, whose mean is -0.285 / 6 = -0.0475.
    evenly_spaced = pd.Series(np.arange(-50, 51) / 1000)
    assert historical_var(evenly_spaced, 0.95) == pytest.approx(0.045)
    assert historical_cvar(evenly_spaced, 0.95) == pytest.approx(0.0475)


def test_historical_measures_ignore_observation_order() -> None:
    shuffled = T.sample(frac=1.0, random_state=3).reset_index(drop=True)
    assert historical_var(shuffled, 0.95) == pytest.approx(0.0525)
    assert historical_cvar(shuffled, 0.95) == pytest.approx(0.10)


def test_parametric_var_with_zero_mean() -> None:
    assert parametric_var(Z, 0.95) == pytest.approx(1.6448536 * SIGMA_Z)
    assert parametric_var(Z, 0.99) == pytest.approx(2.3263479 * SIGMA_Z)


def test_parametric_cvar_with_zero_mean() -> None:
    assert parametric_cvar(Z, 0.95) == pytest.approx(2.0627128 * SIGMA_Z)
    assert parametric_cvar(Z, 0.99) == pytest.approx(2.6652142 * SIGMA_Z)


def test_parametric_measures_subtract_the_mean() -> None:
    shifted = Z + 0.001
    assert parametric_var(shifted, 0.95) == pytest.approx(parametric_var(Z, 0.95) - 0.001)
    assert parametric_cvar(shifted, 0.95) == pytest.approx(parametric_cvar(Z, 0.95) - 0.001)


@pytest.mark.parametrize("confidence", [0.5, 0.4, 1.0, 1.5])
def test_confidence_outside_open_interval_is_rejected(confidence: float) -> None:
    for function in (historical_var, historical_cvar, parametric_var, parametric_cvar):
        with pytest.raises(ConfigurationError, match=r"between 0\.5 and 1"):
            function(T, confidence)


@given(
    st.lists(st.floats(min_value=-0.5, max_value=0.5), min_size=2, max_size=300),
    st.sampled_from([0.9, 0.95, 0.99]),
)
def test_cvar_is_at_least_var(values: list[float], confidence: float) -> None:
    returns = pd.Series(values)
    assert historical_cvar(returns, confidence) >= historical_var(returns, confidence) - 1e-12
    assert parametric_cvar(returns, confidence) >= parametric_var(returns, confidence) - 1e-12


@given(st.lists(st.floats(min_value=-0.5, max_value=0.5), min_size=2, max_size=300))
def test_higher_confidence_never_lowers_historical_var(values: list[float]) -> None:
    returns = pd.Series(values)
    assert historical_var(returns, 0.99) >= historical_var(returns, 0.95) - 1e-12
