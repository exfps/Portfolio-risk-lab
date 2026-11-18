"""Monte Carlo result tables as display strings. Pure: no Streamlit import."""

from __future__ import annotations

import numpy as np
import pandas as pd

from portfolio_risk.simulation import SimulationResult
from portfolio_risk.ui import formatting

SCENARIOS = (
    ("Bull case", 0.90, "90th percentile"),
    ("Base case", 0.50, "median"),
    ("Bear case", 0.10, "10th percentile"),
    ("Severe downturn", 0.01, "1st percentile"),
)


DISCLAIMER = (
    "Simulated outcomes come from a statistical model fitted to past returns. They are not "
    "forecasts, and the percentiles are not confidence intervals for future wealth. A "
    "different model or estimation window gives different numbers."
)


def money(value: float) -> str:
    return f"{value:,.0f}"


def comparison_frame(results: list[SimulationResult]) -> pd.DataFrame:
    """One column per model, one row per statistic, formatted for display."""
    first = results[0].config
    pc = formatting.percent
    rows: dict[str, list[str]] = {}

    def add(label: str, values: list[str]) -> None:
        rows[label] = values

    for p in (5, 50, 95):
        name = "Median" if p == 50 else f"{p}th percentile"
        add(f"{name} ending value", [money(r.summary.ending_percentiles[p]) for r in results])
    add("Mean ending value", [money(r.summary.ending_mean) for r in results])
    add("Annual return, 5th percentile", [pc(r.summary.cagr_p05) for r in results])
    add("Annual return, median", [pc(r.summary.cagr_median) for r in results])
    add("Annual return, 95th percentile", [pc(r.summary.cagr_p95) for r in results])
    add("Probability of loss", [pc(r.summary.prob_loss, 1) for r in results])
    add("VaR 95%, whole horizon", [pc(r.summary.var_95) for r in results])
    add("Expected shortfall 95%", [pc(r.summary.es_95) for r in results])
    add("VaR 99%, whole horizon", [pc(r.summary.var_99) for r in results])
    add("Expected shortfall 99%", [pc(r.summary.es_99) for r in results])
    add("Median maximum drawdown", [pc(r.summary.max_drawdown_median) for r in results])
    add("Maximum drawdown, worst 5%", [pc(r.summary.max_drawdown_worst_5pct) for r in results])
    add("Median annualised volatility", [pc(r.summary.volatility_median) for r in results])
    add(
        f"Probability of a {first.bust_drawdown:.0%} drawdown",
        [pc(r.summary.prob_bust, 1) for r in results],
    )
    add(
        f"Probability of ending {first.target_return:.0%} above start",
        [pc(r.summary.prob_target_end, 1) for r in results],
    )
    add(
        f"Probability of ever reaching +{first.target_return:.0%}",
        [pc(r.summary.prob_target_touch, 1) for r in results],
    )
    unit = {"daily": "days", "weekly": "weeks", "monthly": "months"}[first.frequency]
    add(
        f"Longest time below a peak, median ({unit})",
        [f"{r.summary.longest_drawdown_median:,.0f}" for r in results],
    )
    add(
        f"Longest time below a peak, 95th percentile ({unit})",
        [f"{r.summary.longest_drawdown_p95:,.0f}" for r in results],
    )
    frame = pd.DataFrame(rows, index=[r.model for r in results]).T
    frame.insert(0, "Statistic", frame.index)
    return frame.reset_index(drop=True)


def scenario_frame(result: SimulationResult) -> pd.DataFrame:
    """Scenarios defined as percentiles of the simulated ending value, not as shocks."""
    config = result.config
    out = []
    for name, level, label in SCENARIOS:
        end = float(np.quantile(result.paths.ending, level))
        growth = (end / config.initial_value) ** (1.0 / config.horizon_years) - 1.0
        out.append(
            {
                "Scenario": name,
                "Defined as": f"{label} of ending value",
                "Ending value": money(end),
                "Annual return": formatting.percent(growth),
            }
        )
    return pd.DataFrame(out)
