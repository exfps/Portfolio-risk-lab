"""The Tearsheet tab: table builders, series assembly and the widget through AppTest."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from portfolio_risk import analyse
from portfolio_risk.tearsheet import RELATIVE_ROWS, ROWS, tearsheet_table
from portfolio_risk.ui import charts, tearsheet_tables, theme


def prices(rows: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    steps = rng.normal(0.0004, 0.01, (rows, 3))
    return pd.DataFrame(
        100 * np.cumprod(1 + steps, axis=0),
        index=pd.bdate_range("2023-01-02", periods=rows),
        columns=["A", "B", "BENCH"],
    )


WEIGHTS = pd.Series({"A": 0.6, "B": 0.4})


def test_series_are_aligned_to_the_portfolio_dates() -> None:
    data = prices()
    result = analyse(data, WEIGHTS, benchmark="BENCH")
    series = tearsheet_tables.named_returns(result, data, "BENCH", ["A", "A", "nope"])
    assert list(series) == ["Portfolio", "BENCH", "A"]  # no duplicates, unknown names dropped
    assert all(s.index.equals(result.portfolio_returns.index) for s in series.values())


def test_metrics_frame_formats_every_row_and_marks_blanks() -> None:
    data = prices()
    result = analyse(data, WEIGHTS, benchmark="BENCH")
    series = tearsheet_tables.named_returns(result, data, "BENCH", ["A"])
    table = tearsheet_table(series, periods_per_year=252, benchmark="BENCH")
    shown = tearsheet_tables.metrics_frame(table)
    assert list(shown.columns) == ["Statistic", "Portfolio", "BENCH", "A"]
    assert len(shown) == len(ROWS) + len(RELATIVE_ROWS)
    beta_row = shown[shown["Statistic"] == "Beta to benchmark"].iloc[0]
    assert beta_row["BENCH"] == "n/a"  # the benchmark has no beta to itself
    assert beta_row["Portfolio"] != "n/a"
    total = shown[shown["Statistic"] == "Total return"].iloc[0]["Portfolio"]
    assert total.endswith("%")


def test_cell_formatting() -> None:
    by_key = {r.key: r for r in ROWS}
    assert tearsheet_tables.format_cell(by_key["longest_dd"], 1234.0) == "1,234"
    assert tearsheet_tables.format_cell(by_key["sharpe"], 1.239) == "1.24"
    assert tearsheet_tables.format_cell(by_key["var95"], 0.01234) == "1.23%"
    assert tearsheet_tables.format_cell(by_key["cagr"], math.nan) == "n/a"


def test_episodes_table_for_a_series_with_and_without_drawdowns() -> None:
    wealth = pd.Series([1.0, 1.1, 0.99, 1.2], index=pd.bdate_range("2024-01-01", periods=4))
    shown = tearsheet_tables.episodes_frame(wealth)
    assert shown.iloc[0]["Depth"] == "-10.00%"
    assert shown.iloc[0]["Recovered"] == "2024-01-04"
    rising = pd.Series([1.0, 1.1], index=pd.bdate_range("2024-01-01", periods=2))
    assert tearsheet_tables.episodes_frame(rising).empty


def test_charts_build() -> None:
    frame = pd.DataFrame(
        {"P": [1.0, 1.1, 1.2], "B": [1.0, 1.0, 1.1]}, index=pd.bdate_range("2024-01-01", periods=3)
    )
    assert charts.comparison_chart(frame, title="x", fmt=".2f").to_dict()[
        "layer" if False else "mark"
    ]
    years = pd.DataFrame({"P": [0.1, -0.05], "B": [0.08, 0.02]}, index=[2023, 2024])
    assert charts.year_bars(years).to_dict()["mark"]
    grid = pd.DataFrame({"Jan": [0.02], "Feb": [-0.01], "Year": [0.01]}, index=[2024])
    assert charts.monthly_heatmap(grid).to_dict()["layer"]
    assert len(charts.series_colours(theme.DEFAULT, 8)) == 8


def _app() -> None:
    # AppTest.from_function runs only this function's source, so it imports for itself.
    import numpy as np  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415

    from portfolio_risk import analyse  # noqa: PLC0415
    from portfolio_risk.ui import tearsheet_view, theme  # noqa: PLC0415

    rng = np.random.default_rng(11)
    data = pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0.0004, 0.01, (300, 3)), axis=0),
        index=pd.bdate_range("2023-01-02", periods=300),
        columns=["A", "B", "BENCH"],
    )
    result = analyse(data, pd.Series({"A": 0.6, "B": 0.4}), benchmark="BENCH")
    tearsheet_view.render(result, data, "BENCH", theme.DEFAULT)


def test_tab_renders_and_accepts_peers() -> None:
    app = AppTest.from_function(_app, default_timeout=60).run()
    assert not app.exception
    assert any(h.value == "Key statistics" for h in app.subheader)
    app.multiselect(key="tearsheet_peers").set_value(["A"]).run()
    assert not app.exception
    assert any("<th>A</th>" in m.value for m in app.markdown)
    app.selectbox(key="tearsheet_kind").set_value("Sharpe ratio").run()
    assert not app.exception
    assert not app.info
