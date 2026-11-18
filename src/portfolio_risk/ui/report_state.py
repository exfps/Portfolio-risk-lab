"""What the tabs hand to the report: the latest simulation and comparison, tied to the data.

The export panel is drawn after the tabs, so it sees whatever a tab produced on this run. A
result is stored with a signature of the data and weights it came from; if either changes the
stored result is ignored, so a report never mixes a stale projection with a new portfolio.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

SIMULATION = "report_simulation"
COMPARISON = "report_comparison"

Signature = tuple[int, str, tuple[tuple[str, float], ...]]


def signature(prices: pd.DataFrame, weights: pd.Series) -> Signature:
    items = tuple((str(k), round(float(v), 10)) for k, v in weights.items())
    return (len(prices), str(prices.index[-1]), items)


def remember(key: str, sig: Signature, value: Any) -> None:
    st.session_state[key] = (sig, value)


def forget(key: str) -> None:
    st.session_state.pop(key, None)


def recall(key: str, sig: Signature) -> Any | None:
    stored = st.session_state.get(key)
    if stored is None or stored[0] != sig:
        return None
    return stored[1]
