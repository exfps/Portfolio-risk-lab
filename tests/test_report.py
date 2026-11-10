"""PDF and Excel exports: contents are checked against the numbers in the AnalysisResult."""

from __future__ import annotations

import datetime as dt
import io
import math

import pytest
from openpyxl import load_workbook
from pypdf import PdfReader

from portfolio_risk import AnalysisConfig, AnalysisResult, analyse
from portfolio_risk.report import ReportMeta, excel
from portfolio_risk.report.excel import build_workbook
from portfolio_risk.report.pdf import build_pdf
from portfolio_risk.sample_data import BENCHMARK, generate_sample_prices, sample_weights
from portfolio_risk.ui import formatting

META = ReportMeta(
    source_note="Synthetic sample data",
    risk_free_source="3-month SAIBOR",
    generated=dt.datetime(2026, 11, 8, 12, 0, tzinfo=dt.UTC),
)


@pytest.fixture(scope="module")
def result() -> AnalysisResult:
    return analyse(generate_sample_prices(), sample_weights(), AnalysisConfig(), BENCHMARK)


@pytest.fixture(scope="module")
def no_benchmark() -> AnalysisResult:
    prices = generate_sample_prices().drop(columns=[BENCHMARK])
    return analyse(prices, sample_weights(), AnalysisConfig())


def pdf_text(data: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)


def test_pdf_is_a_valid_multi_page_document(result: AnalysisResult) -> None:
    data = build_pdf(result, META)
    assert data.startswith(b"%PDF")
    reader = PdfReader(io.BytesIO(data))
    assert len(reader.pages) >= 2
    assert reader.metadata is not None
    assert reader.metadata.title == META.title


def test_pdf_shows_the_headline_numbers_and_context(result: AnalysisResult) -> None:
    text = pdf_text(build_pdf(result, META))
    for label, value in formatting.headline_metrics(result):
        assert label in text
        assert value in text
    assert "Synthetic sample data" in text
    assert "3-month SAIBOR" in text
    assert "not investment advice" in text
    assert "Portfolio versus benchmark" in text
    for name in result.weights.index:
        assert str(name) in text


def test_pdf_omits_benchmark_section_without_a_benchmark(no_benchmark: AnalysisResult) -> None:
    assert "Portfolio versus benchmark" not in pdf_text(build_pdf(no_benchmark, META))


def test_pdf_escapes_markup_in_free_text(result: AnalysisResult) -> None:
    meta = ReportMeta(source_note="<b>bold</b> & <script>", title="A & B <i>")
    text = pdf_text(build_pdf(result, meta))
    assert "<b>bold</b> & <script>" in text
    assert "A & B <i>" in text


def test_workbook_sheets_and_values_match_the_result(result: AnalysisResult) -> None:
    book = load_workbook(io.BytesIO(build_workbook(result, META)))
    assert book.sheetnames == [
        "Summary", "Performance", "Risk", "Correlation", "Benchmark", "Inputs", "Series",
    ]  # fmt: skip
    summary = {row[0].value: row[1].value for row in book["Summary"].iter_rows() if row[0].value}
    assert summary["Total return"] == pytest.approx(result.performance.total_return)
    assert summary["Sharpe ratio"] == pytest.approx(result.performance.sharpe_ratio)
    assert summary["Maximum drawdown"] == pytest.approx(result.performance.drawdown.max_drawdown)
    assert summary["Data source"] == "Synthetic sample data"
    assert book["Summary"]["B8"].number_format == "0.00%" or any(
        cell.number_format == "0.00%" for row in book["Summary"].iter_rows() for cell in row
    )


def test_workbook_series_has_one_row_per_date_and_real_numbers(result: AnalysisResult) -> None:
    sheet = load_workbook(io.BytesIO(build_workbook(result, META)))["Series"]
    assert sheet.max_row == len(result.wealth) + 1
    assert sheet["C2"].value == pytest.approx(1.0)
    assert sheet["C3"].value == pytest.approx(float(result.wealth.iloc[1]))
    assert all(isinstance(sheet.cell(row=r, column=3).value, int | float) for r in (2, 50, 300))


def test_workbook_risk_sheet_matches_var_and_assets(result: AnalysisResult) -> None:
    sheet = load_workbook(io.BytesIO(build_workbook(result, META)))["Risk"]
    first = result.var[0]
    assert sheet["A4"].value == pytest.approx(first.confidence)
    assert sheet["B4"].value == pytest.approx(first.historical_var)
    names = [sheet.cell(row=r, column=1).value for r in range(1, sheet.max_row + 1)]
    for asset in result.asset_table.index:
        assert str(asset) in names


def test_workbook_correlation_is_symmetric_with_unit_diagonal(result: AnalysisResult) -> None:
    sheet = load_workbook(io.BytesIO(build_workbook(result, META)))["Correlation"]
    n = result.correlation.shape[0]
    for i in range(n):
        assert sheet.cell(row=4 + i, column=2 + i).value == pytest.approx(1.0)
        for j in range(n):
            assert sheet.cell(row=4 + i, column=2 + j).value == pytest.approx(
                sheet.cell(row=4 + j, column=2 + i).value
            )


def test_workbook_without_benchmark_has_no_benchmark_sheet(no_benchmark: AnalysisResult) -> None:
    assert "Benchmark" not in load_workbook(io.BytesIO(build_workbook(no_benchmark))).sheetnames


def test_workbook_leaves_non_finite_values_empty(result: AnalysisResult) -> None:
    assert excel._number(math.nan) is None
    assert excel._number(math.inf) is None
    assert excel._number(1.5) == 1.5


def test_report_meta_rejects_bad_accent() -> None:
    with pytest.raises(ValueError, match="#RRGGBB"):
        ReportMeta(accent="teal")
    with pytest.raises(ValueError, match="#RRGGBB"):
        ReportMeta(accent="#12345")
