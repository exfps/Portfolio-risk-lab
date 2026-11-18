"""Alpha decay: is the portfolio's recent behaviour unusual compared with its own history?

For each statistic and each window length, the statistic is computed over every rolling
window of that length. The most recent window is then compared with all *earlier* windows of
the same length using a z-score, oriented so that a higher score is always better (a
volatility that is lower than usual scores positive).

Limits worth knowing
--------------------
* Overlapping windows are strongly autocorrelated, so the history holds far fewer independent
  observations than it has windows. The z-score is a rough flag, not a significance test.
* A z-score assumes a roughly symmetric distribution. Drawdown, VaR and payoff ratio are
  skewed, so the percentile rank is reported next to it.
* The rating thresholds are conventions chosen for readability, not statistical results.
* Very short windows give noisy statistics; VaR and shortfall at 95% from fewer than about 20
  observations are close to the single worst day.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt
import pandas as pd

from portfolio_risk._checks import CONSTANT_TOLERANCE
from portfolio_risk.errors import ConfigurationError, InsufficientDataError

Array = npt.NDArray[np.float64]
Rating = Literal["Excellent", "Good", "Warning", "Critical", "Insufficient history"]
RATINGS: tuple[Rating, ...] = ("Excellent", "Good", "Warning", "Critical")

DEFAULT_WINDOWS = (21, 63, 126)
MIN_WINDOW = 5
MIN_HISTORY = 30  # earlier windows needed before a rating is given
EXCELLENT_Z = 1.0
GOOD_Z = -0.5
WARNING_Z = -1.5


@dataclass(frozen=True)
class DecayMetric:
    """A statistic of one window of returns. ``higher_is_better`` orients the z-score."""

    key: str
    label: str
    higher_is_better: bool
    fmt: str  # "pct", "pct2" or "ratio"
    compute: Callable[[Array, int, float], Array]  # (windows, periods_per_year, rf) -> values


def _ann_return(w: Array, ppy: int, _rf: float) -> Array:
    growth = np.prod(1.0 + w, axis=1)
    return np.asarray(growth ** (ppy / w.shape[1]) - 1.0)


def _volatility(w: Array, ppy: int, _rf: float) -> Array:
    return np.asarray(w.std(axis=1, ddof=1) * np.sqrt(ppy))


def _downside(w: Array, ppy: int, _rf: float) -> Array:
    return np.asarray(np.sqrt(np.mean(np.minimum(w, 0.0) ** 2, axis=1)) * np.sqrt(ppy))


def _drawdowns(w: Array) -> Array:
    levels = np.cumprod(1.0 + w, axis=1)
    levels = np.concatenate([np.ones((len(w), 1)), levels], axis=1)
    return np.asarray(levels / np.maximum.accumulate(levels, axis=1) - 1.0)


def _max_drawdown(w: Array, _ppy: int, _rf: float) -> Array:
    return np.asarray(_drawdowns(w).min(axis=1))


def _mean_drawdown(w: Array, _ppy: int, _rf: float) -> Array:
    return np.asarray(_drawdowns(w).mean(axis=1))


def _win_rate(w: Array, _ppy: int, _rf: float) -> Array:
    return np.asarray((w > 0).mean(axis=1))


def _var95(w: Array, _ppy: int, _rf: float) -> Array:
    return np.asarray(-np.quantile(w, 0.05, axis=1))


def _es95(w: Array, _ppy: int, _rf: float) -> Array:
    cutoff = np.quantile(w, 0.05, axis=1, keepdims=True)
    tail = w <= cutoff
    return np.asarray(-(np.where(tail, w, 0.0).sum(axis=1) / tail.sum(axis=1)))


def _payoff(w: Array, _ppy: int, _rf: float) -> Array:
    wins, losses = w > 0, w < 0
    average_win = np.where(wins, w, 0.0).sum(axis=1) / np.maximum(wins.sum(axis=1), 1)
    average_loss = -np.where(losses, w, 0.0).sum(axis=1) / np.maximum(losses.sum(axis=1), 1)
    ratio = np.full(len(w), np.nan)
    np.divide(average_win, average_loss, out=ratio, where=average_loss > 0)
    return ratio


def _sharpe(w: Array, ppy: int, rf: float) -> Array:
    spread = w.mean(axis=1) - rf / ppy
    deviation = w.std(axis=1, ddof=1)
    out = np.full(len(w), np.nan)
    np.divide(spread, deviation, out=out, where=deviation > CONSTANT_TOLERANCE)
    return np.asarray(out * np.sqrt(ppy))


METRICS: tuple[DecayMetric, ...] = (
    DecayMetric("ann_return", "Annualised return", True, "pct", _ann_return),
    DecayMetric("volatility", "Volatility", False, "pct", _volatility),
    DecayMetric("downside", "Downside volatility", False, "pct", _downside),
    DecayMetric("max_dd", "Maximum drawdown", True, "pct", _max_drawdown),
    DecayMetric("mean_dd", "Average drawdown", True, "pct2", _mean_drawdown),
    DecayMetric("win_rate", "Win rate", True, "pct", _win_rate),
    DecayMetric("var95", "Value at Risk 95%", False, "pct2", _var95),
    DecayMetric("es95", "Expected shortfall 95%", False, "pct2", _es95),
    DecayMetric("payoff", "Payoff ratio", True, "ratio", _payoff),
    DecayMetric("sharpe", "Sharpe ratio", True, "ratio", _sharpe),
)
_BY_KEY = {m.key: m for m in METRICS}


@dataclass(frozen=True)
class DecayCell:
    metric: DecayMetric
    window: int
    latest: float
    history_mean: float
    history_std: float
    z: float  # oriented: higher is always better
    percentile: float  # share of earlier windows the latest is better than, 0 to 1
    rating: Rating
    n_history: int


@dataclass(frozen=True)
class DecayReport:
    cells: tuple[DecayCell, ...]
    windows: tuple[int, ...]
    as_of: pd.Timestamp
    observations: int
    periods_per_year: int

    def counts(self) -> dict[Rating, int]:
        out: dict[Rating, int] = dict.fromkeys((*RATINGS, "Insufficient history"), 0)
        for cell in self.cells:
            out[cell.rating] += 1
        return out

    @property
    def rated(self) -> int:
        return sum(1 for c in self.cells if c.rating != "Insufficient history")

    @property
    def healthy(self) -> int:
        """Cells rated Good or Excellent."""
        return sum(1 for c in self.cells if c.rating in ("Good", "Excellent"))

    def cell(self, key: str, window: int) -> DecayCell:
        for c in self.cells:
            if c.metric.key == key and c.window == window:
                return c
        raise KeyError((key, window))


def rate(z: float) -> Rating:
    """Map an oriented z-score to a rating band."""
    if z >= EXCELLENT_Z:
        return "Excellent"
    if z >= GOOD_Z:
        return "Good"
    if z >= WARNING_Z:
        return "Warning"
    return "Critical"


def parse_windows(text: str) -> tuple[int, ...]:
    """Parse '21, 63, 126' into sorted unique window lengths."""
    try:
        values = sorted({int(part) for part in text.replace(";", ",").split(",") if part.strip()})
    except ValueError:
        raise ConfigurationError("Windows must be whole numbers separated by commas.") from None
    if not values or len(values) > 6:
        raise ConfigurationError("Give between one and six window lengths.")
    if values[0] < MIN_WINDOW:
        raise ConfigurationError(f"Windows must be at least {MIN_WINDOW} periods long.")
    return tuple(values)


def rolling_values(
    returns: pd.Series, metric: DecayMetric, window: int, periods_per_year: int, rf: float = 0.0
) -> pd.Series:
    """The statistic over every rolling window, labelled by the window's last date."""
    values = returns.to_numpy(dtype=np.float64)
    if len(values) < window:
        raise InsufficientDataError(f"A {window}-period window needs {window} returns.")
    frames = np.lib.stride_tricks.sliding_window_view(values, window)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = metric.compute(np.ascontiguousarray(frames), periods_per_year, rf)
    return pd.Series(out, index=returns.index[window - 1 :], name=metric.label)


def _unrated(metric: DecayMetric, window: int, latest: float, n_history: int) -> DecayCell:
    nan = float("nan")
    return DecayCell(metric, window, latest, nan, nan, nan, nan, "Insufficient history", n_history)


def _cell(metric: DecayMetric, window: int, series: pd.Series, min_history: int) -> DecayCell:
    latest = float(series.iloc[-1])
    prior = series.iloc[:-1].to_numpy(dtype=np.float64)
    prior = prior[np.isfinite(prior)]
    sign = 1.0 if metric.higher_is_better else -1.0
    if len(prior) < min_history or not np.isfinite(latest):
        return _unrated(metric, window, latest, len(prior))
    mean, std = float(prior.mean()), float(prior.std(ddof=1))
    z = 0.0 if std == 0.0 else sign * (latest - mean) / std
    better = (prior < latest) if metric.higher_is_better else (prior > latest)
    ties = prior == latest
    percentile = float((better.sum() + 0.5 * ties.sum()) / len(prior))
    return DecayCell(metric, window, latest, mean, std, z, percentile, rate(z), len(prior))


def alpha_decay(
    returns: pd.Series,
    *,
    periods_per_year: int,
    windows: tuple[int, ...] = DEFAULT_WINDOWS,
    risk_free: float = 0.0,
    min_history: int = MIN_HISTORY,
) -> DecayReport:
    """Compare the latest rolling window of every statistic with the earlier ones."""
    if not windows:
        raise ConfigurationError("Give at least one window length.")
    if min_history < 2:
        raise ConfigurationError("min_history must be at least 2.")
    clean = returns.dropna()
    if len(clean) < min(windows) + min_history:
        raise InsufficientDataError(
            f"Alpha decay needs at least {min(windows) + min_history} returns "
            f"for a {min(windows)}-period window; got {len(clean)}."
        )
    cells: list[DecayCell] = []
    for window in windows:
        for metric in METRICS:
            if len(clean) < window + 1:
                cells.append(_unrated(metric, window, np.nan, 0))
                continue
            series = rolling_values(clean, metric, window, periods_per_year, risk_free)
            cells.append(_cell(metric, window, series, min_history))
    return DecayReport(
        cells=tuple(cells),
        windows=tuple(windows),
        as_of=pd.Timestamp(clean.index[-1]),
        observations=len(clean),
        periods_per_year=periods_per_year,
    )


def metric_by_key(key: str) -> DecayMetric:
    return _BY_KEY[key]
