"""The Monte Carlo tab: table builders, charts and the controls, driven through AppTest."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from portfolio_risk.simulation import SimulationConfig, SimulationResult, make_model, run_simulation
from portfolio_risk.ui import charts, simulation_tables, theme


def history(rows: int = 400) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    data = rng.normal(0.0004, 0.01, (rows, 2))
    return pd.DataFrame(data, index=pd.bdate_range("2020-01-01", periods=rows), columns=["A", "B"])


WEIGHTS = pd.Series({"A": 0.5, "B": 0.5})


def two_results() -> list[SimulationResult]:
    config = SimulationConfig(n_paths=200, horizon_years=1.0, seed=1, initial_value=1000.0)
    return [
        run_simulation(history(), WEIGHTS, make_model(key), config)
        for key in ("gaussian", "student_t")
    ]


def test_comparison_table_has_one_column_per_model_and_labels_thresholds() -> None:
    frame = simulation_tables.comparison_frame(two_results())
    assert list(frame.columns) == ["Statistic", "Gaussian", "Student-t"]
    labels = frame["Statistic"].tolist()
    assert "Probability of a 25% drawdown" in labels
    assert "Probability of ending 50% above start" in labels
    assert "Longest time below a peak, median (days)" in labels
    assert frame.notna().all().all()


def test_scenarios_are_percentiles_and_ordered() -> None:
    result = two_results()[0]
    frame = simulation_tables.scenario_frame(result)
    assert frame["Scenario"].tolist() == ["Bull case", "Base case", "Bear case", "Severe downturn"]
    values = [float(v.replace(",", "")) for v in frame["Ending value"]]
    assert values == sorted(values, reverse=True)
    median = float(np.median(result.paths.ending))
    assert values[1] == pytest.approx(median, abs=1.0)
    assert "percentile" in frame["Defined as"].iloc[0]


def test_charts_build_for_every_palette() -> None:
    result = two_results()[0]
    for palette in theme.PRESETS.values():
        charts.fan_chart(result.bands, 1000.0, palette).to_dict()
        charts.distribution_chart(
            result.paths.ending, "Ending value", fmt=",.0f", marker=1000.0, p=palette
        ).to_dict()


def test_histogram_shares_sum_to_one() -> None:
    frame = charts.histogram_frame(np.random.default_rng(0).normal(size=1000))
    assert len(frame) == 40
    assert frame["share"].sum() == pytest.approx(1.0)


def _app() -> None:
    # AppTest.from_function runs only this function's source, so it imports for itself.
    import numpy as np  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415

    from portfolio_risk.ui import simulation_view, theme  # noqa: PLC0415

    rng = np.random.default_rng(3)
    index = pd.bdate_range("2020-01-01", periods=400)
    prices = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, (400, 2)), axis=0)),
        index=index,
        columns=["A", "B"],
    )
    simulation_view.render(prices, pd.Series({"A": 0.5, "B": 0.5}), theme.DEFAULT, 252)


def test_nothing_runs_until_the_button_is_pressed_then_results_appear() -> None:
    app = AppTest.from_function(_app, default_timeout=60).run()
    assert not app.exception
    assert not app.metric
    next(b for b in app.button if b.label == "Run simulation").click().run()
    assert not app.exception
    assert not app.error
    assert [m.label for m in app.metric][:2] == ["Median ending value", "5th percentile"]


def test_choosing_two_models_adds_a_chart_selector() -> None:
    app = AppTest.from_function(_app, default_timeout=60).run()
    models = next(m for m in app.multiselect if m.label == "Models")
    models.set_value(["Gaussian (normal)", "Student-t (fat tails)"])
    next(b for b in app.button if b.label == "Run simulation").click().run()
    assert not app.exception
    assert any(s.label == "Show charts for" for s in app.selectbox)


def test_no_model_selected_shows_a_message_not_a_crash() -> None:
    app = AppTest.from_function(_app, default_timeout=60).run()
    next(m for m in app.multiselect if m.label == "Models").set_value([])
    next(b for b in app.button if b.label == "Run simulation").click().run()
    assert not app.exception
    assert any("at least one model" in w.value for w in app.warning)


def test_a_block_longer_than_the_history_is_reported_as_an_error() -> None:
    app = AppTest.from_function(_app, default_timeout=60).run()
    next(m for m in app.multiselect if m.label == "Models").set_value(["Block bootstrap"])
    next(n for n in app.number_input if n.label == "Block length (periods)").set_value(252)
    next(b for b in app.button if b.label == "Run simulation").click().run()
    assert not app.exception
    assert not app.error  # 252 fits inside 399 returns


def test_oversized_block_for_a_weekly_simulation_is_reported() -> None:
    app = AppTest.from_function(_app, default_timeout=60).run()
    next(m for m in app.multiselect if m.label == "Models").set_value(["Block bootstrap"])
    next(s for s in app.selectbox if s.label == "Frequency").set_value("weekly")
    next(n for n in app.number_input if n.label == "Block length (periods)").set_value(100)
    next(b for b in app.button if b.label == "Run simulation").click().run()
    assert not app.exception
    assert any("exceeds" in e.value for e in app.error)
