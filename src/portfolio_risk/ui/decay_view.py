"""The Alpha Decay tab: is the portfolio behaving differently from its own past?"""

from __future__ import annotations

import html
import math

import pandas as pd
import streamlit as st

from portfolio_risk import PortfolioRiskError
from portfolio_risk.decay import (
    DEFAULT_WINDOWS,
    METRICS,
    RATINGS,
    DecayReport,
    alpha_decay,
    metric_by_key,
    parse_windows,
    rolling_values,
)
from portfolio_risk.ui import charts, formatting, theme
from portfolio_risk.ui.decay_tables import METHOD, detail_frame, format_value

WINDOWS_KEY = "decay_windows"
_BADGE = {
    "Excellent": "excellent",
    "Good": "good",
    "Warning": "warning",
    "Critical": "critical",
    "Insufficient history": "none",
}


def badge(rating: str) -> str:
    return f'<span class="badge badge-{_BADGE[rating]}">{html.escape(rating)}</span>'


def matrix_html(report: DecayReport) -> str:
    """Statistic by window grid. Every rating carries its text label as well as its colour."""
    head = "".join(f"<th>{w}-period window</th>" for w in report.windows)
    rows = []
    for metric in METRICS:
        cells = []
        for window in report.windows:
            c = report.cell(metric.key, window)
            score = f"z {c.z:+.2f}" if math.isfinite(c.z) else ""
            cells.append(
                f"<td><div class='dv'>{html.escape(format_value(metric, c.latest))}</div>"
                f"<div class='dz'>{badge(c.rating)} {score}</div></td>"
            )
        rows.append(f"<tr><td>{html.escape(metric.label)}</td>{''.join(cells)}</tr>")
    return (
        '<table class="tbl decay"><thead><tr><th>Statistic</th>'
        f"{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


@st.cache_data(max_entries=8, show_spinner=False)
def _report(returns: pd.Series, windows: tuple[int, ...], ppy: int, rf: float) -> DecayReport:
    return alpha_decay(returns, periods_per_year=ppy, windows=windows, risk_free=rf)


def render(
    returns: pd.Series, palette: theme.Palette, periods_per_year: int, risk_free_annual: float
) -> None:
    st.caption(
        "Compares the portfolio's most recent behaviour with its own history. "
        "A deterioration shows up here before it shows up in the long-run totals."
    )
    text = st.text_input(
        "Window lengths (periods)",
        value=st.session_state.get(WINDOWS_KEY, ", ".join(map(str, DEFAULT_WINDOWS))),
        help="Comma-separated, 5 to 1,000 periods each, up to six windows.",
        key=WINDOWS_KEY,
    )
    try:
        windows = parse_windows(text)
        report = _report(returns, windows, periods_per_year, risk_free_annual)
    except PortfolioRiskError as error:
        st.error(str(error))
        return

    counts = report.counts()
    cols = st.columns(5)
    cols[0].metric("Healthy", f"{report.healthy} of {report.rated}")
    for col, name in zip(cols[1:], RATINGS, strict=True):
        col.metric(name, str(counts[name]))
    st.caption(
        f"As of {formatting.day(report.as_of)}. Healthy means rated Good or Excellent. "
        f"{counts['Insufficient history']} of {len(report.cells)} cells could not be rated "
        "(too few earlier windows)."
    )
    st.markdown(matrix_html(report), unsafe_allow_html=True)

    left, right = st.columns(2)
    labels = {m.label: m.key for m in METRICS}
    label = left.selectbox("Statistic", list(labels), key="decay_metric")
    window = right.selectbox("Window", list(report.windows), key="decay_window")
    metric = metric_by_key(labels[label])
    cell = report.cell(metric.key, int(window))
    series = rolling_values(
        returns.dropna(), metric, int(window), periods_per_year, risk_free_annual
    )
    if cell.rating == "Insufficient history":
        st.info("Not enough earlier windows to rate this statistic. Try a shorter window.")
    else:
        st.markdown(f"{badge(cell.rating)}", unsafe_allow_html=True)
        st.altair_chart(
            charts.decay_chart(
                series,
                mean=cell.history_mean,
                std=cell.history_std,
                label=metric.label,
                fmt=metric.fmt,
                p=palette,
            ),
        )
        st.markdown(formatting.html_table(detail_frame(cell)), unsafe_allow_html=True)
    st.caption(METHOD)
