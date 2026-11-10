"""Drives the real Streamlit script with Streamlit's own test harness (no browser)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import FileUploader, Selectbox

from fake_provider import Fake
from portfolio_risk.sample_data import generate_sample_prices

APP = Path(__file__).resolve().parents[1] / "src" / "portfolio_risk" / "ui" / "app.py"
ENTRY = Path(__file__).resolve().parents[1] / "streamlit_app.py"


def run(path: Path = APP) -> AppTest:
    return AppTest.from_file(str(path), default_timeout=60).run()


def selectbox(app: AppTest, label: str) -> Selectbox[Any]:
    return next(box for box in app.selectbox if box.label == label)


def metric_values(app: AppTest) -> dict[str, str]:
    return {metric.label: metric.value for metric in app.metric}


def test_sample_data_renders_every_section() -> None:
    app = run()
    assert not app.exception
    assert not app.error
    assert not app.warning
    assert [tab.label for tab in app.tabs] == [
        "Performance",
        "Risk",
        "Correlation",
        "Benchmark",
        "Assumptions",
    ]
    metrics = metric_values(app)
    assert metrics["Total return"] == "22.66%"
    assert metrics["Sharpe"] == "0.71"
    assert metrics["Max drawdown"] == "-11.65%"
    assert any("synthetic" in block.value.lower() for block in app.markdown)


def test_the_entry_point_for_hosted_deployments_runs_the_same_app() -> None:
    app = run(ENTRY)
    assert not app.exception
    assert metric_values(app)["Total return"] == "22.66%"


def test_upload_mode_waits_for_a_file_instead_of_failing() -> None:
    app = run()
    app.radio[0].set_value("Upload CSV files").run()
    assert not app.exception
    assert not app.error
    assert any("Upload a prices CSV" in block.value for block in app.markdown)
    assert not app.metric


def test_removing_the_benchmark_hides_the_benchmark_tab_and_keeps_the_sample_working() -> None:
    app = run()
    selectbox(app, "Benchmark").set_value("None").run()
    assert not app.exception
    assert not app.error
    assert "Benchmark" not in [tab.label for tab in app.tabs]


def test_changing_the_risk_free_rate_changes_the_sharpe_ratio() -> None:
    app = run()
    before = metric_values(app)["Sharpe"]
    next(box for box in app.number_input if "Risk-free" in box.label).set_value(3.0).run()
    assert not app.exception
    assert metric_values(app)["Sharpe"] != before


def test_a_wrong_annualisation_factor_is_flagged() -> None:
    app = run()
    selectbox(app, "Periods per year").set_value(52).run()
    assert not app.exception
    assert any("periods_per_year is 52" in warning.value for warning in app.warning)


def test_clearing_every_confidence_level_falls_back_instead_of_crashing() -> None:
    app = run()
    next(box for box in app.multiselect if "confidence" in box.label).set_value([]).run()
    assert not app.exception


# -- screenshot import ---------------------------------------------------------------------------

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
KEY = "sk-ui-test-SECRET-424242"


def _uploader(app: AppTest, label: str) -> FileUploader:
    return next(box for box in app.file_uploader if box.label == label)


def _upload_app() -> AppTest:
    prices = generate_sample_prices().to_csv(lineterminator="\n").encode()
    app = run()
    app.radio[0].set_value("Upload CSV files").run()
    _uploader(app, "Prices CSV").set_value(("prices.csv", prices, "text/csv")).run()
    assert not app.exception
    return app


def _answer(positions: list[dict[str, object]]) -> dict[str, object]:
    text = json.dumps({"currency": "USD", "positions": positions})
    return {
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 500, "output_tokens": 80},
    }


def _click(app: AppTest, label: str) -> AppTest:
    return next(button for button in app.button if button.label == label).click().run()


def _read_screenshot(app: AppTest) -> AppTest:
    next(box for box in app.text_input if box.label == "API key").set_value(KEY).run()
    _uploader(app, "Screenshot").set_value(("holdings.png", PNG, "image/png")).run()
    next(box for box in app.checkbox if "will be sent to" in box.label).set_value(True).run()
    return _click(app, "Read screenshot")


def _visible_text(app: AppTest) -> str:
    parts = [e.value for e in (*app.error, *app.warning, *app.markdown, *app.caption)]
    return "\n".join(str(part) for part in parts)


def test_the_screenshot_section_is_hidden_for_the_synthetic_sample() -> None:
    app = run()
    assert not any("screenshot" in expander.label.lower() for expander in app.expander)


def test_the_screenshot_section_is_hidden_when_the_operator_disables_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PORTFOLIO_RISK_DISABLE_IMPORT", "1")
    app = _upload_app()
    assert not any("screenshot" in expander.label.lower() for expander in app.expander)


def test_reading_a_screenshot_then_confirming_changes_the_weights(fake: Fake) -> None:
    fake.reply["body"] = _answer(
        [
            {"ticker": "syn_eq_us", "market_value": 6000, "weight_percent": None},
            {"ticker": "SYN_GOVT", "market_value": 4000, "weight_percent": None},
        ]
    )
    app = _upload_app()
    equal_weight_sharpe = metric_values(app)["Sharpe"]
    assert any("screenshot" in expander.label.lower() for expander in app.expander)

    app = _read_screenshot(app)
    assert not app.exception
    assert not app.error
    assert fake.seen.headers["x-api-key"] == KEY
    assert "Tokens used: 500 in, 80 out" in _visible_text(app)

    app = _click(app, "Use as weights")
    assert not app.exception
    assert not app.error
    assert any("imported from a screenshot" in block.value for block in app.markdown)
    assert metric_values(app)["Sharpe"] != equal_weight_sharpe
    assert KEY not in _visible_text(app)


def test_a_provider_error_is_shown_without_the_key(fake: Fake) -> None:
    fake.reply.update(status=401, body={"error": {"message": f"bad key {KEY}"}})
    app = _read_screenshot(_upload_app())
    assert not app.exception
    assert any("rejected the API key" in error.value for error in app.error)
    assert KEY not in _visible_text(app)
    assert not any(button.label == "Use as weights" for button in app.button)


def test_percentages_that_do_not_add_up_are_refused_at_confirmation(fake: Fake) -> None:
    fake.reply["body"] = _answer(
        [
            {"ticker": "SYN_EQ_US", "market_value": None, "weight_percent": 40},
            {"ticker": "SYN_GOVT", "market_value": None, "weight_percent": 30},
        ]
    )
    app = _click(_read_screenshot(_upload_app()), "Use as weights")
    assert not app.exception
    assert any("sum to 70.00, not 100" in error.value for error in app.error)
    assert not any("imported from a screenshot" in block.value for block in app.markdown)


def test_imported_weights_do_not_survive_a_different_prices_file(fake: Fake) -> None:
    fake.reply["body"] = _answer(
        [{"ticker": "SYN_EQ_US", "market_value": 1, "weight_percent": None}]
    )
    app = _click(_read_screenshot(_upload_app()), "Use as weights")
    assert any("imported from a screenshot" in block.value for block in app.markdown)

    other = b"date,SYN_EQ_US,SYN_GOVT\n" + b"".join(
        f"2024-01-{day:02d},{100 + day},{100 - day / 10}\n".encode() for day in range(1, 29)
    )
    _uploader(app, "Prices CSV").set_value(("other.csv", other, "text/csv")).run()
    assert not any("imported from a screenshot" in block.value for block in app.markdown)
