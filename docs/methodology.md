# Methodology

This document defines every statistic the library computes, the conventions it assumes, and the
checks applied to input data. Each formula is exercised by a unit test whose expected value is
worked by hand; the worked examples in section 9 are those same fixtures.

The statistics are descriptive. They summarise the history you supply. They do not predict
future performance, and nothing here is investment advice.

## 1. Conventions

| Item | Convention |
|---|---|
| Return type | Simple (arithmetic) period returns, `r_t = P_t / P_{t-1} - 1`, as decimals. |
| Observations | `n` returns come from `n + 1` prices. All "observation" counts mean returns. |
| Portfolio weights | Constant and long-only. The portfolio is assumed to be rebalanced to the target weights every period, so `r_p,t = w' r_t`. Buy-and-hold drift is not modelled. |
| Annualisation factor `m` | Periods per year. Default 252. Use 365 for daily data including weekends, 52 weekly, 12 monthly. The factor is a parameter, never inferred silently; a mismatch with the date spacing produces a warning. |
| Annual-to-period rates | Geometric: `rate_period = (1 + rate_annual)^(1/m) - 1`. Applies to the risk-free rate and the minimum acceptable return (MAR). |
| Sign of loss measures | VaR and CVaR are reported as **positive losses** in return units. 0.02 means a 2% loss. |
| Horizon | VaR and CVaR are for one observation period. No square-root-of-time scaling is applied. |
| Numeric type | 64-bit floating point. No decimal arithmetic. |

Simple returns are used because the weighted sum of simple returns across assets is the
portfolio return exactly. The weighted sum of log returns is not.

## 2. Return measures

With returns `r_1 ... r_n`:

- **Total return** `R = prod(1 + r_t) - 1`.
- **Annualised return (CAGR)** `(prod(1 + r_t))^(m/n) - 1`.
- **Wealth index** `W_0 = 1`, `W_t = W_{t-1} (1 + r_t)`.

## 3. Volatility and risk-adjusted ratios

- **Annualised volatility** `sigma = std(r, ddof=1) * sqrt(m)`. The square-root scaling assumes
  returns are serially uncorrelated.
- **Sharpe ratio** `mean(r - rf) / std(r - rf, ddof=1) * sqrt(m)`, where `rf` is the per-period
  risk-free rate. Undefined (reported as NaN) when the returns are constant.
- **Downside deviation** `DD = sqrt(mean(min(r - MAR, 0)^2))`. The mean is taken over **all**
  `n` observations, not only those below the MAR. Averaging over only the losing periods is a
  common variant that overstates downside risk and is not used here.
- **Sortino ratio** `(mean(r) - MAR) / DD * sqrt(m)`. Undefined (NaN) when no observation falls
  below the MAR.

The default risk-free rate and MAR are both 0. Sharpe and Sortino are sensitive to these inputs;
set them explicitly for any comparison that matters.

## 4. Drawdown

Computed on the wealth index (or any positive level series):

- **Drawdown** `D_t = W_t / max(W_0 ... W_t) - 1`, always in `[-1, 0]`.
- **Maximum drawdown** `min_t D_t`, with its **peak** (last time the running maximum was set
  before the trough), **trough** (date of the minimum) and **recovery** (first date after the
  trough at which the previous peak is regained, or none).
- **Longest drawdown duration** is the longest underwater spell, measured in periods from the
  peak to the first observation at or above that peak. A spell that has not been recovered by
  the final observation is measured to the final observation and flagged as **ongoing**. This
  spell is not necessarily the one containing the maximum drawdown.
- **Current drawdown** is `D_n`.

## 5. Value at Risk and Conditional VaR

`c` is the confidence level (0.95, 0.99 by default) and `alpha = 1 - c`.

- **Historical VaR** `-q_alpha(r)`, where `q_alpha` is the empirical `alpha`-quantile with linear
  interpolation between order statistics (the default `numpy.quantile` method, Hyndman and Fan
  type 7).
- **Historical CVaR** `-mean(r : r <= q_alpha(r))`. With few observations the tail may contain a
  single return, in which case CVaR equals the worst loss.
- **Parametric (normal) VaR** `-mean(r) + std(r, ddof=1) * z_c`, with `z_c` the standard normal
  quantile of `c`.
- **Parametric (normal) CVaR** `-mean(r) + std(r, ddof=1) * phi(z_c) / alpha`, with `phi` the
  standard normal density.

Estimation error is large in the tail. At 99% confidence a 250-observation sample has about two
or three observations beyond the quantile. A warning is issued below 250 observations.
Parametric figures understate risk when returns are fat-tailed or skewed, which is typical.

## 6. Correlation, concentration and risk contribution

- **Correlation and covariance** are sample (`ddof=1`) statistics of per-period asset returns.
  An asset whose returns are constant has undefined correlation and is rejected.
- **Herfindahl-Hirschman index** `HHI = sum(w_i^2)`. It ranges from `1/N` (equal weights) to 1.
- **Effective number of positions** `1 / HHI`.
- **Contribution to risk** (Euler decomposition of variance)
  `RC_i = w_i (Sigma w)_i / (w' Sigma w)`. The shares sum to 1. A share can be negative for an
  asset that diversifies the rest of the portfolio. Shares are of variance, which is how
  portfolio volatility `sqrt(w' Sigma w)` decomposes by homogeneity.

## 7. Benchmark statistics

With portfolio returns `r_p` and benchmark returns `r_b`, both on the same dates:

- **Beta and alpha** from OLS of `r_p - rf` on `r_b - rf`. `beta = cov / var` of the excess
  returns. **Alpha** is the regression intercept multiplied by `m` (Jensen's alpha, arithmetic
  annualisation).
- **Active return** `mean(r_p - r_b) * m`.
- **Tracking error** `std(r_p - r_b, ddof=1) * sqrt(m)`.
- **Information ratio** `active return / tracking error`. NaN if the active return is constant.
- **Correlation and R-squared** of `r_p` with `r_b`.

## 8. Input validation

Problems that would make a result wrong are rejected with a message naming the line, column or
date. Recoverable problems produce a warning. Nothing is repaired silently.

| Condition | Result |
|---|---|
| Empty file, header only, wrong header, wrong field count, non-UTF-8 text, semicolon separators | Rejected, with the line number where one applies. |
| Date not `YYYY-MM-DD`, impossible calendar date, duplicate date | Rejected, with line number(s). |
| Dates out of order | Rejected, unless sorting is requested explicitly. |
| Non-numeric or infinite price | Rejected, with line and column. |
| Non-positive price | Rejected, with ticker and date. |
| More than 5% of a column's prices missing | Rejected. |
| Any missing price within that limit | The date is dropped for all assets (inner join) and the number dropped is reported. |
| Fewer than `min_observations` returns (default 60) | Rejected. |
| Fewer than 250 returns | Warning: tail estimates are unreliable. |
| A single-period move above 50% | Warning, listing the first five. May be an unadjusted split. |
| Date spacing disagrees with the annualisation factor | Warning. |
| Weights negative, non-finite, duplicated, or summing to zero | Rejected. |
| Weights not summing to 1 | Rejected, or rescaled with a warning when requested. A hint is given when they look like percentages. |
| Price column with no weight, weight with no price column, benchmark also weighted | Rejected. Give an asset a weight of 0 to keep it in the correlation matrix. |
| Constant returns for a weighted asset or the benchmark | Rejected: correlation or beta is undefined. |

## 9. Worked examples

These are the fixtures used in `tests/`.

**Returns and drawdown.** Prices 100, 110, 99, 108.9 give returns +10%, -10%, +10%.
Total return `1.10 * 0.90 * 1.10 - 1 = 8.9%`. Running peaks are 100, 110, 110, 110, so the
drawdowns are 0, 0, `99/110 - 1 = -10%`, `108.9/110 - 1 = -1%`. The maximum drawdown is -10%
(peak at the second date, trough at the third) and it has not been recovered: the longest spell
is 2 periods and ongoing.

**Sharpe.** Returns 0.02, 0.04, 0.06, 0.08, 0.10, mean 0.06, sum of squared deviations 0.004,
sample variance 0.001. With `rf = 0.01` per period and `m = 4`:
`0.05 / sqrt(0.001) * 2 = sqrt(10) = 3.1623`.

**Sortino.** Returns -0.02, 0.03, 0.03, -0.04, 0.02, mean 0.004. Shortfalls below 0 are -0.02
and -0.04, so `DD = sqrt((0.0004 + 0.0016) / 5) = 0.02`. With `m = 4`:
`0.004 / 0.02 * 2 = 0.4`.

**Historical VaR.** Twenty returns whose lowest are -0.10, -0.05, -0.03. The 5% quantile sits at
position `0.05 * 19 = 0.95`, so `q = -0.10 + 0.95 * 0.05 = -0.0525` and VaR(95%) = 5.25%. Only
-0.10 lies at or below `q`, so CVaR(95%) = 10%.

**Parametric VaR.** Returns +0.01, -0.01, +0.01, -0.01: mean 0, `std = sqrt(0.0004/3)`.
VaR(95%) = `1.6448536 * std`, CVaR(95%) = `2.0627128 * std`.

**Risk contribution.** Two assets with covariance `[[0.04, 0.01], [0.01, 0.01]]` and equal
weights. `Sigma w = [0.025, 0.010]`, variance `0.0175`, contributions `0.0125/0.0175 = 5/7` and
`0.005/0.0175 = 2/7`.

## 10. Limitations

- Constant weights. Real portfolios drift between rebalances; contributions to risk and
  drawdowns for a buy-and-hold portfolio will differ.
- Long-only. Shorts, leverage and derivatives are not supported.
- One currency. Prices are assumed to be in the same currency and to be total-return or
  adjusted prices. Dividends, splits, fees, taxes and trading costs are not modelled; the
  library cannot tell whether supplied prices are adjusted.
- Time-weighted and money-weighted returns require cash-flow data and are not yet implemented.
- VaR assumes the sample is representative of the next period. Historical VaR cannot see
  scenarios absent from the sample. Parametric VaR assumes normality.
- Volatility, Sharpe and Sortino annualisation assume serially uncorrelated returns.
- All ratios have wide sampling error on a few years of data. A Sharpe ratio of 0.7 over three
  years is not statistically distinguishable from many other values.
- Results are only as good as the input file. The library checks for obvious corruption, not
  correctness.

## 11. References

- Sharpe, W. F. (1994). The Sharpe Ratio. *Journal of Portfolio Management* 21(1).
- Sortino, F. A. and Price, L. N. (1994). Performance Measurement in a Downside Risk Framework.
  *Journal of Investing* 3(3).
- Rockafellar, R. T. and Uryasev, S. (2000). Optimization of Conditional Value-at-Risk.
  *Journal of Risk* 2(3).
- Hyndman, R. J. and Fan, Y. (1996). Sample Quantiles in Statistical Packages.
  *The American Statistician* 50(4).
- Jensen, M. C. (1968). The Performance of Mutual Funds in the Period 1945-1964.
  *Journal of Finance* 23(2).
