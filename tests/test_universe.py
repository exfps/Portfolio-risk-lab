"""The bundled instrument list: structure, validation and the sidebar picker."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from portfolio_risk.data import by_kind, default_universe, parse_universe
from portfolio_risk.errors import DataProviderError
from portfolio_risk.ui import market

APP = Path(__file__).resolve().parents[1] / "src" / "portfolio_risk" / "ui" / "app.py"


def _raw(rows: list[dict[str, str]]) -> str:
    return json.dumps({"instruments": rows})


GOOD = {
    "symbol": "AAA",
    "name": "Alpha",
    "kind": "stock",
    "region": "US",
    "currency": "USD",
    "group": "Tech",
}


def test_default_list_has_25_stocks_and_some_index_funds() -> None:
    assert len(by_kind("stock")) == 25
    assert len(by_kind("index_fund")) >= 10
    assert len(default_universe()) == len(by_kind("stock")) + len(by_kind("index_fund"))


def test_default_list_symbols_are_unique_and_currencies_plausible() -> None:
    symbols = [i.symbol for i in default_universe()]
    assert len(symbols) == len(set(symbols))
    assert {i.currency for i in default_universe()} <= {"USD", "SAR"}


def test_default_list_includes_gulf_names_and_funds() -> None:
    symbols = {i.symbol for i in default_universe()}
    assert {"2222.SR", "KSA", "SPY", "QQQ"} <= symbols


def test_label_shows_symbol_and_name() -> None:
    assert parse_universe(_raw([GOOD]))[0].label == "AAA  |  Alpha"


@pytest.mark.parametrize(
    "mutation",
    [
        {"symbol": "bad symbol"},
        {"kind": "crypto"},
        {"currency": "usd"},
        {"currency": "US"},
    ],
)
def test_invalid_entries_are_rejected(mutation: dict[str, str]) -> None:
    with pytest.raises(DataProviderError):
        parse_universe(_raw([{**GOOD, **mutation}]))


def test_duplicates_missing_fields_and_bad_json_are_rejected() -> None:
    with pytest.raises(DataProviderError, match="duplicated"):
        parse_universe(_raw([GOOD, GOOD]))
    incomplete = {k: v for k, v in GOOD.items() if k != "name"}
    with pytest.raises(DataProviderError, match="incomplete"):
        parse_universe(_raw([incomplete]))
    with pytest.raises(DataProviderError, match="malformed"):
        parse_universe("not json")


def test_file_states_it_was_not_checked_live() -> None:
    raw = json.loads(
        resources.files("portfolio_risk.data").joinpath("universe.json").read_text("utf-8")
    )
    assert raw["checked_live"] is False


def _open() -> AppTest:
    app = AppTest.from_file(str(APP), default_timeout=60)
    app.run()
    app.radio[0].set_value("Search and download").run()
    return app


def test_picker_adds_chosen_stocks_to_the_ticker_box() -> None:
    app = _open()
    stocks = {i.symbol: i.label for i in by_kind("stock")}
    picker = next(m for m in app.multiselect if m.label == "Choose from the list")
    picker.set_value([stocks["AAPL"], stocks["2222.SR"]]).run()
    next(b for b in app.button if b.label == "Add chosen").click().run()
    assert not app.exception
    assert app.session_state[market.TICKERS] == ["AAPL", "2222.SR"]


def test_picker_switches_to_index_funds_and_skips_duplicates() -> None:
    app = _open()
    app.session_state[market.TICKERS] = ["SPY"]
    app.run()
    next(r for r in app.radio if r.label == "Default list").set_value("Index funds").run()
    funds = {i.symbol: i.label for i in by_kind("index_fund")}
    next(m for m in app.multiselect if m.label == "Choose from the list").set_value(
        [funds["SPY"], funds["QQQ"]]
    ).run()
    next(b for b in app.button if b.label == "Add chosen").click().run()
    assert app.session_state[market.TICKERS] == ["SPY", "QQQ"]
