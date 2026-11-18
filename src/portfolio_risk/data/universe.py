"""A small default list of instruments to pick from. Ticker data only, never prices.

The list is a convenience for choosing symbols. It is not a recommendation, and the symbols
have not been checked against the live data service from the build environment, so the
download step remains the authority on whether a symbol exists.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any

from portfolio_risk.errors import DataProviderError

KINDS = ("stock", "index_fund")
_SYMBOL = re.compile(r"^[A-Z0-9^][A-Z0-9.\-=^]{0,14}$")


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: str
    kind: str
    region: str
    currency: str
    group: str

    @property
    def label(self) -> str:
        return f"{self.symbol}  |  {self.name}"


def parse_universe(raw: str) -> tuple[Instrument, ...]:
    """Parse and validate the universe file. Raises DataProviderError on any defect."""
    try:
        data: Any = json.loads(raw)
        rows = data["instruments"]
    except (ValueError, KeyError, TypeError) as error:
        raise DataProviderError(f"Universe file is malformed: {error}") from error
    out: list[Instrument] = []
    seen: set[str] = set()
    for row in rows:
        try:
            item = Instrument(**{k: str(row[k]) for k in Instrument.__dataclass_fields__})
        except (KeyError, TypeError) as error:
            raise DataProviderError(f"Universe entry is incomplete: {row!r}") from error
        if not _SYMBOL.match(item.symbol):
            raise DataProviderError(f"Universe symbol is invalid: {item.symbol!r}")
        if item.kind not in KINDS:
            raise DataProviderError(f"Universe kind is invalid for {item.symbol}: {item.kind!r}")
        if len(item.currency) != 3 or not item.currency.isupper():
            raise DataProviderError(f"Universe currency is invalid for {item.symbol}")
        if item.symbol in seen:
            raise DataProviderError(f"Universe symbol is duplicated: {item.symbol}")
        seen.add(item.symbol)
        out.append(item)
    return tuple(out)


@lru_cache(maxsize=1)
def default_universe() -> tuple[Instrument, ...]:
    """The bundled list: stocks first, then index funds."""
    text = resources.files("portfolio_risk.data").joinpath("universe.json").read_text("utf-8")
    return parse_universe(text)


def by_kind(kind: str) -> tuple[Instrument, ...]:
    return tuple(i for i in default_universe() if i.kind == kind)
