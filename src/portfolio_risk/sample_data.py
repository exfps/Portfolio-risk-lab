"""Synthetic sample data.

Everything produced here is **simulated**. Prices come from a seeded multivariate geometric
Brownian motion with hand-picked drifts, volatilities and correlations. They do not describe
any real security or market, and they are free of third-party licence terms.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pandas as pd

SAMPLE_SEED = 20261127
SAMPLE_PERIODS = 756
SAMPLE_START = "2022-01-03"
BENCHMARK = "SYN_BENCH"

_TICKERS = ("SYN_EQ_US", "SYN_EQ_EU", "SYN_EQ_EM", "SYN_GOVT", "SYN_CORP", "SYN_COMMOD")
_ANNUAL_DRIFT = np.array([0.08, 0.07, 0.06, 0.03, 0.04, 0.03])
_ANNUAL_VOL = np.array([0.16, 0.17, 0.22, 0.06, 0.07, 0.18])
_CORRELATION = np.array(
    [
        [1.00, 0.85, 0.70, -0.15, 0.25, 0.30],
        [0.85, 1.00, 0.75, -0.10, 0.30, 0.35],
        [0.70, 0.75, 1.00, -0.05, 0.30, 0.45],
        [-0.15, -0.10, -0.05, 1.00, 0.55, -0.05],
        [0.25, 0.30, 0.30, 0.55, 1.00, 0.15],
        [0.30, 0.35, 0.45, -0.05, 0.15, 1.00],
    ]
)
_WEIGHTS = (0.30, 0.15, 0.10, 0.25, 0.10, 0.10)
_TRADING_DAYS = 252
_BENCHMARK_NOISE_VOL = 0.0015


def sample_weights() -> pd.Series:
    """Target weights for the sample portfolio. The benchmark is not part of the portfolio."""
    return pd.Series(_WEIGHTS, index=pd.Index(_TICKERS, name="ticker"), name="weight")


def generate_sample_prices(seed: int = SAMPLE_SEED, periods: int = SAMPLE_PERIODS) -> pd.DataFrame:
    """Simulate business-day prices for six synthetic assets and a synthetic benchmark.

    ``periods`` is the number of returns, so the table has ``periods + 1`` rows. Prices start
    at 100 and are rounded to four decimals, matching the committed example file.
    """
    rng = np.random.default_rng(seed)
    dt = 1.0 / _TRADING_DAYS
    cholesky = np.linalg.cholesky(_CORRELATION)
    shocks = rng.standard_normal((periods, len(_TICKERS))) @ cholesky.T

    log_returns = (_ANNUAL_DRIFT - 0.5 * _ANNUAL_VOL**2) * dt + _ANNUAL_VOL * np.sqrt(dt) * shocks
    asset_returns = np.expm1(log_returns)

    benchmark_noise = rng.standard_normal(periods) * _BENCHMARK_NOISE_VOL
    benchmark_returns = 0.6 * asset_returns[:, 0] + 0.4 * asset_returns[:, 3] + benchmark_noise

    all_returns = np.column_stack([asset_returns, benchmark_returns])
    levels = 100.0 * np.vstack(
        [np.ones(all_returns.shape[1]), np.cumprod(1.0 + all_returns, axis=0)]
    )

    index = pd.bdate_range(SAMPLE_START, periods=periods + 1, name="date")
    columns = pd.Index([*_TICKERS, BENCHMARK])
    return pd.DataFrame(_rounded(levels), index=index, columns=columns)


def _rounded(values: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    return np.round(values, 4)
