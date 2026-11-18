# Architecture

## Principles

1. **The core is a library.** Nothing under `src/portfolio_risk/` imports a UI framework, makes a
   network call, or reads the environment. It takes pandas objects and returns numbers, so every
   statistic is testable without a browser.
2. **Metrics are pure functions.** Each takes a Series or DataFrame plus explicit parameters and
   returns a float, Series or small frozen dataclass. No global state, no hidden defaults beyond
   those in `AnalysisConfig`.
3. **Validate at the boundary.** Loaders and `validation.py` turn untrusted files into clean,
   typed pandas objects or raise `DataValidationError`. The metric modules assume clean input and
   only check what could make their own arithmetic meaningless (length, finiteness, zero
   variance).
4. **Nothing is repaired silently.** Anything dropped or rescaled is reported in
   `AnalysisResult.warnings`.
5. **Optional features stay out of the core.** The UI, the PDF and Excel exporters and the screenshot
   import depend on the core. The core does not depend on them.

## Current layout (implemented)

```
src/portfolio_risk/
├── errors.py        PortfolioRiskError > ConfigurationError, DataValidationError > InsufficientDataError
├── config.py        AnalysisConfig: annualisation, risk-free, MAR, confidence levels, minimum sample
├── returns.py       simple returns, portfolio returns, wealth index, total and annualised return
├── risk.py          volatility, Sharpe, downside deviation, Sortino
├── drawdown.py      drawdown series, DrawdownSummary (max, peak, trough, recovery, duration)
├── var.py           historical and parametric VaR and CVaR
├── exposure.py      correlation, covariance, HHI, effective positions, risk contributions
├── benchmark.py     beta, alpha, tracking error, information ratio
├── analysis.py      analyse(): runs everything and returns one AnalysisResult
├── tearsheet.py     20 statistic rows, monthly and calendar-year tables, rolling statistics
├── comparison.py    compare(): several constant-weight portfolios on common dates; JSON store
├── decay.py         alpha decay: rolling-window statistics, oriented z-scores, ratings
├── simulation/      Monte Carlo: models, engine (rebalancing, costs), per-path statistics, run
│   ├── models.py      Gaussian, Student-t, bootstrap and block bootstrap behind one protocol
│   ├── engine.py      SimulationConfig, frequency conversion, wealth paths
│   └── analytics.py   path and across-path statistics, fan bands (NumPy only)
├── sample_data.py   seeded synthetic prices and weights
├── _checks.py       shared argument checks
├── cli.py           `portfolio-risk-lab` command: launches Streamlit with the project theme
├── __main__.py      `python -m portfolio_risk`
├── io/
│   ├── loaders.py     load_prices, load_weights (structure and parsing)
│   └── validation.py  clean_prices, validate_weights, check_columns, frequency checks
├── data/            optional price download; the core never imports it
│   ├── base.py        SymbolMatch, PriceSeries, PriceProvider protocol (vendor-neutral)
│   ├── yahoo.py       Yahoo Finance adapter over the unofficial yfinance library
│   ├── fx.py          conversion to a base currency with provider exchange-rate series
│   ├── align.py       common-day or weekly alignment; mixed-currency warnings (no conversion)
│   ├── universe.py    default instrument list loader and validator (universe.json, symbols only)
│   └── cache.py       CachedProvider (15-minute TTL, bounded) and download_many (parallel)
├── report/          optional exports; needs reportlab and openpyxl, the core never imports it
│   ├── meta.py        ReportMeta (title, data source, accent), disclaimer, assumptions text
│   ├── inputs.py      section keys, ReportInputs, unavailable() and resolve(); no reportlab
│   ├── style.py       ReportStyle, presets, JSON round trip, validation; no reportlab
│   ├── look.py        a style as reportlab colours and fonts, held in a context variable
│   ├── filename.py    safe_stem(): a valid cross-platform file name from typed text
│   ├── pdf.py         build_pdf(): selected sections, page tone, vector charts
│   ├── pdf_parts.py   styles, tables and charts   pdf_sections.py  one builder per section
│   └── excel*.py      build_workbook(): one sheet per section with native charts
├── vision/          optional screenshot import; standard library only, the core never imports it
│   ├── providers.py   OpenAI-compatible (OpenAI, DeepSeek) and Anthropic clients, HTTPS only, key redaction
│   ├── schema.py      strict parsing of the model's answer; positions to weights
│   ├── media.py       image type and size checks from the file's bytes
│   └── extract.py     prompt and the single-call entry point
└── ui/              needs the `app` extra; the core never imports it
    ├── app.py         Streamlit script: inputs, settings, tabs
    ├── charts.py      Altair charts
    ├── tearsheet_view.py, compare_view.py, simulation_view.py, decay_view.py   the analysis tabs
    ├── *_tables.py    pure table builders the tabs and the reports share (no Streamlit)
    ├── report_state.py     latest simulation and comparison, tied to the data they came from
    ├── report_style_panel.py   the Look tab: preset, colours, per-series table, JSON, address
    ├── style.css      stylesheet template; dollar-prefixed names are filled from theme.py
    ├── styles.py      builds the stylesheet and embeds the bundled font (fonts/) as data URIs
    ├── formatting.py  result objects to display tables (percent, n/a for non-finite)
    ├── market.py      sidebar for searching and downloading prices; output is CSV bytes
    ├── inputs.py      weights table to and from a Series
    └── theme.py       palette constants, mirrored in .streamlit/config.toml (a test enforces this)

streamlit_app.py       root entry point for Streamlit Community Cloud
scripts/               generate_sample.py, generate_example_reports.py, capture_screenshots.py,
                       demo_app.py (synthetic provider), browser_check.py (optional Playwright)
```

The launcher runs `[sys.executable, -m, streamlit, run, ui/app.py, ...]` as a subprocess, so it
uses the interpreter that installed the package on any operating system. `app.py` only collects
inputs, calls `analyse()` and renders; every figure comes from the core.

## Data flow

```
prices.csv  ──load_prices──▶ DataFrame ─┐
weights.csv ──load_weights─▶ Series ────┤
                                        ▼
                      analyse(prices, weights, config, benchmark)
                                        │
     validate_weights ─ check_columns ─ clean_prices ─ frequency_warnings
                                        │
        simple_returns ─▶ portfolio_returns ─▶ wealth_index
                                        │
      performance · VaR/CVaR · correlation · HHI · risk contribution · benchmark
                                        ▼
                              AnalysisResult (+ warnings)
```

## Key decisions

| Decision | Reason | Trade-off |
|---|---|---|
| Constant weights | Exact risk decomposition and a simple, honest assumption for the MVP. | Does not match a buy-and-hold portfolio. Planned for the transactions-ledger release. |
| Simple returns | Weighted sums across assets are exact. | Compounding uses `log1p`/`expm1` internally for numerical accuracy. |
| `annualisation` is a parameter | A hard-coded 252 silently mis-scales weekly or crypto data. | The user must set it; a mismatch warns. |
| Reject rather than interpolate missing data | Silent filling distorts correlations and tails. | Messy files fail until fixed. |
| Frozen dataclasses for results | Immutable, comparable, easy to serialise. | `AnalysisResult` is compared by identity because it holds pandas objects. |
| Dependencies limited to NumPy and pandas | Smaller install, fewer licence and supply-chain questions. SciPy is not a dependency; it was used only for one-off cross-checks during development. | Normal quantiles use the standard library `statistics.NormalDist`. |
| Streamlit for the interface | One Python codebase, no JavaScript build, runs locally and can be hosted. | A rerun-per-interaction model and less layout control than a hand-built front end. Floor is 1.58, the lowest version the test suite was run on; 1.40 and 1.46 fail with Altair 5.5. |
| Python 3.12+, `mypy --strict` | Catches shape and type mistakes in numerical code early. | Excludes older interpreters. |

## Planned components (not yet implemented)

| Component | Notes |
|---|---|
| Cash-flow input, TWR, XIRR, buy-and-hold | After the MVP. |

## Testing strategy

- **Hand-calculated fixtures** for each metric, with the working in the test docstring and in
  `methodology.md`.
- **Property tests** (Hypothesis): contributions sum to 1, HHI is bounded, CVaR is at least VaR,
  drawdown is in `[-1, 0]` and scale-invariant, volatility scales with `sqrt(m)`.
- **Malformed-input tests** for every validation rule, asserting the message names the problem.
- **Snapshot test** pinning the numbers quoted in the README for the synthetic sample.
- **Interface tests** with Streamlit's `AppTest` (renders, upload waits, benchmark toggle,
  settings change results, bad input does not crash). `ui/app.py` is omitted from the coverage
  figure because the harness defeats coverage tracing.
- **Import tests** run the real HTTP clients against a local fake provider server
  (`tests/fake_provider.py`): request shapes, headers, error mapping, timeouts, key redaction and
  the full read-review-confirm flow in the interface. No real provider or key is ever contacted.
- **Browser check** (`scripts/browser_check.py`, not run in CI): real Chromium, malformed and
  CRLF/BOM uploads, weights-file mistakes.
- **Independent cross-checks** (scipy, explicit loops, numerical differentiation) were run during
  development and agreed to nine decimal places. They are not part of the shipped test suite.

## Design decisions added with the exporters, theme and cache

- **Exports are built on click.** Streamlit's `download_button` accepts a callable, so the PDF
  and workbook are generated only when pressed; older Streamlit versions fall back to building
  the bytes up front.
- **reportlab and openpyxl, not matplotlib.** The PDF draws charts as vector shapes and the
  workbook uses native Excel charts, so neither needs a rendering backend or system libraries.
- **Theme is data, not CSS in code.** `Palette` is a frozen dataclass; the stylesheet, charts and
  exports all take it as input. An accent that fails a 3:1 contrast check against the background
  is lightened automatically; `on_paper` darkens it for white PDF pages.
  Streamlit's own widgets (toggles, sliders) keep the base colour from `.streamlit/config.toml`
  because Streamlit exposes no runtime theming for them; this is a known limitation.
- **Latency.** Measured: analysis ~14 ms and the correlation chart ~29 ms in Python; page load is
  dominated by Streamlit's own JavaScript (about 1 s bare). The changes that helped were cached
  analysis, lazy tabs, parallel downloads, a provider TTL cache and plain HTML tables. A lazy
  weights editor gave no measurable gain and was reverted.

## Design decisions added with the analysis tabs and report styles

- **The core never imports the interface, and neither does the report layer.** Tables that both
  a tab and a report need live in `ui/*_tables.py` with no Streamlit import, so reports can use
  them without pulling in the app.
- **Lazy tabs.** `_render_results` holds the tabs as an ordered mapping and draws only the open
  one, so a heavy tab (a simulation, a comparison) costs nothing until used.
- **No hidden computation in exports.** The report takes the Monte Carlo and comparison results
  the person has already produced, tied to the data and weights by a signature. If either
  changed, the stored result is dropped. Choosing a section that has no result is impossible,
  and the panel says why.
- **Report style is data, applied through a context variable.** `ReportStyle` is a validated
  frozen dataclass (JSON in and out). `build_pdf` and `build_workbook` set the active look for
  the duration of one build, so two sessions building reports at the same time cannot see each
  other's style, and nothing is stored at module level.
- **In-app chart lines and PDF lines are styled separately.** The PDF styles use colours chosen
  for white paper; the interface is dark, so it offers a colour-blind-safe set and a width.
- **Reproducibility.** Simulations take a seed. The tests use hand-calculated expectations for
  the statistics, and seeded runs for the models.
