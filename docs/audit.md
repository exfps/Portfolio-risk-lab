# Code audit

An internal review of version 0.2.0.dev0, done on 2026-11-18 by the author with Claude's help,
using the standards an institutional code review would apply: correctness of the numbers,
security of inputs and outputs, robustness, and honesty of the documentation. It is a
self-review, not an independent third-party audit. Findings are listed with what was done.

## Scope and method

| Area | How it was checked |
|---|---|
| Test suite, lint, types | `pytest` with coverage, `ruff`, `mypy --strict` |
| Static security scan | `bandit` over `src/` |
| Secrets | pattern scan of the working tree and the Git history; the test `test_no_secrets.py` |
| Financial formulas | every headline statistic recomputed independently (NumPy, SciPy `linregress` and `norm`) on random data and compared to 1e-10 |
| Monte Carlo | statistical checks: simulated mean and volatility against the fitted inputs for all four models, effect of transaction costs, determinism with a seed |
| Input handling | hostile asset names pushed through the PDF, the workbook and the HTML tables |
| Network client | read of the whole client; redirect behaviour tested against a local server |

## Findings

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | High | **Spreadsheet formula injection.** An asset name from a CSV (or a screenshot import) that begins with `=` was written to the Excel workbook as a live formula, for example `=HYPERLINK(...)`. | Fixed: every formula cell is stored as text before saving; this report writes no formulas of its own. Regression test added. |
| 2 | Medium | **Meaningless ratios from near-constant series.** Prices compounding at a fixed rate produce returns that differ by about 1e-16. The exact-equality "constant" check missed this, so Sharpe came out near 7e13 instead of undefined. | Fixed: a series is constant when its spread is below 1e-12; alpha-decay Sharpe uses the same floor. Regression test added. |
| 3 | Medium | **API key could follow a redirect.** `urllib` resends request headers, including `x-api-key` and `Authorization`, to the address a redirect points to. | Fixed: redirects are refused and the error says so. Test with a second local server confirms the key never reaches it. |
| 4 | Low | `assert` used for type narrowing in `simulation/models.py` and `report/excel.py`; asserts vanish under `python -O`. | Fixed: explicit checks with clear errors. |
| 5 | Info | Bandit B310 (`urlopen` scheme) on the AI client. | False positive: the scheme is enforced to HTTPS (HTTP only on localhost) before the call. Marked `nosec` with the reason. |
| 6 | Info | Bandit B406 on `xml.sax.saxutils.escape` in the PDF code. | False positive: it is used to escape output text, not to parse XML. |
| 7 | Info | `pip-audit` could not run in the review environment. | Open: run `pip-audit` (or enable Dependabot) on the published repository. |

## Checked and found sound

- Returns, annualised return, volatility, Sharpe, Sortino, historical and parametric VaR and
  CVaR, drawdown (maximum, peak, trough), beta, alpha, R-squared, tracking error, information
  ratio, risk contributions and the end-to-end `analyse()` result all match independent
  calculations to rounding error.
- Monte Carlo: for Gaussian, Student-t, bootstrap and block bootstrap, the simulated terminal
  mean and per-period volatility match the fitted inputs within sampling error (for example
  Gaussian: volatility 0.00936 against 0.00934 historical); transaction costs lower the
  result; a fixed seed reproduces results exactly.
- HTML output: every table is escaped; hostile names show as text. PDF output: markup in names
  is escaped and shown literally.
- The API key is held in a password field, sent only in a header over HTTPS, removed from every
  error message, and is never placed in the address or written to disk or logs. Uploaded images
  are capped at 5 MB and identified by content, not file name.
- No secrets in the tree or in the Git history; `.env` and similar files are ignored.

## Known weaknesses that remain (also in the README)

1. Not run against live data: Yahoo Finance, Gulf (`.SR`) symbols, FX and the AI providers are
   tested with fakes only (see `verification.md`).
2. Constant weights only; buy-and-hold drift, time-weighted and money-weighted returns are not
   modelled.
3. Monte Carlo is a fitted model, not a forecast; it inherits the calm or turbulence of the
   sample window.
4. Alpha-decay thresholds are conventions and the windows overlap, so z-scores are a flag, not
   a significance test.
5. Uploaded CSVs are bounded only by Streamlit's upload limit (200 MB by default). A hosted
   deployment should set `server.maxUploadSize` lower.
6. Excel output was checked with LibreOffice, not Microsoft Excel.
7. The Streamlit session keeps the typed API key in memory for the length of the session.
