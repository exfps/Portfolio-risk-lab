"""Builds the interface stylesheet from ``style.css``, ``theme.py`` and the bundled fonts.

The fonts (Inter, SIL Open Font License, see ``fonts/``) are embedded in the
stylesheet as data URIs, so the interface makes no request to any font service and looks the same
offline.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path
from string import Template

from portfolio_risk.ui import theme

_DIRECTORY = Path(__file__).resolve().parent
_FONTS = {"inter": "Inter-latin-variable.woff2"}


def _data_uri(filename: str) -> str:
    encoded = base64.b64encode((_DIRECTORY / "fonts" / filename).read_bytes()).decode("ascii")
    return f"data:font/woff2;base64,{encoded}"


@lru_cache(maxsize=32)
def stylesheet(palette: theme.Palette = theme.DEFAULT, base_px: int = 16) -> str:
    """The complete ``<style>`` element. Raises ``KeyError`` if the CSS uses an unknown token."""
    tokens = {
        "background": palette.background,
        "surface": palette.surface,
        "elevated": palette.elevated,
        "border": palette.border,
        "text": palette.text,
        "muted": palette.muted,
        "axis": palette.axis,
        "accent": palette.accent,
        "accent_bright": palette.accent_bright,
        "gold": palette.gold,
        "font_stack": theme.FONT_STACK,
        "base_px": f"{base_px}px",
        **{name: _data_uri(filename) for name, filename in _FONTS.items()},
    }
    css = Template((_DIRECTORY / "style.css").read_text(encoding="utf-8")).substitute(tokens)
    return f"<style>\n{css}\n</style>"
