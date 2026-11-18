"""The Classic tearsheet tab: the portfolio against its benchmark and chosen holdings."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from portfolio_risk import PortfolioRiskError
from portfolio_risk.analysis import AnalysisResult
from portfolio_risk.tearsheet import (
    calendar_years,
    monthly_table,
    rolling_statistic,
    tearsheet_table,
)
from portfolio_risk.ui import charts, formatting, theme
from portfolio_risk.ui.tearsheet_tables import (
    episodes_frame,
    metrics_frame,
    named_returns,
)

PEERS_KEY = "tearsheet_peers"
ROLLING_KINDS = {"Volatility": "volatility", "Sharpe ratio": "sharpe", "Beta to benchmark": "beta"}
WINDOWS = (21, 63, 126, 252)


def render(
    result: AnalysisResult,
    prices: pd.DataFrame,
    benchmark: str | None,
    palette: theme.Palette,
) -> None:
    st.caption(
        "A full set of statistics and calendar views, with the portfolio next to its benchmark "
        "and any holdings you choose to compare against."
    )
    holdings = [str(name) for name in result.weights.index]
    peers = st.multiselect(
        "Compare with holdings",
        holdings,
        default=st.session_state.get(PEERS_KEY, []),
        key=PEERS_KEY,
        max_selections=4,
        help="Up to four. Each is shown as a column and a line next to the portfolio.",
    )
    config = result.config
    series = named_returns(result, prices, benchmark, peers)
    try:
        table = tearsheet_table(
            series,
            periods_per_year=config.periods_per_year,
            rf_per_period=config.risk_free_per_period,
            mar_per_period=config.mar_per_period,
            benchmark=benchmark if benchmark in series else None,
        )
    except PortfolioRiskError as error:
        st.error(str(error))
        return

    st.subheader("Key statistics")
    st.markdown(formatting.html_table(metrics_frame(table)), unsafe_allow_html=True)

    growth = pd.DataFrame({name: (1.0 + s).cumprod() for name, s in series.items()})
    st.subheader("Cumulative growth of 1")
    st.altair_chart(charts.comparison_chart(growth, title="Growth of 1", fmt=".2f", p=palette))

    st.subheader("Returns by calendar year")
    years = calendar_years(series)
    st.altair_chart(charts.year_bars(years, palette))
    if len(result.portfolio_returns) < 250:
        st.caption("Years with less than a full year of data are partial.")

    st.subheader("Monthly returns")
    grid = monthly_table(result.portfolio_returns)
    st.altair_chart(charts.monthly_heatmap(grid, palette))

    st.subheader("Drawdowns")
    st.altair_chart(charts.drawdown_chart(result.drawdowns, palette))
    st.markdown(formatting.html_table(episodes_frame(result.wealth)), unsafe_allow_html=True)

    st.subheader("Rolling statistics")
    left, right = st.columns(2)
    kinds = [k for k in ROLLING_KINDS if k != "Beta to benchmark" or benchmark in series]
    kind = left.selectbox("Statistic", kinds, key="tearsheet_kind")
    window = right.selectbox("Window (periods)", WINDOWS, index=1, key="tearsheet_window")
    key = ROLLING_KINDS[kind]
    try:
        rolling = pd.DataFrame(
            {
                name: rolling_statistic(
                    s,
                    key,
                    int(window),
                    periods_per_year=config.periods_per_year,
                    rf_per_period=config.risk_free_per_period,
                    benchmark=series.get(benchmark) if benchmark else None,
                )
                for name, s in series.items()
                if not (key == "beta" and name == benchmark)
            }
        )
    except PortfolioRiskError as error:
        st.info(str(error))
    else:
        st.altair_chart(
            charts.comparison_chart(
                rolling, title=kind, fmt=".0%" if key == "volatility" else ".2f", p=palette
            )
        )
    st.caption(
        "Statistics use per-period simple returns over the same dates for every column. "
        "Sharpe and Sortino use the risk-free rate and minimum acceptable return from the sidebar. "
        "Value at Risk and expected shortfall are historical, for one period. "
        "Past statistics describe history; they are not forecasts."
    )
