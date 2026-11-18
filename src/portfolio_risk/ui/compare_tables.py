"""Portfolio comparison tables as display strings. Pure: no Streamlit import."""

from __future__ import annotations

import math

import pandas as pd

from portfolio_risk.ui import formatting


def weights_frame(weights: pd.DataFrame) -> pd.DataFrame:
    rows = [
        [
            str(asset),
            *("-" if not math.isfinite(float(v)) else formatting.percent(float(v), 1) for v in row),
        ]
        for asset, row in zip(weights.index, weights.to_numpy(dtype=float), strict=True)
    ]
    return pd.DataFrame(rows, columns=["Holding", *map(str, weights.columns)])


def concentration_frame(concentration: pd.DataFrame) -> pd.DataFrame:
    layout = (
        ("holdings", "Holdings", "{:,.0f}"),
        ("hhi", "Concentration (HHI)", "{:.3f}"),
        ("effective_positions", "Effective number of positions", "{:.2f}"),
    )
    rows = [
        [label, *(pattern.format(float(v)) for v in concentration.loc[key].to_numpy(dtype=float))]
        for key, label, pattern in layout
    ]
    return pd.DataFrame(rows, columns=["Measure", *map(str, concentration.columns)])


def correlation_frame(correlation: pd.DataFrame) -> pd.DataFrame:
    rows = [
        [str(name), *(formatting.ratio(float(v)) for v in row)]
        for name, row in zip(correlation.index, correlation.to_numpy(dtype=float), strict=True)
    ]
    return pd.DataFrame(rows, columns=["", *map(str, correlation.columns)])
