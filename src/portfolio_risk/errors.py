"""Exception hierarchy for portfolio_risk."""

from __future__ import annotations


class PortfolioRiskError(Exception):
    """Base class for every error raised deliberately by this package."""


class ConfigurationError(PortfolioRiskError):
    """An analysis parameter is outside its valid range."""


class DataValidationError(PortfolioRiskError):
    """Input data is malformed or unusable.

    The message identifies the offending line, column, date or value so that it can be
    shown to the person who supplied the file without further interpretation.
    """


class InsufficientDataError(DataValidationError):
    """There are too few observations for the requested statistic."""


class ExtractionError(PortfolioRiskError):
    """Reading positions from an image failed: bad image, provider error or unusable answer.

    Messages never contain the API key.
    """


class DataProviderError(PortfolioRiskError):
    """Downloading or searching market data failed: missing library, network or unknown symbol."""
