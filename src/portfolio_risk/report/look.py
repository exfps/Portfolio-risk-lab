"""A ``ReportStyle`` turned into reportlab colours, fonts and per-series line settings.

The look in force is held in a context variable, so ``build_pdf`` can set it for one report
without module-level state that two simultaneous Streamlit sessions would share.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from reportlab.lib.colors import Color, HexColor

from portfolio_risk.report.style import DASH_PATTERNS, FONTS, PAPERS, ReportStyle

DEFAULT_ACCENT = "#1F8F82"
# The default series order when a style does not set one: the accent, then print-safe colours.
_DEFAULT_REST = ("#B08A3E", "#1B1E24", "#6B7280", "#5B7C99", "#8C6A9E")
DEFAULT_SERIES = (DEFAULT_ACCENT, *_DEFAULT_REST)
_FIRST_SERIES_BOOST = 1.23  # the first series is drawn a little heavier than the rest


@dataclass(frozen=True)
class Look:
    style: ReportStyle
    accent: Color
    paper: Color
    ink: Color
    muted: Color
    rule: Color
    negative: Color
    font: str
    bold: str

    def colour(self, name: str, index: int) -> Color:
        over = self.style.overrides.get(name)
        if over and over.colour:
            return HexColor(over.colour)
        if self.style.series:
            return HexColor(self.style.series[index % len(self.style.series)])
        if index == 0:
            return self.accent
        return HexColor(_DEFAULT_REST[(index - 1) % len(_DEFAULT_REST)])

    def width(self, name: str, index: int) -> float:
        over = self.style.overrides.get(name)
        if over and over.width:
            return over.width
        return self.style.line_width * (_FIRST_SERIES_BOOST if index == 0 else 1.0)

    def dash_name(self, name: str, index: int) -> str:
        over = self.style.overrides.get(name)
        return over.dash if over and over.dash else self.style.dash_for(index)

    def dash(self, name: str, index: int) -> tuple[float, ...] | None:
        return DASH_PATTERNS[self.dash_name(name, index)]

    def series_colours(self, names: Sequence[str]) -> list[Color]:
        return [self.colour(n, i) for i, n in enumerate(names)]


def make_look(style: ReportStyle, interface_accent: str = DEFAULT_ACCENT) -> Look:
    """The style's own accent wins; otherwise the interface accent is used."""
    background, ink, muted, rule = PAPERS[style.paper]
    regular, bold = FONTS[style.font]
    return Look(
        style=style,
        accent=HexColor(style.accent or interface_accent),
        paper=HexColor(background),
        ink=HexColor(ink),
        muted=HexColor(muted),
        rule=HexColor(rule),
        negative=HexColor(style.negative),
        font=regular,
        bold=bold,
    )


_CURRENT: ContextVar[Look | None] = ContextVar("report_look", default=None)


def look() -> Look:
    """The look in force; the Classic style when none has been set."""
    return _CURRENT.get() or make_look(ReportStyle())


@contextmanager
def use(active: Look) -> Iterator[Look]:
    token = _CURRENT.set(active)
    try:
        yield active
    finally:
        _CURRENT.reset(token)
