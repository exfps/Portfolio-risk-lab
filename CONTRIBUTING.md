# Contributing

Contributions are welcome: bug reports, corrections to the methodology, tests, and features that
fit the roadmap in the README. For anything larger than a small fix, open an issue first so the
approach can be agreed before you write code.

## Development setup

Python 3.12 or later.

```bash
git clone <repository-url>
cd portfolio-risk-lab
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

## Checks

All of these run in CI and must pass:

```bash
ruff check .
ruff format --check .
mypy
python -m pytest --cov --cov-fail-under=90
```

`ruff format .` and `ruff check --fix .` fix most style problems automatically.

## Testing the screenshot import

Tests use a local fake provider (`tests/fake_provider.py`), never the real services and never a
real key. Setting `PORTFOLIO_RISK_VISION_BASE_URL=http://127.0.0.1:<port>` points the clients at
it. Do not add tests that need network access or credentials.

## Standards

- **A formula change needs a test with a hand-calculated expected value.** State the working in
  the test docstring or comments so a reviewer can verify it without running code. Do not
  derive the expected value by running the function under test.
- **Update `docs/methodology.md`** when a definition, convention or validation rule changes.
- Library code under `src/` must not import a UI framework, access the network, or read
  environment variables.
- Functions are typed (`mypy --strict`), pure where possible, and raise a `PortfolioRiskError`
  subclass with a message that names the offending value.
- Validation rejects bad data or reports a warning. It does not repair data silently.
- No new runtime dependency without a clear need and a permissive licence.
- Never commit real portfolios, broker exports, screenshots of accounts, or API keys. Test data
  must be synthetic or clearly redistributable.

## Commits and pull requests

- Use short, imperative commit messages in the conventional style, for example
  `fix: handle unrecovered drawdown in duration` or `docs: clarify CVaR tail definition`.
- Keep each pull request to one logical change, with tests, and describe what changed and why.
- Add an entry under "Unreleased" in `CHANGELOG.md`.

## Reporting bugs

Include the version, Python version, a minimal input that reproduces the problem (synthetic
data, please), the output you got and the output you expected. If you believe a statistic is
wrong, cite the definition you are comparing against.
