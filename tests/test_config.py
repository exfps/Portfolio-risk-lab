from __future__ import annotations

import pytest

from portfolio_risk.config import AnalysisConfig
from portfolio_risk.errors import (
    ConfigurationError,
    DataValidationError,
    InsufficientDataError,
    PortfolioRiskError,
)


def test_defaults() -> None:
    config = AnalysisConfig()
    assert config.periods_per_year == 252
    assert config.confidence_levels == (0.95, 0.99)
    assert config.risk_free_per_period == 0.0
    assert config.mar_per_period == 0.0


def test_annual_rates_are_converted_geometrically() -> None:
    config = AnalysisConfig(periods_per_year=2, risk_free_annual=0.21, mar_annual=0.44)
    assert config.risk_free_per_period == pytest.approx(0.10)
    assert config.mar_per_period == pytest.approx(0.20)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"periods_per_year": 0},
        {"risk_free_annual": -1.0},
        {"mar_annual": -1.5},
        {"confidence_levels": ()},
        {"confidence_levels": (0.95, 1.0)},
        {"confidence_levels": (0.5,)},
        {"min_observations": 1},
    ],
)
def test_invalid_parameters_are_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ConfigurationError):
        AnalysisConfig(**kwargs)  # type: ignore[arg-type]


def test_error_hierarchy() -> None:
    assert issubclass(ConfigurationError, PortfolioRiskError)
    assert issubclass(DataValidationError, PortfolioRiskError)
    assert issubclass(InsufficientDataError, DataValidationError)
