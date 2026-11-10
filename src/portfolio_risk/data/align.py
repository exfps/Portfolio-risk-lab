"""Combine separately downloaded series into one price table.

Markets close on different days (Saudi Arabia trades Sunday to Thursday, the UAE Monday to
Friday), so series from different exchanges rarely share every date. Two strategies:

* ``common``: keep only dates on which every series has a price. Daily frequency, but days are
  dropped, and two markets with a single shared weekday would leave very few.
* ``weekly``: take each series' last price in the week ending Friday, then keep weeks present
  in all series. Loses daily detail, but a Sunday-Thursday market and a Monday-Friday market line
  up cleanly. Weekly returns are not scaled to daily ones, so volatility must use 52 periods.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import pandas as pd

from portfolio_risk.errors import DataValidationError

Alignment = Literal["common", "weekly"]
PERIODS_PER_YEAR: dict[str, int] = {"common": 252, "weekly": 52}
MIN_ROWS = 3


@dataclass(frozen=True)
class Aligned:
    prices: pd.DataFrame
    periods_per_year: int
    warnings: list[str]


def align_prices(series: Mapping[str, pd.Series], mode: Alignment = "common") -> Aligned:
    if not series:
        raise DataValidationError("No price series to align.")
    if mode not in PERIODS_PER_YEAR:
        raise DataValidationError(f"Unknown alignment {mode!r}; use 'common' or 'weekly'.")

    prepared: dict[str, pd.Series] = {}
    for name, raw in series.items():
        s = raw.dropna()
        s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
        s = s[~s.index.duplicated(keep="last")].sort_index()
        if mode == "weekly":
            s = s.resample("W-FRI").last().dropna()
        prepared[name] = s

    frame = pd.concat(prepared, axis=1, join="inner")
    frame.columns = list(prepared)
    warnings: list[str] = []
    for name, s in prepared.items():
        dropped = len(s) - len(frame)
        if dropped > 0:
            unit = "weeks" if mode == "weekly" else "days"
            warnings.append(
                f"{name}: {dropped} of {len(s)} {unit} dropped because another series "
                "has no price then."
            )
    if len(frame) < MIN_ROWS:
        raise DataValidationError(
            f"Only {len(frame)} shared {'weeks' if mode == 'weekly' else 'dates'} across "
            f"{', '.join(prepared)}. Widen the date range"
            + ("." if mode == "weekly" else " or switch to weekly alignment.")
        )
    return Aligned(frame, PERIODS_PER_YEAR[mode], warnings)


def currency_warnings(currencies: Mapping[str, str | None]) -> list[str]:
    """Warn about mixed or unknown currencies. No conversion is performed."""
    out: list[str] = []
    unknown = sorted(s for s, c in currencies.items() if not c)
    known = {c for c in currencies.values() if c}
    if unknown:
        out.append(f"Currency not reported for {', '.join(unknown)}.")
    if len(known) > 1:
        detail = ", ".join(f"{s} {c}" for s, c in sorted(currencies.items()) if c)
        out.append(
            f"Mixed currencies ({detail}). Prices are not converted, so returns include "
            "exchange-rate effects only for assets quoted in a foreign currency, and "
            "comparisons against a benchmark in another currency are approximate."
        )
    return out
