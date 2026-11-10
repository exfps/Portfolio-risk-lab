"""Shared inputs for the exporters. Pure: no reportlab or openpyxl import."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from portfolio_risk import __version__


@dataclass(frozen=True)
class ReportMeta:
    """Descriptive text printed on exports.

    ``source_note`` says where the prices came from (for example "Synthetic sample data" or
    "Uploaded CSV file"), because a report that hides its data source is not reproducible.
    ``accent`` is a ``#RRGGBB`` colour used for headings and charts; it follows the interface
    theme when the person has customised it.
    """

    title: str = "Portfolio performance and risk report"
    source_note: str = "Data source not recorded"
    risk_free_source: str = ""
    accent: str = "#1F8F82"
    generated: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))
    version: str = __version__

    def __post_init__(self) -> None:
        colour = self.accent
        if (
            len(colour) != 7
            or colour[0] != "#"
            or any(c not in "0123456789abcdefABCDEF" for c in colour[1:])
        ):
            raise ValueError(f"accent must be #RRGGBB, not {colour!r}")


DISCLAIMER = (
    "This report describes the history that was supplied. It is an analytical output, not "
    "investment advice, and past results do not predict future performance. Value at Risk "
    "and related figures are estimates that depend on the sample and on the stated assumptions."
)

ASSUMPTIONS = (
    "Returns are simple period returns, P(t) / P(t-1) - 1.",
    "Weights are constant, long-only and rebalanced to target every period; buy-and-hold "
    "drift is not modelled.",
    "Volatility and ratios are annualised with the square root of periods per year, which "
    "assumes returns are serially uncorrelated.",
    "VaR and CVaR are one-period losses shown as positive numbers; parametric figures assume "
    "a normal distribution and understate fat tails.",
    "Prices are assumed to be in one currency and adjusted for splits and dividends. This is "
    "not checked. No fees, taxes or dividends are modelled.",
)
