"""Search-and-download flow, driven through Streamlit's test harness with a fake provider."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from portfolio_risk.data import PriceSeries, SymbolMatch
from portfolio_risk.errors import DataProviderError
from portfolio_risk.ui import market
from portfolio_risk.ui.formatting import risk_free_note

APP = Path(__file__).resolve().parents[1] / "src" / "portfolio_risk" / "ui" / "app.py"


class FakeProvider:
    name = "fake"

    def search(self, query: str, limit: int = 10) -> list[SymbolMatch]:
        return [SymbolMatch("2222.SR", "Saudi Aramco", "Saudi", "EQUITY")]

    def download(self, symbol: str, start: dt.date, end: dt.date) -> PriceSeries:
        if symbol == "BAD":
            raise DataProviderError("No prices returned for BAD.")
        index = pd.bdate_range("2024-01-01", periods=120)
        seed = sum(map(ord, symbol))
        steps = np.random.default_rng(seed).normal(0.0004, 0.01, len(index))
        prices = pd.Series(100 * np.exp(np.cumsum(steps)), index=index, name=symbol)
        return PriceSeries(symbol, prices, "SAR" if symbol.endswith(".SR") else "USD")


@pytest.fixture(autouse=True)
def fake_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(market, "PROVIDER_FACTORY", FakeProvider)


def open_download(tickers: list[str]) -> AppTest:
    app = AppTest.from_file(str(APP), default_timeout=60)
    app.session_state[market.TICKERS] = tickers
    app.run()
    app.radio[0].set_value("Search and download").run()
    return app


def press(app: AppTest, label: str) -> AppTest:
    return next(b for b in app.button if b.label == label).click().run()


def test_download_feeds_the_analysis_and_warns_about_mixed_currencies() -> None:
    app = open_download(["AAPL", "2222.SR"])
    assert not app.exception
    app = press(app, "Download prices")
    assert not app.exception
    assert not app.error
    assert any("Mixed currencies" in w.value for w in app.warning)
    assert any(m.label == "Total return" for m in app.metric)


def test_provider_error_is_shown_not_raised() -> None:
    app = press(open_download(["BAD"]), "Download prices")
    assert not app.exception
    assert any("No prices returned for BAD" in e.value for e in app.error)


def test_no_tickers_gives_actionable_message() -> None:
    app = press(open_download([]), "Download prices")
    assert any("Add at least one ticker" in e.value for e in app.error)


def test_search_adds_a_ticker() -> None:
    app = AppTest.from_file(str(APP), default_timeout=60).run()
    app.radio[0].set_value("Search and download").run()
    app.text_input(key="search_q").set_value("aramco").run()
    app = press(app, "Add to portfolio")
    assert app.session_state[market.TICKERS] == ["2222.SR"]


def test_operator_switch_hides_the_feature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(market.DISABLE_DOWNLOAD, "1")
    app = AppTest.from_file(str(APP), default_timeout=60).run()
    assert "Search and download" not in app.radio[0].options


def test_fetch_rejects_too_many_tickers() -> None:
    symbols = [f"T{i}" for i in range(market.MAX_TICKERS + 1)]
    start, end = dt.date(2024, 1, 1), dt.date(2024, 6, 1)
    with pytest.raises(DataProviderError, match="At most"):
        market.fetch(FakeProvider(), symbols, start, end, "common")


def test_benchmark_is_downloaded_and_preselected() -> None:
    app = open_download(["AAPL", "2222.SR"])
    next(t for t in app.text_input if t.label.startswith("Benchmark")).set_value("^IDX").run()
    app = press(app, "Download prices")
    assert not app.exception
    assert next(s for s in app.selectbox if s.label == "Benchmark").value == "^IDX"
    assert any(t.label == "Benchmark" or "benchmark" in t.label.lower() for t in app.tabs)


def test_benchmark_cannot_also_be_a_holding() -> None:
    start, end = dt.date(2024, 1, 1), dt.date(2024, 6, 1)
    with pytest.raises(DataProviderError, match="must not also"):
        market.fetch(FakeProvider(), ["AAPL"], start, end, "common", benchmark="aapl")


def test_risk_free_note_escapes_and_handles_blank() -> None:
    assert risk_free_note("3-month SAIBOR") == " (source: 3-month SAIBOR)"
    assert risk_free_note("  ") == " (source not recorded)"
    assert "<script>" not in risk_free_note("<script>")
