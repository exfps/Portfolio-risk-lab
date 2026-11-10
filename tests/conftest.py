from __future__ import annotations

from collections.abc import Iterator

import pytest

from fake_provider import Fake, serve
from portfolio_risk.vision.providers import BASE_URL_OVERRIDE


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[Fake]:
    """A fake provider; every client in the test talks to it instead of the real service."""
    with serve() as server:
        monkeypatch.setenv(BASE_URL_OVERRIDE, server.url)
        yield server
