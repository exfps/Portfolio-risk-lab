"""Controls for the look of exported PDFs and Excel files.

The choices live in session state and become a ``ReportStyle``. A preset can be named in the
page address (``?pdf=Editorial``); a fully custom style is saved and loaded as a JSON file.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

import pandas as pd
import streamlit as st

from portfolio_risk.report import style as rs
from portfolio_risk.report.look import DEFAULT_ACCENT, DEFAULT_SERIES

PRESET, PAPER, FONT = "rs_preset", "rs_paper", "rs_font"
WIDTH, DASHES, NEGATIVE = "rs_width", "rs_dashes", "rs_negative"
ACCENT_ON, ACCENT, SERIES_ON = "rs_accent_on", "rs_accent", "rs_series_on"
SERIES_KEYS = tuple(f"rs_series_{i}" for i in range(6))
OVERRIDES, GENERATION, ERROR, UPLOAD = "rs_overrides", "rs_generation", "rs_error", "rs_upload"
QUERY = "pdf"
_COLUMNS = ["Series", "Colour", "Width", "Style"]


def _frame(style: rs.ReportStyle) -> pd.DataFrame:
    rows = [
        {"Series": n, "Colour": o.colour or "", "Width": o.width, "Style": o.dash or ""}
        for n, o in style.overrides.items()
    ]
    return pd.DataFrame(rows, columns=_COLUMNS)


def load(style: rs.ReportStyle, preset_name: str | None = None) -> None:
    """Copy ``style`` into the widget state. Call from a callback or before the widgets exist."""
    ss = st.session_state
    ss[PRESET] = preset_name or (
        style.name if style.name in rs.PRESETS else rs.PRESETS["Classic"].name
    )
    ss[PAPER], ss[FONT], ss[WIDTH], ss[DASHES] = (
        style.paper,
        style.font,
        style.line_width,
        style.dashes,
    )
    ss[NEGATIVE] = style.negative
    ss[ACCENT_ON], ss[ACCENT] = style.accent is not None, style.accent or DEFAULT_ACCENT
    ss[SERIES_ON] = style.series is not None
    base = style.series or DEFAULT_SERIES
    for i, key in enumerate(SERIES_KEYS):
        ss[key] = base[i % len(base)]
    ss[OVERRIDES] = _frame(style)
    ss[GENERATION] = int(ss.get(GENERATION, 0)) + 1  # a new editor key discards old edits


def _initialise() -> None:
    if PRESET in st.session_state:
        return
    wanted = str(st.query_params.get(QUERY, "Classic"))
    load(rs.preset(wanted), wanted if wanted in rs.PRESETS else "Classic")


def _choose_preset() -> None:
    name = str(st.session_state[PRESET])
    load(rs.preset(name), name)
    if name == "Classic":
        st.query_params.pop(QUERY, None)
    else:
        st.query_params[QUERY] = name
    st.session_state[ERROR] = ""


def _import() -> None:
    uploaded = st.session_state.get(UPLOAD)
    if uploaded is None:
        return
    try:
        style = rs.from_json(uploaded.getvalue().decode("utf-8"))
    except (rs.StyleError, UnicodeDecodeError) as error:
        st.session_state[ERROR] = f"Could not load that style file: {error}"
        return
    load(style, "Classic")
    st.session_state[ERROR] = ""


def _overrides(edited: pd.DataFrame) -> dict[str, rs.SeriesOverride]:
    found: dict[str, rs.SeriesOverride] = {}
    for _, row in edited.iterrows():
        name = str(row["Series"] or "").strip()
        if not name:
            continue
        colour = str(row["Colour"] or "").strip() or None
        width = None if pd.isna(row["Width"]) else float(row["Width"])
        dash = str(row["Style"] or "").strip() or None
        found[name] = rs.SeriesOverride(colour, width, dash)
    return found


def controls(series_names: Sequence[str]) -> rs.ReportStyle:
    """Draw the controls and return the style they describe (Classic if an entry is invalid)."""
    _initialise()
    ss = st.session_state
    st.selectbox("Style preset", list(rs.PRESETS), key=PRESET, on_change=_choose_preset)
    left, right = st.columns(2)
    with left:
        st.selectbox("Paper", list(rs.PAPERS), key=PAPER)
        st.slider("Line width", rs.MIN_WIDTH, rs.MAX_WIDTH, step=0.1, key=WIDTH)
    with right:
        st.selectbox("Font", list(rs.FONTS), key=FONT)
        st.selectbox(
            "Line styles",
            list(rs.DASH_MODES),
            key=DASHES,
            help="Mixed gives each line its own dash pattern, so they stay distinct in print.",
        )
    if st.toggle("Own accent colour (otherwise the interface accent)", key=ACCENT_ON):
        st.color_picker("Accent", key=ACCENT)
    if st.toggle("Set line colours", key=SERIES_ON):
        st.caption("Colours for the first six lines: portfolio, benchmark, then the others.")
        for number, (col, key) in enumerate(
            zip(st.columns(len(SERIES_KEYS)), SERIES_KEYS, strict=True), start=1
        ):
            with col:
                st.color_picker(f"Line {number}", key=key)
    st.caption("Per-series changes: pick a series by name; leave a cell empty to keep its default.")
    edited = st.data_editor(
        ss.get(OVERRIDES, pd.DataFrame(columns=_COLUMNS)),
        key=f"rs_editor_{ss.get(GENERATION, 0)}",
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "Series": st.column_config.SelectboxColumn(options=list(series_names), required=True),
            "Colour": st.column_config.TextColumn(help="#RRGGBB"),
            "Width": st.column_config.NumberColumn(
                min_value=rs.MIN_WIDTH, max_value=rs.MAX_WIDTH, step=0.1
            ),
            "Style": st.column_config.SelectboxColumn(options=list(rs.DASH_PATTERNS)),
        },
    )
    try:
        style = _build(edited)
    except rs.StyleError as error:
        st.error(f"{error}. The default look is used until this is fixed.")
        return rs.PRESETS["Classic"]
    file_left, file_right = st.columns(2)
    with file_left:
        st.download_button(
            "Save this style (JSON)", rs.to_json(style), "report-style.json", "application/json"
        )
    with file_right:
        st.file_uploader("Load a style file", type="json", key=UPLOAD, on_change=_import)
    if ss.get(ERROR):
        st.error(ss[ERROR])
    return style


def _build(edited: pd.DataFrame) -> rs.ReportStyle:
    ss = st.session_state
    style = rs.ReportStyle(
        name=str(ss[PRESET]),
        accent=str(ss[ACCENT]) if ss[ACCENT_ON] else None,
        series=tuple(str(ss[k]) for k in SERIES_KEYS) if ss[SERIES_ON] else None,
        negative=str(ss[NEGATIVE]),
        line_width=float(ss[WIDTH]),
        dashes=str(ss[DASHES]),
        paper=str(ss[PAPER]),
        font=str(ss[FONT]),
        overrides=_overrides(edited),
    )
    preset = rs.preset(style.name)
    unchanged = replace(style, name=preset.name) == preset
    return style if unchanged else replace(style, name="Custom")
