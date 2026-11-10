"""CSV loaders for price tables and weights.

Price file: first column ``date`` (``YYYY-MM-DD``), then one column of prices per ticker.
Weights file: columns ``ticker`` and ``weight``.

The loaders parse and check *structure* (headers, dates, numbers). Statistical checks, such
as missing-data limits and observation counts, live in ``portfolio_risk.io.validation``.
A ``str`` or path source is a file path; to parse text already in memory, pass a file object.
"""

from __future__ import annotations

import csv
import io
import os
import re
from datetime import datetime
from pathlib import Path
from typing import IO

import numpy as np
import pandas as pd

from portfolio_risk.errors import DataValidationError

Source = str | os.PathLike[str] | IO[str] | IO[bytes]

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
Row = tuple[int, list[str]]


def _read_text(source: Source) -> str:
    if isinstance(source, str | os.PathLike):
        try:
            raw: bytes | str = Path(source).read_bytes()
        except FileNotFoundError as exc:
            raise DataValidationError(f"File not found: {source}") from exc
        except OSError as exc:
            raise DataValidationError(f"Could not read {source}: {exc.strerror}") from exc
    else:
        raw = source.read()
    if isinstance(raw, str):
        return raw.removeprefix("﻿")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DataValidationError("The file is not UTF-8 text. Save it as CSV (UTF-8).") from exc


def _read_rows(text: str) -> list[Row]:
    """Non-blank rows with their physical line numbers."""
    reader = csv.reader(io.StringIO(text))
    rows: list[Row] = []
    try:
        for row in reader:
            if any(cell.strip() for cell in row):
                rows.append((reader.line_num, [cell.strip() for cell in row]))
    except csv.Error as exc:
        raise DataValidationError(f"Malformed CSV near line {reader.line_num}: {exc}") from exc
    if not rows:
        raise DataValidationError("The file is empty.")
    return rows


def _check_row_widths(header: Row, body: list[Row]) -> None:
    width = len(header[1])
    if width == 1 and ";" in header[1][0]:
        raise DataValidationError(
            "The header contains semicolons. Use commas as the field separator."
        )
    for line, cells in body:
        if len(cells) != width:
            raise DataValidationError(f"Line {line} has {len(cells)} fields; expected {width}.")


def _to_float(cell: str, line: int, column: str) -> float:
    if cell == "":
        return float("nan")
    try:
        value = float(cell)
    except ValueError as exc:
        raise DataValidationError(
            f"Line {line}, column {column!r}: {cell!r} is not a number."
        ) from exc
    if np.isinf(value):
        raise DataValidationError(f"Line {line}, column {column!r}: infinite value.")
    return value


def load_prices(source: Source, *, sort_dates: bool = False) -> pd.DataFrame:
    """Read a wide price table into a DataFrame indexed by date.

    Dates must be ISO ``YYYY-MM-DD`` and unique. Unsorted dates are rejected unless
    ``sort_dates`` is true. Empty price cells are kept as NaN for ``clean_prices`` to handle.
    """
    rows = _read_rows(_read_text(source))
    header, body = rows[0], rows[1:]
    _check_row_widths(header, body)

    columns = header[1]
    if columns[0].lower() != "date":
        raise DataValidationError(f"The first column must be named 'date'; found {columns[0]!r}.")
    tickers = columns[1:]
    if not tickers:
        raise DataValidationError("The file has a date column but no price columns.")
    if any(name == "" for name in tickers):
        raise DataValidationError("Every price column needs a ticker name in the header.")
    if len(set(tickers)) != len(tickers):
        repeated = sorted({name for name in tickers if tickers.count(name) > 1})
        raise DataValidationError(f"Duplicate column names in header: {repeated}.")
    if not body:
        raise DataValidationError("The file has a header but no data rows.")

    dates: list[datetime] = []
    seen: dict[datetime, int] = {}
    matrix = np.empty((len(body), len(tickers)), dtype=np.float64)
    for i, (line, cells) in enumerate(body):
        text = cells[0]
        if not _ISO_DATE.match(text):
            raise DataValidationError(f"Line {line}: {text!r} is not a date in YYYY-MM-DD format.")
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d")
        except ValueError as exc:
            raise DataValidationError(
                f"Line {line}: {text!r} is not a valid calendar date."
            ) from exc
        if parsed in seen:
            raise DataValidationError(f"Duplicate date {text} on lines {seen[parsed]} and {line}.")
        seen[parsed] = line
        dates.append(parsed)
        for j, ticker in enumerate(tickers):
            matrix[i, j] = _to_float(cells[j + 1], line, ticker)

    index = pd.DatetimeIndex(dates, name="date")
    frame = pd.DataFrame(matrix, index=index, columns=pd.Index(tickers))
    if not index.is_monotonic_increasing:
        if not sort_dates:
            raise DataValidationError(
                "Dates are not in ascending order. Sort the file or load it with sort_dates=True."
            )
        frame = frame.sort_index()
    return frame


def load_weights(source: Source) -> pd.Series:
    """Read a ``ticker,weight`` file into a float Series indexed by ticker."""
    rows = _read_rows(_read_text(source))
    header, body = rows[0], rows[1:]
    _check_row_widths(header, body)

    names = [name.lower() for name in header[1]]
    if names != ["ticker", "weight"]:
        raise DataValidationError(
            f"Weights header must be 'ticker,weight'; found {','.join(header[1])!r}."
        )
    if not body:
        raise DataValidationError("The weights file has a header but no rows.")

    tickers: list[str] = []
    values: list[float] = []
    seen: dict[str, int] = {}
    for line, (ticker, cell) in ((line, (cells[0], cells[1])) for line, cells in body):
        if ticker == "":
            raise DataValidationError(f"Line {line}: ticker is empty.")
        if ticker in seen:
            raise DataValidationError(
                f"Duplicate ticker {ticker!r} on lines {seen[ticker]} and {line}."
            )
        seen[ticker] = line
        value = _to_float(cell, line, "weight")
        if np.isnan(value):
            raise DataValidationError(f"Line {line}: weight for {ticker!r} is empty.")
        tickers.append(ticker)
        values.append(value)
    return pd.Series(
        values, index=pd.Index(tickers, name="ticker"), name="weight", dtype=np.float64
    )
