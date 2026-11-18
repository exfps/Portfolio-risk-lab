"""Excel sheets for the tearsheet, comparison, Monte Carlo and alpha decay sections."""

from __future__ import annotations

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.worksheet import Worksheet

from portfolio_risk.analysis import AnalysisResult
from portfolio_risk.decay import alpha_decay
from portfolio_risk.drawdown import drawdown_periods
from portfolio_risk.report.excel_common import DATE, PCT, PCT1, RATIO, header, number, title, widths
from portfolio_risk.report.inputs import ReportInputs
from portfolio_risk.report.look import look
from portfolio_risk.tearsheet import (
    RELATIVE_ROWS,
    ROWS,
    calendar_years,
    monthly_table,
    tearsheet_table,
)
from portfolio_risk.ui import formatting, simulation_tables

FORMATS = {"pct": PCT1, "pct2": PCT, "ratio": RATIO, "int": "0"}
LABELS = {r.key: (r.label, FORMATS[r.fmt]) for r in (*ROWS, *RELATIVE_ROWS)}


def _put_statistics(ws: Worksheet, top: int, table: pd.DataFrame, accent: str) -> int:
    """Numeric statistics (rows) by series (columns); returns the next free row."""
    header(ws, top, ["Statistic", *map(str, table.columns)], accent)
    for i, key in enumerate(table.index, start=top + 1):
        label, fmt = LABELS[str(key)]
        ws.cell(row=i, column=1, value=label)
        for j, value in enumerate(table.loc[key].to_numpy(dtype=float), start=2):
            ws.cell(row=i, column=j, value=number(float(value))).number_format = fmt
    return top + len(table) + 2


def _put_frame(
    ws: Worksheet, top: int, frame: pd.DataFrame, accent: str, *, fmt: str, first: str
) -> int:
    """A numeric frame with its index in the first column."""
    header(ws, top, [first, *map(str, frame.columns)], accent)
    for i, (label, row) in enumerate(frame.iterrows(), start=top + 1):
        ws.cell(row=i, column=1, value=label if isinstance(label, int) else str(label))
        for j, value in enumerate(row.to_numpy(dtype=float), start=2):
            ws.cell(row=i, column=j, value=number(float(value))).number_format = fmt
    return top + len(frame) + 2


def _section_title(ws: Worksheet, row: int, text: str, accent: str) -> None:
    ws.cell(row=row, column=1, value=text).font = Font(bold=True, color=accent, size=11)


_EXCEL_DASH = {"solid": "solid", "dashed": "dash", "dotted": "sysDot", "dash-dot": "dashDot"}


def _line_chart(
    ws: Worksheet,
    anchor: str,
    name: str,
    *,
    rows: tuple[int, int],
    columns: int,
    accent: str,
) -> None:
    first_row, last_row = rows
    chart = LineChart()
    chart.title = name
    chart.height, chart.width = 8, 22
    data = Reference(ws, min_col=2, max_col=1 + columns, min_row=first_row, max_row=last_row)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=1, min_row=first_row + 1, max_row=last_row))
    active = look()
    for i, series in enumerate(chart.series):
        label = str(ws.cell(row=first_row, column=2 + i).value)
        line = series.graphicalProperties.line
        series.smooth = False
        line.width = round(active.width(label, i) * 12700)  # points to EMU
        line.dashStyle = _EXCEL_DASH[active.dash_name(label, i)]
        line.solidFill = (
            accent if i == 0 and not active.style.series and label not in active.style.overrides
            else active.colour(label, i).hexval()[2:]
        )  # fmt: skip
    ws.add_chart(chart, anchor)


def _put_series(ws: Worksheet, top: int, frame: pd.DataFrame, accent: str, fmt: str) -> int:
    header(ws, top, ["Date", *map(str, frame.columns)], accent)
    values = frame.to_numpy(dtype=float)
    for i, (stamp, row) in enumerate(
        zip(pd.DatetimeIndex(frame.index), values, strict=True), start=top + 1
    ):
        ws.cell(row=i, column=1, value=stamp.to_pydatetime()).number_format = DATE
        for j, value in enumerate(row, start=2):
            ws.cell(row=i, column=j, value=number(float(value))).number_format = fmt
    return top + len(frame)


def tearsheet(wb: Workbook, result: AnalysisResult, inputs: ReportInputs, accent: str) -> None:
    series = inputs.tearsheet or {}
    cfg = result.config
    table = tearsheet_table(
        series,
        periods_per_year=cfg.periods_per_year,
        rf_per_period=cfg.risk_free_per_period,
        mar_per_period=cfg.mar_per_period,
        benchmark=inputs.benchmark if inputs.benchmark in series else None,
    )
    ws = wb.create_sheet("Tearsheet")
    title(ws, "Classic tearsheet", accent)
    row = _put_statistics(ws, 3, table, accent)
    _section_title(ws, row, "Returns by calendar year", accent)
    row = _put_frame(ws, row + 1, calendar_years(series), accent, fmt=PCT1, first="Year")
    _section_title(ws, row, "Monthly returns (portfolio)", accent)
    row = _put_frame(
        ws, row + 1, monthly_table(result.portfolio_returns), accent, fmt=PCT1, first="Year"
    )
    _section_title(ws, row, "Deepest drawdowns", accent)
    header(ws, row + 1, ["Start", "Trough", "Recovered", "Depth", "Periods"], accent)
    episodes = drawdown_periods(result.wealth, 5)
    start, trough = pd.DatetimeIndex(episodes["start"]), pd.DatetimeIndex(episodes["trough"])
    end = pd.DatetimeIndex(episodes["end"])
    depth = episodes["depth"].to_numpy(dtype=float)
    periods = episodes["periods"].to_numpy(dtype=int)
    recovered = episodes["recovered"].to_numpy(dtype=bool)
    for k in range(len(episodes)):
        i = row + 2 + k
        ws.cell(row=i, column=1, value=start[k].to_pydatetime()).number_format = DATE
        ws.cell(row=i, column=2, value=trough[k].to_pydatetime()).number_format = DATE
        if recovered[k]:
            ws.cell(row=i, column=3, value=end[k].to_pydatetime()).number_format = DATE
        else:
            ws.cell(row=i, column=3, value="Not yet").alignment = Alignment(horizontal="right")
        ws.cell(row=i, column=4, value=float(depth[k])).number_format = PCT
        ws.cell(row=i, column=5, value=int(periods[k]))
    widths(ws, {"A": 40, "B": 16, "C": 16, "D": 16, "E": 16, "F": 16, "G": 16})


def comparison(wb: Workbook, inputs: ReportInputs, accent: str) -> None:
    comp = inputs.comparison
    if comp is None:
        return
    ws = wb.create_sheet("Comparison")
    title(ws, "Portfolio comparison", accent)
    ws["A2"] = (
        f"{formatting.day(comp.start)} to {formatting.day(comp.end)}; "
        f"{comp.observations} observations; constant weights; common dates"
    )
    row = _put_statistics(ws, 4, comp.table, accent)
    _section_title(ws, row, "Holdings (weights)", accent)
    row = _put_frame(ws, row + 1, comp.weights, accent, fmt="0.0%", first="Holding")
    _section_title(ws, row, "Concentration", accent)
    header(ws, row + 1, ["Measure", *map(str, comp.concentration.columns)], accent)
    labels = {"holdings": ("Holdings", "0"), "hhi": ("Concentration (HHI)", "0.000"),
              "effective_positions": ("Effective number of positions", "0.00")}  # fmt: skip
    for i, (key, (label, fmt)) in enumerate(labels.items(), start=row + 2):
        ws.cell(row=i, column=1, value=label)
        for j, value in enumerate(comp.concentration.loc[key].to_numpy(dtype=float), start=2):
            ws.cell(row=i, column=j, value=number(float(value))).number_format = fmt
    row += 6
    _section_title(ws, row, "Correlation of portfolio returns", accent)
    row = _put_frame(ws, row + 1, comp.correlation, accent, fmt=RATIO, first="")
    _section_title(ws, row, "Growth of 1 (chart data below)", accent)
    start = row + 1
    last = _put_series(ws, start, comp.wealth, accent, "0.0000")
    _line_chart(
        ws,
        f"{chr(ord('A') + len(comp.names) + 2)}{start}",
        "Growth of 1",
        rows=(start, last),
        columns=len(comp.names),
        accent=accent,
    )
    widths(ws, {"A": 40, "B": 16, "C": 16, "D": 16, "E": 16, "F": 16, "G": 16})


def monte_carlo(wb: Workbook, inputs: ReportInputs, accent: str) -> None:
    results = list(inputs.simulation or [])
    if not results:
        return
    shown, cfg = results[0], results[0].config
    ws = wb.create_sheet("Monte Carlo")
    title(ws, "Monte Carlo projection", accent)
    ws["A2"] = (
        f"{cfg.n_paths:,} paths; {cfg.horizon_years:g} years, {cfg.frequency}; rebalancing "
        f"{cfg.rebalancing}; seed {cfg.seed}; fitted on {shown.window}. "
        + simulation_tables.DISCLAIMER
    )
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells("A2:F2")
    ws.row_dimensions[2].height = 48
    header(ws, 4, ["Statistic", *[r.model for r in results]], accent)
    rows: list[tuple[str, str, list[float]]] = []

    def add(label: str, fmt: str, pick: str) -> None:
        rows.append((label, fmt, [float(getattr(r.summary, pick)) for r in results]))

    for p in (5, 25, 50, 75, 95):
        rows.append((f"Ending value, {p}th percentile", "#,##0",
                     [r.summary.ending_percentiles[p] for r in results]))  # fmt: skip
    add("Mean ending value", "#,##0", "ending_mean")
    add("Annual return, 5th percentile", PCT, "cagr_p05")
    add("Annual return, median", PCT, "cagr_median")
    add("Annual return, 95th percentile", PCT, "cagr_p95")
    add("Median annualised volatility", PCT, "volatility_median")
    add("Probability of loss", PCT1, "prob_loss")
    add("VaR 95%, whole horizon", PCT, "var_95")
    add("Expected shortfall 95%", PCT, "es_95")
    add("VaR 99%, whole horizon", PCT, "var_99")
    add("Expected shortfall 99%", PCT, "es_99")
    add("Median maximum drawdown", PCT, "max_drawdown_median")
    add("Maximum drawdown, worst 5%", PCT, "max_drawdown_worst_5pct")
    add(f"Probability of a {cfg.bust_drawdown:.0%} drawdown", PCT1, "prob_bust")
    add(f"Probability of ending {cfg.target_return:.0%} above start", PCT1, "prob_target_end")
    add(f"Probability of ever reaching +{cfg.target_return:.0%}", PCT1, "prob_target_touch")
    add("Longest time below a peak, median (periods)", "#,##0", "longest_drawdown_median")
    add("Longest time below a peak, 95th percentile (periods)", "#,##0", "longest_drawdown_p95")
    for i, (label, fmt, values) in enumerate(rows, start=5):
        ws.cell(row=i, column=1, value=label)
        for j, value in enumerate(values, start=2):
            ws.cell(row=i, column=j, value=number(value)).number_format = fmt
    row = 5 + len(rows) + 1
    _section_title(ws, row, f"Scenarios ({shown.model}): percentiles of ending value", accent)
    header(ws, row + 1, ["Scenario", "Percentile", "Ending value", "Annual return"], accent)
    for i, (name, level, _label) in enumerate(simulation_tables.SCENARIOS, start=row + 2):
        end = float(pd.Series(shown.paths.ending).quantile(level))
        growth = (end / cfg.initial_value) ** (1.0 / cfg.horizon_years) - 1.0
        ws.cell(row=i, column=1, value=name)
        ws.cell(row=i, column=2, value=level).number_format = "0%"
        ws.cell(row=i, column=3, value=end).number_format = "#,##0"
        ws.cell(row=i, column=4, value=growth).number_format = PCT
    row += 8
    _section_title(ws, row, f"Percentile bands ({shown.model}); portfolio value by year", accent)
    bands = shown.bands.rename(columns=lambda c: f"{int(str(c)[1:])}th percentile")
    header(ws, row + 1, ["Years", *map(str, bands.columns)], accent)
    for i, (year, vals) in enumerate(
        zip(bands.index.to_numpy(dtype=float), bands.to_numpy(dtype=float), strict=True),
        start=row + 2,
    ):
        ws.cell(row=i, column=1, value=float(year)).number_format = "0.00"
        for j, value in enumerate(vals, start=2):
            ws.cell(row=i, column=j, value=number(float(value))).number_format = "#,##0"
    _line_chart(
        ws,
        f"H{row + 1}",
        "Projected portfolio value",
        rows=(row + 1, row + 1 + len(bands)),
        columns=len(bands.columns),
        accent=accent,
    )
    widths(ws, {"A": 48, "B": 18, "C": 18, "D": 18, "E": 18, "F": 18, "G": 18})


def alpha_decay_sheet(
    wb: Workbook, result: AnalysisResult, inputs: ReportInputs, accent: str
) -> None:
    cfg = result.config
    report = alpha_decay(
        result.portfolio_returns,
        periods_per_year=cfg.periods_per_year,
        windows=inputs.decay_windows,
        risk_free=cfg.risk_free_annual,
    )
    ws = wb.create_sheet("Alpha decay")
    title(ws, "Alpha decay", accent)
    counts = report.counts()
    ws["A2"] = (
        f"As of {formatting.day(report.as_of)}: {report.healthy} of {report.rated} rated cells "
        f"are Good or Excellent. Excellent {counts['Excellent']}, Good {counts['Good']}, "
        f"Warning {counts['Warning']}, Critical {counts['Critical']}, "
        f"not rated {counts['Insufficient history']}."
    )
    header(
        ws,
        4,
        ["Statistic", "Window", "Latest", "History mean", "History std", "Score (z)",
         "Better than share", "Rating", "Earlier windows"],
        accent,
    )  # fmt: skip
    row = 5
    for cell in report.cells:
        fmt = FORMATS[cell.metric.fmt]
        ws.cell(row=row, column=1, value=cell.metric.label)
        ws.cell(row=row, column=2, value=cell.window)
        for col, value in ((3, cell.latest), (4, cell.history_mean), (5, cell.history_std)):
            ws.cell(row=row, column=col, value=number(value)).number_format = fmt
        ws.cell(row=row, column=6, value=number(cell.z)).number_format = "+0.00;-0.00;0.00"
        ws.cell(row=row, column=7, value=number(cell.percentile)).number_format = "0%"
        ws.cell(row=row, column=8, value=cell.rating).alignment = Alignment(horizontal="right")
        ws.cell(row=row, column=9, value=cell.n_history)
        row += 1
    widths(ws, {"A": 26, "B": 10, "C": 14, "D": 14, "E": 14, "F": 12, "G": 16, "H": 20, "I": 16})
