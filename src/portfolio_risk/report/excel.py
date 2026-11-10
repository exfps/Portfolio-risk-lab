"""Excel export: numbers stay numbers, so the workbook can be used for further calculation."""

from __future__ import annotations

import io
import math
from typing import Any

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from portfolio_risk.analysis import AnalysisResult
from portfolio_risk.report.meta import ASSUMPTIONS, DISCLAIMER, ReportMeta
from portfolio_risk.ui import formatting

PCT = "0.00%"
PCT1 = "0.0%"
RATIO = "0.00"
DATE = "yyyy-mm-dd"


def _number(value: float) -> float | None:
    """Excel cannot store NaN or infinity; leave the cell empty instead."""
    return float(value) if math.isfinite(value) else None


def _header(ws: Worksheet, row: int, labels: list[str], accent: str) -> None:
    side = Side(style="thin", color=accent)
    for col, label in enumerate(labels, start=1):
        cell = ws.cell(row=row, column=col, value=label)
        cell.font = Font(bold=True, color=accent)
        cell.border = Border(bottom=side)
        cell.alignment = Alignment(horizontal="left" if col == 1 else "right")


def _title(ws: Worksheet, text: str, accent: str) -> None:
    ws["A1"] = text
    ws["A1"].font = Font(size=14, bold=True, color=accent)


def _paragraph(
    ws: Worksheet, row: int, text: str, *, font: Font | None = None, last: str = "F"
) -> None:
    """Long text across columns A to ``last``, wrapped, so it prints and reads without scrolling."""
    ws.merge_cells(f"A{row}:{last}{row}")
    cell = ws.cell(row=row, column=1, value=text)
    cell.alignment = Alignment(wrap_text=True, vertical="top")
    if font is not None:
        cell.font = font
    ws.row_dimensions[row].height = 15 * max(1, math.ceil(len(text) / 110))


def _widths(ws: Worksheet, widths: dict[str, float]) -> None:
    for letter, width in widths.items():
        ws.column_dimensions[letter].width = width


def _summary(wb: Workbook, result: AnalysisResult, meta: ReportMeta, accent: str) -> None:
    ws = wb.active
    assert ws is not None
    ws.title = "Summary"
    _title(ws, meta.title, accent)
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
    _header(ws, row, ["Metric", "Value"], accent)
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
        cell = ws.cell(row=i, column=2, value=_number(value))
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
        _paragraph(ws, i, text)
    note_row = row + len(ASSUMPTIONS) + 3
    _paragraph(ws, note_row, DISCLAIMER, font=Font(italic=True, color="666666"))
    for text in result.warnings:
        note_row += 1
        _paragraph(ws, note_row, f"Warning: {text}", font=Font(color="B5523B"))
    _widths(ws, {"A": 34, "B": 30, "C": 14, "D": 14, "E": 14, "F": 14})


def _series_sheet(wb: Workbook, result: AnalysisResult, accent: str) -> Worksheet:
    ws = wb.create_sheet("Series")
    _header(ws, 1, ["Date", "Portfolio return", "Wealth index (start = 1)", "Drawdown"], accent)
    returns = result.portfolio_returns.reindex(result.wealth.index)
    for i, (when, wealth) in enumerate(result.wealth.items(), start=2):
        ws.cell(row=i, column=1, value=pd.Timestamp(when).to_pydatetime()).number_format = DATE  # type: ignore[arg-type]
        r = returns.get(when)
        ws.cell(row=i, column=2, value=None if r is None else _number(float(r))).number_format = PCT
        ws.cell(row=i, column=3, value=_number(float(wealth))).number_format = "0.0000"
        ws.cell(
            row=i, column=4, value=_number(float(result.drawdowns.get(when, math.nan)))
        ).number_format = PCT
    ws.freeze_panes = "A2"
    _widths(ws, {"A": 12, "B": 18, "C": 26, "D": 12})
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
    _title(ws, "Performance", accent)
    _header(ws, 3, ["Measure", "Value"], accent)
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
    _widths(ws, {"A": 30, "B": 20})


def _risk(wb: Workbook, result: AnalysisResult, accent: str) -> None:
    ws = wb.create_sheet("Risk")
    _title(ws, "Value at Risk and exposure", accent)
    _header(
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
            ws.cell(row=i, column=col, value=_number(value)).number_format = PCT
    top = 4 + len(result.var) + 1
    ws.cell(row=top, column=1, value="One-period losses, shown as positive numbers.").font = Font(
        italic=True, color="666666"
    )
    start = top + 2
    _header(
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
            ws.cell(row=i, column=col, value=_number(float(row[key]))).number_format = fmt
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
    _widths(ws, {"A": 22, "B": 16, "C": 16, "D": 18, "E": 16, "F": 14})


def _correlation(wb: Workbook, result: AnalysisResult, accent: str) -> None:
    ws = wb.create_sheet("Correlation")
    _title(ws, "Correlation of asset returns", accent)
    matrix = result.correlation
    _header(ws, 3, ["", *[str(c) for c in matrix.columns]], accent)
    for i, (name, row) in enumerate(matrix.iterrows(), start=4):
        ws.cell(row=i, column=1, value=str(name)).font = Font(bold=True)
        for j, value in enumerate(row, start=2):
            ws.cell(row=i, column=j, value=_number(float(value))).number_format = RATIO
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
    _widths(ws, {"A": 18, **{get_column_letter(c): 14 for c in range(2, 2 + matrix.shape[1])}})


def _benchmark(wb: Workbook, result: AnalysisResult, accent: str) -> None:
    stats = result.benchmark
    if stats is None:
        return
    ws = wb.create_sheet("Benchmark")
    _title(ws, "Portfolio versus benchmark", accent)
    _header(ws, 3, ["Measure", "Value"], accent)
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
        ws.cell(row=i, column=2, value=_number(value)).number_format = fmt
    _widths(ws, {"A": 30, "B": 14})


def _inputs(wb: Workbook, result: AnalysisResult, accent: str) -> None:
    ws = wb.create_sheet("Inputs")
    _title(ws, "Inputs used", accent)
    _header(ws, 3, ["Asset", "Weight"], accent)
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
    _widths(ws, {"A": 36, "B": 24})


def build_workbook(result: AnalysisResult, meta: ReportMeta | None = None) -> bytes:
    """Return the ``.xlsx`` file as bytes."""
    meta = meta or ReportMeta()
    accent = meta.accent.lstrip("#")
    wb = Workbook()
    _summary(wb, result, meta, accent)
    series = _series_sheet(wb, result, accent)
    _performance(wb, result, series, accent)
    _risk(wb, result, accent)
    _correlation(wb, result, accent)
    _benchmark(wb, result, accent)
    _inputs(wb, result, accent)
    wb.move_sheet("Series", offset=len(wb.sheetnames))
    for sheet in wb.worksheets:
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
    wb.properties.creator = f"Portfolio Risk Lab {meta.version}"
    wb.properties.title = meta.title
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
