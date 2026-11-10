"""Drive the real interface in a browser: sample view, uploads and error messages.

Optional developer check, not part of the unit-test run. It starts the app itself on a free
port, so nothing needs to be running first.

    python -m pip install playwright
    python -m playwright install chromium
    python scripts/browser_check.py [--screenshots DIR]

Exits with status 1 if any check fails.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

# The fake provider used by the unit tests also serves this check.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from fake_provider import serve
from portfolio_risk.cli import build_command
from portfolio_risk.sample_data import generate_sample_prices, sample_weights
from portfolio_risk.vision.providers import BASE_URL_OVERRIDE

METRICS = '[data-testid="stMetric"]'
ALERTS = '[data-testid="stAlert"]'
TRACEBACK = '[data-testid="stException"]'
RESULTS: list[bool] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def write_fixtures(folder: Path) -> None:
    """Valid and deliberately broken inputs, all derived from the synthetic sample."""
    prices = generate_sample_prices().to_csv(float_format="%.4f", lineterminator="\n")
    lines = prices.splitlines()
    weights = sample_weights()
    (folder / "prices.csv").write_text(prices, encoding="utf-8")
    (folder / "weights.csv").write_text(
        weights.to_csv(float_format="%.2f", lineterminator="\n"), encoding="utf-8"
    )
    (folder / "semicolon.csv").write_text(prices.replace(",", ";"), encoding="utf-8")
    (folder / "unsorted.csv").write_text(
        "\n".join([lines[0], *lines[:0:-1]]) + "\n", encoding="utf-8"
    )
    (folder / "windows_bom.csv").write_bytes(("﻿" + "\r\n".join(lines) + "\r\n").encode("utf-8"))
    short = weights.copy()
    short.iloc[0] -= 0.1  # total becomes 0.9
    (folder / "weights_sum_09.csv").write_text(
        "ticker,weight\n" + "\n".join(f"{n},{v:.2f}" for n, v in short.items()) + "\n",
        encoding="utf-8",
    )
    (folder / "weights_percent.csv").write_text(
        "ticker,weight\n" + "\n".join(f"{n},{v * 100:g}" for n, v in weights.items()) + "\n",
        encoding="utf-8",
    )
    (folder / "weights_unknown.csv").write_text(
        "ticker,weight\nSYN_EQ_US,0.5\nNOPE,0.5\n", encoding="utf-8"
    )


class Session:
    def __init__(self, page: Page, url: str, fixtures: Path) -> None:
        self.page, self.url, self.fixtures = page, url, fixtures

    def open(self) -> None:
        self.page.goto(self.url)
        self.page.wait_for_selector(METRICS, timeout=60_000)

    def upload_mode(self) -> None:
        self.page.get_by_text("Upload CSV files").click()
        self.page.wait_for_selector('input[type="file"]', state="attached", timeout=30_000)

    def upload(self, slot: int, name: str) -> None:
        self.page.locator('input[type="file"]').nth(slot).set_input_files(str(self.fixtures / name))
        self.page.wait_for_timeout(2500)

    def alerts(self) -> str:
        return " | ".join(self.page.locator(ALERTS).all_inner_texts())

    def metrics(self) -> dict[str, str]:
        found: dict[str, str] = {}
        for box in self.page.locator(METRICS).all():
            # text_content ignores CSS text-transform; inner_text would return "TOTAL RETURN".
            label = (box.locator('[data-testid="stMetricLabel"]').text_content() or "").strip()
            found[label] = box.locator('[data-testid="stMetricValue"]').inner_text().strip()
        return found

    def no_traceback(self) -> bool:
        return self.page.locator(TRACEBACK).count() == 0

    def notice(self, text: str) -> bool:
        return self.page.locator(".notice").filter(has_text=text).count() == 1


def scenario_sample(s: Session, shots: Path | None) -> None:
    s.open()
    shown = s.metrics()
    check("sample: total return", shown.get("Total return") == "22.66%")
    check("sample: Sharpe", shown.get("Sharpe") == "0.71")
    check("sample: max drawdown", shown.get("Max drawdown") == "-11.65%")
    check("sample: synthetic notice shown", s.notice("Synthetic sample data"))
    check("sample: no traceback", s.no_traceback())
    box = s.page.locator(METRICS).first.bounding_box()
    check("sample: headline metrics above the fold", box is not None and box["y"] < 700)
    s.page.wait_for_timeout(1500)
    if shots:
        s.page.screenshot(path=str(shots / "overview.png"))
    for tab, name in [("Risk", "risk.png"), ("Correlation", "correlation.png")]:
        s.page.get_by_role("tab", name=tab).click()
        s.page.wait_for_timeout(1800)
        check(f"tab {tab}: chart drawn", s.page.locator(".vega-embed").count() > 0)
        if shots:
            s.page.screenshot(path=str(shots / name))


def scenario_upload_waits(s: Session) -> None:
    s.open()
    s.upload_mode()
    check("upload mode: prompt shown", s.notice("Upload a prices CSV"))


def scenario_bad_prices(s: Session, shots: Path | None) -> None:
    s.open()
    s.upload_mode()
    s.upload(0, "semicolon.csv")
    check("semicolon file: clear error", "semicolons" in s.alerts(), s.alerts()[:80])
    check("semicolon file: no traceback", s.no_traceback())
    if shots:
        s.page.screenshot(path=str(shots / "upload-error.png"))

    s.open()
    s.upload_mode()
    s.upload(0, "unsorted.csv")
    check("unsorted file: clear error", "ascending" in s.alerts(), s.alerts()[:80])
    s.page.get_by_text("Sort dates if out of order").click()
    s.page.wait_for_selector(METRICS, timeout=30_000)
    check("unsorted file + sort option: results shown", len(s.metrics()) >= 6)


def scenario_windows_file(s: Session) -> None:
    s.open()
    s.upload_mode()
    s.upload(0, "windows_bom.csv")
    s.page.wait_for_selector(METRICS, timeout=30_000)
    check("CRLF + BOM file: loads", len(s.metrics()) >= 6)
    check(
        "no benchmark chosen: no Benchmark tab",
        s.page.get_by_role("tab", name="Benchmark").count() == 0,
    )


def scenario_weights(s: Session) -> None:
    s.open()
    s.upload_mode()
    s.upload(0, "prices.csv")
    s.upload(1, "weights.csv")
    s.page.wait_for_selector(METRICS, timeout=30_000)
    check("prices + weights files reproduce the sample Sharpe", s.metrics().get("Sharpe") == "0.71")
    for name, expected in [
        ("weights_sum_09.csv", "sum to 0.9, not 1"),
        ("weights_percent.csv", "percentages"),
        ("weights_unknown.csv", "no price column"),
    ]:
        s.open()
        s.upload_mode()
        s.upload(0, "prices.csv")
        s.upload(1, name)
        check(f"{name}: '{expected}'", expected in s.alerts(), s.alerts()[:90])
        check(f"{name}: no traceback", s.no_traceback())
    s.open()
    s.upload_mode()
    s.upload(0, "prices.csv")
    s.upload(1, "weights_sum_09.csv")
    s.page.get_by_text("Rescale weights that do not sum to 1").click()
    s.page.wait_for_selector(METRICS, timeout=30_000)
    check("rescale option: results with a rescale warning", "rescaled" in s.alerts())


PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360f8cfc000000301010018dd8db00000000049454e44ae426082"
)


def scenario_screenshot_import(s: Session, fake: object, shots: Path | None) -> None:
    """Upload prices, read a screenshot through the fake provider, confirm the weights."""
    answer = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "currency": "USD",
                        "positions": [
                            {"ticker": "SYN_EQ_US", "market_value": 7000, "weight_percent": None},
                            {"ticker": "SYN_GOVT", "market_value": 3000, "weight_percent": None},
                        ],
                    }
                ),
            }
        ],
        "usage": {"input_tokens": 410, "output_tokens": 70},
    }
    fake.reply["body"] = answer  # type: ignore[attr-defined]
    (s.fixtures / "holdings.png").write_bytes(PNG_1X1)
    s.open()
    s.upload_mode()
    s.upload(0, "prices.csv")
    s.page.wait_for_selector(METRICS, timeout=30_000)
    equal_sharpe = s.metrics().get("Sharpe")
    s.page.get_by_text("Import positions from a screenshot").click()
    s.page.get_by_label("API key").fill("sk-browser-check-SECRET")
    box = s.page.get_by_test_id("stFileUploader").filter(has_text="Screenshot")
    box.locator('input[type="file"]').set_input_files(str(s.fixtures / "holdings.png"))
    s.page.wait_for_timeout(1500)
    s.page.get_by_text("I understand this image will be sent to").click()
    s.page.get_by_role("button", name="Read screenshot").click()
    s.page.wait_for_selector("text=Check every row", timeout=30_000)
    check("screenshot: review step shown", True)
    check(
        "screenshot: token usage shown",
        s.page.get_by_text("Tokens used: 410 in, 70 out").count() == 1,
    )
    check(
        "screenshot: key sent as header, never shown on the page",
        fake.seen.headers.get("x-api-key") == "sk-browser-check-SECRET"  # type: ignore[attr-defined]
        and "SECRET" not in s.page.inner_text("body"),
    )
    if shots:
        s.page.screenshot(path=str(shots / "screenshot-import.png"))
    s.page.get_by_role("button", name="Use as weights").click()
    s.page.wait_for_selector(".notice >> text=imported from a screenshot", timeout=30_000)
    s.page.wait_for_selector(METRICS, timeout=30_000)
    check(
        "screenshot: weights confirmed, results change", s.metrics().get("Sharpe") != equal_sharpe
    )
    check("screenshot: no traceback", s.no_traceback())


def wait_until_up(port: int, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=2):
                return
        except OSError:
            time.sleep(0.5)
    raise TimeoutError("The app did not start in time.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--screenshots", type=Path, help="folder to write screenshots to")
    args = parser.parse_args()
    shots: Path | None = args.screenshots
    if shots:
        shots.mkdir(parents=True, exist_ok=True)

    port = free_port()
    command = build_command(["--server.headless", "true", "--server.port", str(port)])
    with serve() as fake:
        environment = {**os.environ, BASE_URL_OVERRIDE: fake.url}
        server = subprocess.Popen(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment
        )
        run_scenarios(port, server, shots, fake)
    failed = RESULTS.count(False)
    print(f"\n{len(RESULTS) - failed}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


def run_scenarios(
    port: int, server: subprocess.Popen[bytes], shots: Path | None, fake: object
) -> None:
    try:
        wait_until_up(port)
        with tempfile.TemporaryDirectory() as folder, sync_playwright() as playwright:
            fixtures = Path(folder)
            write_fixtures(fixtures)
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1250})
            page.on("pageerror", lambda error: check("no uncaught page error", False, str(error)))
            session = Session(page, f"http://127.0.0.1:{port}", fixtures)
            scenarios: list[Callable[[], None]] = [
                lambda: scenario_sample(session, shots),
                lambda: scenario_upload_waits(session),
                lambda: scenario_bad_prices(session, shots),
                lambda: scenario_windows_file(session),
                lambda: scenario_weights(session),
                lambda: scenario_screenshot_import(session, fake, shots),
            ]
            for scenario in scenarios:
                scenario()
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    sys.exit(main())
