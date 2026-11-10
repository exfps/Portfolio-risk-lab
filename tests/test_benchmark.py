"""Benchmark statistics against hand-worked examples.

Benchmark ``B`` = [0.01, -0.02, 0.03, 0.00, 0.02]: mean 0.008, sample variance 0.00037.
Portfolio ``P`` = 1.5 * B + 0.001 has beta exactly 1.5 and per-period alpha exactly 0.001.
Active return P - B = 0.5 * B + 0.001, so tracking error is 0.5 * std(B) * sqrt(periods).
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from portfolio_risk.benchmark import benchmark_statistics
from portfolio_risk.errors import DataValidationError

B = pd.Series([0.01, -0.02, 0.03, 0.00, 0.02])
P = B * 1.5 + 0.001
STD_B = math.sqrt(0.00037)


def test_beta_alpha_correlation() -> None:
    stats = benchmark_statistics(P, B, risk_free_per_period=0.0, periods_per_year=12)
    assert stats.beta == pytest.approx(1.5)
    assert stats.alpha_annualised == pytest.approx(0.001 * 12)
    assert stats.correlation == pytest.approx(1.0)
    assert stats.r_squared == pytest.approx(1.0)


def test_tracking_error_and_information_ratio() -> None:
    stats = benchmark_statistics(P, B, risk_free_per_period=0.0, periods_per_year=12)
    expected_te = 0.5 * STD_B * math.sqrt(12)
    # mean active return = 0.5 * 0.008 + 0.001 = 0.005 per period, 0.06 a year
    assert stats.tracking_error == pytest.approx(expected_te)
    assert stats.active_return_annualised == pytest.approx(0.06)
    assert stats.information_ratio == pytest.approx(0.06 / expected_te)


def test_alpha_is_measured_over_the_risk_free_rate() -> None:
    # With rf = 0.002: P - rf = 1.5 * (B - rf) + 0.002, so the intercept is 0.002.
    stats = benchmark_statistics(P, B, risk_free_per_period=0.002, periods_per_year=12)
    assert stats.beta == pytest.approx(1.5)
    assert stats.alpha_annualised == pytest.approx(0.002 * 12)


def test_portfolio_against_itself() -> None:
    stats = benchmark_statistics(B, B, risk_free_per_period=0.0, periods_per_year=252)
    assert stats.beta == pytest.approx(1.0)
    assert stats.alpha_annualised == pytest.approx(0.0, abs=1e-12)
    assert stats.tracking_error == 0.0
    assert math.isnan(stats.information_ratio)


def test_negative_beta() -> None:
    stats = benchmark_statistics(-B, B, risk_free_per_period=0.0, periods_per_year=12)
    assert stats.beta == pytest.approx(-1.0)
    assert stats.correlation == pytest.approx(-1.0)


def test_constant_benchmark_is_rejected() -> None:
    with pytest.raises(DataValidationError, match="constant"):
        benchmark_statistics(B, pd.Series([0.01] * 5), 0.0, 12)


def test_mismatched_dates_are_rejected() -> None:
    shifted = B.copy()
    shifted.index = pd.RangeIndex(10, 15)
    with pytest.raises(DataValidationError, match="same dates"):
        benchmark_statistics(B, shifted, 0.0, 12)
