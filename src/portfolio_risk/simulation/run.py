"""One call from historical returns to a complete simulation result."""

from __future__ import annotations

import numpy as np
import pandas as pd

from portfolio_risk.simulation.analytics import (
    SimulationResult,
    band_columns,
    fan_bands,
    summarise,
)
from portfolio_risk.simulation.engine import (
    SimulationConfig,
    check_weights,
    prepare_for_simulation,
    simulate_values,
)
from portfolio_risk.simulation.models import ReturnModel

WORST_PATHS = 20


def run_simulation(
    returns: pd.DataFrame,
    weights: pd.Series,
    model: ReturnModel,
    config: SimulationConfig,
    *,
    source_periods_per_year: int = 252,
) -> SimulationResult:
    """Fit ``model`` on ``returns`` and simulate the portfolio described by ``weights``."""
    prepared = prepare_for_simulation(
        returns, config, source_periods_per_year=source_periods_per_year
    )
    assets = [str(c) for c in prepared.returns.columns]
    w = check_weights(weights, assets)
    model.fit(prepared.returns)
    values = simulate_values(model, w, config)
    summary, paths = summarise(values, config)
    worst = np.argsort(paths.ending)[:WORST_PATHS]
    return SimulationResult(
        model=model.name,
        window=prepared.window,
        warnings=prepared.warnings,
        config=config,
        summary=summary,
        paths=paths,
        bands=fan_bands(values, config),
        worst_paths=values[np.ix_(worst, band_columns(values.shape[1]))].astype(np.float64),
    )
