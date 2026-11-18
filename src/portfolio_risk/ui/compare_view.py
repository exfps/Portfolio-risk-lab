"""The Compare tab: save weight sets by name and set several side by side."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile

from portfolio_risk import PortfolioRiskError
from portfolio_risk.analysis import AnalysisResult
from portfolio_risk.comparison import (
    MAX_NAME,
    MAX_PORTFOLIOS,
    MAX_SAVED,
    Comparison,
    compare,
    weight_sets_from_json,
    weight_sets_to_json,
)
from portfolio_risk.tearsheet import calendar_years
from portfolio_risk.ui import charts, formatting, report_state, tearsheet_tables, theme
from portfolio_risk.ui.compare_tables import (
    concentration_frame,
    correlation_frame,
    weights_frame,
)

SAVED = "saved_portfolios"  # name -> {asset: weight}
CHOSEN = "compare_chosen"
CURRENT = "Current weights"
LOADED = "compare_loaded_file"


def _saved() -> dict[str, dict[str, float]]:
    store: dict[str, dict[str, float]] = st.session_state.setdefault(SAVED, {})
    return store


def _save_current(weights: pd.Series) -> None:
    name = str(st.session_state.get("compare_name", "")).strip()
    store = _saved()
    if not name:
        st.session_state["compare_message"] = ("error", "Give the portfolio a name first.")
    elif name == CURRENT:
        st.session_state["compare_message"] = ("error", f"{CURRENT!r} is reserved.")
    elif len(name) > MAX_NAME:
        st.session_state["compare_message"] = (
            "error",
            f"Names are limited to {MAX_NAME} characters.",
        )
    elif name not in store and len(store) >= MAX_SAVED:
        st.session_state["compare_message"] = ("error", f"At most {MAX_SAVED} saved portfolios.")
    else:
        store[name] = {str(k): float(v) for k, v in weights.items() if v > 0}
        st.session_state["compare_message"] = ("ok", f"Saved {name!r}.")
        st.session_state["compare_name"] = ""


def _remove(name: str) -> None:
    _saved().pop(name, None)
    chosen = st.session_state.get(CHOSEN, [])
    st.session_state[CHOSEN] = [c for c in chosen if c != name]


def _load(upload: UploadedFile) -> None:
    try:
        sets = weight_sets_from_json(upload.getvalue())
    except PortfolioRiskError as error:
        st.error(str(error))
        return
    store = _saved()
    if len(store) + len([n for n in sets if n not in store]) > MAX_SAVED:
        st.error(f"That would exceed {MAX_SAVED} saved portfolios. Remove some first.")
        return
    for name, weights in sets.items():
        store[name] = {str(k): float(v) for k, v in weights.items()}
    st.success(f"Loaded {len(sets)} portfolio{'s' if len(sets) != 1 else ''}.")


def _controls(current: pd.Series) -> list[str]:
    store = _saved()
    with st.expander("Saved portfolios", expanded=not store):
        left, right = st.columns([3, 1])
        left.text_input(
            "Save the current weights as",
            key="compare_name",
            max_chars=MAX_NAME,
            placeholder="for example Growth tilt",
        )
        right.markdown("<div style='height:1.9rem'></div>", unsafe_allow_html=True)
        right.button("Save", on_click=_save_current, args=(current,), key="compare_save")
        message = st.session_state.pop("compare_message", None)
        if message:
            (st.success if message[0] == "ok" else st.error)(message[1])
        if store:
            pick = st.selectbox("Saved portfolio", list(store), key="compare_remove_pick")
            st.button("Remove", on_click=_remove, args=(pick,), key="compare_remove")
            st.download_button(
                "Download saved portfolios (JSON)",
                weight_sets_to_json({n: pd.Series(w) for n, w in store.items()}),
                file_name="portfolios.json",
                mime="application/json",
            )
        upload = st.file_uploader("Load portfolios from JSON", type=["json"], key="compare_upload")
        if upload is not None and st.session_state.get(LOADED) != upload.file_id:
            st.session_state[LOADED] = upload.file_id
            _load(upload)
    options = [CURRENT, *store]
    chosen: list[str] = st.multiselect(
        "Portfolios to compare",
        options,
        default=[c for c in st.session_state.get(CHOSEN, [CURRENT]) if c in options],
        key=CHOSEN,
        max_selections=MAX_PORTFOLIOS,
    )
    return chosen


def render(
    result: AnalysisResult,
    prices: pd.DataFrame,
    benchmark: str | None,
    palette: theme.Palette,
) -> None:
    st.caption(
        "Save weight sets under a name, then compare them on exactly the same dates. "
        "Differences come from the weights, not from the sample."
    )
    chosen = _controls(result.weights)
    report_state.forget(report_state.COMPARISON)  # set again below once a comparison succeeds
    if len(chosen) < 2:
        st.info(
            "Choose at least two portfolios. Save the current weights, change them in the "
            "Weights panel, and save again to build a second one."
        )
        return
    store = _saved()
    sets: dict[str, pd.Series] = {}
    for name in chosen:
        sets[name] = result.weights if name == CURRENT else pd.Series(store[name])
    unavailable = {n: [a for a in w.index if a not in prices.columns] for n, w in sets.items()}
    skipped = {n: m for n, m in unavailable.items() if m}
    for name, missing in skipped.items():
        st.warning(f"{name!r} uses holdings that are not in the loaded data: {', '.join(missing)}.")
    sets = {n: w for n, w in sets.items() if n not in skipped}
    if len(sets) < 2:
        st.info("Fewer than two of the chosen portfolios can be compared with the loaded data.")
        return
    try:
        comparison = compare(prices, sets, result.config, benchmark)
    except PortfolioRiskError as error:
        st.error(str(error))
        return
    report_state.remember(
        report_state.COMPARISON, report_state.signature(prices, result.weights), comparison
    )
    _show(comparison, palette)


def _show(comparison: Comparison, palette: theme.Palette) -> None:
    st.caption(
        f"{formatting.day(comparison.start)} to {formatting.day(comparison.end)}  |  "
        f"{comparison.observations} observations  |  constant weights"
    )
    st.subheader("Key statistics")
    st.markdown(
        formatting.html_table(tearsheet_tables.metrics_frame(comparison.table)),
        unsafe_allow_html=True,
    )
    st.subheader("Holdings")
    st.markdown(formatting.html_table(weights_frame(comparison.weights)), unsafe_allow_html=True)
    st.markdown(
        formatting.html_table(concentration_frame(comparison.concentration)),
        unsafe_allow_html=True,
    )
    st.subheader("Cumulative growth of 1")
    st.altair_chart(
        charts.comparison_chart(comparison.wealth, title="Growth of 1", fmt=".2f", p=palette)
    )
    st.subheader("Drawdowns")
    st.altair_chart(
        charts.comparison_chart(comparison.drawdowns, title="Drawdown", fmt="%", p=palette)
    )
    st.subheader("Returns by calendar year")
    st.altair_chart(
        charts.year_bars(
            calendar_years({n: comparison.returns[n] for n in comparison.names}), palette
        )
    )
    st.subheader("Correlation of portfolio returns")
    st.markdown(
        formatting.html_table(correlation_frame(comparison.correlation)), unsafe_allow_html=True
    )
    st.caption(
        "Every portfolio is evaluated over the dates on which all the holdings in the "
        "comparison have prices. Weights are held constant (rebalanced every period). "
        "Past statistics describe history; they are not forecasts."
    )
