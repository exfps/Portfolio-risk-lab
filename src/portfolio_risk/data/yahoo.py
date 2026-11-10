"""Yahoo Finance adapter built on the unofficial ``yfinance`` library.

Status: **not tested against the live service** in this repository's tests, which use a fake
module. Yahoo's data is licensed for personal use only and the endpoints can change without
notice; do not build a commercial service on this adapter.

Symbol suffixes for Gulf exchanges are not hard-coded here: pass full Yahoo symbols
(for example ``2222.SR``) and verify them with search.
"""

from __future__ import annotations

import datetime as dt
import importlib
from types import ModuleType
from typing import Any

import pandas as pd

from portfolio_risk.data.base import PriceSeries, SymbolMatch
from portfolio_risk.errors import DataProviderError


def _load_yfinance() -> ModuleType:
    try:
        return importlib.import_module("yfinance")
    except ImportError as exc:
        raise DataProviderError(
            "Price download needs the optional 'yfinance' package: pip install -e \".[data]\""
        ) from exc


class YahooProvider:
    name = "Yahoo Finance (yfinance, unofficial)"

    def __init__(self, module: Any | None = None) -> None:
        self._module = module

    @property
    def yf(self) -> Any:
        if self._module is None:
            self._module = _load_yfinance()
        return self._module

    def search(self, query: str, limit: int = 10) -> list[SymbolMatch]:
        query = query.strip()
        if not query:
            return []
        try:
            quotes = self.yf.Search(query, max_results=limit).quotes
        except DataProviderError:
            raise
        except Exception as exc:
            raise DataProviderError(f"Search failed: {exc}") from exc
        out: list[SymbolMatch] = []
        for q in quotes or []:
            symbol = q.get("symbol")
            if not symbol:
                continue
            out.append(
                SymbolMatch(
                    symbol=str(symbol),
                    name=str(q.get("shortname") or q.get("longname") or ""),
                    exchange=str(q.get("exchDisp") or q.get("exchange") or ""),
                    kind=str(q.get("quoteType") or ""),
                )
            )
        return out[:limit]

    def download(self, symbol: str, start: dt.date, end: dt.date) -> PriceSeries:
        symbol = symbol.strip().upper()
        if not symbol:
            raise DataProviderError("Empty ticker.")
        if start >= end:
            raise DataProviderError("Start date must be before end date.")
        try:
            ticker = self.yf.Ticker(symbol)
            history = ticker.history(start=start, end=end, auto_adjust=True)
            currency = _currency(ticker)
        except DataProviderError:
            raise
        except Exception as exc:
            raise DataProviderError(f"Download failed for {symbol}: {exc}") from exc
        if history is None or history.empty or "Close" not in history:
            raise DataProviderError(
                f"No prices returned for {symbol} between {start} and {end}. "
                "Check the symbol and its exchange suffix."
            )
        prices = history["Close"].astype(float).dropna()
        prices.index = pd.DatetimeIndex(prices.index).tz_localize(None).normalize()
        prices.name = symbol
        return PriceSeries(symbol, prices, currency)


def _currency(ticker: Any) -> str | None:
    try:
        value = ticker.fast_info["currency"]
    except Exception:
        return None
    return str(value).upper() if value else None
