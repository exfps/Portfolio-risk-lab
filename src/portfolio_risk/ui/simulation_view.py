"""The Monte Carlo tab: controls, results tables and charts."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from portfolio_risk import PortfolioRiskError
from portfolio_risk.returns import simple_returns
from portfolio_risk.simulation import (
    SimulationConfig,
    SimulationResult,
    make_model,
    run_simulation,
)
from portfolio_risk.simulation.engine import FREQUENCIES, REBALANCING
from portfolio_risk.ui import charts, formatting, report_state, theme
from portfolio_risk.ui.simulation_tables import (
    DISCLAIMER,
    comparison_frame,
    money,
    scenario_frame,
)

PARAMS = "mc_params"
MODEL_LABELS = {
    "Student-t (fat tails)": "student_t",
    "Gaussian (normal)": "gaussian",
    "Historical bootstrap": "bootstrap",
    "Block bootstrap": "block_bootstrap",
}
HORIZONS = (1, 3, 5, 10)
PATH_CHOICES = (1_000, 5_000, 10_000)
DRIFTS = {"Historical average return": "historical", "Zero (isolate risk)": "zero"}


@st.cache_data(show_spinner=False, max_entries=24)
def _simulate(
    returns: pd.DataFrame,
    weights: pd.Series,
    model_key: str,
    model_params: tuple[tuple[str, float | str], ...],
    *,
    config: SimulationConfig,
    periods_per_year: int,
) -> SimulationResult:
    model = make_model(model_key, **dict(model_params))
    return run_simulation(returns, weights, model, config, source_periods_per_year=periods_per_year)


def _controls() -> None:
    with st.form("mc_form"):
        picked = st.multiselect(
            "Models",
            list(MODEL_LABELS),
            default=[next(iter(MODEL_LABELS))],
            help="Pick several to compare them on identical inputs.",
        )
        a, b, c = st.columns(3)
        horizon = a.selectbox("Horizon (years)", HORIZONS, index=2)
        paths = b.selectbox("Simulations", PATH_CHOICES, index=1, format_func=lambda n: f"{n:,}")
        frequency = c.selectbox("Frequency", list(FREQUENCIES), index=0)
        d, e, f = st.columns(3)
        rebalancing = d.selectbox("Rebalancing", list(REBALANCING), index=1)
        drift_label = e.selectbox("Expected return", list(DRIFTS), index=0)
        seed = f.number_input("Random seed", min_value=0, value=42, step=1)
        g, h, i = st.columns(3)
        cost_bp = g.number_input("Transaction cost (basis points)", 0.0, 500.0, 0.0, 1.0)
        bust = h.number_input("Drawdown to flag (%)", 1.0, 99.0, 25.0, 1.0)
        goal = i.number_input("Target gain (%)", 1.0, 1000.0, 50.0, 5.0)
        j, k, m = st.columns(3)
        initial = j.number_input("Starting value", 1.0, 1e12, 100_000.0, 1_000.0, format="%.0f")
        degrees = k.number_input("Student-t degrees of freedom", 2.5, 50.0, 5.0, 0.5)
        block = m.number_input("Block length (periods)", 1, 252, 21, 1)
        if st.form_submit_button("Run simulation", type="primary"):
            st.session_state[PARAMS] = {
                "models": picked,
                "horizon": horizon,
                "paths": paths,
                "frequency": frequency,
                "rebalancing": rebalancing,
                "drift": DRIFTS[drift_label],
                "seed": int(seed),
                "cost": cost_bp / 10_000.0,
                "bust": bust / 100.0,
                "goal": goal / 100.0,
                "initial": float(initial),
                "df": float(degrees),
                "block": int(block),
            }


def _model_params(key: str, params: dict[str, object]) -> tuple[tuple[str, float | str], ...]:
    drift = str(params["drift"])
    if key == "student_t":
        return (("df", float(str(params["df"]))), ("drift", drift))
    if key == "block_bootstrap":
        return (("block_length", int(str(params["block"]))), ("drift", drift))
    return (("drift", drift),)


def render(prices: pd.DataFrame, weights: pd.Series, palette: theme.Palette, ppy: int) -> None:
    """Render the Monte Carlo tab for the portfolio currently shown."""
    st.caption(
        "Simulates many possible futures from a model fitted to this portfolio's history. "
        "Choose assumptions, then press Run."
    )
    _controls()
    params = st.session_state.get(PARAMS)
    if not params:
        return
    if not params["models"]:
        st.warning("Choose at least one model.")
        return
    try:
        config = SimulationConfig(
            n_paths=int(params["paths"]),
            horizon_years=float(params["horizon"]),
            frequency=str(params["frequency"]),
            seed=int(params["seed"]),
            rebalancing=str(params["rebalancing"]),
            transaction_cost=float(params["cost"]),
            initial_value=float(params["initial"]),
            bust_drawdown=float(params["bust"]),
            target_return=float(params["goal"]),
        )
        returns = simple_returns(prices[list(weights.index)])
        with st.spinner("Simulating"):
            results = [
                _simulate(
                    returns,
                    weights,
                    MODEL_LABELS[label],
                    _model_params(MODEL_LABELS[label], params),
                    config=config,
                    periods_per_year=ppy,
                )
                for label in params["models"]
            ]
    except PortfolioRiskError as error:
        st.error(str(error))
        return
    report_state.remember(report_state.SIMULATION, report_state.signature(prices, weights), results)
    _render_results(results, palette)


def _render_results(results: list[SimulationResult], palette: theme.Palette) -> None:
    config = results[0].config
    for note in results[0].warnings:
        st.warning(note)
    st.caption(
        f"{config.n_paths:,} paths  |  {config.horizon_years:g} years, {config.frequency}  |  "
        f"rebalancing: {config.rebalancing}  |  seed {config.seed}  |  "
        f"fitted on {results[0].window}"
    )
    shown = results[0]
    if len(results) > 1:
        name = st.selectbox("Show charts for", [r.model for r in results])
        shown = next(r for r in results if r.model == name)
    s = shown.summary
    cols = st.columns(5)
    cols[0].metric("Median ending value", money(s.ending_percentiles[50]))
    cols[1].metric("5th percentile", money(s.ending_percentiles[5]))
    cols[2].metric("95th percentile", money(s.ending_percentiles[95]))
    cols[3].metric("Probability of loss", formatting.percent(s.prob_loss, 1))
    cols[4].metric("Median max drawdown", formatting.percent(s.max_drawdown_median, 1))

    st.markdown(f"**Projection: {shown.model}**")
    st.altair_chart(charts.fan_chart(shown.bands, config.initial_value, palette))
    st.caption("Line: median. Shaded: 25th to 75th and 5th to 95th percentiles. Dashed: start.")
    left, right = st.columns(2)
    with left:
        st.markdown("**Ending value**")
        st.altair_chart(
            charts.distribution_chart(
                shown.paths.ending,
                "Ending value",
                fmt=",.0f",
                marker=config.initial_value,
                p=palette,
            )
        )
    with right:
        st.markdown("**Maximum drawdown per path**")
        st.altair_chart(
            charts.distribution_chart(
                shown.paths.max_drawdown,
                "Maximum drawdown",
                fmt=".0%",
                colour=palette.negative,
                p=palette,
            )
        )
    st.markdown("**Scenarios**")
    st.markdown(formatting.html_table(scenario_frame(shown)), unsafe_allow_html=True)
    st.markdown("**Risk and outcome statistics**" + (" (all models)" if len(results) > 1 else ""))
    st.markdown(formatting.html_table(comparison_frame(results)), unsafe_allow_html=True)
    st.caption(
        "VaR and expected shortfall are losses over the whole horizon, shown as positive "
        "numbers, and are not annualised. " + DISCLAIMER
    )
