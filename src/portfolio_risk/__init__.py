"""Portfolio performance and risk analytics."""

from portfolio_risk.analysis import AnalysisResult, PerformanceSummary, VarEstimate, analyse
from portfolio_risk.benchmark import BenchmarkStats
from portfolio_risk.comparison import Comparison, compare
from portfolio_risk.config import AnalysisConfig
from portfolio_risk.decay import DecayReport, alpha_decay
from portfolio_risk.drawdown import DrawdownSummary
from portfolio_risk.errors import (
    ConfigurationError,
    DataValidationError,
    InsufficientDataError,
    PortfolioRiskError,
)
from portfolio_risk.io import load_prices, load_weights
from portfolio_risk.tearsheet import tearsheet_table

__version__ = "0.2.0.dev0"

__all__ = [
    "AnalysisConfig",
    "AnalysisResult",
    "BenchmarkStats",
    "Comparison",
    "ConfigurationError",
    "DataValidationError",
    "DecayReport",
    "DrawdownSummary",
    "InsufficientDataError",
    "PerformanceSummary",
    "PortfolioRiskError",
    "VarEstimate",
    "__version__",
    "alpha_decay",
    "analyse",
    "compare",
    "load_prices",
    "load_weights",
    "tearsheet_table",
]
