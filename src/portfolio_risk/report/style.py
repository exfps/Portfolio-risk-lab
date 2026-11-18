"""How a PDF report looks: colours, line weights and dashes, paper tone and font.

A ``ReportStyle`` is plain validated data (no reportlab import), so it can be saved as JSON,
shared, and tested without drawing anything. ``report.look`` turns it into drawing objects.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from portfolio_risk.errors import PortfolioRiskError

VERSION = 1
MAX_SERIES = 8
MIN_WIDTH, MAX_WIDTH = 0.5, 3.5
MAX_OVERRIDES = 12

# Dash patterns in points (on, off, ...). ``None`` is a solid line.
DASH_PATTERNS: dict[str, tuple[float, ...] | None] = {
    "solid": None,
    "dashed": (4, 2),
    "dotted": (1, 2),
    "dash-dot": (6, 2, 1, 2),
}
_MIXED_ORDER = ("solid", "solid", "dashed", "dotted", "dash-dot", "dashed")
# every one of the first four lines gets its own pattern, for readers who cannot rely on colour
_DISTINCT_ORDER = ("solid", "dashed", "dotted", "dash-dot", "dashed", "dotted")

# paper tone: (page background, ink, muted text, rules)
PAPERS: dict[str, tuple[str, str, str, str]] = {
    "White": ("#FFFFFF", "#1B1E24", "#6B7280", "#D9DCE1"),
    "Ivory": ("#FBF7EE", "#241F18", "#6F675A", "#DDD5C4"),
    "Cool grey": ("#F4F6F8", "#1B2027", "#667080", "#D3D8DF"),
}
# font family: (regular, bold) among the fonts every PDF reader has
FONTS: dict[str, tuple[str, str]] = {
    "Sans": ("Helvetica", "Helvetica-Bold"),
    "Serif": ("Times-Roman", "Times-Bold"),
}
DASH_MODES = ("mixed", "distinct", "solid")

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


class StyleError(PortfolioRiskError, ValueError):
    """A style file or value is not valid."""


def _hex(value: object, what: str) -> str:
    if not isinstance(value, str) or not _HEX.match(value):
        raise StyleError(f"{what} must be #RRGGBB, not {value!r}")
    return value.upper()


@dataclass(frozen=True)
class SeriesOverride:
    """A change to one named series (a portfolio, the benchmark, a holding). ``None`` keeps it."""

    colour: str | None = None
    width: float | None = None
    dash: str | None = None

    def __post_init__(self) -> None:
        if self.colour is not None:
            object.__setattr__(self, "colour", _hex(self.colour, "series colour"))
        if self.width is not None and not MIN_WIDTH <= self.width <= MAX_WIDTH:
            raise StyleError(f"line width must be between {MIN_WIDTH} and {MAX_WIDTH}")
        if self.dash is not None and self.dash not in DASH_PATTERNS:
            raise StyleError(f"unknown line style {self.dash!r}; use {sorted(DASH_PATTERNS)}")


@dataclass(frozen=True)
class ReportStyle:
    """Everything that can be changed about the look of the PDF.

    ``accent`` and ``series`` of ``None`` mean "follow the interface accent" and "use the
    default order" respectively. ``negative`` colours losses and drawdowns.
    """

    name: str = "Classic"
    accent: str | None = None
    series: tuple[str, ...] | None = None
    negative: str = "#B5523B"
    line_width: float = 1.3
    dashes: str = "mixed"
    paper: str = "White"
    font: str = "Sans"
    overrides: Mapping[str, SeriesOverride] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip() or len(self.name) > 40:
            raise StyleError("style name must be 1 to 40 characters")
        if self.accent is not None:
            object.__setattr__(self, "accent", _hex(self.accent, "accent"))
        if self.series is not None:
            if not 1 <= len(self.series) <= MAX_SERIES:
                raise StyleError(f"series needs 1 to {MAX_SERIES} colours")
            object.__setattr__(self, "series", tuple(_hex(c, "series colour") for c in self.series))
        object.__setattr__(self, "negative", _hex(self.negative, "negative colour"))
        if not MIN_WIDTH <= self.line_width <= MAX_WIDTH:
            raise StyleError(f"line width must be between {MIN_WIDTH} and {MAX_WIDTH}")
        if self.dashes not in DASH_MODES:
            raise StyleError(f"dashes must be one of {DASH_MODES}")
        if self.paper not in PAPERS:
            raise StyleError(f"paper must be one of {sorted(PAPERS)}")
        if self.font not in FONTS:
            raise StyleError(f"font must be one of {sorted(FONTS)}")
        if len(self.overrides) > MAX_OVERRIDES:
            raise StyleError(f"at most {MAX_OVERRIDES} series overrides")

    def dash_for(self, index: int) -> str:
        """The default line style of the series at ``index`` (before overrides)."""
        if self.dashes == "solid":
            return "solid"
        order = _DISTINCT_ORDER if self.dashes == "distinct" else _MIXED_ORDER
        return order[index % len(order)]


# Okabe and Ito (2008): eight colours chosen to stay distinguishable with the common forms of
# colour-vision deficiency. Yellow is left out because it is unreadable on white paper.
OKABE_ITO = ("#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#000000")

PRESETS: dict[str, ReportStyle] = {
    "Classic": ReportStyle(),
    "Colour-blind safe": ReportStyle(
        name="Colour-blind safe", accent="#0072B2", series=OKABE_ITO, negative="#D55E00",
        dashes="distinct"
    ),
    "Black and white print": ReportStyle(
        name="Black and white print",
        accent="#222222",
        series=("#111111", "#555555", "#888888", "#333333", "#999999", "#666666"),
        negative="#444444",
        line_width=1.5,
        dashes="distinct",
    ),
    "Editorial": ReportStyle(
        name="Editorial", accent="#7A4E2D", paper="Ivory", font="Serif",
        series=("#7A4E2D", "#2F5D62", "#241F18", "#8A7F6E", "#5B7C99", "#8C6A9E"),
    ),
}  # fmt: skip


def preset(name: str) -> ReportStyle:
    """The named preset, or Classic for an unknown name."""
    return PRESETS.get(name, PRESETS["Classic"])


def with_changes(style: ReportStyle, **changes: Any) -> ReportStyle:
    """A validated copy. A changed style is no longer the preset it started from."""
    return replace(style, **changes)


# ------------------------------------------------------------------------------- JSON


def to_json(style: ReportStyle) -> str:
    data: dict[str, Any] = {
        "version": VERSION,
        "name": style.name,
        "accent": style.accent,
        "series": list(style.series) if style.series else None,
        "negative": style.negative,
        "line_width": style.line_width,
        "dashes": style.dashes,
        "paper": style.paper,
        "font": style.font,
        "overrides": {
            name: {k: v for k, v in vars(o).items() if v is not None}
            for name, o in style.overrides.items()
        },
    }
    return json.dumps(data, indent=2)


def from_json(text: str) -> ReportStyle:
    """Parse and validate a style file. Raises ``StyleError`` for anything unexpected."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise StyleError(f"not valid JSON: {error.msg}") from error
    if not isinstance(data, dict):
        raise StyleError("a style file is a JSON object")
    if data.get("version") != VERSION:
        raise StyleError(f"unsupported style version {data.get('version')!r}")
    raw = data.get("overrides")
    raw = {} if raw is None else raw
    if not isinstance(raw, dict) or any(not isinstance(v, dict) for v in raw.values()):
        raise StyleError("overrides must map a series name to its settings")
    unknown = {k for v in raw.values() for k in v} - {"colour", "width", "dash"}
    if unknown:
        raise StyleError(f"unknown override setting(s): {sorted(unknown)}")
    series = data.get("series")
    if series is not None and not isinstance(series, list):
        raise StyleError("series must be a list of colours")
    defaults = ReportStyle()
    try:
        return ReportStyle(
            name=str(data.get("name", "Custom")),
            accent=data.get("accent"),
            series=tuple(series) if series else None,
            negative=data.get("negative", defaults.negative),
            line_width=_number(data.get("line_width", defaults.line_width)),
            dashes=data.get("dashes", defaults.dashes),
            paper=data.get("paper", defaults.paper),
            font=data.get("font", defaults.font),
            overrides={
                str(n): SeriesOverride(
                    v.get("colour"),
                    None if v.get("width") is None else _number(v["width"]),
                    v.get("dash"),
                )
                for n, v in raw.items()
            },
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, StyleError):
            raise
        raise StyleError(f"invalid style value: {error}") from error


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise StyleError(f"expected a number, not {value!r}")
    return float(value)
