"""Short-lived in-memory cache and parallel download, the two things that cut waiting time.

Downloading ten tickers one after another costs ten network round trips in sequence. They are
independent, so ``download_many`` runs them concurrently. ``CachedProvider`` remembers recent
answers so that re-running with the same tickers, or a second visitor asking for the same
symbol, does not hit the provider again. Both are plain Python and know nothing about the UI.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from portfolio_risk.data.base import PriceProvider, PriceSeries, SymbolMatch

T = TypeVar("T")


class CachedProvider:
    """Wraps a provider with a bounded time-to-live cache. Thread safe."""

    def __init__(
        self,
        inner: PriceProvider,
        *,
        ttl_seconds: float = 900.0,
        max_entries: int = 256,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._inner = inner
        self._ttl = ttl_seconds
        self._max = max_entries
        self._clock = clock
        self._lock = threading.Lock()
        self._store: OrderedDict[tuple[object, ...], tuple[float, object]] = OrderedDict()
        self.name = inner.name

    def _get(self, key: tuple[object, ...]) -> object | None:
        with self._lock:
            hit = self._store.get(key)
            if hit is None:
                return None
            stamp, value = hit
            if self._clock() - stamp > self._ttl:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return value

    def _put(self, key: tuple[object, ...], value: object) -> None:
        with self._lock:
            self._store[key] = (self._clock(), value)
            self._store.move_to_end(key)
            while len(self._store) > self._max:
                self._store.popitem(last=False)

    def search(self, query: str, limit: int = 10) -> list[SymbolMatch]:
        key: tuple[object, ...] = ("search", query.strip().lower(), limit)
        cached = self._get(key)
        if isinstance(cached, list):
            return list(cached)
        found = self._inner.search(query, limit)
        self._put(key, list(found))
        return found

    def download(self, symbol: str, start: dt.date, end: dt.date) -> PriceSeries:
        key: tuple[object, ...] = ("download", symbol.strip().upper(), start, end)
        cached = self._get(key)
        if isinstance(cached, PriceSeries):
            return PriceSeries(cached.symbol, cached.prices.copy(), cached.currency)
        fresh = self._inner.download(symbol, start, end)
        self._put(key, PriceSeries(fresh.symbol, fresh.prices.copy(), fresh.currency))
        return fresh


def download_many(
    provider: PriceProvider,
    symbols: list[str],
    start: dt.date,
    end: dt.date,
    *,
    workers: int = 8,
) -> list[PriceSeries]:
    """Download concurrently, return in the order given.

    If several fail, the error of the first failing symbol in the given order is raised, so the
    message does not depend on which request happened to finish first.
    """
    if len(symbols) <= 1:
        return [provider.download(s, start, end) for s in symbols]
    with ThreadPoolExecutor(max_workers=min(workers, len(symbols))) as pool:
        futures = [pool.submit(provider.download, s, start, end) for s in symbols]
        return [f.result() for f in futures]
