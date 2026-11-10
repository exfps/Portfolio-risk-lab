"""Altair charts for the interface. Pure construction: nothing here renders or imports Streamlit."""

from __future__ import annotations

from typing import Any, cast

import altair as alt
import pandas as pd

from portfolio_risk.ui import theme

Chart = alt.Chart | alt.LayerChart
_HEIGHT = 260
_FONT = "Inter, system-ui, sans-serif"
_DATE_AXIS = alt.Axis(format="%b %Y", tickCount=7, labelOverlap=True)


def _styled(chart: alt.Chart | alt.LayerChart | alt.FacetChart, p: theme.Palette) -> Chart:
    styled = (
        chart.configure_view(strokeWidth=0)
        .configure_axis(
            gridColor=p.grid,
            gridDash=[2, 4],
            domainColor=p.axis,
            tickColor=p.axis,
            labelColor=p.muted,
            titleColor=p.muted,
            labelFont=_FONT,
            titleFont=_FONT,
            labelFontSize=11,
            titleFontSize=11,
            titleFontWeight="normal",
            titlePadding=10,
        )
        .configure_text(font=_FONT)
    )
    return cast("Chart", styled)


def _fade(colour: str, top: float, bottom: float) -> dict[str, Any]:
    """A vertical Vega-Lite gradient of one colour, from ``top`` to ``bottom`` opacity."""
    return {
        "gradient": "linear",
        "x1": 1,
        "x2": 1,
        "y1": 0,
        "y2": 1,
        "stops": [
            {"offset": 0, "color": theme.rgba(colour, top)},
            {"offset": 1, "color": theme.rgba(colour, bottom)},
        ],
    }


def _time_series(series: pd.Series, column: str) -> pd.DataFrame:
    return pd.DataFrame({"date": pd.DatetimeIndex(series.index), column: series.to_numpy()})


def wealth_chart(wealth: pd.Series, p: theme.Palette = theme.DEFAULT) -> Chart:
    """Growth of 1 invested at the start."""
    frame = _time_series(wealth, "value")
    chart = (
        alt.Chart(frame)
        .mark_area(
            line={"color": p.accent, "strokeWidth": 2},
            color=_fade(p.accent, 0.32, 0.0),
            interpolate="monotone",
        )
        .encode(
            x=alt.X("date:T", title=None, axis=_DATE_AXIS),
            y=alt.Y("value:Q", title="Growth of 1", scale=alt.Scale(zero=False), stack=None),
            y2=alt.value(_HEIGHT),
            tooltip=[
                alt.Tooltip("date:T", title="Date"),
                alt.Tooltip("value:Q", title="Value", format=".4f"),
            ],
        )
        .properties(height=_HEIGHT, width="container")
    )
    return _styled(chart, p)


def drawdown_chart(drawdowns: pd.Series, p: theme.Palette = theme.DEFAULT) -> Chart:
    """Drawdown from the running peak, as a percentage."""
    frame = _time_series(drawdowns, "drawdown")
    chart = (
        alt.Chart(frame)
        .mark_area(
            line={"color": p.negative, "strokeWidth": 1.5},
            color=_fade(p.negative, 0.05, 0.55),
        )
        .encode(
            x=alt.X("date:T", title=None, axis=_DATE_AXIS),
            y=alt.Y("drawdown:Q", title="Drawdown", axis=alt.Axis(format="%")),
            tooltip=[
                alt.Tooltip("date:T", title="Date"),
                alt.Tooltip("drawdown:Q", title="Drawdown", format=".2%"),
            ],
        )
        .properties(height=_HEIGHT, width="container")
    )
    return _styled(chart, p)


def risk_contribution_chart(contributions: pd.Series, p: theme.Palette = theme.DEFAULT) -> Chart:
    """Each asset's share of portfolio variance. Negative shares are drawn in the loss colour."""
    names = [str(name) for name in contributions.index]
    frame = pd.DataFrame({"asset": names, "share": contributions.to_numpy()})
    chart = (
        alt.Chart(frame)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, opacity=0.92)
        .encode(
            x=alt.X("asset:N", sort=names, title=None, axis=alt.Axis(labelAngle=-30)),
            y=alt.Y("share:Q", title="Share of portfolio variance", axis=alt.Axis(format="%")),
            color=alt.condition(alt.datum.share < 0, alt.value(p.negative), alt.value(p.accent)),
            tooltip=[
                alt.Tooltip("asset:N", title="Asset"),
                alt.Tooltip("share:Q", title="Share", format=".1%"),
            ],
        )
        .properties(height=_HEIGHT, width="container")
    )
    return _styled(chart, p)


def correlation_heatmap(correlation: pd.DataFrame, p: theme.Palette = theme.DEFAULT) -> Chart:
    """Correlation matrix, teal for positive, rust for negative, values annotated."""
    names = [str(name) for name in correlation.columns]
    cells = correlation.copy()
    cells.index = pd.Index(names)
    cells.columns = pd.Index(names)
    long = cells.reset_index(names="x").melt(id_vars="x", var_name="y", value_name="rho")
    base = alt.Chart(long).encode(
        x=alt.X("x:N", sort=names, title=None, axis=alt.Axis(labelAngle=-30)),
        y=alt.Y("y:N", sort=names, title=None),
    )
    rectangles = base.mark_rect(stroke=p.background, strokeWidth=2, cornerRadius=4).encode(
        color=alt.Color(
            "rho:Q",
            scale=alt.Scale(domain=[-1, 0, 1], range=[p.negative, p.surface, p.accent]),
            legend=None,
        ),
        tooltip=[
            alt.Tooltip("x:N", title="Asset"),
            alt.Tooltip("y:N", title="Asset"),
            alt.Tooltip("rho:Q", title="Correlation", format=".3f"),
        ],
    )
    labels = base.mark_text(fontSize=11).encode(
        text=alt.Text("rho:Q", format=".2f"),
        color=alt.condition(alt.datum.rho > 0.55, alt.value(p.background), alt.value(p.text)),
    )
    heatmap = alt.layer(rectangles, labels).properties(
        height=max(_HEIGHT, 44 * len(names)), width="container"
    )
    return _styled(heatmap, p)
