"""Selectable report sections: what is available, what is printed, and the export panel."""

from __future__ import annotations

import io

import pandas as pd
import pytest
from openpyxl import load_workbook
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

from portfolio_risk import AnalysisConfig, AnalysisResult, analyse
from portfolio_risk.comparison import compare
from portfolio_risk.report import ReportMeta
from portfolio_risk.report.excel import build_workbook
from portfolio_risk.report.inputs import KEYS, ReportInputs, resolve, unavailable
from portfolio_risk.report.pdf import build_pdf
from portfolio_risk.returns import simple_returns
from portfolio_risk.sample_data import BENCHMARK, generate_sample_prices, sample_weights
from portfolio_risk.simulation import SimulationConfig, make_model, run_simulation
from portfolio_risk.ui.tearsheet_tables import named_returns

META = ReportMeta(source_note="Synthetic sample data")


@pytest.fixture(scope="module")
def prices() -> pd.DataFrame:
    return generate_sample_prices()


@pytest.fixture(scope="module")
def result(prices: pd.DataFrame) -> AnalysisResult:
    return analyse(prices, sample_weights(), AnalysisConfig(), BENCHMARK)


@pytest.fixture(scope="module")
def full(result: AnalysisResult, prices: pd.DataFrame) -> ReportInputs:
    weights = sample_weights()
    other = pd.Series({"SYN_GOVT": 0.6, "SYN_CORP": 0.4})
    comparison = compare(prices, {"Current": weights, "Defensive": other}, result.config, BENCHMARK)
    config = SimulationConfig(n_paths=500, horizon_years=2, seed=1)
    sims = [
        run_simulation(simple_returns(prices[list(weights.index)]), weights, make_model(m), config)
        for m in ("gaussian", "bootstrap")
    ]
    return ReportInputs(
        tearsheet=named_returns(result, prices, BENCHMARK, ["SYN_EQ_US"]),
        comparison=comparison,
        simulation=sims,
        benchmark=BENCHMARK,
    )


def pdf_text(data: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages)


def test_without_extra_material_only_the_base_sections_are_available(
    result: AnalysisResult,
) -> None:
    missing = unavailable(result)
    assert set(missing) == {"tearsheet", "comparison", "monte_carlo"}
    assert "Run a simulation" in missing["monte_carlo"]
    assert resolve(None, result) == [k for k in KEYS if k not in missing]


def test_a_benchmark_less_result_loses_the_benchmark_section(prices: pd.DataFrame) -> None:
    bare = analyse(prices.drop(columns=[BENCHMARK]), sample_weights())
    assert "benchmark" in unavailable(bare)


def test_everything_is_available_with_full_inputs(
    result: AnalysisResult, full: ReportInputs
) -> None:
    assert unavailable(result, full) == {}
    assert resolve(None, result, full) == list(KEYS)


def test_selection_keeps_report_order_and_drops_unavailable_sections(
    result: AnalysisResult,
) -> None:
    assert resolve(["risk", "summary", "monte_carlo"], result) == ["summary", "risk"]


def test_an_unknown_section_is_an_error(result: AnalysisResult) -> None:
    with pytest.raises(ValueError, match="nonsense"):
        resolve(["nonsense"], result)


def test_the_pdf_contains_each_extra_section_only_when_selected(
    result: AnalysisResult, full: ReportInputs
) -> None:
    everything = pdf_text(build_pdf(result, META, full))
    for heading in (
        "Classic tearsheet",
        "Portfolio comparison",
        "Monte Carlo projection",
        "Alpha decay",
    ):
        assert heading in everything
    trimmed = pdf_text(build_pdf(result, META, full, ["summary", "comparison"]))
    assert "Portfolio comparison" in trimmed
    for heading in ("Monte Carlo projection", "Alpha decay", "Classic tearsheet"):
        assert heading not in trimmed
    assert "not investment advice" in trimmed  # the disclaimer is never dropped


def test_the_pdf_figures_for_the_comparison_match_the_computation(
    result: AnalysisResult, full: ReportInputs
) -> None:
    assert full.comparison is not None
    text = pdf_text(build_pdf(result, META, full, ["comparison"]))
    total = full.comparison.results["Defensive"].performance.total_return
    assert f"{total:.1%}" in text  # the tables show one decimal


def test_the_workbook_has_a_sheet_per_selected_section(
    result: AnalysisResult, full: ReportInputs
) -> None:
    book = load_workbook(io.BytesIO(build_workbook(result, META, full)))
    for sheet in ("Comparison", "Monte Carlo", "Alpha decay", "Tearsheet"):
        assert sheet in book.sheetnames
    small = load_workbook(io.BytesIO(build_workbook(result, META, full, ["summary", "risk"])))
    assert "Monte Carlo" not in small.sheetnames
    assert "Risk" in small.sheetnames


def test_selecting_nothing_still_gives_a_valid_report(result: AnalysisResult) -> None:
    assert build_pdf(result, META, None, []).startswith(b"%PDF")


def _panel_app() -> None:
    # AppTest.from_function runs only this function's source, so it imports for itself.
    from portfolio_risk.ui import app  # noqa: PLC0415

    app.main()


def test_the_export_panel_lists_unavailable_sections_with_reasons() -> None:
    app = AppTest.from_function(_panel_app, default_timeout=90).run()
    assert not app.exception
    captions = " ".join(c.value for c in app.caption)
    assert "Not available: Monte Carlo projection" in captions
    assert "Not available: Portfolio comparison" in captions
    picker = next(m for m in app.multiselect if m.label == "Sections to include")
    assert "summary" in picker.value or "Summary and headline figures" in picker.value


def _state_app() -> None:
    import pandas as pd  # noqa: PLC0415
    import streamlit as st  # noqa: PLC0415

    from portfolio_risk.ui import report_state  # noqa: PLC0415

    prices = pd.DataFrame({"A": [1.0, 2.0, 3.0]}, index=pd.bdate_range("2024-01-01", periods=3))
    same = report_state.signature(prices, pd.Series({"A": 1.0}))
    other = report_state.signature(prices, pd.Series({"A": 0.5, "B": 0.5}))
    report_state.remember("k", same, "payload")
    st.session_state["same"] = report_state.recall("k", same)
    st.session_state["changed_weights"] = report_state.recall("k", other)
    report_state.forget("k")
    st.session_state["after_forget"] = report_state.recall("k", same)


def test_stored_report_material_is_ignored_when_the_portfolio_changes() -> None:
    app = AppTest.from_function(_state_app).run()
    assert not app.exception
    assert app.session_state["same"] == "payload"
    assert app.session_state["changed_weights"] is None
    assert app.session_state["after_forget"] is None


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("Q4 review", "Q4 review"),
        ("  Q4   review.pdf ", "Q4 review"),
        ("report.XLSX", "report"),
        ('a/b\\c:d*e?f"g<h>i|j', "abcdefghij"),
        ("...", "fallback"),
        ("", "fallback"),
        ("con", "con_"),
        ("NUL.txt", "NUL.txt_"),
        ("v1.2 final", "v1.2 final"),
    ],
)
def test_safe_stem(typed: str, expected: str) -> None:
    from portfolio_risk.report.filename import safe_stem  # noqa: PLC0415

    assert safe_stem(typed, "fallback") == expected


def test_safe_stem_is_cut_to_the_maximum_length() -> None:
    from portfolio_risk.report.filename import MAX_LENGTH, safe_stem  # noqa: PLC0415

    assert len(safe_stem("x" * 500, "d")) == MAX_LENGTH
