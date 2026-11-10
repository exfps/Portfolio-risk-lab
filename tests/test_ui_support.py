"""Interface helpers that need no running Streamlit: formatting, inputs, charts, launcher."""

from __future__ import annotations

import importlib.util
import math
import subprocess
import sys
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from portfolio_risk import AnalysisResult, analyse
from portfolio_risk import cli as launcher
from portfolio_risk.sample_data import BENCHMARK, generate_sample_prices, sample_weights
from portfolio_risk.ui import charts, formatting, theme
from portfolio_risk.ui.inputs import weights_frame, weights_from_frame
from portfolio_risk.ui.styles import stylesheet
from portfolio_risk.ui.theme import STREAMLIT_OPTIONS

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def sample_result() -> AnalysisResult:
    return analyse(generate_sample_prices(), sample_weights(), benchmark=BENCHMARK)


def pairs(table: pd.DataFrame | None) -> dict[str, str]:
    """A two-column Measure/Value table as a dict."""
    assert table is not None
    return dict(zip(table["Measure"].tolist(), table["Value"].tolist(), strict=True))


def single_asset_result(daily_returns: np.ndarray) -> AnalysisResult:
    index = pd.bdate_range("2024-01-01", periods=len(daily_returns) + 1, name="date")
    levels = 100.0 * np.concatenate([[1.0], np.cumprod(1.0 + daily_returns)])
    return analyse(pd.DataFrame({"A": levels}, index=index), pd.Series({"A": 1.0}))


# -- formatting --------------------------------------------------------------------------------


def test_percent_and_ratio() -> None:
    assert formatting.percent(0.0705) == "7.05%"
    assert formatting.percent(-0.1165, 1) == "-11.7%"
    assert formatting.ratio(0.7127) == "0.71"
    assert formatting.ratio(1.0, 3) == "1.000"


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_values_display_as_not_available(value: float) -> None:
    assert formatting.percent(value) == "n/a"
    assert formatting.ratio(value) == "n/a"


def test_day() -> None:
    assert formatting.day(pd.Timestamp("2024-03-05 00:00")) == "2024-03-05"
    assert formatting.day(None) == "-"
    assert formatting.day(None, missing="none") == "none"


def test_headline_metrics_match_the_documented_sample_numbers(
    sample_result: AnalysisResult,
) -> None:
    metrics = dict(formatting.headline_metrics(sample_result))
    assert metrics == {
        "Total return": "22.66%",
        "Annualised return": "7.05%",
        "Volatility": "10.30%",
        "Sharpe": "0.71",
        "Sortino": "1.05",
        "Max drawdown": "-11.65%",
    }


def test_drawdown_table_for_a_recovered_drawdown(sample_result: AnalysisResult) -> None:
    table = pairs(formatting.drawdown_table(sample_result))
    assert table["Peak"] == "2022-08-15"
    assert table["Trough"] == "2023-04-10"
    assert table["Recovery"] == "2023-11-15"
    assert table["Longest underwater spell"] == "327 periods (recovered)"
    assert table["Current drawdown"] == "-3.33%"


def test_drawdown_table_for_an_unrecovered_drawdown() -> None:
    returns = np.array([0.01, 0.02, -0.05, 0.005, 0.004] * 24)
    table = pairs(formatting.drawdown_table(single_asset_result(returns)))
    assert table["Recovery"] == "not recovered"
    assert table["Longest underwater spell"].endswith("(ongoing)")


def test_rising_prices_have_no_drawdown_and_undefined_sortino() -> None:
    returns = 0.002 + 0.0005 * np.sin(np.arange(120))
    result = single_asset_result(returns)
    table = pairs(formatting.drawdown_table(result))
    assert table["Maximum drawdown"] == "0.00%"
    assert table["Recovery"] == "-"
    assert table["Longest underwater spell"] == "none"
    assert dict(formatting.headline_metrics(result))["Sortino"] == "n/a"


def test_var_table(sample_result: AnalysisResult) -> None:
    table = formatting.var_table(sample_result)
    assert table["Confidence"].tolist() == ["95%", "99%"]
    assert table.loc[0, "Historical VaR"] == "1.00%"
    assert list(table.columns) == [
        "Confidence",
        "Historical VaR",
        "Historical CVaR",
        "Parametric VaR",
        "Parametric CVaR",
    ]


def test_asset_table(sample_result: AnalysisResult) -> None:
    table = formatting.asset_table(sample_result)
    assert table["Asset"].tolist()[0] == "SYN_EQ_US"
    assert table["Weight"].tolist()[0] == "30.0%"
    assert table["Risk share"].tolist()[0] == "43.7%"
    assert len(table) == 6


def test_benchmark_table(sample_result: AnalysisResult) -> None:
    table = formatting.benchmark_table(sample_result)
    assert table is not None
    assert pairs(table)["Beta"] == "0.94"
    without = analyse(generate_sample_prices().drop(columns=BENCHMARK), sample_weights())
    assert formatting.benchmark_table(without) is None


# -- inputs ------------------------------------------------------------------------------------


def test_equal_weights_by_default() -> None:
    frame = weights_frame(["A", "B", "C", "D"], None)
    assert frame["ticker"].tolist() == ["A", "B", "C", "D"]
    assert frame["weight"].tolist() == [0.25] * 4


def test_no_tickers_gives_an_empty_frame() -> None:
    assert weights_frame([], None).empty


def test_supplied_weights_fill_missing_tickers_with_zero_and_keep_extras() -> None:
    supplied = pd.Series({"A": 0.6, "ZZZ": 0.4})
    frame = weights_frame(["A", "B"], supplied)
    assert frame["ticker"].tolist() == ["A", "B", "ZZZ"]
    assert frame["weight"].tolist() == [0.6, 0.0, 0.4]


def test_weights_round_trip_and_cleared_cells_become_nan() -> None:
    frame = pd.DataFrame({"ticker": ["A", "B"], "weight": [0.5, None]})
    weights = weights_from_frame(frame)
    assert weights.index.tolist() == ["A", "B"]
    assert weights["A"] == 0.5
    assert math.isnan(weights["B"])


# -- charts ------------------------------------------------------------------------------------


def test_every_chart_builds_a_valid_specification(sample_result: AnalysisResult) -> None:
    specs = {
        "wealth": charts.wealth_chart(sample_result.wealth),
        "drawdown": charts.drawdown_chart(sample_result.drawdowns),
        "risk": charts.risk_contribution_chart(sample_result.risk_contribution),
        "heatmap": charts.correlation_heatmap(sample_result.correlation),
    }
    for chart in specs.values():
        assert chart.to_dict()["$schema"].startswith("https://vega.github.io/schema/vega-lite/")


def test_heatmap_has_one_cell_per_pair_and_a_bounded_colour_scale(
    sample_result: AnalysisResult,
) -> None:
    spec = charts.correlation_heatmap(sample_result.correlation).to_dict()
    cells = next(iter(spec["datasets"].values()))
    assert len(cells) == 36
    assert {row["x"] for row in cells} == set(sample_result.correlation.columns)
    assert all(-1.0 - 1e-9 <= row["rho"] <= 1.0 + 1e-9 for row in cells)


# -- theme, config and launcher ------------------------------------------------------------------


def test_streamlit_config_file_matches_the_theme_constants() -> None:
    config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    flattened = {
        f"{section}.{name}": str(value).lower() if isinstance(value, bool) else str(value)
        for section, values in config.items()
        for name, value in values.items()
    }
    assert flattened == STREAMLIT_OPTIONS


def test_launcher_command_uses_this_interpreter_and_the_packaged_app() -> None:
    command = launcher.build_command(["--server.port", "8600"])
    assert command[:5] == [sys.executable, "-m", "streamlit", "run", command[4]]
    assert Path(command[4]).is_file()
    assert Path(command[4]).name == "app.py"
    assert command[-2:] == ["--server.port", "8600"]
    assert (
        command[command.index("--theme.primaryColor") + 1]
        == STREAMLIT_OPTIONS["theme.primaryColor"]
    )


def test_launcher_runs_the_command_and_passes_the_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[list[str]] = []

    def fake_call(command: list[str]) -> int:
        seen.append(command)
        return 3

    monkeypatch.setattr(subprocess, "call", fake_call)
    assert launcher.main(["--server.headless", "true"]) == 3
    assert seen[0][-2:] == ["--server.headless", "true"]


def test_launcher_explains_how_to_install_streamlit_when_it_is_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    assert launcher.main([]) == 1
    assert "pip install" in capsys.readouterr().err


# -- stylesheet ----------------------------------------------------------------------------------


def test_stylesheet_resolves_every_token_and_embeds_the_font() -> None:
    css = stylesheet()
    assert css.startswith("<style>")
    assert css.count("data:font/woff2;base64,") == 1
    # No unresolved $token may be left behind (font data is base64, which never contains "$").
    assert "$" not in css
    assert theme.ACCENT in css


def test_stylesheet_makes_no_external_requests() -> None:
    assert "http://" not in stylesheet()
    assert "https://" not in stylesheet()


def test_rgba_converts_hex_colours() -> None:
    assert theme.rgba("#2BB3A3", 0.5) == "rgba(43,179,163,0.5)"


def test_html_table_escapes_cells_and_headers() -> None:
    out = formatting.html_table(pd.DataFrame({"<b>": ["<script>x</script>"], "n": [1.5]}))
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "&lt;b&gt;" in out
    assert out.count("<tr>") == 2
