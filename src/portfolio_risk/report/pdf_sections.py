"""One builder per report section. Each returns reportlab flowables for the PDF story."""

from __future__ import annotations

from dataclasses import dataclass
from xml.sax.saxutils import escape

import pandas as pd
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import CondPageBreak, KeepTogether, Paragraph, Spacer, Table, TableStyle

from portfolio_risk.analysis import AnalysisResult
from portfolio_risk.decay import alpha_decay
from portfolio_risk.report.inputs import ReportInputs
from portfolio_risk.report.look import look
from portfolio_risk.report.meta import ASSUMPTIONS, DISCLAIMER, ReportMeta
from portfolio_risk.report.pdf_parts import (
    CONTENT_W,
    bar_chart,
    correlation_table,
    data_table,
    fan_chart,
    frame_rows,
    grouped_bar_chart,
    heat_table,
    line_chart,
    metric_cards,
    multi_line_chart,
    series_colours,
)
from portfolio_risk.tearsheet import calendar_years, monthly_table, tearsheet_table
from portfolio_risk.ui import compare_tables, decay_tables, formatting, simulation_tables
from portfolio_risk.ui import tearsheet_tables as ts_tables

CHART_W = CONTENT_W
GOLD = HexColor("#9A7B2F")
Story = list[object]


@dataclass(frozen=True)
class Context:
    result: AnalysisResult
    meta: ReportMeta
    inputs: ReportInputs
    accent: Color
    styles: dict[str, ParagraphStyle]

    def head(self, text: str) -> Story:
        return [CondPageBreak(70), Paragraph(escape(text), self.styles["h"])]

    def note(self, text: str) -> Paragraph:
        return Paragraph(escape(text), self.styles["small"])


def _wide(frame: pd.DataFrame, accent: Color, first: float = 0.34) -> Table:
    columns = len(frame.columns)
    rest = (1.0 - first) / max(columns - 1, 1)
    return data_table(
        frame_rows(frame), [CONTENT_W * first, *[CONTENT_W * rest] * (columns - 1)], accent
    )


def summary(c: Context) -> Story:
    story: Story = [metric_cards(c.result, c.accent)]
    for note in c.result.warnings:
        story += [Spacer(1, 4), Paragraph(escape(f"Warning: {note}"), c.styles["warn"])]
    return story


def performance(c: Context) -> Story:
    r = c.result
    return [
        *c.head("Wealth index (start = 1)"),
        line_chart(r.wealth, c.accent, width=CHART_W, height=150, percent=False, fill=False),
        Paragraph("Drawdown", c.styles["h"]),
        line_chart(
            r.drawdowns, look().negative, width=CHART_W, height=110, percent=True, fill=True
        ),
        Paragraph("Drawdown details", c.styles["h"]),
        data_table(
            frame_rows(formatting.drawdown_table(r)), [CONTENT_W * 0.45, CONTENT_W * 0.55], c.accent
        ),
    ]


def risk(c: Context) -> Story:
    r = c.result
    var = formatting.var_table(r)
    return [
        KeepTogether(
            [
                Paragraph("Value at Risk and Conditional VaR (one period)", c.styles["h"]),
                data_table(
                    frame_rows(var), [CONTENT_W / len(var.columns)] * len(var.columns), c.accent
                ),
                Paragraph(
                    "Shown as positive losses. Historical figures use the observed returns; "
                    "parametric figures assume a normal distribution and understate fat tails.",
                    c.styles["small"],
                ),
            ]
        ),
        Paragraph(
            escape(
                f"Concentration (HHI) {formatting.ratio(r.hhi, 3)}  |  "
                f"Effective positions {formatting.ratio(r.effective_positions, 2)}"
            ),
            c.styles["body"],
        ),
        Paragraph("Assets", c.styles["h"]),
        data_table(
            frame_rows(formatting.asset_table(r)),
            [CONTENT_W * 0.25] + [CONTENT_W * 0.15] * 5,
            c.accent,
        ),
        Paragraph("Share of portfolio risk", c.styles["h"]),
        bar_chart(r.risk_contribution, c.accent, width=CHART_W),
    ]


def correlation(c: Context) -> Story:
    return [
        KeepTogether(
            [
                Paragraph("Correlation of asset returns", c.styles["h"]),
                correlation_table(c.result, c.accent),
            ]
        )
    ]


def benchmark(c: Context) -> Story:
    table = formatting.benchmark_table(c.result)
    if table is None:
        return []
    return [
        *c.head("Portfolio versus benchmark"),
        data_table(frame_rows(table), [CONTENT_W * 0.45, CONTENT_W * 0.55], c.accent),
    ]


def tearsheet(c: Context) -> Story:
    series = c.inputs.tearsheet or {}
    cfg = c.result.config
    bench = c.inputs.benchmark
    table = tearsheet_table(
        series,
        periods_per_year=cfg.periods_per_year,
        rf_per_period=cfg.risk_free_per_period,
        mar_per_period=cfg.mar_per_period,
        benchmark=bench if bench in series else None,
    )
    colours = series_colours(list(series))
    growth = pd.DataFrame({n: (1.0 + s).cumprod() for n, s in series.items()})
    grid = monthly_table(c.result.portfolio_returns)
    story: Story = [
        *c.head("Classic tearsheet: key statistics"),
        _wide(ts_tables.metrics_frame(table), c.accent),
        c.note(
            "Per-period simple returns over the same dates for every column. Value at Risk and "
            "expected shortfall are historical, for one period."
        ),
        *c.head("Cumulative growth of 1"),
        multi_line_chart(growth, colours, width=CHART_W, height=160),
        *c.head("Returns by calendar year"),
        grouped_bar_chart(calendar_years(series), colours, width=CHART_W, height=140),
        *c.head("Monthly returns"),
        heat_table(grid, c.accent),
        *c.head("Deepest drawdowns"),
    ]
    episodes = ts_tables.episodes_frame(c.result.wealth)
    if episodes.empty:
        story.append(c.note("The portfolio never fell below a previous high."))
    else:
        story.append(_wide(episodes, c.accent, first=0.2))
    return story


def comparison(c: Context) -> Story:
    comp = c.inputs.comparison
    if comp is None:
        return []
    colours = series_colours(comp.names)
    story: Story = [
        *c.head("Portfolio comparison"),
        c.note(
            f"{formatting.day(comp.start)} to {formatting.day(comp.end)}  |  "
            f"{comp.observations} observations  |  constant weights, common dates"
        ),
        _wide(ts_tables.metrics_frame(comp.table), c.accent),
        *c.head("Holdings"),
        _wide(compare_tables.weights_frame(comp.weights), c.accent, first=0.28),
        Spacer(1, 6),
        _wide(compare_tables.concentration_frame(comp.concentration), c.accent, first=0.28),
        *c.head("Cumulative growth of 1"),
        multi_line_chart(comp.wealth, colours, width=CHART_W, height=150),
        *c.head("Drawdowns"),
        multi_line_chart(comp.drawdowns, colours, width=CHART_W, height=130, kind="percent"),
        *c.head("Returns by calendar year"),
        grouped_bar_chart(
            calendar_years({str(n): comp.returns[n] for n in comp.returns.columns}),
            colours,
            width=CHART_W,
            height=140,
        ),
        *c.head("Correlation of portfolio returns"),
        _wide(compare_tables.correlation_frame(comp.correlation), c.accent, first=0.28),
    ]
    return story


def monte_carlo(c: Context) -> Story:
    results = list(c.inputs.simulation or [])
    if not results:
        return []
    shown, cfg = results[0], results[0].config
    story: Story = [
        *c.head("Monte Carlo projection"),
        c.note(
            f"{cfg.n_paths:,} paths  |  {cfg.horizon_years:g} years, {cfg.frequency}  |  "
            f"rebalancing: {cfg.rebalancing}  |  seed {cfg.seed}  |  fitted on {shown.window}"
        ),
    ]
    for warning in shown.warnings:
        story.append(Paragraph(escape(f"Warning: {warning}"), c.styles["warn"]))
    story += [
        Paragraph(escape(f"Projection: {shown.model}"), c.styles["body"]),
        fan_chart(shown.bands, cfg.initial_value, c.accent, width=CHART_W, height=170),
        c.note("Line: median. Shaded: 25th to 75th and 5th to 95th percentiles. Dashed: start."),
        Paragraph("Scenarios", c.styles["h"]),
        _wide(simulation_tables.scenario_frame(shown), c.accent, first=0.25),
        *c.head("Risk and outcome statistics"),
        _wide(simulation_tables.comparison_frame(results), c.accent, first=0.4),
        c.note(
            "VaR and expected shortfall are losses over the whole horizon, shown as positive "
            "numbers, and are not annualised. " + simulation_tables.DISCLAIMER
        ),
    ]
    return story


def _rating_colours() -> dict[str, Color]:
    return {"Good": look().ink, "Warning": GOLD, "Critical": look().negative}


def alpha_decay_section(c: Context) -> Story:
    cfg = c.result.config
    report = alpha_decay(
        c.result.portfolio_returns,
        periods_per_year=cfg.periods_per_year,
        windows=c.inputs.decay_windows,
        risk_free=cfg.risk_free_annual,
    )
    counts = report.counts()
    frame = decay_tables.matrix_frame(report)
    table = _wide(frame, c.accent, first=0.24)
    commands: list[tuple[object, ...]] = [("FONT", (1, 1), (-1, -1), look().font, 7.5)]
    for i, row in enumerate(frame.itertuples(index=False), start=1):
        for j, text in enumerate(row[1:], start=1):
            rating = str(text).split(" | ")[1].split(" (")[0]
            colour = (
                c.accent if rating == "Excellent" else _rating_colours().get(rating, look().muted)
            )
            commands.append(("TEXTCOLOR", (j, i), (j, i), colour))
    table.setStyle(TableStyle(commands))  # appended to the base style
    return [
        *c.head("Alpha decay"),
        Paragraph(
            escape(
                f"As of {formatting.day(report.as_of)}. {report.healthy} of {report.rated} rated "
                f"cells are Good or Excellent (Excellent {counts['Excellent']}, Good "
                f"{counts['Good']}, Warning {counts['Warning']}, Critical {counts['Critical']}; "
                f"{counts['Insufficient history']} could not be rated)."
            ),
            c.styles["body"],
        ),
        Spacer(1, 4),
        table,
        c.note(decay_tables.METHOD),
    ]


def assumptions(c: Context) -> Story:
    rf = f"Risk-free rate {c.result.config.risk_free_annual:.2%} annual"
    rf += (
        f" (source: {c.meta.risk_free_source})."
        if c.meta.risk_free_source
        else " (source not recorded)."
    )
    story: Story = [*c.head("Assumptions")]
    for text in (*ASSUMPTIONS, rf):
        story.append(Paragraph("&bull; " + escape(text), c.styles["body"]))
    story += [Spacer(1, 8), Paragraph(escape(DISCLAIMER), c.styles["small"])]
    return story


BUILDERS = {
    "summary": summary,
    "performance": performance,
    "risk": risk,
    "correlation": correlation,
    "benchmark": benchmark,
    "tearsheet": tearsheet,
    "comparison": comparison,
    "monte_carlo": monte_carlo,
    "alpha_decay": alpha_decay_section,
    "assumptions": assumptions,
}
