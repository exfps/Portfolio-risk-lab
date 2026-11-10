"""Theme customizer: colour maths, presets, stylesheet and chart use, and the page address."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from portfolio_risk.sample_data import generate_sample_prices
from portfolio_risk.ui import appearance, charts, theme
from portfolio_risk.ui.styles import stylesheet

APP = Path(__file__).resolve().parents[1] / "src" / "portfolio_risk" / "ui" / "app.py"


def test_contrast_ratio_matches_wcag_reference_values() -> None:
    assert theme.contrast_ratio("#FFFFFF", "#000000") == pytest.approx(21.0)
    assert theme.contrast_ratio("#777777", "#777777") == pytest.approx(1.0)
    assert theme.contrast_ratio("#767676", "#FFFFFF") == pytest.approx(4.54, abs=0.02)


def test_every_preset_is_a_complete_readable_palette() -> None:
    assert theme.DEFAULT.name in theme.PRESETS
    for palette in theme.PRESETS.values():
        for field in ("background", "surface", "elevated", "border", "text", "muted", "accent"):
            assert theme.is_hex(getattr(palette, field)), (palette.name, field)
        assert theme.contrast_ratio(palette.text, palette.background) >= 7
        assert theme.contrast_ratio(palette.muted, palette.background) >= 4.5
        assert theme.contrast_ratio(palette.accent, palette.background) >= 3


def test_with_accent_lightens_a_colour_that_is_too_dark() -> None:
    dark = theme.with_accent(theme.DEFAULT, "#1A2A4A")
    assert dark.accent != "#1A2A4A"
    assert theme.contrast_ratio(dark.accent, dark.background) >= theme.MIN_ACCENT_CONTRAST
    bright = theme.with_accent(theme.DEFAULT, "#ff8800")
    assert bright.accent == "#FF8800"
    assert bright.background == theme.DEFAULT.background


def test_with_accent_rejects_non_hex() -> None:
    for bad in ("teal", "#12", "#GGGGGG", "", "123456"):
        with pytest.raises(ValueError, match="#RRGGBB"):
            theme.with_accent(theme.DEFAULT, bad)


def test_on_paper_darkens_a_pale_accent_for_printing() -> None:
    gold = theme.on_paper("#C9A96E")
    assert theme.contrast_ratio(gold, "#FFFFFF") >= theme.MIN_ACCENT_CONTRAST
    assert theme.on_paper("#1F3A5F") == "#1F3A5F"


def test_stylesheet_builds_for_every_preset_and_size() -> None:
    for palette in theme.PRESETS.values():
        for px in theme.FONT_SIZES.values():
            css = stylesheet(palette, px)
            assert palette.background in css
            assert palette.accent in css
            assert f"font-size: {px}px" in css
            assert "${" not in css


def test_charts_take_their_colours_from_the_palette() -> None:
    wealth = (1 + generate_sample_prices().iloc[:, 0].pct_change().dropna()).cumprod()
    default = charts.wealth_chart(wealth).to_json()
    graphite = charts.wealth_chart(wealth, theme.PRESETS["Graphite"]).to_json()
    assert theme.DEFAULT.accent in default
    assert theme.PRESETS["Graphite"].accent in graphite
    assert theme.DEFAULT.accent not in graphite


def test_resolve_falls_back_for_unknown_values() -> None:
    look = appearance.resolve("No such preset", "not-a-colour", "Gigantic")
    assert look.palette == theme.DEFAULT
    assert look.base_px == theme.FONT_SIZES["Comfortable"]
    custom = appearance.resolve("Graphite", "#FF8800", "Large")
    assert custom.palette.accent == "#FF8800"
    assert custom.palette.background == theme.PRESETS["Graphite"].background
    assert custom.base_px == 18


def test_page_address_selects_the_theme() -> None:
    app = AppTest.from_file(str(APP), default_timeout=60)
    app.query_params["theme"] = "Obsidian gold"
    app.query_params["size"] = "Large"
    app.run()
    assert not app.exception
    css = next(m.value for m in app.markdown if m.value.startswith("<style>"))
    assert theme.PRESETS["Obsidian gold"].background in css
    assert "font-size: 18px" in css
    assert next(b for b in app.selectbox if b.label == "Palette").value == "Obsidian gold"


def test_choosing_a_palette_updates_the_address_and_the_page() -> None:
    app = AppTest.from_file(str(APP), default_timeout=60).run()
    next(b for b in app.selectbox if b.label == "Palette").select("Forest").run()
    assert not app.exception
    assert app.query_params["theme"] == "Forest"
    css = next(m.value for m in app.markdown if m.value.startswith("<style>"))
    assert theme.PRESETS["Forest"].accent in css


def test_unknown_values_in_the_address_are_ignored() -> None:
    app = AppTest.from_file(str(APP), default_timeout=60)
    app.query_params["theme"] = "<script>"
    app.query_params["accent"] = "red"
    app.query_params["size"] = "huge"
    app.run()
    assert not app.exception
    assert next(b for b in app.selectbox if b.label == "Palette").value == theme.DEFAULT.name


def test_custom_accent_reaches_the_stylesheet() -> None:
    app = AppTest.from_file(str(APP), default_timeout=60)
    app.query_params["accent"] = "#E07A2F"
    app.run()
    css = next(m.value for m in app.markdown if m.value.startswith("<style>"))
    assert "#E07A2F" in css


def test_export_buttons_are_offered_with_results() -> None:
    app = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not app.exception
    labels = {str(b.proto.label) for b in app.get("download_button")}
    assert {"Download PDF report", "Download Excel"} <= labels
