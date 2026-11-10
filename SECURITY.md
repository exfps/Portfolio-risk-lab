# Security policy

## Supported versions

Only the latest release receives security fixes.

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's private vulnerability
reporting: on the repository page choose **Security**, then **Report a vulnerability**. Include
what you found, how to reproduce it, and the impact you expect. You can expect an initial
response within a week.

## Scope and data handling

- The current release is a local library and a local web interface. It reads the CSV files you
  supply, makes no network requests unless you use one of the two optional features described
  below, and writes nothing to disk. The interface
  holds uploads in memory for the session. It binds to Streamlit's default address; do not
  expose it to an untrusted network, because it has no authentication. Usage statistics are
  disabled in `.streamlit/config.toml`. (The sample-data script writes only to the
  directory you give it.)
- Input files are parsed as untrusted text. Malformed input is rejected with an error and is not
  executed or evaluated.
- Portfolio files can be sensitive. Do not commit real holdings or broker exports to a public
  repository; `.gitignore` excludes `data/` and `uploads/` by default.

## Screenshot import (optional)

The interface can read positions from a screenshot using a vision model and an API key you
supply (Anthropic, OpenAI or DeepSeek). This is one of two features that send data off your machine (the other is price download, below).
It is off until you open the section, tick the consent box and press the button. What the code
does, in `src/portfolio_risk/vision/`:

- **The key** is typed into a masked field and held in memory for the browser session. It is never
  written to disk, never logged, and is removed from any provider error message before display.
  It is sent only in an HTTP header, and requests are refused unless the address is HTTPS. The
  environment variable `PORTFOLIO_RISK_VISION_BASE_URL` can redirect requests, but only to
  localhost, and exists for testing.
- **The image** is sent once, to the provider you chose, and is not stored by this program. Your
  provider's own retention terms apply. Check the type from the file's bytes (PNG, JPEG or WebP)
  and refuse files over 5 MB.
- **The answer** is untrusted text. It is parsed as JSON, validated field by field against a
  fixed schema, shown to you in an editable table, and used only after you press **Use as
  weights**. Text inside the screenshot cannot trigger any action: the program has no tools to
  call and acts only on validated numbers. A malicious screenshot can at worst produce wrong
  figures, which is why review is required.
- **Cost:** one request per press of the button, no automatic retries, and the token counts the
  provider reports are shown.
- **Operators** of a hosted demo can switch the feature off with `PORTFOLIO_RISK_DISABLE_IMPORT=1`.

Not done: images are not downscaled and their metadata is not stripped before sending, so crop out
account numbers and names first. Tests run against a local fake server, and the clients have not yet
been run against the real services.

## Price download (optional)

*Search and download* sends the ticker symbols you type, and the date range, to Yahoo Finance
through the unofficial `yfinance` library. No account, key or portfolio weights are sent. The
downloaded prices are held in memory for the session, pass through the same validation as an
uploaded file, and are not written to disk. The feature needs the optional `data` extra and is
removed entirely by `PORTFOLIO_RISK_DISABLE_DOWNLOAD=1`. Treat third-party responses as untrusted:
they are parsed as numbers only. The adapter has not been run against the live service.

If you find a way these properties could be violated, please report it through the channel above.
