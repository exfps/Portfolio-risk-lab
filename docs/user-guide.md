# User guide

This guide covers the library and the Streamlit interface (version 0.2.0.dev0).

## The interface

Install with `python -m pip install -e ".[app]"` and run `portfolio-risk-lab` (or
`python -m portfolio_risk`). Extra arguments go to Streamlit, for example
`portfolio-risk-lab --server.port 8600`.

1. **Data.** Pick *Synthetic sample* to look around, or *Upload CSV files* and add a prices file
   and, optionally, a weights file (equal weights if omitted). The *Need a template?* section
   downloads files in the right shape. Tick *Sort dates if out of order* if your file runs
   newest first.
2. **Settings.** Periods per year is detected from the dates; change it if the warning says it
   does not fit. Set the risk-free rate, the minimum acceptable return for Sortino and the VaR
   confidence levels. Choose a benchmark column to compare against; it is excluded from the
   portfolio.
   *Search and download* (needs `pip install -e ".[data]"`) fetches adjusted prices from Yahoo
   Finance: search by name, add tickers (full Yahoo symbols such as `AAPL` or `2222.SR`), choose
   the dates and press *Download prices*. Markets that trade on different days are aligned either
   on common days or weekly (weekly sets periods per year to 52). Choose a *Base currency* to convert
   every price with daily exchange rates from the same source; without one, mixed currencies only
   produce a warning. A ticker with no reported currency, or one quoted in a minor unit, is
   refused rather than guessed. Yahoo data is for personal use and the library is
   unofficial, so check every ticker, its currency and its dates before relying on the result.
3. **Weights.** Open the *Weights* section to edit them. They must sum to 1, or tick *Rescale
   weights that do not sum to 1*.
4. **Results.** Headline figures sit above tabs: Performance, Risk, Correlation, Benchmark (only
   when a benchmark is chosen), Tearsheet, Compare, Monte Carlo, Alpha Decay and Assumptions.
   Tabs draw only when opened, so the page stays light. Problems with your files appear as a
   red message that names the line, column or date at fault. The analysis tabs are described
   under [The analysis tabs](#the-analysis-tabs).

   Under *Search and download*, *Default list* lets you tick stocks or index funds and add them
   to the ticker box. It is a convenience list, not a recommendation.
5. **Export.** *Export report (PDF or Excel)* sits under the headline figures. See
   [Exporting a report](#exporting-a-report).
6. **Appearance.** The *Appearance* section in the sidebar offers four presets, a custom accent
   colour, three text sizes, *Chart lines* (Standard, or Colour-blind safe, which also gives each
   line its own dash pattern) and a line width. Low-contrast accents are lightened automatically.
   The choice is stored in the page address (`?theme=...&accent=...&size=...&lines=...&lw=...`),
   so bookmarking the page keeps it. Toggles and sliders keep the default teal.

Uploaded files stay in memory for the session and are not saved.

### The analysis tabs

- **Tearsheet.** The portfolio, the benchmark and up to four holdings you choose, side by side:
  20 statistics (and 5 benchmark-relative ones), a monthly return grid, calendar-year returns,
  rolling volatility, Sharpe and beta over a window you pick, and the five deepest drawdowns.
- **Compare.** Save the current weights under a name, then compare up to five saved portfolios
  on exactly the same dates. Saved sets can be downloaded and loaded as JSON (they live in the
  session otherwise). Shows statistics, holdings, concentration and the correlation of the
  portfolios' returns.
- **Monte Carlo.** Choose one or more return models (Gaussian, Student-t, historical bootstrap,
  block bootstrap), horizon, number of simulations, frequency, rebalancing, expected-return
  treatment (historical average or zero), transaction cost, the drawdown to flag, the target
  gain, the starting value and a random seed (42 by default, so a rerun repeats), then press
  *Run simulation*. Results show a fan chart, percentile tables, the probability of loss, of
  the flagged drawdown and of reaching the target, value at risk and expected shortfall over the
  horizon, and bull, base, bear and severe scenarios. The results are model output, not forecasts.
- **Alpha Decay.** Ten statistics over rolling windows (21, 63 and 126 periods by default; you can
  type others), each rated Excellent, Good, Warning or Critical by how the latest window compares
  with the earlier ones, shown as a matrix with a chart for one statistic and window. See
  [methodology section 11](methodology.md#11-alpha-decay-rolling-window-health) for what the
  rating does and does not mean.

### Exporting a report

Open *Export report (PDF or Excel)*.

1. **Contents and file name.** Choose the sections. Summary, performance, risk, correlation,
   benchmark (if chosen), classic tearsheet, alpha decay and assumptions are always available.
   The comparison and Monte Carlo sections are listed as unavailable, with the reason, until
   you have run them in their tabs; a result is used only while the data and weights are
   unchanged. Type a file name without an extension (the PDF gets `.pdf`, the workbook `.xlsx`);
   characters that Windows, macOS or Linux do not allow are removed and the field says what it
   saved. Empty means `portfolio-report-YYYYMMDD`.
2. **Look.** Pick a preset (Classic, Colour-blind safe, Black and white print, Editorial) or
   change paper tone, font, line width, line styles, accent and the first six line colours, and
   override colour, width or style for a named series. *Save this style (JSON)* writes it to a
   file and *Load a style file* reads one back; a preset can also be chosen in the address with
   `?pdf=Editorial`. A style changes presentation only, never a number.
3. Press *Download PDF report* or *Download Excel*. The file is built when you press the button.
   Dark paper is not offered because reports are meant to be printed.

### Importing positions from a screenshot

This is optional and needs an API key from Anthropic, OpenAI or DeepSeek. Usage is billed by that
provider, not by this project.

1. Choose *Upload CSV files* and upload a prices file. The import section appears only then,
   because the positions must be matched to your price columns.
2. Open *Import positions from a screenshot*. Pick a provider and a model. Anthropic and DeepSeek
   have a suggested model. For OpenAI, enter a vision-capable model from your account. Names
   change, so check your provider's list.
3. Paste your API key, add a PNG, JPEG or WebP screenshot (under 5 MB), tick the consent box and
   press *Read screenshot*. Crop out account numbers first.
4. Check every row against the screenshot. Set each row's *Price column*, or leave it on
   *(skip)*. Use one kind of figure for all rows: market values, or percentages that total
   about 100.
5. Press *Use as weights*. Weights are market values divided by their total, over the listed
   positions only, so cash or holdings you skipped are outside the analysis. You can still edit
   them in the Weights section. *Remove imported weights* undoes it. Uploading a different prices
   file discards them.

If you see `CERTIFICATE_VERIFY_FAILED` or "Could not verify ... security certificate": on a Mac
with Python from python.org, open `/Applications/Python 3.x/` and run *Install Certificates.command*,
or run `python -m pip install --upgrade certifi`, then restart the app. Certificate checking is
never turned off.

The model can misread numbers, so treat its output as a draft. Its token usage is shown after each
read. The data flow and limits are in [SECURITY.md](../SECURITY.md).

## Input files

### Prices

A CSV with a `date` column followed by one column of prices per ticker.

```csv
date,SYN_EQ_US,SYN_GOVT,SYN_BENCH
2022-01-03,100.0000,100.0000,100.0000
2022-01-04,101.2787,99.3232,100.5258
```

- Dates are `YYYY-MM-DD`, unique, and in ascending order.
- Prices are positive numbers. Use adjusted (total-return) prices if you want dividends included;
  the library cannot tell which you supplied.
- All prices must be in one currency.
- A benchmark is an ordinary price column that you name when calling `analyse`. It must not
  also be a weighted asset.
- Empty cells are allowed up to 5% per column. Affected dates are dropped for all assets and the
  count is reported.
- Comma-separated, UTF-8. Blank lines are ignored.

### Weights

```csv
ticker,weight
SYN_EQ_US,0.30
SYN_GOVT,0.70
```

- Fractions that sum to 1, not percentages.
- Long-only: no negative weights.
- Every weighted ticker needs a price column, and every price column needs a weight (or be the
  benchmark). A weight of `0` keeps an asset in the correlation matrix without holding it.

## Running an analysis

```python
from portfolio_risk import AnalysisConfig, analyse, load_prices, load_weights

prices = load_prices("examples/sample_prices_synthetic.csv")
weights = load_weights("examples/sample_weights_synthetic.csv")

config = AnalysisConfig(periods_per_year=252, risk_free_annual=0.0)
result = analyse(prices, weights, config, benchmark="SYN_BENCH")

print(result.performance.sharpe_ratio)
print(result.performance.drawdown.max_drawdown)
print(result.var[0].historical_var)  # 95% one-period loss, as a positive fraction
print(result.risk_contribution)
print(result.warnings)
```

`AnalysisResult` fields: `performance`, `var` (one entry per confidence level), `correlation`,
`asset_table`, `hhi`, `effective_positions`, `risk_contribution`, `benchmark`, `wealth`,
`drawdowns`, `portfolio_returns`, and `warnings`.

### Configuration

| Parameter | Default | Meaning |
|---|---|---|
| `periods_per_year` | 252 | Annualisation factor. 365 for daily data with weekends, 52 weekly, 12 monthly. |
| `risk_free_annual` | 0.0 | Effective annual risk-free rate, used by Sharpe and by alpha. |
| `mar_annual` | 0.0 | Minimum acceptable annual return for Sortino. |
| `confidence_levels` | (0.95, 0.99) | VaR and CVaR levels. |
| `min_observations` | 60 | Fewest returns accepted. |

`analyse(..., normalise_weights=True)` rescales weights that do not sum to 1 and records a
warning, instead of rejecting them.

## Reading the output

- **Warnings are not errors.** Read them. A short history, dropped dates, a possible split, or a
  frequency mismatch all change how much you should trust a number.
- **VaR and CVaR are positive losses.** 0.01 means a 1% loss over one period at the stated
  confidence.
- **NaN means undefined**, for example Sharpe for a constant series or Sortino when no return is
  below the MAR. It is deliberate rather than a failure.
- **Contribution to risk** is a share of variance and sums to 1. A negative share means the
  asset reduces overall risk.

Full definitions are in [methodology.md](methodology.md).

## Common errors

| Message begins | Cause and fix |
|---|---|
| `The first column must be named 'date'` | Rename the first header cell. |
| `Line N: '...' is not a date in YYYY-MM-DD format` | Reformat dates, for example `02/01/2024` to `2024-01-02`. |
| `Dates are not in ascending order` | Sort the file, or call `load_prices(..., sort_dates=True)`. |
| `Line N, column 'X': '...' is not a number` | Remove currency symbols and thousands separators. |
| `The header contains semicolons` | Re-export with commas as the separator. |
| `Weights sum to X, not 1` | Use fractions, or pass `normalise_weights=True`. |
| `Price columns with no weight` | Add a weight (0 is allowed), remove the column, or name it as the benchmark. |
| `N return observations after cleaning; at least M are required` | Supply a longer history. |
| `... has constant returns` | A stale or flat price series. Remove it or fix the data. |

## Sample data

`examples/sample_prices_synthetic.csv` and `examples/sample_weights_synthetic.csv` are
**synthetic**. They come from a seeded simulation (`scripts/generate_sample.py`), describe no real
security, and should not be read as market history. Regenerate them with:

```bash
python scripts/generate_sample.py
```
