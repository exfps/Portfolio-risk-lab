"""Portfolio performance and risk analytics."""

from portfolio_risk.analysis import AnalysisResult, PerformanceSummary, VarEstimate, analyse
from portfolio_risk.benchmark import BenchmarkStats
from portfolio_risk.config import AnalysisConfig
from portfolio_risk.drawdown import DrawdownSummary
from portfolio_risk.errors import (
    ConfigurationError,
    DataValidationError,
    InsufficientDataError,
    PortfolioRiskError,
)
from portfolio_risk.io import load_prices, load_weights

__version__ = "0.1.0.dev0"

__all__ = [
    "AnalysisConfig",
    "AnalysisResult",
    "BenchmarkStats",
    "ConfigurationError",
    "DataValidationError",
    "DrawdownSummary",
    "InsufficientDataError",
    "PerformanceSummary",
    "PortfolioRiskError",
    "VarEstimate",
    "__version__",
    "analyse",
    "load_prices",
    "load_weights",
]
