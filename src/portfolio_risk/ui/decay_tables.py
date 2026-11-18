"""Alpha Decay tables as display strings. Pure: no Streamlit import."""

from __future__ import annotations

import math

import pandas as pd

from portfolio_risk.decay import METRICS, DecayCell, DecayMetric, DecayReport
from portfolio_risk.ui import formatting

METHOD = (
    "Each statistic is computed over rolling windows of the portfolio's returns. The latest window "
    "is compared with every earlier window of the same length: the score is how many standard "
    "deviations it sits from their average, signed so that higher is always better (lower "
    "volatility scores positively). Excellent is +1.0 or more, Good down to -0.5, Warning down to "
    "-1.5, Critical below that. The bands are conventions, not tests. Windows overlap, so "
    "neighbouring values are strongly correlated and the scores are descriptive, not statistical "
    "evidence that a strategy has stopped working."
)


def format_value(metric: DecayMetric, value: float) -> str:
    if not math.isfinite(value):
        return formatting.NOT_AVAILABLE
    if metric.fmt == "ratio":
        return formatting.ratio(value)
    return formatting.percent(value, 1 if metric.fmt == "pct" else 2)


def detail_frame(cell: DecayCell) -> pd.DataFrame:
    metric = cell.metric
    rows = [
        ("Latest window", format_value(metric, cell.latest)),
        ("Average of earlier windows", format_value(metric, cell.history_mean)),
        ("Standard deviation of earlier windows", format_value(metric, cell.history_std)),
        ("Score (z, higher is better)", f"{cell.z:+.2f}" if math.isfinite(cell.z) else "n/a"),
        (
            "Better than this share of earlier windows",
            formatting.percent(cell.percentile, 0) if math.isfinite(cell.percentile) else "n/a",
        ),
        ("Earlier windows compared", f"{cell.n_history:,}"),
    ]
    return pd.DataFrame(rows, columns=["Measure", "Value"])


def matrix_frame(report: DecayReport) -> pd.DataFrame:
    """Statistic by window, each cell as "value | rating (z)" for the PDF and Excel exports."""
    rows = []
    for metric in METRICS:
        cells = []
        for window in report.windows:
            c = report.cell(metric.key, window)
            score = f" ({c.z:+.2f})" if math.isfinite(c.z) else ""
            cells.append(f"{format_value(metric, c.latest)} | {c.rating}{score}")
        rows.append([metric.label, *cells])
    return pd.DataFrame(
        rows, columns=["Statistic", *(f"{w}-period window" for w in report.windows)]
    )
