"""Analysis parameters."""

from __future__ import annotations

from dataclasses import dataclass

from portfolio_risk.errors import ConfigurationError
from portfolio_risk.returns import to_period_rate


@dataclass(frozen=True, slots=True)
class AnalysisConfig:
    """Parameters that change the numbers an analysis produces.

    ``periods_per_year`` annualises volatility and ratios: 252 for daily equity data, 365 for
    daily data that includes weekends, 52 for weekly, 12 for monthly.
    ``risk_free_annual`` and ``mar_annual`` are effective annual rates and are converted to
    per-period rates geometrically.
    ``min_observations`` is the minimum number of *returns* an analysis will accept.
    """

    periods_per_year: int = 252
    risk_free_annual: float = 0.0
    mar_annual: float = 0.0
    confidence_levels: tuple[float, ...] = (0.95, 0.99)
    min_observations: int = 60

    def __post_init__(self) -> None:
        if self.periods_per_year < 1:
            raise ConfigurationError("periods_per_year must be at least 1.")
        if self.risk_free_annual <= -1.0 or self.mar_annual <= -1.0:
            raise ConfigurationError("Annual rates must be greater than -100%.")
        if not self.confidence_levels:
            raise ConfigurationError("At least one confidence level is required.")
        if any(not 0.5 < level < 1.0 for level in self.confidence_levels):
            raise ConfigurationError("Confidence levels must lie strictly between 0.5 and 1.")
        if self.min_observations < 2:
            raise ConfigurationError("min_observations must be at least 2.")

    @property
    def risk_free_per_period(self) -> float:
        return to_period_rate(self.risk_free_annual, self.periods_per_year)

    @property
    def mar_per_period(self) -> float:
        return to_period_rate(self.mar_annual, self.periods_per_year)
