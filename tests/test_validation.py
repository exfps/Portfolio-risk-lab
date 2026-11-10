"""Statistical and structural validation of loaded data."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from portfolio_risk.errors import DataValidationError, InsufficientDataError
from portfolio_risk.io.validation import (
    check_columns,
    clean_prices,
    frequency_warnings,
    infer_periods_per_year,
    validate_weights,
)


def frame(n: int = 100, **columns: list[float]) -> pd.DataFrame:
    """Business-day prices. Explicit columns set the length; else one rising column of ``n``."""
    data = columns or {"A": list(100 + np.arange(n) * 0.1)}
    length = len(next(iter(data.values())))
    index = pd.bdate_range("2024-01-01", periods=length, name="date")
    return pd.DataFrame(data, index=index)


# -- weights ---------------------------------------------------------------------------------


def test_valid_weights_pass_unchanged() -> None:
    weights, notes = validate_weights(pd.Series({"A": 0.6, "B": 0.4}))
    assert weights.tolist() == [0.6, 0.4]
    assert notes == []


def test_wrong_total_is_rejected_by_default() -> None:
    with pytest.raises(DataValidationError, match=r"sum to 0\.9, not 1"):
        validate_weights(pd.Series({"A": 0.5, "B": 0.4}))


def test_percentage_weights_get_a_hint() -> None:
    with pytest.raises(DataValidationError, match="percentages"):
        validate_weights(pd.Series({"A": 60.0, "B": 40.0}))


def test_wrong_total_can_be_normalised_and_is_reported() -> None:
    weights, notes = validate_weights(pd.Series({"A": 3.0, "B": 1.0}), normalise=True)
    assert weights.tolist() == pytest.approx([0.75, 0.25])
    assert len(notes) == 1
    assert "rescaled" in notes[0]


def test_negative_weights_are_rejected_even_when_normalising() -> None:
    with pytest.raises(DataValidationError, match=r"long-only.*B=-0.2"):
        validate_weights(pd.Series({"A": 1.2, "B": -0.2}), normalise=True)


def test_zero_total_empty_and_duplicate_weights_are_rejected() -> None:
    with pytest.raises(DataValidationError, match="sum to zero"):
        validate_weights(pd.Series({"A": 0.0, "B": 0.0}))
    with pytest.raises(DataValidationError, match="No weights"):
        validate_weights(pd.Series([], dtype=float))
    with pytest.raises(DataValidationError, match="Duplicate"):
        validate_weights(pd.Series([0.5, 0.5], index=["A", "A"]))


def test_nan_weight_is_rejected() -> None:
    with pytest.raises(DataValidationError, match=r"\['B'\]"):
        validate_weights(pd.Series({"A": 0.5, "B": float("nan")}))


# -- columns ---------------------------------------------------------------------------------


def test_columns_must_line_up() -> None:
    prices = frame(A=[1.0] * 3, B=[1.0] * 3)
    weights = pd.Series({"A": 1.0})
    with pytest.raises(DataValidationError, match=r"no weight: \['B'\]"):
        check_columns(prices, weights, None)
    with pytest.raises(DataValidationError, match=r"no price column: \['C'\]"):
        check_columns(prices, pd.Series({"A": 0.5, "C": 0.5}), None)
    with pytest.raises(DataValidationError, match="not a column"):
        check_columns(prices, weights, "ZZZ")
    with pytest.raises(DataValidationError, match="must not also be a weighted asset"):
        check_columns(prices, weights, "A")


def test_benchmark_column_is_allowed_extra() -> None:
    prices = frame(A=[1.0] * 3, B=[1.0] * 3)
    check_columns(prices, pd.Series({"A": 1.0}), "B")


def test_zero_weight_keeps_a_column_in_scope() -> None:
    prices = frame(A=[1.0] * 3, B=[1.0] * 3)
    check_columns(prices, pd.Series({"A": 1.0, "B": 0.0}), None)


# -- prices ----------------------------------------------------------------------------------


def test_clean_prices_returns_data_unchanged_when_valid() -> None:
    prices = frame(300)
    cleaned, notes = clean_prices(prices, min_observations=60)
    assert cleaned.equals(prices)
    assert notes == []


def test_too_few_observations_is_rejected() -> None:
    with pytest.raises(InsufficientDataError, match=r"59 return observations.*60"):
        clean_prices(frame(60), min_observations=60)


def test_short_but_sufficient_history_warns_about_tail_estimates() -> None:
    _, notes = clean_prices(frame(101), min_observations=60)
    assert any("99% VaR" in note for note in notes)


def test_missing_dates_are_dropped_and_reported() -> None:
    prices = frame(300, A=[float(100 + i) for i in range(300)])
    prices.iloc[10, 0] = np.nan
    cleaned, notes = clean_prices(prices, min_observations=60)
    assert len(cleaned) == 299
    assert any("Dropped 1 date" in note for note in notes)


def test_excessive_missing_data_is_rejected() -> None:
    values = [float(100 + i) for i in range(300)]
    prices = frame(300, A=values)
    prices.iloc[:30, 0] = np.nan
    with pytest.raises(DataValidationError, match=r"'A' is missing 10.0%"):
        clean_prices(prices, min_observations=60)


def test_non_positive_price_is_located() -> None:
    values = [float(100 + i) for i in range(300)]
    values[7] = 0.0
    prices = frame(300, A=values)
    with pytest.raises(DataValidationError, match=r"Non-positive price 0 for 'A' on 2024-01-10"):
        clean_prices(prices, min_observations=60)


def test_infinite_price_is_located() -> None:
    prices = frame(300, A=[float(100 + i) for i in range(300)])
    prices.iloc[5, 0] = np.inf
    with pytest.raises(DataValidationError, match="Infinite price for 'A'"):
        clean_prices(prices, min_observations=60)


def test_large_single_period_move_is_flagged() -> None:
    values = [100.0] * 300
    values[150:] = [40.0] * 150  # a -60% step that could be an unadjusted split
    prices = frame(300, A=[v + i * 0.01 for i, v in enumerate(values)])
    _, notes = clean_prices(prices, min_observations=60)
    assert any("above 50%" in note and "A 2024-" in note for note in notes)


def test_index_must_be_unique_sorted_dates() -> None:
    prices = frame(300)
    with pytest.raises(DataValidationError, match="ascending"):
        clean_prices(prices.iloc[::-1], min_observations=60)
    with pytest.raises(DataValidationError, match="indexed by date"):
        clean_prices(prices.reset_index(drop=True), min_observations=60)


def test_empty_table_is_rejected() -> None:
    with pytest.raises(DataValidationError, match="empty"):
        clean_prices(pd.DataFrame(), min_observations=60)


def test_non_numeric_columns_are_rejected() -> None:
    prices = frame(300)
    prices["B"] = "x"
    with pytest.raises(DataValidationError, match=r"Non-numeric.*'B'"):
        clean_prices(prices, min_observations=60)


# -- frequency -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("freq", "expected"),
    [("B", 252), ("D", 365), ("W-FRI", 52), ("ME", 12), ("QE", 4), ("YE", 1)],
)
def test_frequency_inference(freq: str, expected: int) -> None:
    index = pd.date_range("2020-01-01", periods=40, freq=freq)
    assert infer_periods_per_year(index) == expected


def test_frequency_inference_gives_up_on_irregular_spacing() -> None:
    # gaps of 15, 45 and 60 days: median 45 matches no common frequency
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-16", "2024-03-01", "2024-04-30"])
    assert infer_periods_per_year(index) is None
    assert infer_periods_per_year(index[:2]) is None


def test_frequency_warnings() -> None:
    weekly = pd.date_range("2020-01-03", periods=40, freq="W-FRI")
    assert frequency_warnings(weekly, 52) == []
    assert "52 periods per year but periods_per_year is 252" in frequency_warnings(weekly, 252)[0]
    irregular = pd.DatetimeIndex(["2024-01-01", "2024-01-16", "2024-03-01", "2024-04-30"])
    assert "Could not infer" in frequency_warnings(irregular, 252)[0]
