"""The Alpha Decay tab: table builders, chart and the widget, driven through AppTest."""

from __future__ import annotations

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from portfolio_risk.decay import METRICS, alpha_decay
from portfolio_risk.ui import charts, decay_tables, decay_view, theme


def returns(rows: int = 420) -> pd.Series:
    rng = np.random.default_rng(5)
    return pd.Series(
        rng.normal(0.0004, 0.01, rows), index=pd.bdate_range("2021-01-01", periods=rows)
    )


def test_matrix_has_one_row_per_statistic_and_one_column_per_window() -> None:
    report = alpha_decay(returns(), periods_per_year=252, windows=(21, 63))
    html = decay_view.matrix_html(report)
    assert html.count("<tr>") == 1 + len(METRICS)
    assert "21-period window" in html
    assert "63-period window" in html
    # colour never stands alone: every badge also says its rating in words
    assert html.count('class="badge') == len(report.cells)
    assert any(word in html for word in ("Excellent", "Good", "Warning", "Critical"))


def test_unrated_cells_are_labelled_not_blank() -> None:
    report = alpha_decay(returns(80), periods_per_year=252, windows=(21, 60))
    assert "Insufficient history" in decay_view.matrix_html(report)


def test_value_formatting() -> None:
    assert decay_tables.format_value(METRICS[0], 0.1234) == "12.3%"
    assert decay_tables.format_value(METRICS[0], float("nan")) == "n/a"
    assert decay_tables.format_value(METRICS[-1], 1.239) == "1.24"


def test_detail_table_lists_the_comparison() -> None:
    cell = alpha_decay(returns(), periods_per_year=252, windows=(21,)).cell("volatility", 21)
    frame = decay_tables.detail_frame(cell)
    assert frame["Measure"].iloc[0] == "Latest window"
    assert frame.iloc[-1]["Value"] == f"{cell.n_history:,}"


def test_chart_builds_with_every_format() -> None:
    series = pd.Series([0.1, 0.2, 0.15], index=pd.bdate_range("2024-01-01", periods=3))
    for fmt in ("pct", "pct2", "ratio"):
        spec = charts.decay_chart(
            series, mean=0.15, std=0.05, label="x", fmt=fmt, p=theme.DEFAULT
        ).to_dict()
        assert spec["layer"]


def _app() -> None:
    # AppTest.from_function runs only this function's source, so it imports for itself.
    import numpy as np  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415
    import streamlit as st  # noqa: PLC0415

    from portfolio_risk.ui import decay_view, theme  # noqa: PLC0415

    rng = np.random.default_rng(5)
    series = pd.Series(
        rng.normal(0.0004, 0.01, 420), index=pd.bdate_range("2021-01-01", periods=420)
    )
    decay_view.render(series, theme.DEFAULT, 252, 0.0)
    st.write("done")


def test_tab_renders_and_rejects_bad_windows() -> None:
    app = AppTest.from_function(_app, default_timeout=60).run()
    assert not app.exception
    assert any(m.label == "Healthy" for m in app.metric)
    assert any("21-period window" in m.value for m in app.markdown)

    app.text_input(key="decay_windows").set_value("abc").run()
    assert not app.exception
    assert app.error
