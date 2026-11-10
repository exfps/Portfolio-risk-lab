"""Streamlit interface for Portfolio Risk Lab.

Start it with ``portfolio-risk-lab`` (or ``python -m portfolio_risk``), or directly with
``streamlit run src/portfolio_risk/ui/app.py``. All numbers come from ``portfolio_risk.analyse``;
this module only collects inputs and displays results.
"""

from __future__ import annotations

import hashlib
import html
import inspect
import io
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitAPIException

from portfolio_risk import (
    AnalysisConfig,
    AnalysisResult,
    PortfolioRiskError,
    __version__,
    analyse,
    load_prices,
    load_weights,
    vision,
)
from portfolio_risk.io.validation import infer_periods_per_year
from portfolio_risk.sample_data import BENCHMARK, generate_sample_prices, sample_weights
from portfolio_risk.ui import appearance, charts, formatting, market, styles, theme
from portfolio_risk.ui.inputs import (
    SKIP,
    positions_from_review,
    review_frame,
    weights_frame,
    weights_from_frame,
)

SAMPLE = "Synthetic sample"
UPLOAD = "Upload CSV files"
DOWNLOAD = "Search and download"
NO_BENCHMARK = "None"
RF_SOURCE = "risk_free_source"
IMPORTED = "imported_weights"  # (digest of the prices file, weights, notes, serial)
REVIEW = "screenshot_review"  # (table of positions read from the screenshot, extraction)
FREQUENCIES = {
    252: "252: daily, trading days",
    365: "365: daily, every calendar day",
    52: "52: weekly",
    12: "12: monthly",
    4: "4: quarterly",
    1: "1: annual",
}
CONFIDENCE_OPTIONS = (90.0, 95.0, 97.5, 99.0)


# Newer Streamlit can render only the selected tab. Older versions render every tab each time,
# which is correct but slower, so this is detected rather than required.
_LAZY_TABS = "on_change" in inspect.signature(st.tabs).parameters


def _tabs(names: list[str]) -> dict[str, Any]:
    if not _LAZY_TABS:
        return dict(zip(names, st.tabs(names), strict=True))
    return dict(
        zip(names, st.tabs(names, key="tab|" + "|".join(names), on_change="rerun"), strict=True)
    )


def _is_open(tab: Any) -> bool:
    return bool(getattr(tab, "open", True))


def _notice(text: str) -> None:
    """A quiet, on-palette notice for neutral information. Text must be a trusted constant."""
    st.markdown(f'<div class="notice">{html.escape(text)}</div>', unsafe_allow_html=True)


@dataclass(frozen=True)
class DataChoice:
    prices: pd.DataFrame
    weights: pd.Series | None
    synthetic: bool
    origin: str = ""


@st.cache_data(show_spinner=False)
def _sample_prices() -> pd.DataFrame:
    return generate_sample_prices()


@st.cache_data(show_spinner=False)
def _parse_prices(raw: bytes, sort_dates: bool) -> pd.DataFrame:
    return load_prices(io.BytesIO(raw), sort_dates=sort_dates)


@st.cache_data(show_spinner=False)
def _parse_weights(raw: bytes) -> pd.Series:
    return load_weights(io.BytesIO(raw))


@st.cache_data(show_spinner=False)
def _template_files() -> tuple[bytes, bytes]:
    prices = _sample_prices().to_csv(float_format="%.4f", lineterminator="\n")
    weights = sample_weights().to_csv(float_format="%.2f", lineterminator="\n")
    return prices.encode(), weights.encode()


@st.cache_data(show_spinner=False, max_entries=16)
def _analysis(
    prices: pd.DataFrame,
    weights: pd.Series,
    config: AnalysisConfig,
    benchmark: str | None,
    normalise: bool,
) -> AnalysisResult:
    """Cached so that switching tabs or reopening a section does not recompute the metrics."""
    return analyse(prices, weights, config, benchmark, normalise_weights=normalise)


def _sidebar_data_source() -> tuple[str, bytes | None, bytes | None, bool]:
    st.header("Data")
    sources = [SAMPLE, UPLOAD] if market.download_disabled() else [SAMPLE, UPLOAD, DOWNLOAD]
    mode = st.radio("Source", sources, label_visibility="collapsed")
    if mode == SAMPLE:
        st.caption("Simulated prices for six synthetic assets. Not real market data.")
        return mode, None, None, False
    if mode == DOWNLOAD:
        return mode, market.sidebar_download(), None, False
    prices_file = st.file_uploader(
        "Prices CSV", type="csv", help="date column, then one column per ticker"
    )
    weights_file = st.file_uploader(
        "Weights CSV (optional)", type="csv", help="ticker,weight. Otherwise weights are equal."
    )
    sort_dates = st.checkbox("Sort dates if out of order", value=False)
    with st.expander("Need a template?"):
        template_prices, template_weights = _template_files()
        st.download_button("Sample prices CSV", template_prices, "sample_prices.csv", "text/csv")
        st.download_button("Sample weights CSV", template_weights, "sample_weights.csv", "text/csv")
    return (
        mode,
        prices_file.getvalue() if prices_file is not None else None,
        weights_file.getvalue() if weights_file is not None else None,
        sort_dates,
    )


def _imported_weights(prices_raw: bytes | None) -> tuple[pd.Series, str] | None:
    """Weights confirmed from a screenshot, if they were made for this very prices file."""
    saved = st.session_state.get(IMPORTED)
    if saved is None or prices_raw is None:
        return None
    digest, weights, _notes, serial = saved
    if digest != hashlib.sha256(prices_raw).hexdigest():
        st.session_state.pop(IMPORTED, None)
        return None
    return weights, f"import{serial}"


def _read_data(
    mode: str, prices_raw: bytes | None, weights_raw: bytes | None, sort_dates: bool
) -> DataChoice | None:
    """Parse the chosen inputs. Returns None when an upload is still awaited."""
    if mode == SAMPLE:
        return DataChoice(_sample_prices(), sample_weights(), synthetic=True, origin="sample")
    if prices_raw is None:
        return None
    prices = _parse_prices(prices_raw, sort_dates)
    if weights_raw is not None:
        return DataChoice(prices, _parse_weights(weights_raw), synthetic=False, origin="file")
    imported = _imported_weights(prices_raw)
    if imported is not None:
        return DataChoice(prices, imported[0], synthetic=False, origin=imported[1])
    return DataChoice(prices, None, synthetic=False, origin="equal")


def _sidebar_settings(
    prices: pd.DataFrame, synthetic: bool, preferred: str | None = None
) -> tuple[AnalysisConfig, str | None, bool]:
    st.header("Settings")
    inferred = infer_periods_per_year(pd.DatetimeIndex(prices.index)) or 252
    options = list(FREQUENCIES)
    periods = st.selectbox(
        "Periods per year",
        options,
        index=options.index(inferred) if inferred in options else 0,
        format_func=lambda value: FREQUENCIES[value],
        help="Annualisation factor. Detected from the dates; change it if it is wrong.",
    )
    risk_free = st.number_input(
        "Risk-free rate (annual, %)", min_value=-99.0, value=0.0, step=0.25, format="%.2f"
    )
    st.text_input(
        "Risk-free rate source (optional)",
        key=RF_SOURCE,
        placeholder="for example 3-month SAIBOR, date",
        help="Recorded in the Assumptions tab so the number can be traced. Not used in any maths.",
    )
    mar = st.number_input(
        "Minimum acceptable return for Sortino (annual, %)",
        min_value=-99.0,
        value=0.0,
        step=0.25,
        format="%.2f",
    )
    levels = st.multiselect(
        "VaR confidence levels (%)",
        CONFIDENCE_OPTIONS,
        default=[95.0, 99.0],
        format_func=lambda value: f"{value:g}",
    )
    choices = [NO_BENCHMARK, *map(str, prices.columns)]
    if preferred in choices:
        default = choices.index(str(preferred))
    else:
        default = choices.index(BENCHMARK) if synthetic and BENCHMARK in choices else 0
    benchmark = st.selectbox(
        "Benchmark", choices, index=default, help="A price column to compare against."
    )
    normalise = st.checkbox("Rescale weights that do not sum to 1", value=False)
    config = AnalysisConfig(
        periods_per_year=periods if periods is not None else 252,
        risk_free_annual=risk_free / 100.0,
        mar_annual=mar / 100.0,
        confidence_levels=tuple(level / 100.0 for level in levels) or (0.95,),
    )
    return config, None if benchmark in (None, NO_BENCHMARK) else benchmark, normalise


def _token_note(extraction: vision.Extraction) -> str:
    if extraction.input_tokens is None and extraction.output_tokens is None:
        return f"Model {extraction.model}. The provider did not report token usage."
    return (
        f"Model {extraction.model}. Tokens used: {extraction.input_tokens or '?'} in, "
        f"{extraction.output_tokens or '?'} out. Your provider bills you for these."
    )


def _read_screenshot(
    provider: vision.Provider, model: str, key: str, image: bytes, columns: list[str]
) -> None:
    try:
        with st.spinner("Reading the screenshot..."):
            client = vision.VisionClient(provider, key, model)
            extraction = vision.extract_positions(client, image)
    except PortfolioRiskError as error:
        st.session_state.pop(REVIEW, None)
        st.error(str(error))
        return
    st.session_state[REVIEW] = (review_frame(extraction.positions, columns), extraction)


def _review_screenshot(prices_raw: bytes, columns: list[str]) -> None:
    saved = st.session_state.get(REVIEW)
    if saved is None:
        return
    frame, extraction = saved
    st.markdown("**Check every row against your screenshot.** The model can misread figures.")
    for note in extraction.warnings:
        st.warning(note)
    st.caption(_token_note(extraction))
    edited = st.data_editor(
        frame,
        key=f"review|{extraction.model}|{len(frame)}",
        hide_index=True,
        num_rows="fixed",
        column_config={
            "ticker": st.column_config.TextColumn("Read as", disabled=True),
            "market_value": st.column_config.NumberColumn("Market value", min_value=0.0),
            "weight_percent": st.column_config.NumberColumn(
                "Weight %", min_value=0.0, max_value=100.0
            ),
            "price_column": st.column_config.SelectboxColumn(
                "Price column", options=[SKIP, *columns], required=True
            ),
        },
    )
    st.caption(
        "Map each row to a column of your prices file, or skip it. Use one figure for all rows: "
        "market values, or percentages."
    )
    if st.button("Use as weights"):
        positions, skipped = positions_from_review(pd.DataFrame(edited))
        try:
            weights, notes = vision.weights_from_positions(positions)
        except PortfolioRiskError as error:
            st.error(str(error))
            return
        if skipped:
            notes = [*notes, f"Not mapped to a price column, so left out: {skipped}."]
        serial = int(st.session_state.get(IMPORTED, (None, None, None, 0))[3]) + 1
        digest = hashlib.sha256(prices_raw).hexdigest()
        st.session_state[IMPORTED] = (digest, weights, notes, serial)
        st.session_state.pop(REVIEW, None)
        st.rerun()


@st.fragment
def _screenshot_panel(data: DataChoice, benchmark: str | None, prices_raw: bytes | None) -> None:
    """Optional: read positions from a screenshot with the user's own API key."""
    if data.synthetic or prices_raw is None or vision.import_disabled():
        return
    columns = [str(name) for name in data.prices.columns if str(name) != benchmark]
    with st.expander("Import positions from a screenshot (optional)"):
        st.caption(
            "An AI model reads your screenshot, using an API key you provide. The image is sent "
            "to that provider. The key is kept in memory for this session only, never saved or "
            "logged. The result is a suggestion: you review it before it is used."
        )
        provider = st.selectbox(
            "Provider", vision.PROVIDERS, format_func=lambda item: item.label, key="provider"
        )
        st.caption(provider.note)
        model = st.text_input("Model", value=provider.default_model, key=f"model|{provider.key}")
        api_key = st.text_input("API key", type="password", key="api_key")
        upload = st.file_uploader("Screenshot", type=["png", "jpg", "jpeg", "webp"], key="shot")
        agreed = st.checkbox(f"I understand this image will be sent to {provider.label}.")
        ready = bool(upload is not None and api_key.strip() and model.strip() and agreed)
        if st.button("Read screenshot", disabled=not ready) and upload is not None:
            _read_screenshot(provider, model, api_key, upload.getvalue(), columns)
        _review_screenshot(prices_raw, columns)


def _imported_notice(prices_raw: bytes | None) -> None:
    saved = st.session_state.get(IMPORTED)
    if saved is None or prices_raw is None:
        return
    for note in saved[2]:
        st.warning(note)
    _notice("Weights were imported from a screenshot and confirmed by you.")
    if st.button("Remove imported weights"):
        st.session_state.pop(IMPORTED, None)
        st.rerun()


def _static_table(frame: pd.DataFrame) -> None:
    """Small read-only table without Streamlit's table component (see ``html_table``)."""
    st.markdown(formatting.html_table(frame), unsafe_allow_html=True)


def _weights_editor(data: DataChoice, benchmark: str | None) -> pd.Series:
    tickers = [str(name) for name in data.prices.columns if str(name) != benchmark]
    frame = weights_frame(tickers, data.weights)
    with st.expander("Weights"):
        edited = st.data_editor(
            frame,
            key=f"weights|{data.origin}|{benchmark}|{'|'.join(frame['ticker'])}",
            hide_index=True,
            disabled=["ticker"],
            num_rows="fixed",
            column_config={
                "ticker": st.column_config.TextColumn("Asset"),
                "weight": st.column_config.NumberColumn(
                    "Weight", min_value=0.0, step=0.01, format="%.4f"
                ),
            },
        )
        weights = weights_from_frame(pd.DataFrame(edited))
        total = float(weights.sum(skipna=True))
        st.caption(f"Weights sum to {total:.4f}. They must sum to 1, or tick the rescale option.")
    return weights


def _offer(label: str, build: Callable[[], bytes], name: str, mime: str, key: str) -> None:
    """A download button that builds its file only when clicked, where Streamlit allows it."""
    try:
        st.download_button(label, data=build, file_name=name, mime=mime, key=key)
    except StreamlitAPIException:  # older Streamlit wants the bytes up front
        st.download_button(label, data=build(), file_name=name, mime=mime, key=key)


def _render_exports(result: AnalysisResult, source: str, palette: theme.Palette) -> None:
    try:
        from portfolio_risk.report import ReportMeta  # noqa: PLC0415 - optional extra
        from portfolio_risk.report.excel import build_workbook  # noqa: PLC0415
        from portfolio_risk.report.pdf import build_pdf  # noqa: PLC0415
    except ImportError:
        st.caption('PDF and Excel export need the report extra: pip install -e ".[app]"')
        return
    meta = ReportMeta(
        source_note=source,
        risk_free_source=str(st.session_state.get(RF_SOURCE, "")).strip(),
        accent=theme.on_paper(palette.accent),
    )
    stamp = pd.Timestamp(result.end).strftime("%Y%m%d")
    left, middle, _ = st.columns([1.3, 1, 5])
    with left:
        _offer(
            "Download PDF report",
            lambda: build_pdf(result, meta),
            f"portfolio-report-{stamp}.pdf",
            "application/pdf",
            "dl_pdf",
        )
    with middle:
        _offer(
            "Download Excel",
            lambda: build_workbook(result, meta),
            f"portfolio-report-{stamp}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "dl_xlsx",
        )


def _render_headline(result: AnalysisResult) -> None:
    for column, (label, value) in zip(
        st.columns(6), formatting.headline_metrics(result), strict=True
    ):
        column.metric(label, value)


def _render_performance(result: AnalysisResult, palette: theme.Palette) -> None:
    st.altair_chart(charts.wealth_chart(result.wealth, palette))
    st.altair_chart(charts.drawdown_chart(result.drawdowns, palette))
    _static_table(formatting.drawdown_table(result))


def _render_risk(result: AnalysisResult, palette: theme.Palette) -> None:
    st.markdown("**Value at Risk and Conditional VaR, one period**")
    _static_table(formatting.var_table(result))
    st.caption(
        "Shown as positive losses. Historical figures use the observed returns; parametric "
        "figures assume a normal distribution and understate fat tails."
    )
    left, right = st.columns(2)
    left.metric("Concentration (HHI)", formatting.ratio(result.hhi, 3))
    right.metric("Effective positions", formatting.ratio(result.effective_positions, 2))
    st.altair_chart(charts.risk_contribution_chart(result.risk_contribution, palette))
    _static_table(formatting.asset_table(result))


def _render_assumptions(result: AnalysisResult) -> None:
    config = result.config
    source = str(st.session_state.get(RF_SOURCE, "")).strip()
    rf_note = formatting.risk_free_note(source)
    st.markdown(
        f"""
- **Returns:** simple period returns, `P_t / P_(t-1) - 1`, from {result.observations}
  observations between {formatting.day(result.start)} and {formatting.day(result.end)}.
- **Weights:** constant, long-only, rebalanced to target every period. Buy-and-hold drift is
  not modelled.
- **Annualisation:** {config.periods_per_year} periods per year. Volatility and ratios scale
  by the square root of this, which assumes returns are serially uncorrelated.
- **Risk-free rate:** {config.risk_free_annual:.2%} annual{rf_note}.
  **Minimum acceptable return:** {config.mar_annual:.2%} annual.
- **VaR and CVaR:** positive one-period losses. Historical uses linear-interpolated quantiles.
- **Prices:** assumed to be in one currency and adjusted for splits and dividends. This is
  not checked.

Full definitions and limitations are in `docs/methodology.md`. These figures describe the
history you supplied. They are not predictions or investment advice.
"""
    )


def _render_results(
    result: AnalysisResult, *, synthetic: bool, palette: theme.Palette, source: str
) -> None:
    if synthetic:
        _notice("Synthetic sample data, simulated for demonstration. It is not a real market.")
    for note in result.warnings:
        st.warning(note)
    st.caption(
        f"{formatting.day(result.start)} to {formatting.day(result.end)}  |  "
        f"{result.observations} observations  |  constant weights"
    )
    _render_headline(result)
    _render_exports(result, source, palette)

    names = ["Performance", "Risk", "Correlation"]
    benchmark_table = formatting.benchmark_table(result)
    if benchmark_table is not None:
        names.append("Benchmark")
    names.append("Assumptions")
    tabs = _tabs(names)

    with tabs["Performance"]:
        if _is_open(tabs["Performance"]):
            _render_performance(result, palette)
    with tabs["Risk"]:
        if _is_open(tabs["Risk"]):
            _render_risk(result, palette)
    with tabs["Correlation"]:
        if _is_open(tabs["Correlation"]):
            st.altair_chart(charts.correlation_heatmap(result.correlation, palette))
    if benchmark_table is not None:
        with tabs["Benchmark"]:
            if _is_open(tabs["Benchmark"]):
                _static_table(benchmark_table)
    with tabs["Assumptions"]:
        if _is_open(tabs["Assumptions"]):
            _render_assumptions(result)


def main() -> None:
    st.set_page_config(page_title="Portfolio Risk Lab", layout="wide")
    look = appearance.current()
    st.markdown(styles.stylesheet(look.palette, look.base_px), unsafe_allow_html=True)
    st.title("Portfolio Risk Lab")
    st.caption(f"Performance and risk analytics for a constant-weight portfolio  |  v{__version__}")

    with st.sidebar:
        mode, prices_raw, weights_raw, sort_dates = _sidebar_data_source()
        appearance.controls()

    try:
        data = _read_data(mode, prices_raw, weights_raw, sort_dates)
    except PortfolioRiskError as error:
        st.error(str(error))
        st.stop()
    if data is None:
        _notice(
            "Choose tickers and download prices in the sidebar."
            if mode == DOWNLOAD
            else "Upload a prices CSV in the sidebar, or switch to the synthetic sample."
        )
        st.stop()

    with st.sidebar:
        try:
            config, benchmark, normalise = _sidebar_settings(
                data.prices,
                data.synthetic,
                market.downloaded_benchmark() if mode == DOWNLOAD else None,
            )
        except PortfolioRiskError as error:
            st.error(str(error))
            st.stop()

    _screenshot_panel(data, benchmark, prices_raw)
    weights = _weights_editor(data, benchmark)
    try:
        result = _analysis(data.prices, weights, config, benchmark, normalise)
    except PortfolioRiskError as error:
        st.error(str(error))
        st.stop()
    if data.origin.startswith("import"):
        _imported_notice(prices_raw)
    sources = {
        SAMPLE: "Synthetic sample data (simulated, not market data)",
        UPLOAD: "Uploaded CSV file",
        DOWNLOAD: market.downloaded_source(),
    }
    _render_results(
        result, synthetic=data.synthetic, palette=look.palette, source=sources.get(mode, "")
    )


if __name__ == "__main__":
    main()
