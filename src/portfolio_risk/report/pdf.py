"""PDF export with reportlab: vector charts and tables on A4, light paper style.

The report is meant to be printed or attached to an email, so it uses a white page with one
accent colour rather than the dark interface theme. Charts are drawn as vector graphics, which
keeps the file small and sharp and avoids a plotting dependency.
"""

from __future__ import annotations

import io
import math
from collections.abc import Sequence
from xml.sax.saxutils import escape

import numpy as np
import pandas as pd
from reportlab.graphics.shapes import Drawing, Line, Polygon, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from portfolio_risk.analysis import AnalysisResult
from portfolio_risk.report.meta import ASSUMPTIONS, DISCLAIMER, ReportMeta
from portfolio_risk.ui import formatting

INK = HexColor("#1B1E24")
MUTED = HexColor("#6B7280")
RULE = HexColor("#D9DCE1")
NEGATIVE = HexColor("#B5523B")
PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN
MAX_POINTS = 400


def _styles(accent: Color) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["Normal"]
    return {
        "title": ParagraphStyle(
            "t", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=INK
        ),
        "sub": ParagraphStyle("s", parent=base, fontSize=9.5, leading=13, textColor=MUTED),
        "h": ParagraphStyle(
            "h",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=accent,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "body": ParagraphStyle("b", parent=base, fontSize=9, leading=12.5, textColor=INK),
        "small": ParagraphStyle("sm", parent=base, fontSize=7.5, leading=10, textColor=MUTED),
        "warn": ParagraphStyle("w", parent=base, fontSize=8.5, leading=12, textColor=NEGATIVE),
    }


def _thin(series: pd.Series) -> pd.Series:
    if len(series) <= MAX_POINTS:
        return series
    index = np.unique(np.linspace(0, len(series) - 1, MAX_POINTS).round().astype(int))
    return series.iloc[index]


def _nice_range(low: float, high: float) -> tuple[float, float, float]:
    """Round axis bounds outward to a tidy step; returns (low, high, step)."""
    if not math.isfinite(low) or not math.isfinite(high) or high <= low:
        low, high = (low - 0.5, low + 0.5) if math.isfinite(low) else (0.0, 1.0)
    raw = (high - low) / 4
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    return math.floor(low / step) * step, math.ceil(high / step) * step, step


def _line_chart(
    series: pd.Series, accent: Color, *, width: float, height: float, percent: bool, fill: bool
) -> Drawing:
    series = _thin(series.dropna())
    left, bottom, top, right = 42.0, 18.0, 6.0, 6.0
    drawing = Drawing(width, height)
    if series.empty:
        return drawing
    low, high, step = _nice_range(float(series.min()), float(series.max()))
    if fill:
        high = max(high, 0.0)
    inner_w, inner_h = width - left - right, height - bottom - top

    def y(value: float) -> float:
        return bottom + (value - low) / (high - low) * inner_h

    n = len(series)

    def x(i: int) -> float:
        return left + (i / max(n - 1, 1)) * inner_w

    tick = low
    while tick <= high + step / 2:
        drawing.add(Line(left, y(tick), width - right, y(tick), strokeColor=RULE, strokeWidth=0.4))
        label = f"{0.0 if abs(tick) < 1e-12 else tick:.0%}" if percent else f"{tick:.2f}"
        drawing.add(
            String(
                left - 4,
                y(tick) - 2.5,
                label,
                fontName="Helvetica",
                fontSize=7,
                fillColor=MUTED,
                textAnchor="end",
            )
        )
        tick += step
    points = [(x(i), y(float(v))) for i, v in enumerate(series.to_numpy())]
    if fill:
        base_y = y(0.0)
        poly = [(points[0][0], base_y), *points, (points[-1][0], base_y)]
        flat = [c for pt in poly for c in pt]
        drawing.add(
            Polygon(
                flat,
                fillColor=Color(accent.red, accent.green, accent.blue, alpha=0.18),
                strokeColor=None,
            )
        )
    drawing.add(PolyLine([c for pt in points for c in pt], strokeColor=accent, strokeWidth=1.1))
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        i = round(frac * (n - 1))
        label = pd.Timestamp(series.index[i]).strftime("%b %Y")
        anchor = "start" if frac == 0 else "end" if frac == 1 else "middle"
        drawing.add(
            String(
                x(i), 5, label, fontName="Helvetica", fontSize=7, fillColor=MUTED, textAnchor=anchor
            )
        )
    return drawing


def _bar_chart(values: pd.Series, accent: Color, *, width: float) -> Drawing:
    ordered = values.sort_values(ascending=True)
    row_h = 14.0
    height = row_h * len(ordered) + 8
    drawing = Drawing(width, height)
    left = 90.0
    top = float(max(ordered.max(), 1e-9))
    scale = (width - left - 40) / top
    for i, (name, value) in enumerate(ordered.items()):
        yy = 4 + i * row_h
        drawing.add(
            String(
                left - 6,
                yy + 2.5,
                str(name)[:16],
                fontName="Helvetica",
                fontSize=7.5,
                fillColor=INK,
                textAnchor="end",
            )
        )
        drawing.add(
            Rect(
                left,
                yy,
                max(float(value), 0) * scale,
                row_h - 5,
                fillColor=accent,
                strokeColor=None,
            )
        )
        drawing.add(
            String(
                left + max(float(value), 0) * scale + 4,
                yy + 2.5,
                f"{value:.1%}",
                fontName="Helvetica",
                fontSize=7.5,
                fillColor=MUTED,
            )
        )
    return drawing


def _table(
    rows: Sequence[Sequence[str]],
    widths: Sequence[float],
    accent: Color,
    *,
    align_first_left: bool = True,
) -> Table:
    table = Table(list(rows), colWidths=list(widths), repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
                ("TEXTCOLOR", (0, 0), (-1, 0), accent),
                ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
                ("TEXTCOLOR", (0, 1), (-1, -1), INK),
                ("ALIGN", (1 if align_first_left else 0, 0), (-1, -1), "RIGHT"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, accent),
                ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def _frame_rows(frame: pd.DataFrame) -> list[list[str]]:
    return [
        list(map(str, frame.columns)),
        *[list(map(str, row)) for row in frame.itertuples(index=False, name=None)],
    ]


def _metric_cards(result: AnalysisResult, accent: Color) -> Table:
    metrics = formatting.headline_metrics(result)
    label_style = ParagraphStyle(
        "l", fontName="Helvetica", fontSize=7.5, textColor=MUTED, leading=10
    )
    value_style = ParagraphStyle(
        "v", fontName="Helvetica-Bold", fontSize=14, textColor=INK, leading=17
    )
    cells = [
        [Paragraph(escape(label), label_style), Paragraph(escape(value), value_style)]
        for label, value in metrics
    ]
    row = [Table([[a], [b]], colWidths=[CONTENT_W / 3 - 4]) for a, b in cells]
    grid = Table([row[:3], row[3:]], colWidths=[CONTENT_W / 3] * 3)
    grid.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 1.2, accent),
                ("LINEABOVE", (0, 1), (-1, 1), 0.4, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return grid


def _correlation_table(result: AnalysisResult, accent: Color) -> Table:
    matrix = result.correlation
    names = [str(c) for c in matrix.columns]
    rows = [[""] + [n[:10] for n in names]] + [
        [n[:14]] + [f"{v:.2f}" for v in matrix.iloc[i]] for i, n in enumerate(names)
    ]
    first = 28 * mm
    cell = min(22 * mm, (CONTENT_W - first) / max(len(names), 1))
    table = Table(rows, colWidths=[first] + [cell] * len(names))
    commands: list[tuple[object, ...]] = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 7.5),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7),
        ("FONT", (0, 1), (0, -1), "Helvetica-Bold", 7.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for i in range(len(names)):
        for j in range(len(names)):
            value = float(matrix.to_numpy()[i, j])
            target = accent if value >= 0 else NEGATIVE
            alpha = min(abs(value), 1.0) * 0.85
            shade = colors.Color(
                1 - (1 - target.red) * alpha,
                1 - (1 - target.green) * alpha,
                1 - (1 - target.blue) * alpha,
            )
            commands.append(("BACKGROUND", (j + 1, i + 1), (j + 1, i + 1), shade))
    table.setStyle(TableStyle(commands))
    return table


def _footer(meta: ReportMeta):  # type: ignore[no-untyped-def]
    def draw(canvas: Canvas, doc: SimpleDocTemplate) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(
            MARGIN, 10 * mm, f"Portfolio Risk Lab {meta.version}  |  not investment advice"
        )
        canvas.drawRightString(PAGE_W - MARGIN, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return draw


def build_pdf(result: AnalysisResult, meta: ReportMeta | None = None) -> bytes:
    """Return the report as PDF bytes."""
    meta = meta or ReportMeta()
    accent = HexColor(meta.accent)
    st = _styles(accent)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=meta.title,
        author=f"Portfolio Risk Lab {meta.version}",
    )
    story: list[object] = [
        Paragraph(escape(meta.title), st["title"]),
        Spacer(1, 3),
        Paragraph(
            escape(
                f"{formatting.day(result.start)} to {formatting.day(result.end)}  |  "
                f"{result.observations} observations  |  "
                f"{result.config.periods_per_year} periods per year  |  "
                f"{meta.source_note}"
            ),
            st["sub"],
        ),
        Paragraph(escape(f"Generated {meta.generated:%Y-%m-%d %H:%M} UTC"), st["sub"]),
        Spacer(1, 8),
        _metric_cards(result, accent),
    ]
    for note in result.warnings:
        story += [Spacer(1, 4), Paragraph(escape(f"Warning: {note}"), st["warn"])]
    chart_w = CONTENT_W
    story += [
        Paragraph("Wealth index (start = 1)", st["h"]),
        _line_chart(result.wealth, accent, width=chart_w, height=150, percent=False, fill=False),
        Paragraph("Drawdown", st["h"]),
        _line_chart(result.drawdowns, NEGATIVE, width=chart_w, height=110, percent=True, fill=True),
        Paragraph("Drawdown details", st["h"]),
        _table(
            _frame_rows(formatting.drawdown_table(result)),
            [CONTENT_W * 0.45, CONTENT_W * 0.55],
            accent,
        ),
    ]
    var = formatting.var_table(result)
    story += [
        KeepTogether(
            [
                Paragraph("Value at Risk and Conditional VaR (one period)", st["h"]),
                _table(_frame_rows(var), [CONTENT_W / len(var.columns)] * len(var.columns), accent),
                Paragraph(
                    "Shown as positive losses. Historical figures use the observed returns; "
                    "parametric figures assume a normal distribution and understate fat tails.",
                    st["small"],
                ),
            ]
        ),
        Paragraph(
            escape(
                f"Concentration (HHI) {formatting.ratio(result.hhi, 3)}  |  "
                f"Effective positions {formatting.ratio(result.effective_positions, 2)}"
            ),
            st["body"],
        ),
        Paragraph("Assets", st["h"]),
    ]
    assets = formatting.asset_table(result)
    story += [
        _table(_frame_rows(assets), [CONTENT_W * 0.25] + [CONTENT_W * 0.15] * 5, accent),
        Paragraph("Share of portfolio risk", st["h"]),
        _bar_chart(result.risk_contribution, accent, width=chart_w),
        KeepTogether(
            [Paragraph("Correlation of asset returns", st["h"]), _correlation_table(result, accent)]
        ),
    ]
    bench = formatting.benchmark_table(result)
    if bench is not None:
        story += [
            Paragraph("Portfolio versus benchmark", st["h"]),
            _table(_frame_rows(bench), [CONTENT_W * 0.45, CONTENT_W * 0.55], accent),
        ]
    rf = f"Risk-free rate {result.config.risk_free_annual:.2%} annual"
    rf += (
        f" (source: {meta.risk_free_source})."
        if meta.risk_free_source
        else " (source not recorded)."
    )
    story.append(Paragraph("Assumptions", st["h"]))
    for text in (*ASSUMPTIONS, rf):
        story.append(Paragraph("&bull; " + escape(text), st["body"]))
    story += [Spacer(1, 8), Paragraph(escape(DISCLAIMER), st["small"])]
    footer = _footer(meta)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
