"""Shared constants and cell helpers for the Excel sheets."""

from __future__ import annotations

import math

from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.worksheet.worksheet import Worksheet

PCT = "0.00%"
PCT1 = "0.0%"
RATIO = "0.00"
DATE = "yyyy-mm-dd"


def number(value: float) -> float | None:
    """Excel cannot store NaN or infinity; leave the cell empty instead."""
    return float(value) if math.isfinite(value) else None


def header(ws: Worksheet, row: int, labels: list[str], accent: str) -> None:
    side = Side(style="thin", color=accent)
    for col, label in enumerate(labels, start=1):
        cell = ws.cell(row=row, column=col, value=label)
        cell.font = Font(bold=True, color=accent)
        cell.border = Border(bottom=side)
        cell.alignment = Alignment(horizontal="left" if col == 1 else "right")


def title(ws: Worksheet, text: str, accent: str) -> None:
    ws["A1"] = text
    ws["A1"].font = Font(size=14, bold=True, color=accent)


def paragraph(
    ws: Worksheet, row: int, text: str, *, font: Font | None = None, last: str = "F"
) -> None:
    """Long text across columns A to ``last``, wrapped, so it prints and reads without scrolling."""
    ws.merge_cells(f"A{row}:{last}{row}")
    cell = ws.cell(row=row, column=1, value=text)
    cell.alignment = Alignment(wrap_text=True, vertical="top")
    if font is not None:
        cell.font = font
    ws.row_dimensions[row].height = 15 * max(1, math.ceil(len(text) / 110))


def widths(ws: Worksheet, widths: dict[str, float]) -> None:
    for letter, width in widths.items():
        ws.column_dimensions[letter].width = width
