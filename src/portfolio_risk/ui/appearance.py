"""Appearance controls: palette preset, optional custom accent colour, and text size.

The choice lives in session state and in the page address (``?theme=Graphite&accent=%23C9A96E``),
so a refresh keeps it and a link can share it. Charts, the stylesheet and the exports all read
the same ``Appearance``. Streamlit's own widgets (toggles, sliders) keep the base colour from
``.streamlit/config.toml``; that file is the place to change them.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import streamlit as st

from portfolio_risk.ui import theme

THEME_KEY, CUSTOM_KEY, ACCENT_KEY, SIZE_KEY = "ap_theme", "ap_custom", "ap_accent", "ap_size"
LINES_KEY, LINE_WIDTH_KEY = "ap_lines", "ap_line_width"
LINE_MODES = ("Standard", "Colour-blind safe")
DEFAULT_LINE_WIDTH = 1.6
INITIALISED = "ap_initialised"
DEFAULT_SIZE = "Comfortable"


@dataclass(frozen=True)
class Appearance:
    palette: theme.Palette
    base_px: int


def resolve(
    preset: str,
    custom_accent: str | None,
    size: str,
    lines: str = LINE_MODES[0],
    line_width: float = DEFAULT_LINE_WIDTH,
) -> Appearance:
    """Turn raw choices into an ``Appearance``, falling back to defaults for unknown values."""
    palette = theme.PRESETS.get(preset, theme.DEFAULT)
    if custom_accent and theme.is_hex(custom_accent):
        palette = theme.with_accent(palette, custom_accent)
    low, high = theme.LINE_WIDTHS
    palette = replace(
        palette,
        colour_blind_lines=lines == LINE_MODES[1],
        line_width=min(max(float(line_width), low), high),
    )
    return Appearance(palette, theme.FONT_SIZES.get(size, theme.FONT_SIZES[DEFAULT_SIZE]))


def _width_from(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        return DEFAULT_LINE_WIDTH
    low, high = theme.LINE_WIDTHS
    return min(max(value, low), high)


def _load_from_address() -> None:
    """Copy the choices in the page address into session state, once per session."""
    if st.session_state.get(INITIALISED):
        return
    params = st.query_params
    preset = params.get("theme", theme.DEFAULT.name)
    st.session_state.setdefault(
        THEME_KEY, preset if preset in theme.PRESETS else theme.DEFAULT.name
    )
    accent = params.get("accent", "")
    st.session_state.setdefault(CUSTOM_KEY, theme.is_hex(accent))
    st.session_state.setdefault(ACCENT_KEY, accent.upper() if theme.is_hex(accent) else "")
    size = params.get("size", DEFAULT_SIZE)
    st.session_state.setdefault(SIZE_KEY, size if size in theme.FONT_SIZES else DEFAULT_SIZE)
    lines = params.get("lines", LINE_MODES[0])
    st.session_state.setdefault(LINES_KEY, lines if lines in LINE_MODES else LINE_MODES[0])
    st.session_state.setdefault(LINE_WIDTH_KEY, _width_from(params.get("lw", "")))
    st.session_state[INITIALISED] = True


def current() -> Appearance:
    """The appearance chosen so far. Call before rendering anything that uses it."""
    _load_from_address()
    custom = st.session_state.get(ACCENT_KEY) if st.session_state.get(CUSTOM_KEY) else None
    return resolve(
        str(st.session_state.get(THEME_KEY, theme.DEFAULT.name)),
        str(custom) if custom else None,
        str(st.session_state.get(SIZE_KEY, DEFAULT_SIZE)),
        str(st.session_state.get(LINES_KEY, LINE_MODES[0])),
        float(st.session_state.get(LINE_WIDTH_KEY, DEFAULT_LINE_WIDTH)),
    )


def _write_address() -> None:
    wanted: dict[str, str] = {}
    if st.session_state[THEME_KEY] != theme.DEFAULT.name:
        wanted["theme"] = st.session_state[THEME_KEY]
    if st.session_state[CUSTOM_KEY] and theme.is_hex(str(st.session_state[ACCENT_KEY])):
        wanted["accent"] = str(st.session_state[ACCENT_KEY])
    if st.session_state[SIZE_KEY] != DEFAULT_SIZE:
        wanted["size"] = st.session_state[SIZE_KEY]
    if st.session_state[LINES_KEY] != LINE_MODES[0]:
        wanted["lines"] = st.session_state[LINES_KEY]
    if abs(float(st.session_state[LINE_WIDTH_KEY]) - DEFAULT_LINE_WIDTH) > 1e-9:
        wanted["lw"] = f"{float(st.session_state[LINE_WIDTH_KEY]):g}"
    for key in ("theme", "accent", "size", "lines", "lw"):
        if key in wanted:
            st.query_params[key] = wanted[key]
        elif key in st.query_params:
            del st.query_params[key]


def controls() -> None:
    """The sidebar section."""
    _load_from_address()
    with st.expander("Appearance"):
        st.selectbox("Palette", list(theme.PRESETS), key=THEME_KEY, on_change=_write_address)
        if st.toggle("Custom accent colour", key=CUSTOM_KEY, on_change=_write_address):
            if not theme.is_hex(str(st.session_state.get(ACCENT_KEY, ""))):
                st.session_state[ACCENT_KEY] = theme.PRESETS[st.session_state[THEME_KEY]].accent
            picked = st.color_picker("Accent", key=ACCENT_KEY, on_change=_write_address)
            shown = current().palette.accent
            if shown.upper() != picked.upper():
                st.caption(f"Lightened to {shown} so it stays readable on the dark background.")
        st.select_slider(
            "Text size", list(theme.FONT_SIZES), key=SIZE_KEY, on_change=_write_address
        )
        st.selectbox(
            "Chart lines",
            LINE_MODES,
            key=LINES_KEY,
            on_change=_write_address,
            help="Colour-blind safe also gives each line its own dash pattern.",
        )
        st.slider(
            "Line width", *theme.LINE_WIDTHS, step=0.2, key=LINE_WIDTH_KEY, on_change=_write_address
        )
