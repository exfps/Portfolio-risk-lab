"""Validation and cleaning of price and weight data.

Functions here raise ``DataValidationError`` for problems that make an analysis wrong and
return a list of warnings for problems the user should know about but can proceed past.
Nothing is repaired silently: every dropped row or rescaled weight appears in a warning.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from portfolio_risk.errors import DataValidationError, InsufficientDataError

RECOMMENDED_OBSERVATIONS = 250
LARGE_MOVE_THRESHOLD = 0.5
DEFAULT_MAX_MISSING_FRACTION = 0.05
_MAX_LISTED = 5
# (lowest, highest) median gap in days for each lower-than-daily frequency, and its factor.
_FREQUENCY_BANDS = (
    (5.0, 9.0, 52),
    (25.0, 35.0, 12),
    (80.0, 100.0, 4),
    (350.0, 380.0, 1),
)


def validate_weights(
    weights: pd.Series, *, tolerance: float = 1e-6, normalise: bool = False
) -> tuple[pd.Series, list[str]]:
    """Check that weights are usable and return them as a float series.

    Weights must be finite, non-negative (long-only) and sum to one within ``tolerance``.
    With ``normalise=True`` a wrong total is rescaled and reported instead of rejected.
    """
    warnings: list[str] = []
    if weights.empty:
        raise DataValidationError("No weights were provided.")
    if weights.index.has_duplicates:
        repeated = sorted({str(name) for name in weights.index[weights.index.duplicated()]})
        raise DataValidationError(f"Duplicate tickers in weights: {repeated}.")

    numeric = pd.to_numeric(weights, errors="coerce").astype(np.float64)
    unreadable = [str(name) for name in numeric.index[~np.isfinite(numeric.to_numpy())]]
    if unreadable:
        raise DataValidationError(f"Weights for {unreadable} are missing or not finite numbers.")

    negative = numeric[numeric < 0.0]
    if not negative.empty:
        listed = ", ".join(f"{name}={value:g}" for name, value in negative.items())
        raise DataValidationError(
            f"Negative weights are not supported (long-only portfolios only): {listed}."
        )

    total = float(numeric.sum())
    if total <= 0.0:
        raise DataValidationError("Weights sum to zero.")
    if abs(total - 1.0) > tolerance:
        if not normalise:
            hint = " They look like percentages; use fractions such as 0.25." if total > 1.5 else ""
            raise DataValidationError(f"Weights sum to {total:.6g}, not 1.{hint}")
        numeric = numeric / total
        warnings.append(f"Weights summed to {total:.6g} and were rescaled to sum to 1.")

    return numeric.rename("weight"), warnings


def check_columns(prices: pd.DataFrame, weights: pd.Series, benchmark: str | None) -> None:
    """Require that price columns, weights and the benchmark name line up exactly."""
    price_names = list(prices.columns)
    if benchmark is not None:
        if benchmark in weights.index:
            raise DataValidationError(f"Benchmark {benchmark!r} must not also be a weighted asset.")
        if benchmark not in price_names:
            raise DataValidationError(f"Benchmark {benchmark!r} is not a column in the prices.")

    missing = [name for name in weights.index if name not in price_names]
    if missing:
        raise DataValidationError(f"Weighted assets with no price column: {missing}.")

    allowed = set(weights.index) | ({benchmark} if benchmark is not None else set())
    extra = [name for name in price_names if name not in allowed]
    if extra:
        raise DataValidationError(
            f"Price columns with no weight: {extra}. Remove them, or give them a weight of 0 "
            "to keep them in the correlation matrix."
        )


def clean_prices(
    prices: pd.DataFrame,
    *,
    min_observations: int,
    max_missing_fraction: float = DEFAULT_MAX_MISSING_FRACTION,
) -> tuple[pd.DataFrame, list[str]]:
    """Validate a price table and drop dates with any missing value.

    ``min_observations`` counts returns, so ``min_observations + 1`` prices are required.
    """
    warnings: list[str] = []
    if prices.shape[1] == 0 or prices.empty:
        raise DataValidationError("The price table is empty.")
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise DataValidationError("Prices must be indexed by date.")
    if not prices.index.is_unique or not prices.index.is_monotonic_increasing:
        raise DataValidationError("Price dates must be unique and in ascending order.")

    non_numeric = [str(c) for c, dtype in prices.dtypes.items() if not _is_float(dtype)]
    if non_numeric:
        raise DataValidationError(f"Non-numeric price columns: {non_numeric}.")

    values = prices.to_numpy(dtype=np.float64)
    if np.isinf(values).any():
        row, col = np.argwhere(np.isinf(values))[0]
        raise DataValidationError(
            f"Infinite price for {prices.columns[col]!r} on {_day(prices.index[row])}."
        )

    missing_fraction = prices.isna().mean()
    for name, fraction in missing_fraction.items():
        if fraction > max_missing_fraction:
            raise DataValidationError(
                f"{name!r} is missing {fraction:.1%} of its prices (limit "
                f"{max_missing_fraction:.0%}). Fix the file or remove the column."
            )

    complete = prices.dropna(how="any")
    dropped = len(prices) - len(complete)
    if dropped:
        warnings.append(
            f"Dropped {dropped} date(s) where at least one price was missing "
            "(dates are inner-joined across tickers)."
        )

    level_values = complete.to_numpy(dtype=np.float64)
    non_positive = np.argwhere(level_values <= 0.0)
    if non_positive.size:
        row, col = non_positive[0]
        raise DataValidationError(
            f"Non-positive price {level_values[row, col]:g} for {complete.columns[col]!r} "
            f"on {_day(complete.index[row])}."
        )

    observations = len(complete) - 1
    if observations < min_observations:
        raise InsufficientDataError(
            f"{max(observations, 0)} return observations after cleaning; at least "
            f"{min_observations} are required."
        )
    if observations < RECOMMENDED_OBSERVATIONS:
        warnings.append(
            f"Only {observations} observations. Tail estimates, especially 99% VaR and CVaR, "
            f"are unreliable below about {RECOMMENDED_OBSERVATIONS}."
        )

    moves = (complete / complete.shift(1) - 1.0).iloc[1:]
    move_values = moves.to_numpy(dtype=np.float64)
    large = np.argwhere(np.abs(move_values) > LARGE_MOVE_THRESHOLD)
    if large.size:
        listed = "; ".join(
            f"{moves.columns[col]!s} {_day(moves.index[row])} ({move_values[row, col]:+.0%})"
            for row, col in large[:_MAX_LISTED]
        )
        extra = f" (+{len(large) - _MAX_LISTED} more)" if len(large) > _MAX_LISTED else ""
        warnings.append(
            f"Single-period moves above {LARGE_MOVE_THRESHOLD:.0%}: {listed}{extra}. "
            "These may be splits or data errors."
        )

    return complete, warnings


def _is_float(dtype: np.dtype[np.generic] | pd.api.extensions.ExtensionDtype) -> bool:
    return bool(pd.api.types.is_float_dtype(dtype) or pd.api.types.is_integer_dtype(dtype))


def _day(label: object) -> str:
    """Format a date-index label as ``YYYY-MM-DD`` for use in messages."""
    return str(pd.Timestamp(label).date())  # type: ignore[arg-type]


def infer_periods_per_year(index: pd.DatetimeIndex) -> int | None:
    """Guess the annualisation factor from the median gap between dates.

    Returns ``None`` when the spacing matches no common frequency.
    """
    if len(index) < 3:
        return None
    gaps = pd.Series(index).diff().dropna().dt.days
    median = float(gaps.median())
    if median <= 1.5:
        has_weekend = bool((index.day_of_week >= 5).any())
        return 365 if has_weekend else 252
    for low, high, periods in _FREQUENCY_BANDS:
        if low <= median <= high:
            return periods
    return None


def frequency_warnings(index: pd.DatetimeIndex, periods_per_year: int) -> list[str]:
    """Warn when the configured annualisation factor disagrees with the date spacing."""
    inferred = infer_periods_per_year(index)
    if inferred is None:
        return [
            "Could not infer the data frequency from the dates; "
            f"check that periods_per_year={periods_per_year} is correct."
        ]
    if inferred != periods_per_year:
        return [
            f"The dates look like {inferred} periods per year but periods_per_year is "
            f"{periods_per_year}. Annualised figures will be mis-scaled if this is wrong."
        ]
    return []
