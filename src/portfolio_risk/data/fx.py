"""Convert downloaded prices into one base currency using daily exchange-rate series.

A price in currency C becomes ``price * rate(C to base)`` on each date, where the rate is the
last available rate on or before that date (exchange rates trade on days equities do not). The
returns of a converted series therefore include exchange-rate movement, which is what a
base-currency investor experiences. Rates come from the same provider as the prices, so their
quality is the provider's.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from portfolio_risk.data.base import PriceProvider, PriceSeries
from portfolio_risk.errors import DataProviderError


def pair_symbol(currency: str, base: str) -> str:
    """Yahoo-style symbol for the rate converting one unit of ``currency`` into ``base``."""
    return f"{currency}{base}=X"


def to_base(
    series: list[PriceSeries],
    base: str,
    provider: PriceProvider,
    start: dt.date,
    end: dt.date,
) -> tuple[list[PriceSeries], list[str]]:
    base = base.strip().upper()
    if len(base) != 3 or not base.isalpha():
        raise DataProviderError(f"Base currency must be a three-letter code, not {base!r}.")
    rates: dict[str, pd.Series] = {}
    out: list[PriceSeries] = []
    notes: list[str] = []
    for item in series:
        code = item.currency
        if not code:
            raise DataProviderError(
                f"{item.symbol} has no reported currency, so it cannot be converted to {base}. "
                "Remove it or choose 'No conversion'."
            )
        if code != code.upper() or len(code) != 3:
            raise DataProviderError(
                f"{item.symbol} is quoted in {code!r}, which looks like a minor unit or an "
                "unusual code. Conversion is not attempted; check the quote currency."
            )
        if code == base:
            out.append(item)
            continue
        if code not in rates:
            rates[code] = provider.download(pair_symbol(code, base), start, end).prices
            if rates[code].empty:
                raise DataProviderError(f"No exchange rates for {code} to {base}.")
        fx = rates[code]
        union = item.prices.index.union(fx.index)
        aligned = fx.reindex(union).ffill().reindex(item.prices.index)
        converted = (item.prices * aligned).dropna()
        lost = len(item.prices) - len(converted)
        if lost:
            notes.append(
                f"{item.symbol}: {lost} early dates dropped because no {code}/{base} rate "
                "was available on or before them."
            )
        if converted.empty:
            raise DataProviderError(f"No overlap between {item.symbol} prices and {code}/{base}.")
        converted.name = item.symbol
        out.append(PriceSeries(item.symbol, converted, base))
        notes.append(f"{item.symbol} converted from {code} to {base}.")
    return out, notes
