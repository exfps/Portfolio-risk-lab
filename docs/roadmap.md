# Roadmap and to-do list

Status of planned work. Items are not promises; the order follows what makes the tool most useful.

## Done

- Calculation core, validation and tests (see `docs/methodology.md`).
- Streamlit interface with CSV upload, editable weights and benchmark comparison.
- Optional screenshot import with a user-supplied API key (Anthropic, OpenAI, DeepSeek).

## Done: price download by ticker

- [x] Replaceable price-provider interface (`portfolio_risk.data`) with a Yahoo Finance adapter.
- [x] Symbol search by name or ticker.
- [x] Calendar alignment: common days or weekly.
- [x] Currency detection, warnings, and conversion to a base currency.
- [x] Optional benchmark ticker and a recorded risk-free-rate source.
- [x] Prices go through the same validator as uploaded files.

Constraint: Yahoo's data is for personal use and the yfinance library is unofficial. Fine for a
personal tool or demo; a commercial product serving clients needs a licensed data provider.
None of this has been run against the live service yet.

## Planned: GCC investors

The main intended audience is investors in Gulf markets (Saudi Tadawul, Dubai, Abu Dhabi, Qatar,
Kuwait, Bahrain, Oman).

- [ ] **Coverage test:** confirm which Gulf exchanges and tickers the chosen data source really
      returns, including the correct symbol suffixes. Not yet verified.
- [x] **Multi-currency (downloaded prices):** built; Gulf pairs untested live. Most Gulf currencies are pegged to the US dollar; the Kuwaiti dinar tracks a basket.
- [x] **Trading calendars:** Saudi and several neighbours trade Sunday to Thursday, the UAE Monday
      to Friday. Choose between common-day alignment and weekly returns.
- [~] **Benchmarks:** any ticker can be a benchmark; ready-made shortcuts for TASI and the Dubai
      and Abu Dhabi indices are not built and their Yahoo symbols are unverified.
- [x] **Risk-free rate:** user-entered, with the source recorded in the Assumptions tab.
- [ ] **Decision needed:** individual investors, or advisers serving clients? The second needs a
      licensed data source.
- [ ] Optional: Shariah-compliance flag from a separate source; Arabic labels and right-to-left layout.

## Next

- [x] PDF and Excel report, theme customiser (done).
- [ ] Buy-and-hold with real transactions: time-weighted and money-weighted returns.
- [x] Windows CI job (added; not yet run on GitHub). [ ] Verification on real Windows hardware.
- [ ] Screenshot import: test against the real provider APIs, downscale images and strip metadata.
