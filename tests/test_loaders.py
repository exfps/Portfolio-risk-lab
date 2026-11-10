"""CSV loading: valid files parse, and every malformed case produces a specific message."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from portfolio_risk.errors import DataValidationError
from portfolio_risk.io.loaders import load_prices, load_weights

GOOD = "date,A,B\n2024-01-02,100,50\n2024-01-03,101,51.5\n2024-01-04,102.5,50.5\n"


def prices(text: str, **kwargs: bool) -> pd.DataFrame:
    return load_prices(io.StringIO(text), **kwargs)


def test_loads_a_valid_price_file() -> None:
    frame = prices(GOOD)
    assert list(frame.columns) == ["A", "B"]
    assert frame.index.name == "date"
    assert frame.index[0] == pd.Timestamp("2024-01-02")
    assert frame.loc["2024-01-03", "B"] == 51.5


def test_loads_from_path_and_tolerates_bom_and_crlf(tmp_path: Path) -> None:
    path = tmp_path / "prices.csv"
    path.write_bytes(("﻿" + GOOD.replace("\n", "\r\n")).encode("utf-8"))
    assert load_prices(path).shape == (3, 2)
    assert load_prices(str(path)).shape == (3, 2)


def test_loads_from_binary_file_object() -> None:
    assert load_prices(io.BytesIO(GOOD.encode())).shape == (3, 2)


def test_empty_price_cells_become_nan() -> None:
    frame = prices("date,A\n2024-01-02,100\n2024-01-03,\n2024-01-04,102\n")
    assert frame["A"].isna().tolist() == [False, True, False]


def test_blank_lines_are_ignored_but_line_numbers_stay_physical() -> None:
    with pytest.raises(DataValidationError, match=r"Line 5.*'oops'"):
        prices("date,A\n\n2024-01-02,100\n\n2024-01-03,oops\n")


def test_unsorted_dates_are_rejected_unless_sorting_is_requested() -> None:
    text = "date,A\n2024-01-03,101\n2024-01-02,100\n"
    with pytest.raises(DataValidationError, match="ascending"):
        prices(text)
    frame = prices(text, sort_dates=True)
    assert frame.index.is_monotonic_increasing
    assert frame["A"].tolist() == [100.0, 101.0]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "empty"),
        ("\n\n", "empty"),
        ("date,A\n", "no data rows"),
        ("date\n2024-01-02\n", "no price columns"),
        ("day,A\n2024-01-02,1\n", "first column must be named 'date'"),
        ("date,A,A\n2024-01-02,1,2\n", r"Duplicate column names.*'A'"),
        ("date,A,\n2024-01-02,1,2\n", "ticker name"),
        ("date,A\n2024-01-02,1\n2024-01-02,2\n", r"Duplicate date 2024-01-02 on lines 2 and 3"),
        ("date,A\n02/01/2024,1\n", r"Line 2.*YYYY-MM-DD"),
        ("date,A\n2024-02-30,1\n", r"Line 2.*valid calendar date"),
        ("date,A\n2024-01-02,abc\n", r"Line 2, column 'A': 'abc' is not a number"),
        ("date,A\n2024-01-02,inf\n", "infinite"),
        ("date,A,B\n2024-01-02,1\n", r"Line 2 has 2 fields; expected 3"),
        ("date,A\n2024-01-02,1,2\n", r"Line 2 has 3 fields; expected 2"),
        ("date;A;B\n2024-01-02;1;2\n", "semicolons"),
    ],
)
def test_malformed_price_files_get_specific_messages(text: str, message: str) -> None:
    with pytest.raises(DataValidationError, match=message):
        prices(text)


def test_missing_file_is_reported_by_name(tmp_path: Path) -> None:
    with pytest.raises(DataValidationError, match="File not found"):
        load_prices(tmp_path / "nope.csv")


def test_non_utf8_file_is_rejected() -> None:
    with pytest.raises(DataValidationError, match="UTF-8"):
        load_prices(io.BytesIO(b"date,A\n2024-01-02,\xff\xfe\n"))


def test_loads_valid_weights() -> None:
    weights = load_weights(io.StringIO("ticker,weight\nA,0.6\nB,0.4\n"))
    assert weights.index.tolist() == ["A", "B"]
    assert weights.tolist() == [0.6, 0.4]
    assert weights.dtype == np.float64


def test_weights_header_is_case_insensitive() -> None:
    assert load_weights(io.StringIO("Ticker,Weight\nA,1\n")).tolist() == [1.0]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "empty"),
        ("symbol,weight\nA,1\n", "must be 'ticker,weight'"),
        ("ticker,weight\n", "no rows"),
        ("ticker,weight\nA,0.5\nA,0.5\n", r"Duplicate ticker 'A' on lines 2 and 3"),
        ("ticker,weight\n,0.5\n", "ticker is empty"),
        ("ticker,weight\nA,\n", "weight for 'A' is empty"),
        ("ticker,weight\nA,half\n", r"Line 2, column 'weight': 'half'"),
        ("ticker,weight\nA,0.5,0.5\n", "expected 2"),
    ],
)
def test_malformed_weight_files_get_specific_messages(text: str, message: str) -> None:
    with pytest.raises(DataValidationError, match=message):
        load_weights(io.StringIO(text))


def test_bundled_example_files_load() -> None:
    root = Path(__file__).resolve().parents[1] / "examples"
    frame = load_prices(root / "sample_prices_synthetic.csv")
    weights = load_weights(root / "sample_weights_synthetic.csv")
    assert frame.shape == (757, 7)
    assert weights.sum() == pytest.approx(1.0)
