"""Strict parsing of a model's answer into positions, and conversion of positions to weights.

The model's answer is untrusted text. Nothing is evaluated or executed; it is parsed as JSON,
checked field by field against a fixed schema, and rejected with a specific message otherwise.
Whatever passes is still only a suggestion: the interface shows every row for review.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from portfolio_risk.errors import DataValidationError, ExtractionError

MAX_POSITIONS = 200
PERCENT_TOLERANCE = 1.0
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .\-_^=/&]{0,39}$")
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class ExtractedPosition:
    """One holding read from an image. Either figure may be missing."""

    ticker: str
    market_value: float | None
    weight_percent: float | None


@dataclass(frozen=True)
class ParsedAnswer:
    positions: tuple[ExtractedPosition, ...]
    currency: str | None
    warnings: tuple[str, ...]


def _json_text(text: str) -> str:
    fenced = _FENCE.search(text)
    candidate = fenced.group(1) if fenced else text
    start, end = candidate.find("{"), candidate.rfind("}")
    if start < 0 or end <= start:
        raise ExtractionError("The model did not return JSON, so nothing could be read.")
    return candidate[start : end + 1]


def _number(value: object, where: str, field: str, *, upper: float | None = None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ExtractionError(f"{where}: {field} must be a number or null, got {value!r}.")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ExtractionError(f"{where}: {field} must be a finite number of at least 0.")
    if upper is not None and number > upper:
        raise ExtractionError(f"{where}: {field} must be at most {upper:g}, got {number:g}.")
    return number


def _position(item: object, index: int) -> ExtractedPosition:
    where = f"Position {index + 1}"
    if not isinstance(item, dict):
        raise ExtractionError(f"{where} is not an object.")
    raw = item.get("ticker")
    if not isinstance(raw, str) or not _NAME.match(raw.strip()):
        raise ExtractionError(f"{where}: ticker {raw!r} is missing or not a plausible symbol.")
    return ExtractedPosition(
        ticker=" ".join(raw.upper().split()),
        market_value=_number(item.get("market_value"), where, "market_value"),
        weight_percent=_number(item.get("weight_percent"), where, "weight_percent", upper=100.0),
    )


def _merge_duplicates(positions: list[ExtractedPosition]) -> tuple[list[ExtractedPosition], str]:
    merged: dict[str, ExtractedPosition] = {}
    repeated: list[str] = []
    for position in positions:
        earlier = merged.get(position.ticker)
        if earlier is None:
            merged[position.ticker] = position
            continue
        repeated.append(position.ticker)
        merged[position.ticker] = ExtractedPosition(
            position.ticker,
            _add(earlier.market_value, position.market_value),
            _add(earlier.weight_percent, position.weight_percent),
        )
    note = ""
    if repeated:
        note = f"Listed more than once and summed: {sorted(set(repeated))}. Check they are lots."
    return list(merged.values()), note


def _add(first: float | None, second: float | None) -> float | None:
    if first is None:
        return second
    return first if second is None else first + second


def parse_response(text: str) -> ParsedAnswer:
    """Turn the model's reply into validated positions. Raises ``ExtractionError``."""
    try:
        data = json.loads(_json_text(text))
    except json.JSONDecodeError as error:
        raise ExtractionError(
            f"The model's answer is not valid JSON ({error.msg} at position {error.pos}). "
            "It may have been cut off; try again or use a clearer screenshot."
        ) from error
    items = data.get("positions") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ExtractionError('The model\'s answer has no "positions" list.')
    if not items:
        raise ExtractionError("No positions were found in the image.")
    if len(items) > MAX_POSITIONS:
        raise ExtractionError(f"{len(items)} positions is more than the limit of {MAX_POSITIONS}.")

    positions, duplicate_note = _merge_duplicates(
        [_position(item, index) for index, item in enumerate(items)]
    )
    warnings = [duplicate_note] if duplicate_note else []
    empty = [p.ticker for p in positions if p.market_value is None and p.weight_percent is None]
    if empty:
        warnings.append(f"No value or percentage was read for {empty}. Fill it in or skip them.")
    currency = data.get("currency")
    return ParsedAnswer(
        tuple(positions),
        currency.strip()[:10] if isinstance(currency, str) and currency.strip() else None,
        tuple(warnings),
    )


def weights_from_positions(positions: Sequence[ExtractedPosition]) -> tuple[pd.Series, list[str]]:
    """Convert reviewed positions to weights that sum to 1.

    If every position has a market value, weights are values divided by their total. Otherwise,
    if every position has a percentage, weights are percentages divided by 100 (their total must
    be within one point of 100). Mixed or missing figures are rejected. Anything not listed, such
    as cash, is outside the weights by construction.
    """
    if not positions:
        raise DataValidationError("There are no positions to turn into weights.")
    names = [p.ticker for p in positions]
    repeated = sorted({n for n in names if names.count(n) > 1})
    if repeated:
        raise DataValidationError(f"More than one position maps to the same asset: {repeated}.")

    if all(p.market_value is not None for p in positions):
        values = [float(p.market_value or 0.0) for p in positions]
        total = sum(values)
        if total <= 0:
            raise DataValidationError("The market values sum to zero.")
        note = "Weights are market values divided by their total, over the listed positions only."
        return pd.Series([v / total for v in values], index=names, name="weight"), [note]

    if all(p.weight_percent is not None for p in positions):
        percents = [float(p.weight_percent or 0.0) for p in positions]
        total = sum(percents)
        if abs(total - 100.0) > PERCENT_TOLERANCE:
            raise DataValidationError(
                f"The percentages sum to {total:.2f}, not 100. Add the missing positions, "
                "correct a figure, or enter market values instead."
            )
        notes = (
            [f"Percentages summed to {total:.2f} and were rescaled to 100."]
            if total != 100.0
            else []
        )
        return pd.Series([v / total for v in percents], index=names, name="weight"), notes

    missing = [p.ticker for p in positions if p.market_value is None and p.weight_percent is None]
    detail = f" No figure for {missing}." if missing else ""
    raise DataValidationError(
        "Fill in the same column for every position: a market value for all, or a percentage "
        f"for all.{detail}"
    )
