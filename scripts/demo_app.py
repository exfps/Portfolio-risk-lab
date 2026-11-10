"""The interface with an offline demo price source, used only to take documentation screenshots.

The real app downloads prices from Yahoo Finance. Screenshots must not depend on the network or
show real tickers next to made-up numbers, so this wrapper swaps in a provider that returns
clearly synthetic series (``DEMO.*``). Nothing here is part of the installed package.

    streamlit run scripts/demo_app.py
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from portfolio_risk.data import PriceSeries, SymbolMatch
from portfolio_risk.errors import DataProviderError
from portfolio_risk.ui import app, market

CATALOGUE = {
    # symbol: (name, exchange, currency, annual drift, annual volatility, trades Sunday-Thursday)
    "DEMO.A": ("Demo Equity A", "Synthetic exchange (USD)", "USD", 0.09, 0.18, False),
    "DEMO.B": ("Demo Equity B", "Synthetic exchange (SAR)", "SAR", 0.07, 0.22, True),
    "DEMO.C": ("Demo Equity C", "Synthetic exchange (SAR)", "SAR", 0.05, 0.16, True),
    "DEMO.IDX": ("Demo Index", "Synthetic exchange (USD)", "USD", 0.06, 0.14, False),
}


class DemoProvider:
    name = "Offline demo data (synthetic)"

    def search(self, query: str, limit: int = 10) -> list[SymbolMatch]:
        q = query.strip().lower()
        return [
            SymbolMatch(symbol, name, exchange, "EQUITY")
            for symbol, (name, exchange, *_rest) in CATALOGUE.items()
            if q in symbol.lower() or q in name.lower()
        ][:limit]

    def download(self, symbol: str, start: dt.date, end: dt.date) -> PriceSeries:
        if symbol == "SARUSD=X":
            days = pd.bdate_range(start, end)
            rate = pd.Series(0.2667 + np.random.default_rng(7).normal(0, 0.00004, len(days)), days)
            return PriceSeries(symbol, rate, None)
        if symbol not in CATALOGUE:
            raise DataProviderError(f"No prices returned for {symbol}.")
        _name, _exchange, currency, drift, vol, sun_thu = CATALOGUE[symbol]
        weekmask = "Sun Mon Tue Wed Thu" if sun_thu else "Mon Tue Wed Thu Fri"
        days = pd.bdate_range(start, end, freq="C", weekmask=weekmask)
        rng = np.random.default_rng(sum(map(ord, symbol)))
        steps = rng.normal(drift / 252, vol / 252**0.5, len(days))
        prices = pd.Series(100 * np.exp(np.cumsum(steps)), days, name=symbol)
        return PriceSeries(symbol, prices, currency)


market.PROVIDER_FACTORY = DemoProvider
app.main()
