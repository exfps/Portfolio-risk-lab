"""Compare several constant-weight portfolios on the same data.

All portfolios are evaluated over the dates on which every asset they use (and the benchmark)
has a price, so differences between them come from the weights and not from the sample.
Weight sets can be saved to, and loaded from, a small JSON document.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from portfolio_risk.analysis import AnalysisResult, analyse
from portfolio_risk.config import AnalysisConfig
from portfolio_risk.errors import ConfigurationError, DataValidationError
from portfolio_risk.tearsheet import tearsheet_table

MAX_PORTFOLIOS = 5
MAX_SAVED = 10
MAX_ASSETS = 50
MAX_NAME = 40
SCHEMA_VERSION = 1
TOLERANCE = 1e-6


@dataclass(frozen=True, slots=True, eq=False)
class Comparison:
    names: tuple[str, ...]
    results: dict[str, AnalysisResult]
    returns: pd.DataFrame  # one column per portfolio
    wealth: pd.DataFrame
    drawdowns: pd.DataFrame
    table: pd.DataFrame  # tearsheet rows; includes the benchmark column when one is given
    weights: pd.DataFrame  # rows: assets, columns: portfolios, blank where not held
    concentration: pd.DataFrame  # rows: number of holdings, HHI, effective positions
    correlation: pd.DataFrame  # correlation of portfolio returns
    benchmark: str | None
    start: pd.Timestamp
    end: pd.Timestamp
    observations: int


def _clean_name(name: object) -> str:
    text = str(name).strip()
    if not text:
        raise DataValidationError("Every portfolio needs a name.")
    if len(text) > MAX_NAME:
        raise DataValidationError(f"Portfolio names are limited to {MAX_NAME} characters.")
    return text


def _clean_weights(name: str, raw: Mapping[str, object]) -> pd.Series:
    if not raw:
        raise DataValidationError(f"Portfolio {name!r} has no holdings.")
    if len(raw) > MAX_ASSETS:
        raise DataValidationError(f"Portfolio {name!r} has more than {MAX_ASSETS} holdings.")
    values: dict[str, float] = {}
    for key, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise DataValidationError(
                f"Portfolio {name!r}: the weight for {key!r} is not a number."
            )
        number = float(value)
        if not math.isfinite(number) or number < 0.0:
            raise DataValidationError(
                f"Portfolio {name!r}: the weight for {key!r} must be zero or positive."
            )
        values[str(key)] = number
    series = pd.Series(values, dtype=float)
    if abs(float(series.sum()) - 1.0) > TOLERANCE:
        raise DataValidationError(f"Portfolio {name!r}: weights sum to {series.sum():.6f}, not 1.")
    return series[series > 0.0]


def weight_sets_to_json(sets: Mapping[str, pd.Series]) -> str:
    """A JSON document holding the named weight sets (rounded to 10 decimals)."""
    payload = {
        "version": SCHEMA_VERSION,
        "portfolios": [
            {"name": name, "weights": {str(k): round(float(v), 10) for k, v in w.items()}}
            for name, w in sets.items()
        ],
    }
    return json.dumps(payload, indent=2)


def weight_sets_from_json(text: str | bytes) -> dict[str, pd.Series]:
    """Parse and validate a document written by :func:`weight_sets_to_json`."""
    try:
        payload = json.loads(text)
    except (ValueError, UnicodeDecodeError) as error:
        raise DataValidationError("The file is not valid JSON.") from error
    if not isinstance(payload, dict) or payload.get("version") != SCHEMA_VERSION:
        raise DataValidationError("This is not a portfolio file this version understands.")
    items = payload.get("portfolios")
    if not isinstance(items, list) or not items:
        raise DataValidationError("The file contains no portfolios.")
    if len(items) > MAX_SAVED:
        raise DataValidationError(f"At most {MAX_SAVED} portfolios can be loaded at once.")
    out: dict[str, pd.Series] = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("weights"), dict):
            raise DataValidationError("Each portfolio needs a name and a weights object.")
        name = _clean_name(item.get("name"))
        if name in out:
            raise DataValidationError(f"The portfolio name {name!r} appears twice.")
        out[name] = _clean_weights(name, item["weights"])
    return out


def compare(
    prices: pd.DataFrame,
    sets: Mapping[str, pd.Series],
    config: AnalysisConfig | None = None,
    benchmark: str | None = None,
) -> Comparison:
    """Analyse each weight set on the dates common to all of them."""
    if not sets:
        raise ConfigurationError("Choose at least one portfolio to compare.")
    if len(sets) > MAX_PORTFOLIOS:
        raise ConfigurationError(f"Compare at most {MAX_PORTFOLIOS} portfolios at once.")
    config = config or AnalysisConfig()
    sets = {name: w[w > 0.0] for name, w in sets.items()}
    for name, w in sets.items():
        if w.empty:
            raise DataValidationError(f"Portfolio {name!r} has no holdings.")
    needed = list(dict.fromkeys([a for w in sets.values() for a in w.index]))
    missing = [a for a in needed if a not in prices.columns]
    if missing:
        raise DataValidationError("No prices for: " + ", ".join(map(str, missing)) + ".")
    wanted = [*needed, *([benchmark] if benchmark and benchmark not in needed else [])]
    if benchmark and benchmark not in prices.columns:
        raise DataValidationError(f"No prices for the benchmark {benchmark!r}.")
    common = prices[wanted].dropna()

    results: dict[str, AnalysisResult] = {}
    for name, w in sets.items():
        columns = [*w.index, *([benchmark] if benchmark and benchmark not in w.index else [])]
        try:
            results[name] = analyse(common[columns], w, config, benchmark or None)
        except DataValidationError as error:
            raise DataValidationError(f"Portfolio {name!r}: {error}") from error
    names = tuple(results)
    returns = pd.DataFrame({n: r.portfolio_returns for n, r in results.items()})
    named: dict[str, pd.Series] = {str(c): returns[c] for c in returns.columns}
    if benchmark:
        bench_returns = common[benchmark].pct_change().reindex(returns.index)
        named[benchmark] = bench_returns
    table = tearsheet_table(
        named,
        periods_per_year=config.periods_per_year,
        rf_per_period=config.risk_free_per_period,
        mar_per_period=config.mar_per_period,
        benchmark=benchmark,
    )
    weights = pd.DataFrame({n: sets[n] for n in names}).reindex(needed)
    concentration = pd.DataFrame(
        {
            n: {
                "holdings": float(len(sets[n])),
                "hhi": results[n].hhi,
                "effective_positions": results[n].effective_positions,
            }
            for n in names
        }
    )
    first = results[names[0]]
    return Comparison(
        names=names,
        results=results,
        returns=returns,
        wealth=pd.DataFrame({n: r.wealth for n, r in results.items()}),
        drawdowns=pd.DataFrame({n: r.drawdowns for n, r in results.items()}),
        table=table,
        weights=weights,
        concentration=concentration,
        correlation=returns.corr(),
        benchmark=benchmark,
        start=first.start,
        end=first.end,
        observations=first.observations,
    )
