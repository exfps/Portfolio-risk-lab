"""Regenerate the synthetic example files in ``examples/``.

    python scripts/generate_sample.py

The output is deterministic for a given seed. All values are simulated.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from portfolio_risk.sample_data import (
    SAMPLE_PERIODS,
    SAMPLE_SEED,
    generate_sample_prices,
    sample_weights,
)

PRICES_FILE = "sample_prices_synthetic.csv"
WEIGHTS_FILE = "sample_weights_synthetic.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--output-dir", type=Path, default=Path("examples"))
    parser.add_argument("--seed", type=int, default=SAMPLE_SEED)
    parser.add_argument("--periods", type=int, default=SAMPLE_PERIODS)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    prices = generate_sample_prices(seed=args.seed, periods=args.periods)
    prices.to_csv(args.output_dir / PRICES_FILE, float_format="%.4f", lineterminator="\n")
    sample_weights().to_csv(
        args.output_dir / WEIGHTS_FILE, float_format="%.2f", lineterminator="\n"
    )
    print(f"Wrote {PRICES_FILE} ({len(prices)} rows) and {WEIGHTS_FILE} to {args.output_dir}/")


if __name__ == "__main__":
    main()
