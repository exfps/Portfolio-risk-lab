"""Regenerate the interface screenshots used in the README and the documentation vault.

Starts ``scripts/demo_app.py`` (the real interface with an offline, clearly synthetic price
source and a local fake vision API) and drives it with Playwright. No network or API key is used.

    python -m pip install playwright && python -m playwright install chromium
    python scripts/capture_screenshots.py [--out screenshots]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from fake_provider import serve  # noqa: E402
from portfolio_risk.sample_data import generate_sample_prices  # noqa: E402
from portfolio_risk.vision.providers import BASE_URL_OVERRIDE  # noqa: E402

METRICS = '[data-testid="stMetric"]'
WIDTH, HEIGHT, SCALE = 1440, 1000, 1.25


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_until_up(port: int) -> None:
    for _ in range(120):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=2)
            return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError("the app did not start")


def settle(page: Page) -> None:
    page.wait_for_selector(METRICS, timeout=60_000)
    page.wait_for_selector(".vega-embed", timeout=60_000)
    page.wait_for_timeout(1200)  # entrance animations and chart transitions


def shoot(page: Page, out: Path, name: str, *, full: bool = False) -> None:
    page.screenshot(path=str(out / name), full_page=full)
    print("wrote", name)


def open_app(page: Page, url: str, query: str = "") -> None:
    page.goto(url + query)
    settle(page)


def tab(page: Page, label: str) -> None:
    page.get_by_role("tab", name=label).click()
    page.wait_for_timeout(1500)


def scene_compare(page: Page, out: Path) -> None:
    tab(page, "Compare")
    page.wait_for_selector("text=Saved portfolios", timeout=30_000)
    sample = {
        "Equity heavy": {"SYN_EQ_US": 0.4, "SYN_EQ_EU": 0.3, "SYN_EQ_EM": 0.2, "SYN_GOVT": 0.1},
        "Defensive": {"SYN_GOVT": 0.5, "SYN_CORP": 0.3, "SYN_EQ_US": 0.2},
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/portfolios.json"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "version": 1,
                    "portfolios": [{"name": n, "weights": w} for n, w in sample.items()],
                },
                handle,
            )
        # the export panel has a JSON loader too, so pick the one inside the Compare tab
        panel = page.locator("[role=tabpanel]").filter(has_text="Saved portfolios").last
        panel.locator("input[type=file][accept*='json']").set_input_files(path)
        page.wait_for_selector("text=Loaded 2 portfolios", timeout=30_000)
    box = page.get_by_label("Portfolios to compare")
    box.click()
    for name in ("Equity heavy", "Defensive"):
        page.get_by_role("option", name=name).click()
    page.keyboard.press("Escape")
    page.wait_for_selector("text=Key statistics", timeout=30_000)
    page.wait_for_timeout(2000)
    shoot(page, out, "compare.png")
    page.get_by_text("Holdings", exact=True).first.scroll_into_view_if_needed()
    page.wait_for_timeout(1200)
    shoot(page, out, "compare-holdings.png")


def scene_main(page: Page, url: str, out: Path) -> None:
    open_app(page, url)
    shoot(page, out, "overview.png")
    tab(page, "Risk")
    shoot(page, out, "risk.png", full=True)
    tab(page, "Correlation")
    shoot(page, out, "correlation.png")
    tab(page, "Benchmark")
    shoot(page, out, "benchmark.png")
    tab(page, "Tearsheet")
    page.wait_for_selector("text=Key statistics", timeout=30_000)
    page.wait_for_timeout(2000)
    shoot(page, out, "tearsheet.png")
    page.get_by_text("Returns by calendar year").scroll_into_view_if_needed()
    page.wait_for_timeout(1500)
    shoot(page, out, "tearsheet-calendar.png")
    page.get_by_text("Drawdowns", exact=True).scroll_into_view_if_needed()
    page.wait_for_timeout(1500)
    shoot(page, out, "tearsheet-drawdowns.png")
    scene_compare(page, out)
    tab(page, "Monte Carlo")
    shoot(page, out, "monte-carlo-controls.png")
    page.get_by_role("combobox", name="Models").click()
    page.get_by_role("option", name="Gaussian (normal)").click()
    page.keyboard.press("Escape")
    page.get_by_role("button", name="Run simulation").click()
    page.wait_for_selector("text=Projection: Student-t", timeout=90_000)
    page.wait_for_timeout(2500)
    page.get_by_text("Projection: Student-t").scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    shoot(page, out, "monte-carlo.png")
    page.get_by_text("Scenarios", exact=True).scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    shoot(page, out, "monte-carlo-tables.png")
    tab(page, "Alpha Decay")
    page.wait_for_selector("table.decay", timeout=30_000)
    page.wait_for_timeout(1500)
    shoot(page, out, "alpha-decay.png")
    page.get_by_text("Window", exact=True).last.scroll_into_view_if_needed()
    page.wait_for_selector(
        "[data-testid='stVegaLiteChart'] canvas, [data-testid='stVegaLiteChart'] svg"
    )
    page.wait_for_timeout(1200)
    page.mouse.wheel(0, 380)
    page.wait_for_timeout(600)
    shoot(page, out, "alpha-decay-chart.png")
    tab(page, "Assumptions")
    shoot(page, out, "assumptions.png")
    page.get_by_text("Appearance", exact=True).click()
    page.wait_for_timeout(600)
    shoot(page, out, "appearance.png")


def scene_export(page: Page, url: str, out: Path) -> None:
    open_app(page, url, "/?pdf=Editorial")
    page.get_by_text("Export report (PDF or Excel)").click()
    page.wait_for_timeout(1200)
    shoot(page, out, "export-contents.png")
    page.get_by_role("tab", name="Look").click()
    page.wait_for_timeout(1200)
    shoot(page, out, "export-look.png")


def scene_themes(page: Page, url: str, out: Path) -> None:
    open_app(page, url, "/?theme=Obsidian%20gold")
    shoot(page, out, "theme-obsidian-gold.png")
    open_app(page, url, "/?theme=Graphite&size=Large")
    shoot(page, out, "theme-graphite-large.png")
    open_app(page, url, "/?theme=Forest&accent=%23E07A2F")
    shoot(page, out, "theme-custom-accent.png")


def scene_download(page: Page, url: str, out: Path) -> None:
    open_app(page, url)
    page.get_by_text("Search and download", exact=True).click()
    picker = page.get_by_role("combobox", name="Choose from the list")
    for name in ("AAPL", "2222.SR", "NVDA"):
        picker.click()
        picker.fill(name)
        page.get_by_role("option", name=re.compile(rf"^{re.escape(name)}\s")).first.click()
        page.wait_for_timeout(300)
    page.keyboard.press("Escape")
    shoot(page, out, "default-list.png")
    page.get_by_label("Find a ticker").fill("demo")
    page.get_by_label("Find a ticker").press("Enter")
    page.wait_for_selector("text=Add to portfolio", timeout=30_000)
    page.wait_for_timeout(500)
    shoot(page, out, "download-search.png")
    page.get_by_role("button", name="Add to portfolio").click()
    page.wait_for_timeout(800)
    tickers = page.get_by_role("combobox", name="Tickers")
    for symbol in ("DEMO.B", "DEMO.C"):
        tickers.click()
        tickers.fill(symbol)
        tickers.press("Enter")
        page.wait_for_timeout(500)
    bench = page.get_by_placeholder("for example ^GSPC")
    bench.fill("DEMO.IDX")
    bench.press("Enter")
    page.get_by_text("Weekly, last price of the week").click()
    page.get_by_role("combobox", name="Base currency").click()
    page.get_by_role("option", name="USD").click()
    page.wait_for_timeout(500)
    page.get_by_role("button", name="Download prices").click()
    settle(page)
    shoot(page, out, "download-result.png")


def scene_import(page: Page, url: str, out: Path, fake: object, workdir: Path) -> None:
    holdings = ROOT / "examples" / "sample_holdings_screenshot.png"
    prices = workdir / "prices.csv"
    generate_sample_prices().to_csv(prices, float_format="%.4f")
    names = ["SYN_EQ_US", "SYN_EQ_EU", "SYN_EQ_EM", "SYN_GOVT", "SYN_CORP", "SYN_COMMOD"]
    values = [30000, 15000, 10000, 25000, 10000, 10000]
    fake.reply["body"] = {  # type: ignore[attr-defined]
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "currency": "USD",
                        "positions": [
                            {"ticker": n, "market_value": v, "weight_percent": None}
                            for n, v in zip(names, values, strict=True)
                        ],
                    }
                ),
            }
        ],
        "usage": {"input_tokens": 520, "output_tokens": 140},
    }
    open_app(page, url)
    page.get_by_text("Upload CSV files", exact=True).click()
    page.get_by_test_id("stSidebar").locator('input[type="file"]').first.set_input_files(
        str(prices)
    )
    settle(page)
    page.get_by_text("Import positions from a screenshot").click()
    page.get_by_label("API key", exact=True).fill("sk-demo-not-a-real-key")
    box = page.get_by_test_id("stFileUploader").filter(has_text="Screenshot")
    box.locator('input[type="file"]').set_input_files(str(holdings))
    page.wait_for_timeout(1500)
    page.get_by_text("I understand this image will be sent to").click()
    page.get_by_role("button", name="Read screenshot").click()
    page.wait_for_selector("text=Check every row", timeout=30_000)
    page.wait_for_timeout(800)
    shoot(page, out, "import-review.png", full=True)


def scene_mobile(browser: object, url: str, out: Path) -> None:
    page = browser.new_page(  # type: ignore[attr-defined]
        viewport={"width": 430, "height": 932}, device_scale_factor=2
    )
    open_app(page, url)
    shoot(page, out, "mobile.png")
    page.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--out", type=Path, default=ROOT / "screenshots")
    out: Path = parser.parse_args().out
    out.mkdir(parents=True, exist_ok=True)
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    command = [
        sys.executable, "-m", "streamlit", "run", str(ROOT / "scripts" / "demo_app.py"),
        "--server.headless", "true", "--server.port", str(port),
        "--browser.gatherUsageStats", "false", "--client.toolbarMode", "minimal",
        "--theme.base", "dark", "--theme.primaryColor", "#2BB3A3",
        "--theme.backgroundColor", "#0B0C0E", "--theme.secondaryBackgroundColor", "#14161A",
        "--theme.textColor", "#ECECEC",
    ]  # fmt: skip
    with serve() as fake, tempfile.TemporaryDirectory() as work:
        env = {**os.environ, BASE_URL_OVERRIDE: fake.url}
        server = subprocess.Popen(
            command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        try:
            wait_until_up(port)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                scenes: list[Callable[[Page], None]] = [
                    lambda p: scene_main(p, url, out),
                    lambda p: scene_themes(p, url, out),
                    lambda p: scene_export(p, url, out),
                    lambda p: scene_download(p, url, out),
                    lambda p: scene_import(p, url, out, fake, Path(work)),
                ]
                for scene in scenes:
                    page = browser.new_page(
                        viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=SCALE
                    )
                    scene(page)
                    page.close()
                scene_mobile(browser, url, out)
                browser.close()
        finally:
            server.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
