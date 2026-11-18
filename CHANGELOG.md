# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added in 0.2.0 (in development)

- Default list of 25 stocks and 12 index funds (symbols only).
- Monte Carlo projection (`portfolio_risk.simulation`): Gaussian, Student-t, historical-bootstrap
  and block-bootstrap models, rebalancing, transaction costs, seeded runs, per-path and
  across-path statistics, scenarios; a Monte Carlo tab.
- Alpha decay (`portfolio_risk.decay`): ten rolling-window statistics, oriented z-scores and
  ratings; an Alpha Decay tab.
- Classic tearsheet (`portfolio_risk.tearsheet`): 20 statistics plus benchmark-relative rows,
  monthly and calendar-year tables, rolling statistics, deepest drawdown episodes; a Tearsheet tab.
- Portfolio comparison (`portfolio_risk.comparison`): up to five constant-weight portfolios on
  common dates, concentration, return correlation, validated JSON for saved weight sets; a
  Compare tab.
- Reports with selectable sections (`ReportInputs`, `resolve`, `unavailable`); the PDF and the
  workbook include the tearsheet, comparison, Monte Carlo and alpha decay.
- A chosen file name for exports (`report.filename.safe_stem`): forbidden characters removed,
  reserved Windows names suffixed, a typed extension dropped, length capped.
- Report style customiser (`report.style`, `report.look`): presets (Classic, Colour-blind safe,
  Black and white print, Editorial), accent, line colours, width, dash mode, per-series
  overrides, paper tone and font, JSON save and load, `?pdf=` preset in the address. Excel charts
  take the same colours, widths and dashes.
- Colour-blind-safe chart lines and a line width in Appearance (`?lines=`, `?lw=`).
- `docs/verification.md`: what is checked, what is not, and a live-data checklist.

### Fixed in 0.2.0

- Excel export: asset names beginning with `=` were written as live formulas; they are now
  stored as text (spreadsheet formula injection).
- A return series that is constant up to rounding no longer gives an astronomically large
  Sharpe ratio; it is treated as constant (undefined).
- The screenshot-import client no longer follows HTTP redirects, so the API key header cannot be
  resent to another address.
- `assert` statements used for type narrowing replaced by explicit errors.
- `docs/audit.md`: findings of the self-review.

### Changed in 0.2.0

- Quieter interface: headline figures without boxes, hairline-framed charts and tables.
- Table builders moved out of the Streamlit views into `ui/*_tables.py`, so reports can share them.
- The workbook's default contents now include an alpha-decay sheet.

### Added

- Core analytics library: simple, total and annualised returns; constant-weight portfolio
  returns; volatility, Sharpe and Sortino ratios; drawdown series with maximum drawdown, peak,
  trough, recovery and longest underwater duration; historical and parametric VaR and CVaR;
  correlation, covariance, HHI, effective number of positions and contribution to risk; beta,
  alpha, tracking error and information ratio against a benchmark.
- `analyse()` entry point returning a single `AnalysisResult` with warnings.
- CSV loaders for prices and weights, with line-specific error messages.
- Validation of dates, prices, missing data, observation counts, large single-period moves,
  weights, column alignment and annualisation frequency.
- Seeded synthetic sample data, clearly labelled, and the script that generates it.
- Test suite with hand-calculated fixtures, property-based tests and malformed-input tests.
- Methodology, architecture and user documentation.
- CI workflow running ruff, mypy (strict) and pytest with a coverage floor.
- Streamlit interface (`portfolio-risk-lab` command, `python -m portfolio_risk`, and
  `streamlit_app.py` for hosted use): sample or CSV input, weights editor, benchmark selection,
  performance, risk, correlation and benchmark tabs, assumptions summary, specific error messages.
- Default instrument list (`data/universe.json`, 25 stocks and 12 index funds; symbols only) with
  a validated loader and a sidebar picker.
- PDF report and Excel workbook export (`portfolio_risk.report`, reportlab and openpyxl), built
  on click, with data source, assumptions and disclaimer; example files in `examples/`.
- Theme customiser: presets, custom accent with automatic contrast correction, text sizes,
  persisted in the page address; print-safe accent for exports.
- In-memory TTL cache and parallel downloads for the price provider; cached analysis, lazy tabs
  and lightweight HTML tables in the interface.
- `scripts/capture_screenshots.py`, `scripts/demo_app.py` (synthetic provider) and
  `scripts/generate_example_reports.py`; CI now also runs on Windows.
- Optional price download (`portfolio_risk.data`, `pip install -e ".[data]"`): ticker search and
  adjusted-price download through a replaceable provider interface with a Yahoo Finance adapter,
  alignment of markets that trade on different days (common days or weekly), warnings for
  mixed or unreported currencies, and optional conversion to a base currency (refuses unknown
  or minor-unit quote currencies rather than guessing). Tested with a fake client only; not yet run against the live
  service, and Gulf exchange coverage is unverified. New "Search and download" source in the
  interface; `PORTFOLIO_RISK_DISABLE_DOWNLOAD=1` removes it.
- Interface: single bundled Inter font for readability, lazy-rendered tabs and cached analysis
  for smoother interaction, screenshot panel isolated as a fragment.
- Optional screenshot import (`portfolio_risk.vision`): reads positions from an image with the
  user's own Anthropic, OpenAI or DeepSeek key, validates the answer against a strict schema,
  and requires review in the interface before use. The clients are tested against a local fake
  server only.
- Screenshot import verifies TLS certificates with the `certifi` bundle, fixing
  CERTIFICATE_VERIFY_FAILED on macOS Python installs without root certificates.
- A test that fails if anything shaped like an API key is committed.
- Interface styling: bundled Inter font (offline, OFL), card-style metrics,
  gradient chart fills, subtle entrance and hover animations that respect reduced-motion settings.
- Interface tests using Streamlit's test harness, and `scripts/browser_check.py`, an optional
  real-browser check.

### Not yet implemented

- Time-weighted and money-weighted returns, buy-and-hold weights, factor regression and regimes.
- Screenshot import does not yet downscale images or strip metadata, and has not been run against the real provider APIs.
