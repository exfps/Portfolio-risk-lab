"""Provider-neutral types for downloading prices.

Nothing here knows about a specific vendor, so a licensed provider can replace Yahoo Finance
by implementing ``PriceProvider``.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Protocol

import pandas as pd


@dataclass(frozen=True)
class SymbolMatch:
    """One search result."""

    symbol: str
    name: str
    exchange: str
    kind: str


@dataclass(frozen=True)
class PriceSeries:
    """Adjusted closing prices for one symbol.

    ``currency`` is whatever the provider reports, or None when it reports nothing.
    """

    symbol: str
    prices: pd.Series
    currency: str | None


class PriceProvider(Protocol):
    """What the rest of the package needs from a data source."""

    name: str

    def search(self, query: str, limit: int = 10) -> list[SymbolMatch]: ...

    def download(self, symbol: str, start: dt.date, end: dt.date) -> PriceSeries: ...
