"""Helpers for the weights editor. Pure: no Streamlit import."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from portfolio_risk.vision import ExtractedPosition


def weights_frame(tickers: Sequence[str], supplied: pd.Series | None) -> pd.DataFrame:
    """Rows for the weights editor, with columns ``ticker`` and ``weight``.

    Without ``supplied`` weights, every ticker gets an equal weight. With them, a ticker not
    listed gets 0, so it stays visible and editable instead of being dropped. Tickers that
    appear only in ``supplied`` are appended so the analysis can report them.
    """
    names = [str(name) for name in tickers]
    if supplied is None:
        values = [1.0 / len(names)] * len(names) if names else []
    else:
        lookup = {str(name): float(value) for name, value in supplied.items()}
        names += [name for name in lookup if name not in names]
        values = [lookup.get(name, 0.0) for name in names]
    return pd.DataFrame({"ticker": names, "weight": values})


def weights_from_frame(frame: pd.DataFrame) -> pd.Series:
    """Series of weights indexed by ticker. Cleared cells become NaN and are rejected later."""
    values = pd.to_numeric(frame["weight"], errors="coerce").to_numpy(dtype=np.float64)
    return pd.Series(values, index=pd.Index(frame["ticker"].astype(str)), name="weight")


SKIP = "(skip)"


def review_frame(positions: Sequence[ExtractedPosition], columns: Sequence[str]) -> pd.DataFrame:
    """Editable review table for positions read from a screenshot.

    ``price_column`` is pre-filled only when a price column has the same name ignoring case;
    otherwise it is ``SKIP`` and the person chooses. Guessing a mapping would hide errors.
    """
    by_name = {name.casefold(): name for name in columns}
    return pd.DataFrame(
        {
            "ticker": [p.ticker for p in positions],
            "market_value": [p.market_value for p in positions],
            "weight_percent": [p.weight_percent for p in positions],
            "price_column": [by_name.get(p.ticker.casefold(), SKIP) for p in positions],
        }
    )


def positions_from_review(frame: pd.DataFrame) -> tuple[list[ExtractedPosition], list[str]]:
    """Reviewed rows as positions keyed by price column, and the tickers left unmapped."""

    def number(value: object) -> float | None:
        converted = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        return None if pd.isna(converted) else float(converted)

    mapped: list[ExtractedPosition] = []
    skipped: list[str] = []
    for row in frame.itertuples(index=False):
        column = str(row.price_column)
        if column == SKIP or not column:
            skipped.append(str(row.ticker))
            continue
        mapped.append(
            ExtractedPosition(column, number(row.market_value), number(row.weight_percent))
        )
    return mapped, skipped
