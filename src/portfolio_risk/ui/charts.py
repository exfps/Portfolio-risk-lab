"""Altair charts for the interface. Pure construction: nothing here renders or imports Streamlit."""

from __future__ import annotations

from typing import Any, cast

import altair as alt
import numpy as np
import numpy.typing as npt
import pandas as pd

from portfolio_risk.ui import theme

Chart = alt.Chart | alt.LayerChart
_HEIGHT = 260
_FONT = "Inter, system-ui, sans-serif"
_PAD = {"left": 4, "right": 18, "top": 6, "bottom": 4}
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
        .properties(height=_HEIGHT, width="container", padding=_PAD)
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


def fan_chart(bands: pd.DataFrame, initial: float, p: theme.Palette = theme.DEFAULT) -> Chart:
    """Simulated portfolio value: median line with 25-75% and 5-95% percentile bands."""
    frame = bands.reset_index()
    base = alt.Chart(frame).encode(
        x=alt.X("years:Q", title="Years", axis=alt.Axis(tickMinStep=1, format="d"))
    )
    outer = base.mark_area(color=theme.rgba(p.accent, 0.14)).encode(
        y=alt.Y("p05:Q", title="Portfolio value", scale=alt.Scale(zero=False)), y2="p95:Q"
    )
    inner = base.mark_area(color=theme.rgba(p.accent, 0.30)).encode(y="p25:Q", y2="p75:Q")
    median = base.mark_line(color=p.accent_bright, strokeWidth=2).encode(
        y="p50:Q",
        tooltip=[
            alt.Tooltip("years:Q", title="Years", format=".2f"),
            alt.Tooltip("p95:Q", title="95th percentile", format=",.0f"),
            alt.Tooltip("p50:Q", title="Median", format=",.0f"),
            alt.Tooltip("p05:Q", title="5th percentile", format=",.0f"),
        ],
    )
    start = (
        alt.Chart(pd.DataFrame({"v": [initial]}))
        .mark_rule(color=p.muted, strokeDash=[4, 4])
        .encode(y="v:Q")
    )
    return _styled(
        alt.layer(outer, inner, start, median).properties(
            height=_HEIGHT + 40, width="container", padding=_PAD
        ),
        p,
    )


def histogram_frame(values: npt.NDArray[np.float64], bins: int = 40) -> pd.DataFrame:
    """Bin ``values`` into ``bins`` equal-width bins; ``share`` is the fraction in each."""
    counts, edges = np.histogram(values, bins=bins)
    return pd.DataFrame(
        {"left": edges[:-1], "right": edges[1:], "share": counts / float(max(1, int(counts.sum())))}
    )


def distribution_chart(
    values: npt.NDArray[np.float64],
    title: str,
    *,
    fmt: str,
    marker: float | None = None,
    colour: str | None = None,
    p: theme.Palette = theme.DEFAULT,
) -> Chart:
    """Histogram of simulated outcomes, with an optional vertical reference line."""
    frame = histogram_frame(values)
    bars = (
        alt.Chart(frame)
        .mark_bar(color=colour or p.accent, opacity=0.85)
        .encode(
            x=alt.X("left:Q", title=title, axis=alt.Axis(format=fmt), scale=alt.Scale(zero=False)),
            x2="right:Q",
            y=alt.Y("share:Q", title="Share of paths", axis=alt.Axis(format="%")),
            y2=alt.datum(0),
            tooltip=[
                alt.Tooltip("left:Q", title="From", format=fmt),
                alt.Tooltip("right:Q", title="To", format=fmt),
                alt.Tooltip("share:Q", title="Share", format=".1%"),
            ],
        )
    )
    layers = [bars]
    if marker is not None:
        layers.append(
            alt.Chart(pd.DataFrame({"x": [marker]}))
            .mark_rule(color=p.muted, strokeDash=[4, 4])
            .encode(x="x:Q")
        )
    return _styled(
        alt.layer(*layers).properties(height=_HEIGHT, width="container", padding=_PAD), p
    )


def decay_chart(
    series: pd.Series,
    *,
    mean: float,
    std: float,
    label: str,
    fmt: str,
    p: theme.Palette = theme.DEFAULT,
) -> Chart:
    """A rolling statistic, its history mean, a one-sigma band and the latest window."""
    frame = pd.DataFrame({"date": series.index, "value": series.to_numpy(dtype=float)})
    frame = frame.dropna()
    band = pd.DataFrame({"low": [mean - std], "high": [mean + std]})
    axis_format = {"pct": ".1%", "pct2": ".2%", "ratio": ".2f"}[fmt]
    shade = (
        alt.Chart(band)
        .mark_rect(color=theme.rgba(p.accent, 0.12))
        .encode(y=alt.Y("low:Q", scale=alt.Scale(zero=False)), y2="high:Q")
    )
    line = (
        alt.Chart(frame)
        .mark_line(color=p.accent_bright, strokeWidth=1.6)
        .encode(
            x=alt.X("date:T", title=None),
            y=alt.Y(
                "value:Q",
                title=label,
                scale=alt.Scale(zero=False),
                axis=alt.Axis(format=axis_format),
            ),
            tooltip=[
                alt.Tooltip("date:T", title="Window ends"),
                alt.Tooltip("value:Q", title=label, format=axis_format),
            ],
        )
    )
    average = (
        alt.Chart(pd.DataFrame({"v": [mean]}))
        .mark_rule(color=p.muted, strokeDash=[4, 4])
        .encode(y="v:Q")
    )
    latest = (
        alt.Chart(frame.tail(1))
        .mark_point(color=p.gold, filled=True, size=70, opacity=1)
        .encode(x="date:T", y="value:Q")
    )
    return _styled(
        alt.layer(shade, average, line, latest).properties(
            height=_HEIGHT, width="container", padding=_PAD
        ),
        p,
    )


def series_colours(p: theme.Palette, count: int) -> list[str]:
    """Distinct line colours: the portfolio first, then the benchmark, then the peers."""
    if p.colour_blind_lines:
        return [theme.COLOUR_BLIND_LINES[i % len(theme.COLOUR_BLIND_LINES)] for i in range(count)]
    order = [p.accent_bright, p.gold, p.text, p.muted, p.accent, p.axis]
    return [order[i % len(order)] for i in range(count)]


_DASHES = ([1, 0], [6, 3], [2, 3], [8, 3, 2, 3], [12, 4], [4, 4])


def _dash_encoding(names: list[str], p: theme.Palette) -> dict[str, alt.StrokeDash]:
    """Colour-blind mode also varies the dash pattern, so colour is never the only cue."""
    if not p.colour_blind_lines:
        return {}
    ranges = [_DASHES[i % len(_DASHES)] for i in range(len(names))]
    return {
        "strokeDash": alt.StrokeDash(
            "series:N", scale=alt.Scale(domain=names, range=ranges), legend=None
        )
    }


def comparison_chart(
    frame: pd.DataFrame, *, title: str, fmt: str, p: theme.Palette = theme.DEFAULT
) -> Chart:
    """Several named series on one set of axes (columns of ``frame``, dated index)."""
    long = frame.rename_axis("date").reset_index().melt("date", var_name="series", value_name="v")
    names = [str(c) for c in frame.columns]
    chart = (
        alt.Chart(long.dropna())
        .mark_line(strokeWidth=p.line_width)
        .encode(
            x=alt.X("date:T", title=None, axis=_DATE_AXIS),
            y=alt.Y("v:Q", title=title, scale=alt.Scale(zero=False), axis=alt.Axis(format=fmt)),
            **_dash_encoding(names, p),
            color=alt.Color(
                "series:N",
                scale=alt.Scale(domain=names, range=series_colours(p, len(names))),
                legend=alt.Legend(
                    orient="top", title=None, labelColor=p.muted, symbolType="stroke"
                ),
            ),
            tooltip=[
                alt.Tooltip("date:T", title="Date"),
                alt.Tooltip("series:N", title="Series"),
                alt.Tooltip("v:Q", title=title, format=fmt),
            ],
        )
        .properties(height=_HEIGHT, width="container", padding=_PAD)
    )
    return _styled(chart, p)


def year_bars(frame: pd.DataFrame, p: theme.Palette = theme.DEFAULT) -> Chart:
    """Calendar-year returns, grouped by series."""
    long = frame.rename_axis("year").reset_index().melt("year", var_name="series", value_name="v")
    names = [str(c) for c in frame.columns]
    chart = (
        alt.Chart(long.dropna())
        .mark_bar()
        .encode(
            x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0)),
            xOffset="series:N",
            y=alt.Y("v:Q", title="Return", axis=alt.Axis(format="%")),
            color=alt.Color(
                "series:N",
                scale=alt.Scale(domain=names, range=series_colours(p, len(names))),
                legend=alt.Legend(orient="top", title=None, labelColor=p.muted),
            ),
            tooltip=[
                alt.Tooltip("year:O", title="Year"),
                alt.Tooltip("series:N", title="Series"),
                alt.Tooltip("v:Q", title="Return", format=".2%"),
            ],
        )
        .properties(height=_HEIGHT, width="container", padding=_PAD)
    )
    return _styled(chart, p)


def monthly_heatmap(grid: pd.DataFrame, p: theme.Palette = theme.DEFAULT) -> Chart:
    """Calendar grid of monthly returns, centred on zero (losses in the loss colour)."""
    months = [c for c in grid.columns if c != "Year"]
    long = (
        grid[months]
        .rename_axis("year")
        .reset_index()
        .melt("year", var_name="month", value_name="v")
        .dropna()
    )
    limit = float(max(abs(long["v"]).max(), 0.01))
    base = alt.Chart(long).encode(
        x=alt.X("month:N", sort=months, title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("year:O", title=None),
    )
    cells = base.mark_rect(stroke=p.background, strokeWidth=2).encode(
        color=alt.Color(
            "v:Q",
            scale=alt.Scale(
                domain=[-limit, 0, limit],
                range=[p.negative, p.surface, p.accent],
                interpolate="lab",
            ),
            legend=None,
        ),
        tooltip=[
            alt.Tooltip("year:O", title="Year"),
            alt.Tooltip("month:N", title="Month"),
            alt.Tooltip("v:Q", title="Return", format=".2%"),
        ],
    )
    labels = base.mark_text(fontSize=10, color=p.text).encode(text=alt.Text("v:Q", format=".1%"))
    height = max(80, 34 * len(grid))
    return _styled(
        alt.layer(cells, labels).properties(height=height, width="container", padding=_PAD), p
    )
