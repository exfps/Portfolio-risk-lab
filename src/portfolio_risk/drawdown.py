"""Drawdown measures.

Drawdown functions operate on a *level* series (prices or a wealth index), not on returns.
The drawdown at time ``t`` is ``L_t / max(L_0 .. L_t) - 1`` and is always in ``[-1, 0]``.
"""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

from portfolio_risk.errors import DataValidationError


@dataclass(frozen=True, slots=True)
class DrawdownSummary:
    """Summary of the underwater periods in a level series.

    ``max_drawdown`` is zero or negative. ``peak``, ``trough`` and ``recovery`` label the
    deepest drawdown; they are ``None`` when the series never fell below a prior high, and
    ``recovery`` is also ``None`` when the deepest drawdown has not been recovered.

    ``longest_duration_periods`` is the number of periods from a peak to the first
    observation at or above that peak, or to the last observation if it was never regained.
    ``longest_ongoing`` flags the latter case.
    """

    max_drawdown: float
    peak: Hashable | None
    trough: Hashable | None
    recovery: Hashable | None
    longest_duration_periods: int
    longest_ongoing: bool
    current_drawdown: float


def _levels(levels: pd.Series, statistic: str) -> npt.NDArray[np.float64]:
    values = levels.to_numpy(dtype=np.float64)
    if values.size == 0:
        raise DataValidationError(f"{statistic} needs at least one observation.")
    if not np.isfinite(values).all() or (values <= 0.0).any():
        raise DataValidationError(f"{statistic} requires finite, strictly positive levels.")
    return values


def drawdown_series(levels: pd.Series) -> pd.Series:
    """Drawdown from the running maximum at every observation."""
    values = _levels(levels, "Drawdown")
    drawdown = values / np.maximum.accumulate(values) - 1.0
    return pd.Series(drawdown, index=levels.index, name="drawdown")


def _underwater_runs(underwater: npt.NDArray[np.bool_]) -> list[tuple[int, int]]:
    """Half-open index ranges ``[start, end)`` of consecutive True values."""
    padded = np.concatenate(([False], underwater, [False])).astype(np.int8)
    edges = np.diff(padded)
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)
    return [(int(start), int(end)) for start, end in zip(starts, ends, strict=True)]


def summarise_drawdowns(levels: pd.Series) -> DrawdownSummary:
    """Maximum drawdown, its peak, trough and recovery, and the longest underwater spell."""
    values = _levels(levels, "Drawdown summary")
    drawdown = values / np.maximum.accumulate(values) - 1.0
    labels = levels.index
    current = float(drawdown[-1])

    runs = _underwater_runs(drawdown < 0.0)
    if not runs:
        return DrawdownSummary(0.0, None, None, None, 0, False, current)

    trough = int(np.argmin(drawdown))
    peak = int(np.flatnonzero(drawdown[: trough + 1] == 0.0)[-1])
    regained = np.flatnonzero(drawdown[trough + 1 :] == 0.0)
    recovery = trough + 1 + int(regained[0]) if regained.size else None

    def duration(run: tuple[int, int]) -> int:
        start, end = run
        return (end - start) + (1 if end < values.size else 0)

    longest = max(runs, key=duration)
    return DrawdownSummary(
        max_drawdown=float(drawdown[trough]),
        peak=labels[peak],
        trough=labels[trough],
        recovery=labels[recovery] if recovery is not None else None,
        longest_duration_periods=duration(longest),
        longest_ongoing=longest[1] == values.size,
        current_drawdown=current,
    )
