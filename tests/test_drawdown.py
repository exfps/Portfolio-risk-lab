"""Drawdown measures against hand-worked examples.

Drawdown is level / running maximum - 1. Durations count periods from a peak to the first
observation that regains it (or to the last observation if it is never regained).
"""

from __future__ import annotations

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from portfolio_risk.drawdown import drawdown_series, summarise_drawdowns
from portfolio_risk.errors import DataValidationError


def levels(values: list[float], labels: str = "abcdefghij") -> pd.Series:
    return pd.Series(values, index=list(labels[: len(values)]), dtype=float)


def test_drawdown_series_hand_values() -> None:
    # peaks 100, 110, 110, 110 -> 0, 0, 99/110 - 1 = -0.1, 108.9/110 - 1 = -0.01
    result = drawdown_series(levels([100.0, 110.0, 99.0, 108.9]))
    assert result.tolist() == pytest.approx([0.0, 0.0, -0.10, -0.01])


def test_unrecovered_drawdown() -> None:
    summary = summarise_drawdowns(levels([100.0, 110.0, 99.0, 108.9]))
    assert summary.max_drawdown == pytest.approx(-0.10)
    assert (summary.peak, summary.trough, summary.recovery) == ("b", "c", None)
    # Peak at index 1, last observation at index 3: two periods underwater so far.
    assert summary.longest_duration_periods == 2
    assert summary.longest_ongoing is True
    assert summary.current_drawdown == pytest.approx(-0.01)


def test_recovered_drawdown() -> None:
    summary = summarise_drawdowns(levels([1.0, 1.1, 0.99, 1.089, 1.2]))
    assert summary.max_drawdown == pytest.approx(-0.10)
    assert (summary.peak, summary.trough, summary.recovery) == ("b", "c", "e")
    # Peak at index 1, regained at index 4: three periods.
    assert summary.longest_duration_periods == 3
    assert summary.longest_ongoing is False
    assert summary.current_drawdown == 0.0


def test_longest_spell_can_differ_from_deepest_drawdown() -> None:
    # Spell 1: 100 -> 90 -> 100, depth 10%, peak (0) to recovery (2) = 2 periods.
    # Spell 2: 100 -> 95, 92, 96 -> 100, depth 8%, peak (2) to recovery (6) = 4 periods.
    summary = summarise_drawdowns(levels([100.0, 90.0, 100.0, 95.0, 92.0, 96.0, 100.0]))
    assert summary.max_drawdown == pytest.approx(-0.10)
    assert (summary.peak, summary.trough, summary.recovery) == ("a", "b", "c")
    assert summary.longest_duration_periods == 4
    assert summary.longest_ongoing is False


def test_monotonic_series_has_no_drawdown() -> None:
    summary = summarise_drawdowns(levels([1.0, 2.0, 3.0]))
    assert summary.max_drawdown == 0.0
    assert summary.peak is None
    assert summary.trough is None
    assert summary.recovery is None
    assert summary.longest_duration_periods == 0
    assert summary.longest_ongoing is False


def test_single_observation() -> None:
    assert summarise_drawdowns(levels([5.0])).max_drawdown == 0.0


@pytest.mark.parametrize("bad", [[1.0, 0.0, 2.0], [1.0, -1.0], [1.0, float("nan")]])
def test_non_positive_or_non_finite_levels_are_rejected(bad: list[float]) -> None:
    with pytest.raises(DataValidationError, match="strictly positive"):
        drawdown_series(levels(bad))


def test_empty_series_is_rejected() -> None:
    with pytest.raises(DataValidationError, match="at least one"):
        summarise_drawdowns(pd.Series([], dtype=float))


@given(st.lists(st.floats(min_value=0.01, max_value=1e6), min_size=1, max_size=200))
def test_drawdown_is_bounded_and_consistent_with_summary(values: list[float]) -> None:
    series = pd.Series(values)
    drawdown = drawdown_series(series)
    summary = summarise_drawdowns(series)
    assert drawdown.iloc[0] == 0.0
    assert -1.0 < drawdown.min() <= 0.0
    assert summary.max_drawdown == drawdown.min()
    assert summary.current_drawdown == drawdown.iloc[-1]
    assert (summary.longest_duration_periods == 0) == (summary.max_drawdown == 0.0)


@given(
    st.lists(st.floats(min_value=0.01, max_value=1e6), min_size=1, max_size=100),
    st.floats(min_value=0.01, max_value=1e3),
)
def test_drawdown_is_invariant_to_scale(values: list[float], factor: float) -> None:
    base = summarise_drawdowns(pd.Series(values))
    scaled = summarise_drawdowns(pd.Series(values) * factor)
    assert scaled.max_drawdown == pytest.approx(base.max_drawdown, abs=1e-9)
