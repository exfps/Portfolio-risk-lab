"""Launcher: ``portfolio-risk-lab`` or ``python -m portfolio_risk`` opens the interface."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from portfolio_risk.ui.theme import STREAMLIT_OPTIONS

INSTALL_HINT = (
    "The interface needs Streamlit. Install it with:\n"
    '    python -m pip install "portfolio-risk-lab[app]"\n'
    '(from a source checkout: python -m pip install -e ".[app]")'
)


def build_command(extra_args: Sequence[str] = ()) -> list[str]:
    """The command that starts Streamlit with this project's app and theme.

    Uses the current interpreter, so it works the same in any virtual environment on
    macOS, Linux and Windows. Extra arguments are passed to ``streamlit run`` unchanged.
    """
    script = Path(__file__).resolve().parent / "ui" / "app.py"
    options: list[str] = []
    for name, value in STREAMLIT_OPTIONS.items():
        options += [f"--{name}", value]
    return [sys.executable, "-m", "streamlit", "run", str(script), *options, *extra_args]


def main(argv: Sequence[str] | None = None) -> int:
    if importlib.util.find_spec("streamlit") is None:
        print(INSTALL_HINT, file=sys.stderr)
        return 1
    extra = list(sys.argv[1:] if argv is None else argv)
    try:
        return subprocess.call(build_command(extra))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
