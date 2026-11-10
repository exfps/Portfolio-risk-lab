"""Data layer tests use a fake yfinance module; nothing here touches the network."""

from __future__ import annotations

import datetime as dt
import time
from typing import Any

import pandas as pd
import pytest

from portfolio_risk.data import (
    CachedProvider,
    PriceSeries,
    SymbolMatch,
    YahooProvider,
    align_prices,
    currency_warnings,
    download_many,
    to_base,
)
from portfolio_risk.errors import DataProviderError, DataValidationError

D = dt.date


class FakeTicker:
    def __init__(
        self, symbol: str, frames: dict[str, pd.DataFrame], currencies: dict[str, str]
    ) -> None:
        self.symbol = symbol
        self._frames = frames
        self.fast_info = {"currency": currencies.get(symbol)}

    def history(self, start: dt.date, end: dt.date, auto_adjust: bool) -> pd.DataFrame:
        assert auto_adjust is True
        return self._frames.get(self.symbol, pd.DataFrame())


class FakeSearch:
    def __init__(self, query: str, max_results: int) -> None:
        self.quotes: list[dict[str, str]] = [
            {
                "symbol": "2222.SR",
                "shortname": "Saudi Aramco",
                "exchDisp": "Saudi",
                "quoteType": "EQUITY",
            },
            {"shortname": "no symbol"},
        ][:max_results]


class FakeYF:
    def __init__(
        self,
        frames: dict[str, pd.DataFrame] | None = None,
        currencies: dict[str, str] | None = None,
    ) -> None:
        self.frames = frames or {}
        self.currencies = currencies or {}
        self.Search = FakeSearch

    def Ticker(self, symbol: str) -> FakeTicker:  # noqa: N802 - mirrors yfinance
        return FakeTicker(symbol, self.frames, self.currencies)


class BoomYF(FakeYF):
    def Ticker(self, symbol: str) -> FakeTicker:  # noqa: N802
        raise RuntimeError("timeout")


def frame(dates: list[str], closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"Close": closes}, index=pd.DatetimeIndex(dates, tz="Asia/Riyadh"))


def series(dates: list[str], values: list[float]) -> pd.Series[Any]:
    return pd.Series(values, index=pd.DatetimeIndex(dates), dtype=float)


def test_search_skips_rows_without_symbol() -> None:
    out = YahooProvider(FakeYF()).search("aramco")
    assert [m.symbol for m in out] == ["2222.SR"]
    assert out[0].name == "Saudi Aramco"


def test_search_empty_query_makes_no_call() -> None:
    assert YahooProvider(object()).search("  ") == []


def test_download_normalises_index_and_currency() -> None:
    yf = FakeYF({"2222.SR": frame(["2025-01-05", "2025-01-06"], [10.0, 11.0])}, {"2222.SR": "sar"})
    got = YahooProvider(yf).download("2222.sr", D(2025, 1, 1), D(2025, 2, 1))
    assert got.symbol == "2222.SR"
    assert got.currency == "SAR"
    assert pd.DatetimeIndex(got.prices.index).tz is None
    assert list(got.prices) == [10.0, 11.0]


def test_download_unknown_symbol_is_actionable() -> None:
    with pytest.raises(DataProviderError, match="No prices returned for NOPE"):
        YahooProvider(FakeYF()).download("NOPE", D(2025, 1, 1), D(2025, 2, 1))


def test_download_rejects_bad_range() -> None:
    with pytest.raises(DataProviderError, match="before"):
        YahooProvider(FakeYF()).download("X", D(2025, 2, 1), D(2025, 1, 1))


def test_missing_currency_is_none() -> None:
    yf = FakeYF({"X": frame(["2025-01-05"], [1.0])})
    assert YahooProvider(yf).download("X", D(2025, 1, 1), D(2025, 2, 1)).currency is None


def test_network_error_wrapped() -> None:
    with pytest.raises(DataProviderError, match="timeout"):
        YahooProvider(BoomYF()).download("X", D(2025, 1, 1), D(2025, 2, 1))


def test_common_alignment_drops_unshared_days_and_warns() -> None:
    # 2025-01-05 is a Sunday and 2025-01-10 a Friday: a Sun-Thu market against a Mon-Fri market.
    sa = series(
        ["2025-01-05", "2025-01-06", "2025-01-07", "2025-01-08", "2025-01-09"], [1, 2, 3, 4, 5]
    )
    ae = series(
        ["2025-01-06", "2025-01-07", "2025-01-08", "2025-01-09", "2025-01-10"], [1, 2, 3, 4, 5]
    )
    out = align_prices({"SA": sa, "AE": ae}, "common")
    assert len(out.prices) == 4
    assert out.periods_per_year == 252
    assert out.prices.index[0] == pd.Timestamp("2025-01-06")
    assert any("SA: 1 of 5 days" in w for w in out.warnings)


def test_weekly_alignment_uses_last_price_in_week() -> None:
    sa = series(
        ["2025-01-05", "2025-01-09", "2025-01-12", "2025-01-16", "2025-01-19", "2025-01-23"],
        [1, 2, 3, 4, 5, 6],
    )
    ae = series(
        ["2025-01-06", "2025-01-10", "2025-01-13", "2025-01-17", "2025-01-20", "2025-01-24"],
        [10, 20, 30, 40, 50, 60],
    )
    out = align_prices({"SA": sa, "AE": ae}, "weekly")
    assert out.periods_per_year == 52
    # Week ending Fri 10 Jan: SA saw Sun 5th and Thu 9th (last = 2); AE saw Mon 6th, Fri 10th.
    assert list(out.prices.loc["2025-01-10"]) == [2.0, 20.0]
    # Sunday the 5th falls in the week ending Friday the 10th, so it is not a week of its own.
    assert len(out.prices) == 3


def test_too_few_shared_dates_raises_with_hint() -> None:
    a = series(["2025-01-06", "2025-01-07", "2025-01-08"], [1, 2, 3])
    b = series(["2025-02-06", "2025-02-07", "2025-02-08"], [1, 2, 3])
    with pytest.raises(DataValidationError, match="weekly alignment"):
        align_prices({"A": a, "B": b})


def test_unknown_mode_and_empty_input() -> None:
    with pytest.raises(DataValidationError):
        align_prices({})
    with pytest.raises(DataValidationError, match="Unknown alignment"):
        align_prices({"A": series(["2025-01-06"], [1])}, "monthly")  # type: ignore[arg-type]


def test_duplicate_dates_keep_last() -> None:
    s = series(["2025-01-06", "2025-01-06", "2025-01-07", "2025-01-08"], [1, 9, 2, 3])
    assert align_prices({"A": s}).prices["A"].iloc[0] == 9.0


def test_currency_warnings() -> None:
    assert currency_warnings({"A": "SAR", "B": "SAR"}) == []
    assert "Mixed currencies" in currency_warnings({"A": "SAR", "B": "USD"})[0]
    assert "not reported for B" in currency_warnings({"A": "SAR", "B": None})[0]


class FxProvider:
    """Prices in SAR and USD plus a SARUSD=X rate that moves, to check the arithmetic."""

    name = "fx-fake"

    def search(self, query: str, limit: int = 10) -> list[SymbolMatch]:
        return []

    def download(self, symbol: str, start: dt.date, end: dt.date) -> PriceSeries:
        days = pd.date_range("2025-01-01", periods=6, freq="D")  # includes a weekend
        if symbol == "SARUSD=X":
            return PriceSeries(symbol, pd.Series([0.25, 0.25, 0.26, 0.26, 0.27, 0.27], days), None)
        raise AssertionError(symbol)


def test_to_base_multiplies_by_last_available_rate() -> None:
    bdays = pd.DatetimeIndex(["2025-01-01", "2025-01-03", "2025-01-06"])
    sar = PriceSeries("AAA.SR", pd.Series([100.0, 100.0, 100.0], bdays), "SAR")
    usd = PriceSeries("BBB", pd.Series([5.0, 5.0, 5.0], bdays), "USD")
    out, notes = to_base([sar, usd], "USD", FxProvider(), D(2025, 1, 1), D(2025, 2, 1))
    assert list(out[0].prices) == [25.0, 26.0, 27.0]
    assert out[0].currency == "USD"
    assert list(out[1].prices) == [5.0, 5.0, 5.0]
    assert notes == ["AAA.SR converted from SAR to USD."]


def test_to_base_refuses_unknown_and_minor_unit_currencies() -> None:
    s = pd.Series([1.0], pd.DatetimeIndex(["2025-01-01"]))
    with pytest.raises(DataProviderError, match="no reported currency"):
        to_base([PriceSeries("X", s, None)], "USD", FxProvider(), D(2025, 1, 1), D(2025, 2, 1))
    with pytest.raises(DataProviderError, match="minor unit"):
        to_base([PriceSeries("X", s, "GBp")], "USD", FxProvider(), D(2025, 1, 1), D(2025, 2, 1))
    with pytest.raises(DataProviderError, match="three-letter"):
        to_base([PriceSeries("X", s, "USD")], "US", FxProvider(), D(2025, 1, 1), D(2025, 2, 1))


def test_to_base_drops_dates_before_first_rate() -> None:
    idx = pd.DatetimeIndex(["2024-12-30", "2025-01-02"])
    sar = PriceSeries("AAA.SR", pd.Series([100.0, 100.0], idx), "SAR")
    out, notes = to_base([sar], "USD", FxProvider(), D(2024, 12, 1), D(2025, 2, 1))
    assert list(out[0].prices) == [25.0]
    assert "1 early dates dropped" in notes[0]


class CountingProvider:
    name = "counting"

    def __init__(self) -> None:
        self.downloads = 0
        self.searches = 0

    def search(self, query: str, limit: int = 10) -> list[SymbolMatch]:
        self.searches += 1
        return [SymbolMatch("X", "x", "e", "EQUITY")]

    def download(self, symbol: str, start: dt.date, end: dt.date) -> PriceSeries:
        self.downloads += 1
        if symbol == "BAD":
            raise DataProviderError("bad symbol")
        s = pd.Series([1.0, 2.0], pd.DatetimeIndex(["2025-01-01", "2025-01-02"]))
        return PriceSeries(symbol, s, "USD")


def test_cache_serves_repeats_and_returns_independent_copies() -> None:
    inner = CountingProvider()
    cached = CachedProvider(inner)
    first = cached.download("a", D(2025, 1, 1), D(2025, 2, 1))
    first.prices.iloc[0] = 99.0
    again = cached.download("A", D(2025, 1, 1), D(2025, 2, 1))
    assert inner.downloads == 1
    assert again.prices.iloc[0] == 1.0
    cached.search("Aramco")
    cached.search(" aramco ")
    assert inner.searches == 1


def test_cache_expires_and_is_bounded() -> None:
    now = [0.0]
    inner = CountingProvider()
    cached = CachedProvider(inner, ttl_seconds=10, max_entries=2, clock=lambda: now[0])
    cached.download("A", D(2025, 1, 1), D(2025, 2, 1))
    now[0] = 11.0
    cached.download("A", D(2025, 1, 1), D(2025, 2, 1))
    assert inner.downloads == 2
    for sym in ("B", "C", "D"):
        cached.download(sym, D(2025, 1, 1), D(2025, 2, 1))
    cached.download("B", D(2025, 1, 1), D(2025, 2, 1))
    assert inner.downloads == 6  # B was evicted by the bound of two entries


def test_errors_are_not_cached() -> None:
    inner = CountingProvider()
    cached = CachedProvider(inner)
    for _ in range(2):
        with pytest.raises(DataProviderError):
            cached.download("BAD", D(2025, 1, 1), D(2025, 2, 1))
    assert inner.downloads == 2


def test_download_many_keeps_order_and_reports_first_failure_in_order() -> None:
    inner = CountingProvider()
    out = download_many(inner, ["B", "A", "C"], D(2025, 1, 1), D(2025, 2, 1))
    assert [o.symbol for o in out] == ["B", "A", "C"]
    with pytest.raises(DataProviderError, match="bad symbol"):
        download_many(inner, ["A", "BAD", "C"], D(2025, 1, 1), D(2025, 2, 1))


def test_download_many_runs_requests_concurrently() -> None:

    class Slow(CountingProvider):
        def download(self, symbol: str, start: dt.date, end: dt.date) -> PriceSeries:
            time.sleep(0.2)
            return super().download(symbol, start, end)

    began = time.perf_counter()
    out = download_many(Slow(), list("ABCDEF"), D(2025, 1, 1), D(2025, 2, 1))
    elapsed = time.perf_counter() - began
    assert len(out) == 6
    assert elapsed < 0.8  # six sequential 0.2 s calls would take 1.2 s
