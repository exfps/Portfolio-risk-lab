"""Classic tearsheet tables as display strings. Pure: no Streamlit import."""

from __future__ import annotations

import math

import pandas as pd

from portfolio_risk.analysis import AnalysisResult
from portfolio_risk.drawdown import drawdown_periods
from portfolio_risk.returns import simple_returns
from portfolio_risk.tearsheet import RELATIVE_ROWS, ROWS, Row
from portfolio_risk.ui import formatting

PORTFOLIO = "Portfolio"


def named_returns(
    result: AnalysisResult,
    prices: pd.DataFrame,
    benchmark: str | None,
    peers: list[str],
) -> dict[str, pd.Series]:
    """Portfolio, benchmark and peers on the portfolio's own dates."""
    index = result.portfolio_returns.index
    out: dict[str, pd.Series] = {PORTFOLIO: result.portfolio_returns}
    names = [n for n in ([benchmark] if benchmark else []) + peers if n in prices.columns]
    asset_returns = simple_returns(prices[list(dict.fromkeys(names))]) if names else None
    if asset_returns is not None:
        for name in dict.fromkeys(names):
            series = asset_returns[name].reindex(index)
            if series.notna().all():
                out[name] = series
    return out


def format_cell(row: Row, value: float) -> str:
    if not math.isfinite(value):
        return formatting.NOT_AVAILABLE
    if row.fmt == "int":
        return f"{value:,.0f}"
    if row.fmt == "ratio":
        return formatting.ratio(value)
    return formatting.percent(value, 1 if row.fmt == "pct" else 2)


def metrics_frame(table: pd.DataFrame) -> pd.DataFrame:
    """The numeric table as display strings, with a leading ``Statistic`` column."""
    rows = {r.key: r for r in (*ROWS, *RELATIVE_ROWS)}
    shown = [
        [rows[key].label, *(format_cell(rows[key], float(v)) for v in table.loc[key])]
        for key in table.index
    ]
    return pd.DataFrame(shown, columns=["Statistic", *map(str, table.columns)])


def episodes_frame(wealth: pd.Series) -> pd.DataFrame:
    episodes = drawdown_periods(wealth, 5)
    if episodes.empty:
        return pd.DataFrame(columns=["Start", "Trough", "Recovered", "Depth", "Periods"])
    return pd.DataFrame(
        {
            "Start": [formatting.day(d) for d in episodes["start"]],
            "Trough": [formatting.day(d) for d in episodes["trough"]],
            "Recovered": [
                formatting.day(d) if bool(ok) else "Not yet"
                for d, ok in zip(episodes["end"], episodes["recovered"], strict=True)
            ],
            "Depth": [formatting.percent(float(v)) for v in episodes["depth"]],
            "Periods": [f"{int(n):,}" for n in episodes["periods"]],
        }
    )
