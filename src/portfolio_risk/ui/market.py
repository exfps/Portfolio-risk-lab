"""Sidebar panel for searching and downloading prices.

Downloaded prices are turned into CSV bytes and handed to the same loader and validator as an
uploaded file, so nothing downstream knows where the data came from. The provider is created
through ``PROVIDER_FACTORY`` so tests can replace it, and an operator can remove the whole
feature with ``PORTFOLIO_RISK_DISABLE_DOWNLOAD=1``.
"""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Callable
from dataclasses import dataclass

import streamlit as st

from portfolio_risk import PortfolioRiskError
from portfolio_risk.data import (
    CachedProvider,
    PriceProvider,
    PriceSeries,
    YahooProvider,
    align_prices,
    currency_warnings,
    download_many,
    to_base,
)
from portfolio_risk.data.align import Alignment
from portfolio_risk.errors import DataProviderError

DISABLE_DOWNLOAD = "PORTFOLIO_RISK_DISABLE_DOWNLOAD"
TICKERS = "tickers"
DOWNLOAD = "downloaded_prices"
MAX_TICKERS = 25
ALIGNMENTS: dict[str, Alignment] = {
    "Common trading days (daily)": "common",
    "Weekly, last price of the week": "weekly",
}

NO_CONVERSION = "No conversion"
BASE_CURRENCIES = (NO_CONVERSION, "USD", "SAR", "AED", "QAR", "KWD", "BHD", "OMR", "EUR", "GBP")

PROVIDER_FACTORY: Callable[[], PriceProvider] = YahooProvider


_shared: tuple[object, CachedProvider] | None = None


def _provider() -> PriceProvider:
    """One cache shared by every session of this server, rebuilt if the factory changes."""
    global _shared  # noqa: PLW0603 - deliberate process-wide cache
    if _shared is None or _shared[0] is not PROVIDER_FACTORY:
        _shared = (PROVIDER_FACTORY, CachedProvider(PROVIDER_FACTORY()))
    return _shared[1]


def download_disabled() -> bool:
    return os.environ.get(DISABLE_DOWNLOAD, "").strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Downloaded:
    csv: bytes
    symbols: tuple[str, ...]
    warnings: tuple[str, ...]
    benchmark: str | None = None
    source: str = "Downloaded prices"


def fetch(
    provider: PriceProvider,
    symbols: list[str],
    start: dt.date,
    end: dt.date,
    mode: Alignment,
    *,
    base: str | None = None,
    benchmark: str | None = None,
) -> Downloaded:
    """Download, align and serialise. Raises PortfolioRiskError subclasses with readable text."""
    if not symbols:
        raise DataProviderError("Add at least one ticker.")
    if len(symbols) > MAX_TICKERS:
        raise DataProviderError(f"At most {MAX_TICKERS} tickers at a time.")
    benchmark = benchmark.strip().upper() if benchmark else None
    if benchmark and benchmark in symbols:
        raise DataProviderError("The benchmark must not also be a portfolio ticker.")
    wanted = [*symbols, benchmark] if benchmark else list(symbols)
    got: list[PriceSeries] = download_many(provider, wanted, start, end)
    notes: list[str] = []
    if base:
        got, notes = to_base(got, base, provider, start, end)
    aligned = align_prices({g.symbol: g.prices for g in got}, mode)
    warnings = [
        *aligned.warnings,
        *currency_warnings({g.symbol: g.currency for g in got}),
        *notes,
    ]
    csv = aligned.prices.to_csv(float_format="%.6f", lineterminator="\n", index_label="date")
    source = (
        f"Yahoo Finance via yfinance, {start} to {end}, "
        f"{'weekly' if mode == 'weekly' else 'common-day'} alignment, "
        f"{'prices in ' + base if base else 'no currency conversion'}"
    )
    return Downloaded(
        csv.encode(), tuple(aligned.prices.columns), tuple(warnings), benchmark, source
    )


def _search_box() -> None:
    query = st.text_input("Find a ticker", placeholder="Company name or ticker", key="search_q")
    if not query.strip():
        return
    try:
        matches = _provider().search(query)
    except PortfolioRiskError as error:
        st.error(str(error))
        return
    if not matches:
        st.caption("No matches.")
        return
    labels = {f"{m.symbol}  |  {m.name}  |  {m.exchange}": m.symbol for m in matches}
    choice = st.selectbox("Matches", list(labels), key="search_pick")
    if st.button("Add to portfolio") and choice is not None:
        current = list(st.session_state.get(TICKERS, []))
        if labels[choice] not in current:
            current.append(labels[choice])
        st.session_state[TICKERS] = current


def downloaded_benchmark() -> str | None:
    """Benchmark symbol of the last successful download, used to preselect it in the settings."""
    saved: Downloaded | None = st.session_state.get(DOWNLOAD)
    return saved.benchmark if saved is not None else None


def downloaded_source() -> str:
    saved: Downloaded | None = st.session_state.get(DOWNLOAD)
    return saved.source if saved is not None else "Downloaded prices"


def sidebar_download() -> bytes | None:
    """Render the download controls. Returns the CSV bytes of the last successful download."""
    st.caption(
        "Prices come from Yahoo Finance through an unofficial library, for personal use. "
        "Check each ticker and its currency before relying on the result."
    )
    _search_box()
    symbols = st.multiselect(
        "Tickers",
        options=st.session_state.get(TICKERS, []),
        default=st.session_state.get(TICKERS, []),
        accept_new_options=True,
        help="Full Yahoo symbols, for example AAPL or 2222.SR. Type one and press Enter.",
    )
    today = dt.date.today()
    start = st.date_input("From", value=today - dt.timedelta(days=3 * 365), max_value=today)
    end = st.date_input("To", value=today, max_value=today)
    benchmark = st.text_input(
        "Benchmark ticker (optional)",
        placeholder="for example ^GSPC",
        help="An index or fund to compare against. Search for it above and copy the symbol.",
    ).strip()
    label = st.radio("Alignment", list(ALIGNMENTS), help="Markets trade on different days.")
    base_choice = st.selectbox(
        "Base currency",
        BASE_CURRENCIES,
        help="Convert every price to one currency using daily exchange rates from the same source.",
    )
    base = None if base_choice in (None, NO_CONVERSION) else base_choice
    if st.button("Download prices", type="primary"):
        try:
            with st.spinner("Downloading"):
                st.session_state[DOWNLOAD] = fetch(
                    _provider(),
                    [s.strip().upper() for s in symbols],
                    start if isinstance(start, dt.date) else today,
                    end if isinstance(end, dt.date) else today,
                    ALIGNMENTS[label or next(iter(ALIGNMENTS))],
                    base=base,
                    benchmark=benchmark or None,
                )
        except PortfolioRiskError as error:
            st.session_state.pop(DOWNLOAD, None)
            st.error(str(error))
    saved: Downloaded | None = st.session_state.get(DOWNLOAD)
    if saved is None:
        return None
    st.caption(f"Loaded: {', '.join(saved.symbols)}")
    for warning in saved.warnings:
        st.warning(warning)
    return saved.csv


__all__ = [
    "Downloaded",
    "download_disabled",
    "downloaded_benchmark",
    "downloaded_source",
    "fetch",
    "sidebar_download",
]
