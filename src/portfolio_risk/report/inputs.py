"""What a report can contain and what it needs. Pure: no reportlab or openpyxl import."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import pandas as pd

from portfolio_risk.analysis import AnalysisResult
from portfolio_risk.comparison import Comparison
from portfolio_risk.decay import DEFAULT_WINDOWS, MIN_HISTORY
from portfolio_risk.simulation import SimulationResult
from portfolio_risk.tearsheet import MIN_OBSERVATIONS


@dataclass(frozen=True, slots=True)
class Section:
    key: str
    label: str
    needs: str  # what must exist for the section to be included, in plain words


SECTIONS: tuple[Section, ...] = (
    Section("summary", "Summary and headline figures", ""),
    Section("performance", "Performance and drawdowns", ""),
    Section("risk", "Risk, Value at Risk and assets", ""),
    Section("correlation", "Correlation of asset returns", ""),
    Section("benchmark", "Benchmark comparison", "a benchmark selected in the sidebar"),
    Section(
        "tearsheet", "Classic tearsheet", "a benchmark or holdings chosen in the Tearsheet tab"
    ),
    Section(
        "comparison", "Portfolio comparison", "two or more portfolios chosen in the Compare tab"
    ),
    Section("monte_carlo", "Monte Carlo projection", "a simulation run in the Monte Carlo tab"),
    Section("alpha_decay", "Alpha decay", "enough history for the chosen windows"),
    Section("assumptions", "Assumptions and disclaimer", ""),
)
KEYS = tuple(s.key for s in SECTIONS)


@dataclass(frozen=True, eq=False)
class ReportInputs:
    """Optional material beyond the base analysis. Each part is built by the interface."""

    tearsheet: dict[str, pd.Series] | None = None  # "Portfolio", benchmark and peers
    comparison: Comparison | None = None
    simulation: Sequence[SimulationResult] | None = None
    decay_windows: tuple[int, ...] = DEFAULT_WINDOWS
    benchmark: str | None = None  # the benchmark's column name, when there is one


def unavailable(result: AnalysisResult, inputs: ReportInputs | None = None) -> dict[str, str]:
    """Sections that cannot be included, each with the reason."""
    inputs = inputs or ReportInputs()
    missing: dict[str, str] = {}
    if result.benchmark is None:
        missing["benchmark"] = "No benchmark is selected."
    tearsheet = inputs.tearsheet
    if tearsheet is None or len(tearsheet) < 2:
        missing["tearsheet"] = "Needs a benchmark or a holding to compare with."
    elif len(result.portfolio_returns.dropna()) < MIN_OBSERVATIONS:
        missing["tearsheet"] = f"Needs at least {MIN_OBSERVATIONS} returns."
    if inputs.comparison is None:
        missing["comparison"] = "Choose two or more portfolios in the Compare tab first."
    if not inputs.simulation:
        missing["monte_carlo"] = "Run a simulation in the Monte Carlo tab first."
    needed = min(inputs.decay_windows) + MIN_HISTORY
    if len(result.portfolio_returns.dropna()) < needed:
        missing["alpha_decay"] = f"Needs at least {needed} returns for the shortest window."
    return missing


def resolve(
    selection: Iterable[str] | None, result: AnalysisResult, inputs: ReportInputs | None = None
) -> list[str]:
    """The sections to print, in report order. ``None`` means everything that is available."""
    missing = unavailable(result, inputs)
    wanted = set(KEYS if selection is None else selection)
    unknown = wanted - set(KEYS)
    if unknown:
        raise ValueError(f"Unknown report sections: {sorted(unknown)}")
    return [k for k in KEYS if k in wanted and k not in missing]
