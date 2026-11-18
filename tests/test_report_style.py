"""Report style: validation, JSON round trip, how it reaches the PDF and Excel, and the panel."""

from __future__ import annotations

import io
import json
import re
import zipfile

import pandas as pd
import pytest
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

from portfolio_risk import AnalysisConfig, AnalysisResult, analyse
from portfolio_risk.comparison import compare
from portfolio_risk.report import ReportMeta
from portfolio_risk.report import style as rs
from portfolio_risk.report.excel import build_workbook
from portfolio_risk.report.inputs import ReportInputs
from portfolio_risk.report.look import make_look, use
from portfolio_risk.report.pdf import build_pdf
from portfolio_risk.sample_data import BENCHMARK, generate_sample_prices, sample_weights
from portfolio_risk.ui.tearsheet_tables import named_returns

META = ReportMeta()


@pytest.fixture(scope="module")
def result() -> AnalysisResult:
    return analyse(generate_sample_prices(), sample_weights(), AnalysisConfig(), BENCHMARK)


@pytest.fixture(scope="module")
def inputs(result: AnalysisResult) -> ReportInputs:
    prices = generate_sample_prices()
    other = pd.Series({"SYN_GOVT": 0.6, "SYN_CORP": 0.4})
    comparison = compare(
        prices, {"Current": sample_weights(), "Defensive": other}, result.config, BENCHMARK
    )
    return ReportInputs(
        tearsheet=named_returns(result, prices, BENCHMARK, ["SYN_EQ_US"]),
        comparison=comparison,
        benchmark=BENCHMARK,
    )


def pdf_streams(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    streams = [p.get_contents() for p in reader.pages]
    return "\n".join(c.get_data().decode("latin-1") for c in streams if c is not None)


# ------------------------------------------------------------------ the style itself


def test_every_preset_survives_a_json_round_trip() -> None:
    for name, style in rs.PRESETS.items():
        assert rs.from_json(rs.to_json(style)) == style, name


def test_overrides_survive_a_json_round_trip() -> None:
    style = rs.ReportStyle(overrides={"Current": rs.SeriesOverride("#ff00aa", 2.5, "dotted")})
    assert rs.from_json(rs.to_json(style)).overrides["Current"] == rs.SeriesOverride(
        "#FF00AA", 2.5, "dotted"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"accent": "teal"},
        {"accent": "#12345"},
        {"series": ()},
        {"series": ("#000000",) * 9},
        {"series": ("red",)},
        {"line_width": 0.1},
        {"line_width": 9.0},
        {"dashes": "wavy"},
        {"paper": "Neon"},
        {"font": "Comic"},
        {"name": ""},
    ],
)
def test_invalid_values_are_rejected(change: dict[str, object]) -> None:
    with pytest.raises(rs.StyleError):
        rs.ReportStyle(**change)  # type: ignore[arg-type]


def test_invalid_overrides_are_rejected() -> None:
    for bad in (
        {"colour": "blue"},
        {"width": 0.0},
        {"width": 50.0},
        {"dash": "zigzag"},
    ):
        with pytest.raises(rs.StyleError):
            rs.SeriesOverride(**bad)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not json", "not valid JSON"),
        ("[]", "JSON object"),
        ('{"version": 2}', "unsupported style version"),
        ('{"version": 1, "overrides": []}', "overrides must map"),
        ('{"version": 1, "overrides": {"A": {"colour": "#000000", "size": 3}}}', "unknown"),
        ('{"version": 1, "line_width": "thick"}', "expected a number"),
        ('{"version": 1, "line_width": true}', "expected a number"),
        ('{"version": 1, "series": "#000000"}', "list of colours"),
        ('{"version": 1, "paper": "Neon"}', "paper"),
    ],
)
def test_bad_style_files_are_refused_with_a_reason(text: str, message: str) -> None:
    with pytest.raises(rs.StyleError, match=message):
        rs.from_json(text)


def test_a_style_file_may_leave_settings_out() -> None:
    style = rs.from_json(json.dumps({"version": 1, "paper": "Ivory"}))
    assert style.paper == "Ivory"
    assert style.line_width == rs.ReportStyle().line_width


def test_the_colour_blind_preset_uses_the_okabe_ito_colours() -> None:
    assert rs.PRESETS["Colour-blind safe"].series == rs.OKABE_ITO
    assert len(set(rs.OKABE_ITO)) == len(rs.OKABE_ITO)


def test_mixed_dashes_give_neighbouring_series_different_patterns() -> None:
    style = rs.ReportStyle()
    assert style.dash_for(1) != style.dash_for(2) != style.dash_for(3)
    assert {rs.ReportStyle(dashes="solid").dash_for(i) for i in range(8)} == {"solid"}


def test_distinct_dashes_never_repeat_across_the_first_four_lines() -> None:
    style = rs.ReportStyle(dashes="distinct")
    assert len({style.dash_for(i) for i in range(4)}) == 4
    for name in ("Colour-blind safe", "Black and white print"):
        assert rs.PRESETS[name].dashes == "distinct"


def test_an_unknown_preset_name_falls_back_to_classic() -> None:
    assert rs.preset("nope") == rs.PRESETS["Classic"]


# ------------------------------------------------------------------------- the look


def test_look_resolves_overrides_before_the_series_order() -> None:
    style = rs.ReportStyle(
        series=("#111111", "#222222"),
        overrides={"B": rs.SeriesOverride("#ABCDEF", 3.0, "dash-dot")},
    )
    active = make_look(style)
    assert active.colour("A", 0).hexval() == "0x111111"
    assert active.colour("B", 1).hexval() == "0xabcdef"
    assert active.colour("C", 2).hexval() == "0x111111"  # the order wraps
    assert active.width("B", 1) == 3.0
    assert active.dash("B", 1) == (6, 2, 1, 2)
    assert active.width("A", 0) > active.width("A", 1)  # first line is a little heavier


def test_without_a_series_order_the_first_line_follows_the_accent() -> None:
    active = make_look(rs.ReportStyle(), "#123456")
    assert active.colour("x", 0).hexval() == "0x123456"
    assert active.colour("x", 1).hexval() != "0x123456"


def test_the_style_accent_beats_the_interface_accent() -> None:
    assert make_look(rs.ReportStyle(accent="#AA0000"), "#123456").accent.hexval() == "0xaa0000"


def test_the_look_is_restored_after_use() -> None:
    from portfolio_risk.report.look import look  # noqa: PLC0415

    before = look().style
    with use(make_look(rs.PRESETS["Editorial"])):
        assert look().style.paper == "Ivory"
    assert look().style == before


# ----------------------------------------------------------------------- PDF output


def test_a_serif_style_changes_the_fonts_and_a_tinted_paper_the_background(
    result: AnalysisResult,
) -> None:
    classic = pdf_streams(build_pdf(result, META, None, ["summary"]))
    editorial = pdf_streams(build_pdf(result, META, None, ["summary"], rs.PRESETS["Editorial"]))
    reader = PdfReader(
        io.BytesIO(build_pdf(result, META, None, ["summary"], rs.PRESETS["Editorial"]))
    )
    resources = reader.pages[0]["/Resources"].get_object()
    fonts = {str(f.get_object()["/BaseFont"]) for f in resources["/Font"].values()}  # type: ignore[index]
    assert {"/Times-Roman", "/Times-Bold"} <= fonts
    # the Ivory page tone is #FBF7EE, written by reportlab as three fractions
    assert re.search(r"\.9843\d* \.9686\d* \.9333\d* rg", editorial)
    assert not re.search(r"\.9843\d* \.9686\d* \.9333\d* rg", classic)


def test_a_per_series_override_reaches_the_chart(
    result: AnalysisResult, inputs: ReportInputs
) -> None:
    style = rs.ReportStyle(overrides={"Current": rs.SeriesOverride("#FF00AA", 2.8, "dotted")})
    text = pdf_streams(build_pdf(result, META, inputs, ["comparison"], style))
    assert re.search(r"1 0 \.6666\d* RG", text)  # the override colour
    assert "2.8 w" in text  # its line width
    assert "[1 2] 0 d" in text  # its dotted pattern
    plain = pdf_streams(build_pdf(result, META, inputs, ["comparison"]))
    assert "2.8 w" not in plain


def test_styles_do_not_leak_between_reports(result: AnalysisResult) -> None:
    build_pdf(result, META, None, ["summary"], rs.PRESETS["Editorial"])
    after = pdf_streams(build_pdf(result, META, None, ["summary"]))
    assert not re.search(r"\.9843\d* \.9686\d* \.9333\d* rg", after)


# --------------------------------------------------------------------- Excel output


def test_the_workbook_chart_takes_the_style_colours(
    result: AnalysisResult, inputs: ReportInputs
) -> None:
    style = rs.ReportStyle(
        series=("#AA0000", "#00AA00", "#0000AA"),
        overrides={"Defensive": rs.SeriesOverride(dash="dotted")},
    )
    data = build_workbook(result, META, inputs, ["comparison"], style)
    with zipfile.ZipFile(io.BytesIO(data)) as book:
        charts = [book.read(n).decode() for n in book.namelist() if "charts/chart" in n]
    xml = "".join(charts)
    assert 'val="aa0000"' in xml
    assert 'val="00aa00"' in xml
    assert 'prstDash val="sysDot"' in xml


# -------------------------------------------------------------------------- the panel


def _panel_app() -> None:
    from portfolio_risk.ui import app  # noqa: PLC0415

    app.main()


def _open_panel() -> AppTest:
    app = AppTest.from_function(_panel_app, default_timeout=90).run()
    assert not app.exception
    return app


def test_the_panel_offers_every_preset_and_starts_on_classic() -> None:
    app = _open_panel()
    preset = next(s for s in app.selectbox if s.label == "Style preset")
    assert preset.value == "Classic"
    assert set(preset.options) == set(rs.PRESETS)


def test_choosing_a_preset_loads_its_values_into_the_controls() -> None:
    app = _open_panel()
    next(s for s in app.selectbox if s.label == "Style preset").select("Editorial").run()
    assert not app.exception
    assert next(s for s in app.selectbox if s.label == "Paper").value == "Ivory"
    assert next(s for s in app.selectbox if s.label == "Font").value == "Serif"
    assert app.query_params["pdf"] == "Editorial"


def test_a_preset_in_the_page_address_is_applied() -> None:
    app = AppTest.from_function(_panel_app, default_timeout=90)
    app.query_params["pdf"] = "Black and white print"
    app.run()
    assert not app.exception
    assert next(s for s in app.selectbox if s.label == "Style preset").value == (
        "Black and white print"
    )


def test_a_bad_preset_in_the_page_address_falls_back_to_classic() -> None:
    app = AppTest.from_function(_panel_app, default_timeout=90)
    app.query_params["pdf"] = "nonsense"
    app.run()
    assert not app.exception
    assert next(s for s in app.selectbox if s.label == "Style preset").value == "Classic"
