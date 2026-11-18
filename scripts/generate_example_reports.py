"""Write the example reports from the bundled synthetic sample (every section, seeded).

Writes examples/sample_report.pdf and .xlsx, and sample_report_colour_blind.pdf, which shows
the colour-blind-safe style.

Run from the repository root:  python scripts/generate_example_reports.py
The generation time is fixed so the files change only when the code does.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from portfolio_risk import AnalysisConfig, analyse, load_prices, load_weights
from portfolio_risk.comparison import compare
from portfolio_risk.report import ReportMeta
from portfolio_risk.report.excel import build_workbook
from portfolio_risk.report.inputs import ReportInputs
from portfolio_risk.report.pdf import build_pdf
from portfolio_risk.report.style import preset
from portfolio_risk.returns import simple_returns
from portfolio_risk.simulation import SimulationConfig, make_model, run_simulation
from portfolio_risk.ui.tearsheet_tables import named_returns

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "examples"


def main() -> None:
    prices = load_prices(OUT / "sample_prices_synthetic.csv")
    weights = load_weights(OUT / "sample_weights_synthetic.csv")
    result = analyse(prices, weights, AnalysisConfig(), benchmark="SYN_BENCH")
    own = prices[list(weights.index)]
    sets = {
        "Current": weights,
        "Defensive": pd.Series({"SYN_GOVT": 0.5, "SYN_CORP": 0.3, "SYN_EQ_US": 0.2}),
        "Equity heavy": pd.Series(
            {"SYN_EQ_US": 0.4, "SYN_EQ_EU": 0.3, "SYN_EQ_EM": 0.2, "SYN_GOVT": 0.1}
        ),
    }
    config = SimulationConfig(n_paths=2000, horizon_years=5, seed=42)
    returns = simple_returns(own)
    inputs = ReportInputs(
        tearsheet=named_returns(result, prices, "SYN_BENCH", ["SYN_EQ_US"]),
        comparison=compare(prices, sets, result.config, "SYN_BENCH"),
        simulation=[
            run_simulation(returns, weights, make_model(key), config)
            for key in ("gaussian", "student_t")
        ],
        benchmark="SYN_BENCH",
    )
    meta = ReportMeta(
        source_note="Synthetic sample data (examples/sample_prices_synthetic.csv)",
        generated=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
    )
    (OUT / "sample_report.pdf").write_bytes(build_pdf(result, meta, inputs))
    (OUT / "sample_report.xlsx").write_bytes(build_workbook(result, meta, inputs))
    safe = preset("Colour-blind safe")
    (OUT / "sample_report_colour_blind.pdf").write_bytes(
        build_pdf(result, meta, inputs, None, safe)
    )
    print("wrote sample_report.pdf, sample_report.xlsx and sample_report_colour_blind.pdf")


if __name__ == "__main__":
    main()
