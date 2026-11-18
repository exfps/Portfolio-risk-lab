"""Portfolio comparison against hand calculations and the JSON round trip.

Two assets over 80 returns: A alternates +2%, -1%; B alternates -1%, +2%. Because B's return is
always 1% minus A's, a portfolio with weights (a, 1 - a) returns, on A's up days,
0.02a - 0.01(1 - a), and on its down days -0.01a + 0.02(1 - a):

* 60/40 earns +0.8% then +0.2%, so it never has a drawdown; 50/50 earns exactly +0.5% every
  period (zero variance, which the analysis refuses);
* 70/30 earns +1.1% then -0.1%, perfectly correlated with A; 30/70 is perfectly anti-correlated;
* A alone is the +2% / -1% series.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from portfolio_risk.comparison import (
    MAX_PORTFOLIOS,
    compare,
    weight_sets_from_json,
    weight_sets_to_json,
)
from portfolio_risk.errors import ConfigurationError, DataValidationError

N = 80
INDEX = pd.bdate_range("2024-01-01", periods=N + 1)
RET_A = np.tile([0.02, -0.01], N // 2)
RET_B = 0.01 - RET_A
PRICES = pd.DataFrame(
    {
        "A": 100 * np.concatenate([[1.0], np.cumprod(1 + RET_A)]),
        "B": 100 * np.concatenate([[1.0], np.cumprod(1 + RET_B)]),
        "IDX": 100 * np.concatenate([[1.0], np.cumprod(1 + RET_A)]),
    },
    index=INDEX,
)
SETS = {
    "A only": pd.Series({"A": 1.0}),
    "Sixty": pd.Series({"A": 0.6, "B": 0.4}),
    "Seventy": pd.Series({"A": 0.7, "B": 0.3}),
    "Thirty": pd.Series({"A": 0.3, "B": 0.7}),
}


def cell(frame: pd.DataFrame, row: str, column: str) -> float:
    return float(np.asarray(frame.loc[row, column], dtype=float))


def test_total_returns_match_the_hand_calculation() -> None:
    comparison = compare(PRICES, SETS)
    total = comparison.table.loc["total_return"].astype(float)
    assert total["A only"] == pytest.approx((1.02 * 0.99) ** 40 - 1)
    assert total["Sixty"] == pytest.approx((1.008 * 1.002) ** 40 - 1)
    assert total["Seventy"] == pytest.approx((1.011 * 0.999) ** 40 - 1)
    assert total["Thirty"] == pytest.approx(
        (1 + 0.3 * 0.02 + 0.7 * -0.01) ** 40 * (1 + 0.3 * -0.01 + 0.7 * 0.02) ** 40 - 1
    )


def test_an_always_rising_portfolio_has_no_drawdown() -> None:
    comparison = compare(PRICES, SETS)
    assert comparison.drawdowns["Sixty"].min() == pytest.approx(0.0)
    assert cell(comparison.table, "max_dd", "Sixty") == pytest.approx(0.0)
    assert cell(comparison.table, "max_dd", "A only") == pytest.approx(-0.01)


def test_correlations_are_plus_and_minus_one() -> None:
    corr = compare(PRICES, SETS).correlation
    assert corr.loc["A only", "Seventy"] == pytest.approx(1.0)
    assert corr.loc["A only", "Thirty"] == pytest.approx(-1.0)
    assert corr.loc["Seventy", "Thirty"] == pytest.approx(-1.0)


def test_concentration_and_weights_tables() -> None:
    comparison = compare(PRICES, SETS)
    conc = comparison.concentration
    assert conc.loc["hhi", "A only"] == pytest.approx(1.0)
    assert conc.loc["hhi", "Sixty"] == pytest.approx(0.52)
    assert conc.loc["effective_positions", "Sixty"] == pytest.approx(1 / 0.52)
    assert conc.loc["holdings", "A only"] == 1.0
    assert list(comparison.weights.index) == ["A", "B"]
    assert math.isnan(cell(comparison.weights, "B", "A only"))  # not held
    assert comparison.weights.loc["B", "Seventy"] == pytest.approx(0.3)


def test_benchmark_adds_its_column_and_relative_rows() -> None:
    comparison = compare(
        PRICES, {"A only": SETS["A only"], "Sixty": SETS["Sixty"]}, benchmark="IDX"
    )
    assert list(comparison.table.columns) == ["A only", "Sixty", "IDX"]
    assert cell(comparison.table, "beta", "A only") == pytest.approx(1.0)
    assert cell(comparison.table, "correlation", "A only") == pytest.approx(1.0)
    assert math.isnan(cell(comparison.table, "beta", "IDX"))


def test_all_portfolios_share_the_same_dates_even_with_gaps() -> None:
    gappy = PRICES.copy()
    gappy.loc[gappy.index[:10], "B"] = np.nan  # B starts later
    comparison = compare(gappy, {"A only": SETS["A only"], "Sixty": SETS["Sixty"]})
    assert comparison.start == gappy.index[10]
    assert comparison.returns.notna().all().all()
    assert comparison.observations == N - 10


def test_zero_weights_are_ignored_and_an_empty_portfolio_is_refused() -> None:
    comparison = compare(PRICES, {"x": pd.Series({"A": 1.0, "B": 0.0}), "y": SETS["Sixty"]})
    assert comparison.concentration.loc["holdings", "x"] == 1.0
    assert list(comparison.weights.index) == ["A", "B"]
    with pytest.raises(DataValidationError, match="no holdings"):
        compare(PRICES, {"z": pd.Series({"A": 0.0})})


def test_a_perfectly_hedged_portfolio_is_refused_by_name() -> None:
    half = {"Hedged": pd.Series({"A": 0.5, "B": 0.5})}
    with pytest.raises(DataValidationError, match="Portfolio 'Hedged'"):
        compare(PRICES, half)


def test_unknown_assets_and_limits_are_reported() -> None:
    with pytest.raises(DataValidationError, match="No prices for: Z"):
        compare(PRICES, {"x": pd.Series({"Z": 1.0})})
    with pytest.raises(DataValidationError, match="benchmark"):
        compare(PRICES, {"x": SETS["A only"]}, benchmark="NOPE")
    with pytest.raises(ConfigurationError):
        compare(PRICES, {})
    many = {f"p{i}": SETS["A only"] for i in range(MAX_PORTFOLIOS + 1)}
    with pytest.raises(ConfigurationError, match="at most"):
        compare(PRICES, many)


# ------------------------------------------------------------------------- JSON


def test_json_round_trip() -> None:
    restored = weight_sets_from_json(weight_sets_to_json(SETS))
    assert list(restored) == list(SETS)
    for name, weights in SETS.items():
        assert restored[name].to_dict() == pytest.approx(weights.to_dict())


def doc(*portfolios: tuple[str, object]) -> str:
    return json.dumps(
        {"version": 1, "portfolios": [{"name": n, "weights": w} for n, w in portfolios]}
    )


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ("not json", "not valid JSON"),
        ("[]", "not a portfolio file"),
        ('{"version": 2, "portfolios": []}', "not a portfolio file"),
        ('{"version": 1, "portfolios": []}', "no portfolios"),
        (doc(("", {"A": 1})), "needs a name"),
        (doc(("x", {"A": 0.6})), "not 1"),
        (doc(("x", {"A": -0.5, "B": 1.5})), "zero or positive"),
        (doc(("x", {"A": "1"})), "not a number"),
        (doc(("x", {"A": True})), "not a number"),
        (doc(("x", {})), "no holdings"),
        (doc(("x", 5)), "weights object"),
        (doc(("x", {"A": 1}), ("x", {"A": 1})), "twice"),
    ],
)
def test_malformed_documents_are_rejected_with_a_reason(document: str, message: str) -> None:
    with pytest.raises(DataValidationError, match=message):
        weight_sets_from_json(document)


def test_nan_and_oversized_inputs_are_rejected() -> None:
    nan_doc = '{"version": 1, "portfolios": [{"name": "x", "weights": {"A": NaN}}]}'
    with pytest.raises(DataValidationError):
        weight_sets_from_json(nan_doc)
    long_name = json.dumps({"version": 1, "portfolios": [{"name": "n" * 41, "weights": {"A": 1}}]})
    with pytest.raises(DataValidationError, match="limited"):
        weight_sets_from_json(long_name)
    too_many = json.dumps(
        {"version": 1, "portfolios": [{"name": f"p{i}", "weights": {"A": 1}} for i in range(11)]}
    )
    with pytest.raises(DataValidationError, match="At most"):
        weight_sets_from_json(too_many)


def test_zero_weights_are_dropped() -> None:
    doc = '{"version": 1, "portfolios": [{"name": "x", "weights": {"A": 1, "B": 0}}]}'
    assert list(weight_sets_from_json(doc)["x"].index) == ["A"]
