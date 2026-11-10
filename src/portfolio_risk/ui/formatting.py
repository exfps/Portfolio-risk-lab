"""Turns an ``AnalysisResult`` into display-ready values. Pure: no Streamlit import."""

from __future__ import annotations

import html
import math
from collections.abc import Hashable

import pandas as pd

from portfolio_risk.analysis import AnalysisResult

NOT_AVAILABLE = "n/a"


def html_table(frame: pd.DataFrame) -> str:
    """A small read-only table as escaped HTML.

    Streamlit's own table and dataframe elements each pull in several hundred kilobytes of
    script on first use; a plain HTML table does not, and these tables are tiny.
    """
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in frame.columns)
    rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in row) + "</tr>"
        for row in frame.itertuples(index=False, name=None)
    )
    return f'<table class="tbl"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>'


def risk_free_note(source: str) -> str:
    """Suffix for the risk-free line in the assumptions; the source is HTML-escaped."""
    source = source.strip()
    return f" (source: {html.escape(source)})" if source else " (source not recorded)"


def percent(value: float, digits: int = 2) -> str:
    """``0.0705`` -> ``'7.05%'``. NaN and infinity become ``'n/a'``."""
    return f"{value:.{digits}%}" if math.isfinite(value) else NOT_AVAILABLE


def ratio(value: float, digits: int = 2) -> str:
    """``0.7127`` -> ``'0.71'``. NaN and infinity become ``'n/a'``."""
    return f"{value:.{digits}f}" if math.isfinite(value) else NOT_AVAILABLE


def day(label: Hashable | None, *, missing: str = "-") -> str:
    """Format a date label as ``YYYY-MM-DD``; ``None`` becomes ``missing``."""
    if label is None:
        return missing
    return str(pd.Timestamp(label).date())  # type: ignore[arg-type]


def headline_metrics(result: AnalysisResult) -> list[tuple[str, str]]:
    performance = result.performance
    return [
        ("Total return", percent(performance.total_return)),
        ("Annualised return", percent(performance.cagr)),
        ("Volatility", percent(performance.annualised_volatility)),
        ("Sharpe", ratio(performance.sharpe_ratio)),
        ("Sortino", ratio(performance.sortino_ratio)),
        ("Max drawdown", percent(performance.drawdown.max_drawdown)),
    ]


def drawdown_table(result: AnalysisResult) -> pd.DataFrame:
    summary = result.performance.drawdown
    if summary.trough is None:
        recovery = "-"
    elif summary.recovery is None:
        recovery = "not recovered"
    else:
        recovery = day(summary.recovery)
    if summary.longest_duration_periods == 0:
        spell = "none"
    else:
        status = "ongoing" if summary.longest_ongoing else "recovered"
        spell = f"{summary.longest_duration_periods} periods ({status})"
    rows = [
        ("Maximum drawdown", percent(summary.max_drawdown)),
        ("Peak", day(summary.peak)),
        ("Trough", day(summary.trough)),
        ("Recovery", recovery),
        ("Longest underwater spell", spell),
        ("Current drawdown", percent(summary.current_drawdown)),
    ]
    return pd.DataFrame(rows, columns=pd.Index(["Measure", "Value"]))


def var_table(result: AnalysisResult) -> pd.DataFrame:
    """One row per confidence level. Losses are shown as positive percentages."""
    rows = [
        {
            "Confidence": f"{estimate.confidence:.1%}".replace(".0%", "%"),
            "Historical VaR": percent(estimate.historical_var),
            "Historical CVaR": percent(estimate.historical_cvar),
            "Parametric VaR": percent(estimate.parametric_var),
            "Parametric CVaR": percent(estimate.parametric_cvar),
        }
        for estimate in result.var
    ]
    return pd.DataFrame(rows)


def asset_table(result: AnalysisResult) -> pd.DataFrame:
    table = result.asset_table
    return pd.DataFrame(
        {
            "Asset": [str(name) for name in table.index],
            "Weight": [percent(value, 1) for value in table["weight"]],
            "Return (ann.)": [percent(value) for value in table["annualised_return"]],
            "Volatility (ann.)": [percent(value) for value in table["annualised_volatility"]],
            "Max drawdown": [percent(value) for value in table["max_drawdown"]],
            "Risk share": [percent(value, 1) for value in table["risk_contribution"]],
        }
    )


def benchmark_table(result: AnalysisResult) -> pd.DataFrame | None:
    stats = result.benchmark
    if stats is None:
        return None
    rows = [
        ("Beta", ratio(stats.beta)),
        ("Alpha (annualised)", percent(stats.alpha_annualised)),
        ("Correlation", ratio(stats.correlation)),
        ("R-squared", ratio(stats.r_squared)),
        ("Active return (annualised)", percent(stats.active_return_annualised)),
        ("Tracking error", percent(stats.tracking_error)),
        ("Information ratio", ratio(stats.information_ratio)),
    ]
    return pd.DataFrame(rows, columns=pd.Index(["Measure", "Value"]))
