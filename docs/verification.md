# Verification status and checklist

What has been checked, by what means, and what is still unchecked. The build environment has no
access to market data services or Microsoft Office, and runs Linux. Nothing below has been
assumed to work; items are ticked only when they were observed.

## Checked

| Area | How |
|---|---|
| Calculations | Hand-calculated expectations in the tests, property-based tests, and independent cross-checks during development (not shipped). |
| Interface | Streamlit's test harness, and a real Chromium browser driven by `scripts/capture_screenshots.py` and `scripts/browser_check.py` (Linux, Python 3.13). |
| PDF | Built and read back page by page; text extracted with pypdf in the tests; style effects (fonts, paper tone, line colours, widths, dash patterns) asserted from the page content. |
| Excel | Built with openpyxl, opened and rendered through LibreOffice, values compared with the PDF; chart colours and dash styles asserted from the workbook XML. |
| Screenshots | Regenerated with `python scripts/capture_screenshots.py` from synthetic data and a fake provider. |

## Not checked

| Area | Why it matters | How to check |
|---|---|---|
| Live price download | Tested with a fake client only. | See below. |
| Gulf symbols (`.SR` and others) | The default list holds five Saudi symbols that were not confirmed against the live service. | Search each one in the app; check currency and dates. |
| FX conversion | Pairs such as `USDSAR=X` were not fetched. | Download one Saudi and one US ticker with base currency USD. |
| Screenshot import | Clients tested against a local fake server only. | Use your own key on a real holdings screenshot. |
| Windows hardware | CI is configured for Windows but has not run on GitHub. | Follow the Quick start in PowerShell, then run `python -m pytest`. |
| Microsoft Excel | Only LibreOffice was used. | Open `examples/sample_report.xlsx` and a report with every section. |
| Performance on a laptop | Measured on a cloud container. | Time the first page load and the Monte Carlo tab at 10,000 simulations. |

## Live data check (about 15 minutes, needs a network connection)

1. `python -m pip install -e ".[app,data]"` and run `portfolio-risk-lab`.
2. Choose *Search and download*. Search for `Apple`, `2222`, `Aramco`, `S&P 500`.
3. Add `AAPL`, `2222.SR` and one index. Download three years. Open *Assumptions* and read the
   currencies and dates reported.
4. Choose a base currency. The app refuses an unknown or minor-unit currency rather than
   guessing; confirm that it converts Saudi riyal prices sensibly (SAR is pegged to the dollar at
   about 3.75, so converted values should move closely with the local ones).
5. Compare one price against the exchange's own chart for the same date.
6. Record the results in `CHANGELOG.md`, with the date, before describing any of this as verified.
