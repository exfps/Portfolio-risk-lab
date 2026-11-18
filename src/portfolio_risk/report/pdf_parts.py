"""Building blocks for the PDF: styles, tables and vector charts on a light A4 page.

Charts are drawn as vector graphics, which keeps the file small and sharp and avoids a
plotting dependency.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from xml.sax.saxutils import escape

import numpy as np
import pandas as pd
from reportlab.graphics.shapes import Drawing, Line, Polygon, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    Table,
    TableStyle,
)

from portfolio_risk.analysis import AnalysisResult
from portfolio_risk.report.look import look
from portfolio_risk.ui import formatting

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN
MAX_POINTS = 400


def make_styles(accent: Color) -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("base", parent=getSampleStyleSheet()["Normal"], fontName=look().font)
    return {
        "title": ParagraphStyle(
            "t", parent=base, fontName=look().bold, fontSize=20, leading=24, textColor=look().ink
        ),
        "sub": ParagraphStyle("s", parent=base, fontSize=9.5, leading=13, textColor=look().muted),
        "h": ParagraphStyle(
            "h",
            parent=base,
            fontName=look().bold,
            fontSize=12,
            leading=15,
            textColor=accent,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "body": ParagraphStyle("b", parent=base, fontSize=9, leading=12.5, textColor=look().ink),
        "small": ParagraphStyle(
            "sm", parent=base, fontSize=7.5, leading=10, textColor=look().muted
        ),
        "warn": ParagraphStyle(
            "w", parent=base, fontSize=8.5, leading=12, textColor=look().negative
        ),
    }


def thin(series: pd.Series) -> pd.Series:
    if len(series) <= MAX_POINTS:
        return series
    index = np.unique(np.linspace(0, len(series) - 1, MAX_POINTS).round().astype(int))
    return series.iloc[index]


def nice_range(low: float, high: float) -> tuple[float, float, float]:
    """Round axis bounds outward to a tidy step; returns (low, high, step)."""
    if not math.isfinite(low) or not math.isfinite(high) or high <= low:
        low, high = (low - 0.5, low + 0.5) if math.isfinite(low) else (0.0, 1.0)
    raw = (high - low) / 4
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    return math.floor(low / step) * step, math.ceil(high / step) * step, step


def line_chart(
    series: pd.Series, accent: Color, *, width: float, height: float, percent: bool, fill: bool
) -> Drawing:
    series = thin(series.dropna())
    left, bottom, top, right = 42.0, 18.0, 6.0, 6.0
    drawing = Drawing(width, height)
    if series.empty:
        return drawing
    low, high, step = nice_range(float(series.min()), float(series.max()))
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
        drawing.add(
            Line(left, y(tick), width - right, y(tick), strokeColor=look().rule, strokeWidth=0.4)
        )
        label = f"{0.0 if abs(tick) < 1e-12 else tick:.0%}" if percent else f"{tick:.2f}"
        drawing.add(
            String(
                left - 4,
                y(tick) - 2.5,
                label,
                fontName=look().font,
                fontSize=7,
                fillColor=look().muted,
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
    drawing.add(
        PolyLine(
            [c for pt in points for c in pt],
            strokeColor=accent,
            strokeWidth=look().style.line_width * 0.85,
        )
    )
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        i = round(frac * (n - 1))
        label = pd.Timestamp(series.index[i]).strftime("%b %Y")
        anchor = "start" if frac == 0 else "end" if frac == 1 else "middle"
        drawing.add(
            String(
                x(i),
                5,
                label,
                fontName=look().font,
                fontSize=7,
                fillColor=look().muted,
                textAnchor=anchor,
            )
        )
    return drawing


def bar_chart(values: pd.Series, accent: Color, *, width: float) -> Drawing:
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
                fontName=look().font,
                fontSize=7.5,
                fillColor=look().ink,
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
                fontName=look().font,
                fontSize=7.5,
                fillColor=look().muted,
            )
        )
    return drawing


def data_table(
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
                ("FONT", (0, 0), (-1, 0), look().bold, 8),
                ("TEXTCOLOR", (0, 0), (-1, 0), accent),
                ("FONT", (0, 1), (-1, -1), look().font, 8.5),
                ("TEXTCOLOR", (0, 1), (-1, -1), look().ink),
                ("ALIGN", (1 if align_first_left else 0, 0), (-1, -1), "RIGHT"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, accent),
                ("LINEBELOW", (0, 1), (-1, -1), 0.3, look().rule),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def frame_rows(frame: pd.DataFrame) -> list[list[str]]:
    return [
        list(map(str, frame.columns)),
        *[list(map(str, row)) for row in frame.itertuples(index=False, name=None)],
    ]


def metric_cards(result: AnalysisResult, accent: Color) -> Table:
    metrics = formatting.headline_metrics(result)
    label_style = ParagraphStyle(
        "l", fontName=look().font, fontSize=7.5, textColor=look().muted, leading=10
    )
    value_style = ParagraphStyle(
        "v", fontName=look().bold, fontSize=14, textColor=look().ink, leading=17
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
                ("LINEABOVE", (0, 1), (-1, 1), 0.4, look().rule),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return grid


def correlation_table(result: AnalysisResult, accent: Color) -> Table:
    matrix = result.correlation
    names = [str(c) for c in matrix.columns]
    rows = [[""] + [n[:10] for n in names]] + [
        [n[:14]] + [f"{v:.2f}" for v in matrix.iloc[i]] for i, n in enumerate(names)
    ]
    first = 28 * mm
    cell = min(22 * mm, (CONTENT_W - first) / max(len(names), 1))
    table = Table(rows, colWidths=[first] + [cell] * len(names))
    commands: list[tuple[object, ...]] = [
        ("FONT", (0, 0), (-1, -1), look().font, 7.5),
        ("FONT", (0, 0), (-1, 0), look().bold, 7),
        ("FONT", (0, 1), (0, -1), look().bold, 7.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), look().muted),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for i in range(len(names)):
        for j in range(len(names)):
            value = float(matrix.to_numpy()[i, j])
            target = accent if value >= 0 else look().negative
            alpha = min(abs(value), 1.0) * 0.85
            shade = colors.Color(
                1 - (1 - target.red) * alpha,
                1 - (1 - target.green) * alpha,
                1 - (1 - target.blue) * alpha,
            )
            commands.append(("BACKGROUND", (j + 1, i + 1), (j + 1, i + 1), shade))
    table.setStyle(TableStyle(commands))
    return table


# ----------------------------------------------------------------- multi-series charts


def series_colours(names: Sequence[str]) -> list[Color]:
    """Colours for named series under the style in force (overrides by name, else by position)."""
    return look().series_colours([str(n) for n in names])


def _axis_label(value: float, kind: str) -> str:
    value = 0.0 if abs(value) < 1e-12 else value
    return {"percent": f"{value:.0%}", "money": f"{value:,.0f}"}.get(kind, f"{value:.2f}")


def _date_ticks(drawing: Drawing, index: pd.Index, x: object, count: int) -> None:
    n = len(index)
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        i = round(frac * (n - 1))
        label = pd.Timestamp(index[i]).strftime("%b %Y")
        anchor = "start" if frac == 0 else "end" if frac == 1 else "middle"
        drawing.add(
            String(
                x(i),  # type: ignore[operator]
                5,
                label,
                fontName=look().font,
                fontSize=7,
                fillColor=look().muted,
                textAnchor=anchor,
            )
        )


def _gridlines(
    drawing: Drawing,
    low: float,
    high: float,
    step: float,
    *,
    y: object,
    left: float,
    right: float,
    kind: str,
) -> None:
    tick = low
    while tick <= high + step / 2:
        yy = y(tick)  # type: ignore[operator]
        drawing.add(Line(left, yy, right, yy, strokeColor=look().rule, strokeWidth=0.4))
        drawing.add(
            String(
                left - 4,
                yy - 2.5,
                _axis_label(tick, kind),
                fontName=look().font,
                fontSize=7,
                fillColor=look().muted,
                textAnchor="end",
            )
        )
        tick += step


def _legend(
    drawing: Drawing,
    names: Sequence[str],
    colours: Sequence[Color],
    top: float,
    left: float,
    *,
    dashed: bool = True,
) -> None:
    x = left
    for i, (name, colour) in enumerate(zip(names, colours, strict=True)):
        label = str(name)[:22]
        drawing.add(
            Line(
                x,
                top - 3,
                x + 14,
                top - 3,
                strokeColor=colour,
                strokeWidth=look().width(str(name), i) if dashed else 3.0,
                strokeDashArray=look().dash(str(name), i) if dashed else None,
            )
        )
        drawing.add(
            String(x + 18, top - 6, label, fontName=look().font, fontSize=7.5, fillColor=look().ink)
        )
        x += 18 + 4.4 * len(label) + 12


def multi_line_chart(
    frame: pd.DataFrame,
    colours: Sequence[Color],
    *,
    width: float,
    height: float,
    kind: str = "ratio",
) -> Drawing:
    """Several dated series on shared axes, with a legend. ``kind``: percent, money or ratio."""
    frame = frame.dropna(how="all")
    drawing = Drawing(width, height)
    if frame.empty:
        return drawing
    keep = np.unique(
        np.linspace(0, len(frame) - 1, min(len(frame), MAX_POINTS)).round().astype(int)
    )
    frame = frame.iloc[keep]
    left, bottom, top, right = 42.0, 18.0, 20.0, 6.0
    low, high, step = nice_range(
        float(np.nanmin(frame.to_numpy())), float(np.nanmax(frame.to_numpy()))
    )
    inner_w, inner_h = width - left - right, height - bottom - top
    n = len(frame)

    def y(value: float) -> float:
        return bottom + (value - low) / (high - low) * inner_h

    def x(i: int) -> float:
        return left + (i / max(n - 1, 1)) * inner_w

    _gridlines(drawing, low, high, step, y=y, left=left, right=width - right, kind=kind)
    for j, column in enumerate(frame.columns):
        values = frame[column].to_numpy(dtype=float)
        points = [(x(i), y(v)) for i, v in enumerate(values) if math.isfinite(v)]
        if len(points) > 1:
            drawing.add(
                PolyLine(
                    [c for pt in points for c in pt],
                    strokeColor=colours[j % len(colours)],
                    strokeWidth=look().width(str(column), j),
                    strokeDashArray=look().dash(str(column), j),
                )
            )
    _date_ticks(drawing, frame.index, x, n)
    _legend(drawing, [str(c) for c in frame.columns], colours, height - 2, left)
    return drawing


def fan_chart(
    bands: pd.DataFrame, initial: float, accent: Color, *, width: float, height: float
) -> Drawing:
    """Median line with 25-75% and 5-95% bands; the x axis is years."""
    drawing = Drawing(width, height)
    left, bottom, top, right = 52.0, 18.0, 6.0, 6.0
    low, high, step = nice_range(
        float(min(bands["p05"].min(), initial)), float(max(bands["p95"].max(), initial))
    )
    inner_w, inner_h = width - left - right, height - bottom - top
    years = bands.index.to_numpy(dtype=float)
    span = max(float(years[-1] - years[0]), 1e-9)

    def y(value: float) -> float:
        return bottom + (value - low) / (high - low) * inner_h

    def x(year: float) -> float:
        return left + (year - float(years[0])) / span * inner_w

    _gridlines(drawing, low, high, step, y=y, left=left, right=width - right, kind="money")

    def band(lower: str, upper: str, alpha: float) -> None:
        up = [(x(t), y(float(v))) for t, v in zip(years, bands[upper].to_numpy(), strict=True)]
        down = [(x(t), y(float(v))) for t, v in zip(years, bands[lower].to_numpy(), strict=True)]
        flat = [c for pt in (*up, *reversed(down)) for c in pt]
        drawing.add(
            Polygon(
                flat,
                fillColor=Color(accent.red, accent.green, accent.blue, alpha=alpha),
                strokeColor=None,
            )
        )

    band("p05", "p95", 0.16)
    band("p25", "p75", 0.32)
    drawing.add(
        Line(
            left,
            y(initial),
            width - right,
            y(initial),
            strokeColor=look().muted,
            strokeWidth=0.6,
            strokeDashArray=(3, 3),
        )
    )
    median = [(x(t), y(float(v))) for t, v in zip(years, bands["p50"].to_numpy(), strict=True)]
    drawing.add(
        PolyLine(
            [c for pt in median for c in pt],
            strokeColor=accent,
            strokeWidth=look().style.line_width * 1.15,
        )
    )
    for year in range(math.ceil(float(years[0])), int(float(years[-1])) + 1):
        drawing.add(
            String(
                x(float(year)),
                5,
                f"{year}y" if year else "start",
                fontName=look().font,
                fontSize=7,
                fillColor=look().muted,
                textAnchor="middle",
            )
        )
    return drawing


def grouped_bar_chart(
    frame: pd.DataFrame, colours: Sequence[Color], *, width: float, height: float
) -> Drawing:
    """Calendar-year returns: one cluster per row of ``frame`` (the index), one bar per column."""
    frame = frame.dropna(how="all")
    drawing = Drawing(width, height)
    if frame.empty:
        return drawing
    left, bottom, top, right = 42.0, 18.0, 20.0, 6.0
    values = frame.to_numpy(dtype=float)
    low, high, step = nice_range(
        min(float(np.nanmin(values)), 0.0), max(float(np.nanmax(values)), 0.0)
    )
    inner_w, inner_h = width - left - right, height - bottom - top

    def y(value: float) -> float:
        return bottom + (value - low) / (high - low) * inner_h

    _gridlines(drawing, low, high, step, y=y, left=left, right=width - right, kind="percent")
    clusters, per = len(frame), len(frame.columns)
    slot = inner_w / clusters
    bar = min(slot * 0.8 / per, 22.0)
    for i, label in enumerate(frame.index):
        start = left + i * slot + (slot - bar * per) / 2
        for j in range(per):
            value = values[i, j]
            if not math.isfinite(value):
                continue
            top_y, base_y = sorted((y(value), y(0.0)))[::-1][0], sorted((y(value), y(0.0)))[0]
            drawing.add(
                Rect(
                    start + j * bar,
                    base_y,
                    bar - 1,
                    max(top_y - base_y, 0.3),
                    fillColor=colours[j % len(colours)],
                    strokeColor=None,
                )
            )
        drawing.add(
            String(
                left + i * slot + slot / 2,
                5,
                str(label),
                fontName=look().font,
                fontSize=7,
                fillColor=look().muted,
                textAnchor="middle",
            )
        )
    _legend(drawing, [str(c) for c in frame.columns], colours, height - 2, left, dashed=False)
    return drawing


def heat_table(grid: pd.DataFrame, accent: Color) -> Table:
    """Monthly returns by year, shaded by sign and size. ``grid`` has month columns and Year."""
    columns = list(grid.columns)
    rows = [["", *columns]]
    for year, row in grid.iterrows():
        rows.append(
            [str(year), *["" if not math.isfinite(float(v)) else f"{float(v):.1%}" for v in row]]
        )
    first = 14 * mm
    cell = (CONTENT_W - first) / len(columns)
    table = Table(rows, colWidths=[first, *[cell] * len(columns)])
    commands: list[tuple[object, ...]] = [
        ("FONT", (0, 0), (-1, -1), look().font, 7),
        ("FONT", (0, 0), (-1, 0), look().bold, 7),
        ("FONT", (0, 1), (0, -1), look().bold, 7),
        ("FONT", (-1, 1), (-1, -1), look().bold, 7),
        ("TEXTCOLOR", (0, 0), (-1, 0), look().muted),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    scale = max(
        float(np.nanmax(np.abs(grid.drop(columns="Year", errors="ignore").to_numpy(dtype=float)))),
        0.01,
    )
    for i, (_, row) in enumerate(grid.iterrows(), start=1):
        for j, value in enumerate(row, start=1):
            number = float(value)
            if not math.isfinite(number) or columns[j - 1] == "Year":
                continue
            target = accent if number >= 0 else look().negative
            alpha = min(abs(number) / scale, 1.0) * 0.75
            commands.append(
                (
                    "BACKGROUND",
                    (j, i),
                    (j, i),
                    colors.Color(
                        1 - (1 - target.red) * alpha,
                        1 - (1 - target.green) * alpha,
                        1 - (1 - target.blue) * alpha,
                    ),
                )
            )
    table.setStyle(TableStyle(commands))
    return table
