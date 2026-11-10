"""Write examples/sample_report.pdf and .xlsx from the bundled synthetic sample.

Run from the repository root:  python scripts/generate_example_reports.py
The generation time is fixed so the files change only when the code does.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from portfolio_risk import AnalysisConfig, analyse, load_prices, load_weights
from portfolio_risk.report import ReportMeta
from portfolio_risk.report.excel import build_workbook
from portfolio_risk.report.pdf import build_pdf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "examples"


def main() -> None:
    prices = load_prices(OUT / "sample_prices_synthetic.csv")
    weights = load_weights(OUT / "sample_weights_synthetic.csv")
    result = analyse(prices, weights, AnalysisConfig(), benchmark="SYN_BENCH")
    meta = ReportMeta(
        source_note="Synthetic sample data (examples/sample_prices_synthetic.csv)",
        generated=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
    )
    (OUT / "sample_report.pdf").write_bytes(build_pdf(result, meta))
    (OUT / "sample_report.xlsx").write_bytes(build_workbook(result, meta))
    print("wrote examples/sample_report.pdf and examples/sample_report.xlsx")


if __name__ == "__main__":
    main()
