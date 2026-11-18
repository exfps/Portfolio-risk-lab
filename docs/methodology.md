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

## 10. Monte Carlo projection

The projection simulates many possible futures for the constant-weight portfolio and reports
the spread of outcomes. It is a model of the past, not a forecast.

**Inputs.** Validated simple returns (no missing or infinite values, at least 60 observations,
a warning below 252), the portfolio weights, and a `SimulationConfig`: number of paths
(10 to 200,000), horizon in years, frequency (daily 252, weekly 52, monthly 12 periods a year),
rebalancing (never, every period, monthly, quarterly, annually), transaction cost as a fraction
of traded value, starting value, the "bust" drawdown (default 25%), the target return
(default +50%) and an optional random seed. Daily history is compounded to weekly or monthly
returns for those frequencies; partial periods at the edges are dropped. Every assumption used is
printed with the result and in the report.

**Return models** (each is fitted to the historical returns and produces simulated asset returns):

| Model | What it assumes |
|---|---|
| Gaussian | Returns are multivariate normal with the historical mean and covariance. |
| Student-t | Same covariance, fatter tails: `R = mu + sqrt((nu - 2) / W) * A Z`, with `Z` standard normal, `W` chi-squared with `nu` degrees of freedom (default 5) and `A A' = Sigma`. One `W` per path and period is shared by all assets, so extreme days hit assets together. The `(nu - 2)` factor keeps the covariance equal to the historical one. |
| Historical bootstrap | Whole historical days are drawn with replacement, which keeps the relationships between assets but not the order of days. |
| Block bootstrap | Runs of consecutive days (default 21, circular) are drawn, which keeps some volatility clustering. The circular join is one artificial seam. |

With **drift = historical** the average historical return is kept. Averages estimated from a few
years are very noisy, so **drift = zero** removes them and isolates risk. Parametric returns
are floored at -100% so a wealth path cannot go negative.

**Wealth.** Holdings grow with the simulated asset returns. At each rebalancing date they are
returned to the target weights and the traded value (the sum of absolute differences) is charged
at the transaction cost.

**Statistics.** Per path: ending value, annualised return, maximum drawdown, volatility, longest
time below a previous peak. Across paths: percentiles (5, 10, 25, 50, 75, 90, 95) of ending
value; value at risk and expected shortfall over the whole horizon at 95% and 99%, reported as
positive losses and not annualised; the probability of ending below the start; the probability
that any path falls the bust drawdown below its peak; and the probability of ending above, or
ever touching, the target. The scenario table is a reading of percentiles of the ending value:
bull is the 90th, base the median, bear the 10th and severe downturn the 1st. These are
conventions chosen for readability, not forecasts.

**Reproducibility.** A fixed seed gives identical paths. Without one each run differs, within
Monte Carlo error (shrinking with the square root of the number of paths).

**Limits.** The models inherit the estimation window: a calm window gives calm futures. The
historical mean is a poor guide to the future and dominates long-horizon results, which is why
the zero-drift option exists. Over multi-year horizons the Gaussian and Student-t models give
similar answers because sums of many returns approach normality, so a fat-tailed model matters
mainly for short horizons and tail risk. A bootstrap cannot produce an event that is absent
from the history. Percentiles of simulated wealth are not confidence intervals for the real
future.

## 11. Alpha decay (rolling-window health)

The question is whether recent behaviour is unusual compared with the portfolio's own history.
For each statistic and each window length (default 21, 63 and 126 periods) the statistic is
computed over every rolling window. The most recent window is then compared with the earlier
ones.

**Statistics (10).** Annualised return, volatility, downside volatility, maximum drawdown,
average drawdown, win rate, Value at Risk 95%, expected shortfall 95%, payoff ratio and Sharpe
ratio. Each has a direction: a volatility lower than usual is good, a return higher than usual
is good.

**Score.** With `prior` the statistic in all earlier windows of the same length, `z = sign *
(latest - mean(prior)) / std(prior)`, where `sign` is +1 when higher is better and -1 otherwise,
so a higher score is always better. The percentile rank of the latest value among `prior` is
shown beside it, with ties counted as half.

**Ratings.** Excellent for `z >= 1.0`, Good for `z >= -0.5`, Warning for `z >= -1.5`, Critical
below that. With fewer than 30 earlier windows the cell is shown as "Insufficient history"
instead of a rating. These thresholds are conventions, not statistical results.

**Limits.** Rolling windows overlap, including the earlier windows with the latest one, so they
are strongly autocorrelated and the history holds far fewer independent observations than it
has windows. The z-score is a rough flag, not a significance test. A z-score assumes a roughly
symmetric distribution; drawdown, VaR and payoff ratio are skewed, hence the percentile. Short
windows are noisy (VaR from fewer than about 20 observations is close to the single worst day).
A "Critical" reading says recent behaviour differs from the past, not why, and not that it will
continue.

## 12. Classic tearsheet

A table of 20 statistics side by side for the portfolio, the benchmark and up to four holdings:
total return, annualised return, volatility, Sharpe, Sortino, Calmar, maximum drawdown,
longest drawdown, one-period VaR and expected shortfall at 95%, skewness, excess kurtosis, best
and worst period, share of positive periods, payoff ratio, profit factor, best and worst calendar
month and share of positive months. Five benchmark-relative rows (beta, annualised alpha,
correlation, tracking error and information ratio) use the formulas in section 7.

Monthly returns compound the per-period returns inside each calendar month. The calendar-year
table does the same by year; the first and last years may be partial years, and they are
included as they are. Rolling volatility, Sharpe and beta use the window you choose (at least 5
periods). The deepest five drawdown episodes run from the last high through the first return to
that high, with the depth and the number of observations; an episode that has not recovered has
no end date. Ratios with a zero denominator are shown as not available rather than as a large
number. A series with fewer than 30 returns is refused with a message, because the statistics
would not mean much.

## 13. Portfolio comparison

Up to five constant-weight portfolios are evaluated on the dates on which every asset used by
any of them, and the benchmark, has a price, so differences come from the weights and not from
the sample. Each portfolio is analysed exactly as the main portfolio is. The comparison adds the
holdings side by side, concentration (the number of holdings, the Herfindahl-Hirschman index
and the effective number of positions, `1 / HHI`) and the correlation between the portfolios'
returns. A portfolio whose return series has zero variance cannot be analysed and is reported
by name. Weight sets are saved as a versioned JSON document (at most 10 sets, 50 assets, 40
character names) that is validated on load.

## 14. Reports

The PDF and Excel exports contain only the sections you select. Monte Carlo and the comparison
appear only if you have already run them in their tabs, with the same data and weights; a
stored result is discarded if either has changed, so a report never mixes a stale projection with
a new portfolio. Nothing is simulated at export time. Every report states the data source, the
assumptions in force and a notice that it is not investment advice. The PDF charts are vector
drawings; the Excel charts are native workbook charts.

A report style controls presentation only: colours, line width and dash pattern, per-series
overrides, paper tone and font. It never changes a number. The colour-blind preset uses the Okabe
and Ito (2008) palette, and its dash patterns differ between lines so colour is not the only cue.

## 15. Limitations

- Constant weights. Real portfolios drift between rebalances; contributions to risk and
  drawdowns for a buy-and-hold portfolio will differ.
- Long-only. Shorts, leverage and derivatives are not supported.
- One currency. Prices are assumed to be in the same currency and to be total-return or
  adjusted prices. Dividends, splits, fees, taxes and trading costs are not modelled; the
  library cannot tell whether supplied prices are adjusted.
- Time-weighted and money-weighted returns require cash-flow data and are not yet implemented.
- Monte Carlo, alpha decay and the comparison inherit every limit above and add their own
  (sections 10, 11 and 13). They describe the model and the sample, not the future.
- VaR assumes the sample is representative of the next period. Historical VaR cannot see
  scenarios absent from the sample. Parametric VaR assumes normality.
- Volatility, Sharpe and Sortino annualisation assume serially uncorrelated returns.
- All ratios have wide sampling error on a few years of data. A Sharpe ratio of 0.7 over three
  years is not statistically distinguishable from many other values.
- Results are only as good as the input file. The library checks for obvious corruption, not
  correctness.

## 16. References

- Sharpe, W. F. (1994). The Sharpe Ratio. *Journal of Portfolio Management* 21(1).
- Sortino, F. A. and Price, L. N. (1994). Performance Measurement in a Downside Risk Framework.
  *Journal of Investing* 3(3).
- Rockafellar, R. T. and Uryasev, S. (2000). Optimization of Conditional Value-at-Risk.
  *Journal of Risk* 2(3).
- Hyndman, R. J. and Fan, Y. (1996). Sample Quantiles in Statistical Packages.
  *The American Statistician* 50(4).
- Jensen, M. C. (1968). The Performance of Mutual Funds in the Period 1945-1964.
  *Journal of Finance* 23(2).
- Okabe, M. and Ito, K. (2008). Color Universal Design (CUD): how to make figures and
  presentations that are friendly to colorblind people.
- Efron, B. (1979). Bootstrap Methods: Another Look at the Jackknife. *Annals of Statistics* 7(1).
- Politis, D. N. and Romano, J. P. (1992). A Circular Block-Resampling Procedure for Stationary
  Data. In *Exploring the Limits of Bootstrap*.
