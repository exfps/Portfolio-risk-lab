"""Excel export: numbers stay numbers, so the workbook can be used for further calculation."""

from __future__ import annotations

import io
import math
from collections.abc import Iterable
from typing import Any

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from portfolio_risk.analysis import AnalysisResult
from portfolio_risk.report import excel_sections
from portfolio_risk.report.excel_common import (
    DATE,
    PCT,
    PCT1,
    RATIO,
    header,
    number,
    paragraph,
    title,
    widths,
)
from portfolio_risk.report.inputs import ReportInputs, resolve
from portfolio_risk.report.look import make_look, use
from portfolio_risk.report.meta import ASSUMPTIONS, DISCLAIMER, ReportMeta
from portfolio_risk.report.style import ReportStyle
from portfolio_risk.ui import formatting


def _summary(wb: Workbook, result: AnalysisResult, meta: ReportMeta, accent: str) -> None:
    ws = wb.active
    if ws is None:  # a new Workbook always has an active sheet; this satisfies the type checker
        raise RuntimeError("Workbook has no active sheet.")
    ws.title = "Summary"
    title(ws, meta.title, accent)
    facts = [
        ("Period", f"{formatting.day(result.start)} to {formatting.day(result.end)}"),
        ("Observations", result.observations),
        ("Periods per year", result.config.periods_per_year),
        ("Data source", meta.source_note),
        ("Generated (UTC)", meta.generated.strftime("%Y-%m-%d %H:%M")),
        ("Software", f"Portfolio Risk Lab {meta.version}"),
    ]
    for i, (label, value) in enumerate(facts, start=3):
        ws.cell(row=i, column=1, value=label).font = Font(color="666666")
        ws.cell(row=i, column=2, value=value).alignment = Alignment(horizontal="left")
    row = 3 + len(facts) + 1
    header(ws, row, ["Metric", "Value"], accent)
    p = result.performance
    metrics: list[tuple[str, float, str]] = [
        ("Total return", p.total_return, PCT),
        ("Annualised return", p.cagr, PCT),
        ("Annualised volatility", p.annualised_volatility, PCT),
        ("Sharpe ratio", p.sharpe_ratio, RATIO),
        ("Sortino ratio", p.sortino_ratio, RATIO),
        ("Maximum drawdown", p.drawdown.max_drawdown, PCT),
        ("Concentration (HHI)", result.hhi, "0.000"),
        ("Effective number of positions", result.effective_positions, RATIO),
    ]
    for i, (label, value, fmt) in enumerate(metrics, start=row + 1):
        ws.cell(row=i, column=1, value=label)
        cell = ws.cell(row=i, column=2, value=number(value))
        cell.number_format = fmt
    row += len(metrics) + 2
    ws.cell(row=row, column=1, value="Assumptions").font = Font(bold=True, color=accent)
    rf = f"Risk-free rate {result.config.risk_free_annual:.2%} annual"
    rf += (
        f" (source: {meta.risk_free_source})."
        if meta.risk_free_source
        else " (source not recorded)."
    )
    for i, text in enumerate([*ASSUMPTIONS, rf], start=row + 1):
        paragraph(ws, i, text)
    note_row = row + len(ASSUMPTIONS) + 3
    paragraph(ws, note_row, DISCLAIMER, font=Font(italic=True, color="666666"))
    for text in result.warnings:
        note_row += 1
        paragraph(ws, note_row, f"Warning: {text}", font=Font(color="B5523B"))
    widths(ws, {"A": 34, "B": 30, "C": 14, "D": 14, "E": 14, "F": 14})


def _series_sheet(wb: Workbook, result: AnalysisResult, accent: str) -> Worksheet:
    ws = wb.create_sheet("Series")
    header(ws, 1, ["Date", "Portfolio return", "Wealth index (start = 1)", "Drawdown"], accent)
    returns = result.portfolio_returns.reindex(result.wealth.index)
    for i, (when, wealth) in enumerate(result.wealth.items(), start=2):
        ws.cell(row=i, column=1, value=pd.Timestamp(when).to_pydatetime()).number_format = DATE  # type: ignore[arg-type]
        r = returns.get(when)
        ws.cell(row=i, column=2, value=None if r is None else number(float(r))).number_format = PCT
        ws.cell(row=i, column=3, value=number(float(wealth))).number_format = "0.0000"
        ws.cell(
            row=i, column=4, value=number(float(result.drawdowns.get(when, math.nan)))
        ).number_format = PCT
    ws.freeze_panes = "A2"
    widths(ws, {"A": 12, "B": 18, "C": 26, "D": 12})
    return ws


def _line(
    series: Worksheet,
    column: int,
    rows: int,
    title: str,
    *,
    accent: str,
    bounds: tuple[float, float],
) -> LineChart:
    chart = LineChart()
    chart.title = title
    chart.height, chart.width = 7.5, 22
    chart.legend = None
    chart.add_data(
        Reference(series, min_col=column, min_row=1, max_row=rows), titles_from_data=True
    )
    chart.set_categories(Reference(series, min_col=1, min_row=2, max_row=rows))
    chart.series[0].graphicalProperties.line.solidFill = accent.lstrip("#")
    chart.series[0].graphicalProperties.line.width = 15000
    chart.series[0].smooth = False
    chart.x_axis.number_format = "yyyy-mm"
    chart.x_axis.tickLblPos = "low"
    chart.x_axis.tickLblSkip = max(1, (rows - 1) // 6)
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    chart.y_axis.scaling.min, chart.y_axis.scaling.max = bounds
    return chart


def _performance(wb: Workbook, result: AnalysisResult, series: Worksheet, accent: str) -> None:
    ws = wb.create_sheet("Performance", 1)
    title(ws, "Performance", accent)
    header(ws, 3, ["Measure", "Value"], accent)
    for i, (label, value) in enumerate(
        formatting.drawdown_table(result).itertuples(index=False), start=4
    ):
        ws.cell(row=i, column=1, value=label)
        ws.cell(row=i, column=2, value=value).alignment = Alignment(horizontal="right")
    rows = result.wealth.shape[0] + 1
    wealth = result.wealth.dropna()
    ws.add_chart(
        _line(
            series,
            3,
            rows,
            "Wealth index",
            accent=accent,
            bounds=(math.floor(wealth.min() * 20) / 20, math.ceil(wealth.max() * 20) / 20),
        ),
        "A12",
    )
    depth = float(result.drawdowns.min())
    ws.add_chart(
        _line(
            series, 4, rows, "Drawdown", accent=accent, bounds=(math.floor(depth * 20) / 20, 0.0)
        ),
        "A28",
    )
    widths(ws, {"A": 30, "B": 20})


def _risk(wb: Workbook, result: AnalysisResult, accent: str) -> None:
    ws = wb.create_sheet("Risk")
    title(ws, "Value at Risk and exposure", accent)
    header(
        ws,
        3,
        ["Confidence", "Historical VaR", "Historical CVaR", "Parametric VaR", "Parametric CVaR"],
        accent,
    )
    for i, e in enumerate(result.var, start=4):
        ws.cell(row=i, column=1, value=e.confidence).number_format = "0.0%"
        for col, value in enumerate(
            (e.historical_var, e.historical_cvar, e.parametric_var, e.parametric_cvar), start=2
        ):
            ws.cell(row=i, column=col, value=number(value)).number_format = PCT
    top = 4 + len(result.var) + 1
    ws.cell(row=top, column=1, value="One-period losses, shown as positive numbers.").font = Font(
        italic=True, color="666666"
    )
    start = top + 2
    header(
        ws,
        start,
        ["Asset", "Weight", "Return (ann.)", "Volatility (ann.)", "Max drawdown", "Risk share"],
        accent,
    )
    table = result.asset_table
    for i, (name, row) in enumerate(table.iterrows(), start=start + 1):
        ws.cell(row=i, column=1, value=str(name))
        for col, (key, fmt) in enumerate(
            [
                ("weight", PCT1),
                ("annualised_return", PCT),
                ("annualised_volatility", PCT),
                ("max_drawdown", PCT),
                ("risk_contribution", PCT1),
            ],
            start=2,
        ):
            ws.cell(row=i, column=col, value=number(float(row[key]))).number_format = fmt
    end = start + len(table)
    chart = BarChart()
    chart.type = "bar"
    chart.title = "Risk share by asset"
    chart.legend = None
    chart.height, chart.width = 7.5, 16
    chart.add_data(Reference(ws, min_col=6, min_row=start, max_row=end), titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=1, min_row=start + 1, max_row=end))
    chart.series[0].graphicalProperties.solidFill = accent.lstrip("#")
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    ws.add_chart(chart, f"A{end + 3}")
    widths(ws, {"A": 22, "B": 16, "C": 16, "D": 18, "E": 16, "F": 14})


def _correlation(wb: Workbook, result: AnalysisResult, accent: str) -> None:
    ws = wb.create_sheet("Correlation")
    title(ws, "Correlation of asset returns", accent)
    matrix = result.correlation
    header(ws, 3, ["", *[str(c) for c in matrix.columns]], accent)
    for i, (name, row) in enumerate(matrix.iterrows(), start=4):
        ws.cell(row=i, column=1, value=str(name)).font = Font(bold=True)
        for j, value in enumerate(row, start=2):
            ws.cell(row=i, column=j, value=number(float(value))).number_format = RATIO
    last = get_column_letter(1 + matrix.shape[1])
    ws.conditional_formatting.add(
        f"B4:{last}{3 + matrix.shape[0]}",
        ColorScaleRule(
            start_type="num",
            start_value=-1,
            start_color="B5523B",
            mid_type="num",
            mid_value=0,
            mid_color="FFFFFF",
            end_type="num",
            end_value=1,
            end_color=accent.lstrip("#"),
        ),
    )
    widths(ws, {"A": 18, **{get_column_letter(c): 14 for c in range(2, 2 + matrix.shape[1])}})


def _benchmark(wb: Workbook, result: AnalysisResult, accent: str) -> None:
    stats = result.benchmark
    if stats is None:
        return
    ws = wb.create_sheet("Benchmark")
    title(ws, "Portfolio versus benchmark", accent)
    header(ws, 3, ["Measure", "Value"], accent)
    rows: list[tuple[str, float, str]] = [
        ("Beta", stats.beta, RATIO),
        ("Alpha (annualised)", stats.alpha_annualised, PCT),
        ("Correlation", stats.correlation, RATIO),
        ("R-squared", stats.r_squared, RATIO),
        ("Active return (annualised)", stats.active_return_annualised, PCT),
        ("Tracking error", stats.tracking_error, PCT),
        ("Information ratio", stats.information_ratio, RATIO),
    ]
    for i, (label, value, fmt) in enumerate(rows, start=4):
        ws.cell(row=i, column=1, value=label)
        ws.cell(row=i, column=2, value=number(value)).number_format = fmt
    widths(ws, {"A": 30, "B": 14})


def _inputs(wb: Workbook, result: AnalysisResult, accent: str) -> None:
    ws = wb.create_sheet("Inputs")
    title(ws, "Inputs used", accent)
    header(ws, 3, ["Asset", "Weight"], accent)
    for i, (name, weight) in enumerate(result.weights.items(), start=4):
        ws.cell(row=i, column=1, value=str(name))
        ws.cell(row=i, column=2, value=float(weight)).number_format = "0.0000"
    row = 4 + len(result.weights) + 1
    config: list[tuple[str, Any]] = [
        ("Periods per year", result.config.periods_per_year),
        ("Risk-free rate (annual)", result.config.risk_free_annual),
        ("Minimum acceptable return (annual)", result.config.mar_annual),
        ("VaR confidence levels", ", ".join(f"{c:.1%}" for c in result.config.confidence_levels)),
    ]
    for i, (label, value) in enumerate(config, start=row):
        ws.cell(row=i, column=1, value=label)
        ws.cell(row=i, column=2, value=value).alignment = Alignment(horizontal="right")
    widths(ws, {"A": 36, "B": 24})


def build_workbook(
    result: AnalysisResult,
    meta: ReportMeta | None = None,
    inputs: ReportInputs | None = None,
    sections: Iterable[str] | None = None,
    style: ReportStyle | None = None,
) -> bytes:
    """Return the ``.xlsx`` file as bytes. ``sections`` and ``style`` work as for the PDF.

    From a style, the Excel file takes the accent, series colours, line width and line style.

    The Summary, Series and Inputs sheets are always present: they carry the data every other
    sheet refers to. The other sheets follow the chosen sections.
    """
    meta = meta or ReportMeta()
    inputs = inputs or ReportInputs()
    chosen = set(resolve(sections, result, inputs))
    active = make_look(style or ReportStyle(), meta.accent)
    accent = active.style.accent or meta.accent
    accent = accent.lstrip("#")
    with use(active):
        return _build(result, meta, inputs, chosen, accent)


def _neutralise_formulas(wb: Workbook) -> None:
    """Store text that starts with ``=`` as text, never as a formula.

    openpyxl treats any string beginning with ``=`` as a formula. Asset names come from the
    person's CSV (or a screenshot read by a model), so a name such as ``=HYPERLINK(...)`` would
    otherwise run when the workbook is opened. This report writes no formulas of its own.
    """
    for sheet in wb.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if cell.data_type == "f":
                    cell.data_type = "s"


def _build(
    result: AnalysisResult,
    meta: ReportMeta,
    inputs: ReportInputs,
    chosen: set[str],
    accent: str,
) -> bytes:
    wb = Workbook()
    _summary(wb, result, meta, accent)
    series = _series_sheet(wb, result, accent)
    if "performance" in chosen:
        _performance(wb, result, series, accent)
    if "risk" in chosen:
        _risk(wb, result, accent)
    if "correlation" in chosen:
        _correlation(wb, result, accent)
    if "benchmark" in chosen:
        _benchmark(wb, result, accent)
    if "tearsheet" in chosen:
        excel_sections.tearsheet(wb, result, inputs, accent)
    if "comparison" in chosen:
        excel_sections.comparison(wb, inputs, accent)
    if "monte_carlo" in chosen:
        excel_sections.monte_carlo(wb, inputs, accent)
    if "alpha_decay" in chosen:
        excel_sections.alpha_decay_sheet(wb, result, inputs, accent)
    _inputs(wb, result, accent)
    wb.move_sheet("Series", offset=len(wb.sheetnames))
    for sheet in wb.worksheets:
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
    wb.properties.creator = f"Portfolio Risk Lab {meta.version}"
    wb.properties.title = meta.title
    _neutralise_formulas(wb)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
