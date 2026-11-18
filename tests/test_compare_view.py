"""The Compare tab: table builders and the save, load and compare flow through AppTest."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from portfolio_risk.comparison import compare
from portfolio_risk.ui import compare_tables


def _frames() -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    rng = np.random.default_rng(2)
    data = pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0.0004, 0.01, (200, 3)), axis=0),
        index=pd.bdate_range("2023-01-02", periods=200),
        columns=["A", "B", "C"],
    )
    return data, {"One": pd.Series({"A": 0.7, "B": 0.3}), "Two": pd.Series({"B": 0.5, "C": 0.5})}


def test_table_builders() -> None:
    data, sets = _frames()
    comparison = compare(data, sets)
    weights = compare_tables.weights_frame(comparison.weights)
    assert list(weights.columns) == ["Holding", "One", "Two"]
    assert list(weights["Holding"]) == ["A", "B", "C"]
    assert weights.loc[weights["Holding"] == "A", "Two"].iloc[0] == "-"  # not held
    assert weights.loc[weights["Holding"] == "B", "One"].iloc[0] == "30.0%"
    conc = compare_tables.concentration_frame(comparison.concentration)
    assert list(conc["Measure"]) == [
        "Holdings",
        "Concentration (HHI)",
        "Effective number of positions",
    ]
    assert conc.loc[conc["Measure"] == "Holdings", "Two"].iloc[0] == "2"
    assert conc.loc[conc["Measure"] == "Concentration (HHI)", "One"].iloc[0] == "0.580"
    corr = compare_tables.correlation_frame(comparison.correlation)
    assert corr.iloc[0, 1] == "1.00"


def _app() -> None:
    # AppTest.from_function runs only this function's source, so it imports for itself.
    import numpy as np  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415

    from portfolio_risk import analyse  # noqa: PLC0415
    from portfolio_risk.ui import compare_view, theme  # noqa: PLC0415

    rng = np.random.default_rng(2)
    data = pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0.0004, 0.01, (200, 3)), axis=0),
        index=pd.bdate_range("2023-01-02", periods=200),
        columns=["A", "B", "C"],
    )
    result = analyse(data, pd.Series({"A": 0.6, "B": 0.4, "C": 0.0}))
    compare_view.render(result, data, None, theme.DEFAULT)


def fresh() -> AppTest:
    app = AppTest.from_function(_app, default_timeout=60).run()
    assert not app.exception
    return app


def click(app: AppTest, key: str) -> AppTest:
    next(b for b in app.button if b.key == key).click()
    return app.run()


def test_a_single_choice_asks_for_a_second() -> None:
    app = fresh()
    assert any("at least two" in i.value for i in app.info)


def test_saving_needs_a_name_and_then_stores_the_current_weights() -> None:
    app = click(fresh(), "compare_save")
    assert any("name" in e.value for e in app.error)
    app.text_input(key="compare_name").set_value("Growth tilt").run()
    app = click(app, "compare_save")
    assert not app.exception
    assert app.session_state["saved_portfolios"] == {"Growth tilt": {"A": 0.6, "B": 0.4}}
    assert any("Saved 'Growth tilt'" in s.value for s in app.success)
    assert app.text_input(key="compare_name").value == ""


def test_the_reserved_name_is_refused() -> None:
    app = fresh()
    app.text_input(key="compare_name").set_value("Current weights").run()
    app = click(app, "compare_save")
    assert any("reserved" in e.value for e in app.error)
    assert not app.session_state["saved_portfolios"]


def test_two_portfolios_are_compared_side_by_side() -> None:
    app = fresh()
    app.session_state["saved_portfolios"] = {"Other": {"B": 0.5, "C": 0.5}}
    app.run()
    app.multiselect(key="compare_chosen").set_value(["Current weights", "Other"]).run()
    assert not app.exception
    html = "".join(m.value for m in app.markdown)
    assert "<th>Current weights</th>" in html
    assert "<th>Other</th>" in html
    assert any(h.value == "Key statistics" for h in app.subheader)


def test_a_portfolio_with_unknown_holdings_is_skipped_with_a_warning() -> None:
    app = fresh()
    app.session_state["saved_portfolios"] = {
        "Gone": {"ZZZ": 1.0},
        "Fine": {"C": 1.0},
    }
    app.run()
    app.multiselect(key="compare_chosen").set_value(["Current weights", "Gone", "Fine"]).run()
    assert any("ZZZ" in w.value for w in app.warning)
    assert "<th>Fine</th>" in "".join(m.value for m in app.markdown)


def test_remove_drops_the_portfolio_and_its_selection() -> None:
    app = fresh()
    app.session_state["saved_portfolios"] = {"Other": {"B": 0.5, "C": 0.5}}
    app.run()
    app.multiselect(key="compare_chosen").set_value(["Current weights", "Other"]).run()
    app = click(app, "compare_remove")
    assert app.session_state["saved_portfolios"] == {}
    assert "Other" not in app.session_state["compare_chosen"]


def test_loading_a_file_and_rejecting_a_bad_one() -> None:
    app = fresh()
    good = json.dumps(
        {"version": 1, "portfolios": [{"name": "Loaded", "weights": {"A": 0.5, "C": 0.5}}]}
    ).encode()
    app.file_uploader(key="compare_upload").set_value(("p.json", good, "application/json")).run()
    assert not app.exception
    assert "Loaded" in app.session_state["saved_portfolios"]
    bad = fresh()
    bad.file_uploader(key="compare_upload").set_value(("p.json", b"nope", "application/json")).run()
    assert any("not valid JSON" in e.value for e in bad.error)
    assert not bad.session_state["saved_portfolios"]
