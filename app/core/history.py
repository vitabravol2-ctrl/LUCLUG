from __future__ import annotations

from collections import deque
from threading import Lock
from time import time
from typing import Dict, List, Optional

from app.core.models import QuoteTick


class RollingHistory:
    def __init__(self, window_ms: int = 5 * 60 * 1000) -> None:
        self.window_ms = window_ms
        self._lock = Lock()
        self._data: Dict[str, deque[QuoteTick]] = {}

    def add_tick(self, tick: QuoteTick) -> None:
        with self._lock:
            series = self._data.setdefault(tick.symbol, deque())
            series.append(tick)
            self._trim(series, tick.timestamp_ms)

    def latest(self, symbol: str) -> Optional[QuoteTick]:
        with self._lock:
            series = self._data.get(symbol)
            return series[-1] if series else None

    def snapshot(self, symbol: str | None = None) -> List[QuoteTick] | Dict[str, List[QuoteTick]]:
        with self._lock:
            if symbol is not None:
                series = self._data.get(symbol)
                return list(series) if series else []
            return {sym: list(series) for sym, series in self._data.items()}

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def count(self, symbol: str) -> int:
        with self._lock:
            return len(self._data.get(symbol, ()))

    def age_ms(self, symbol: str) -> int | None:
        with self._lock:
            series = self._data.get(symbol)
            if not series:
                return None
            return max(0, int(time() * 1000) - series[-1].timestamp_ms)

    def _trim(self, series: deque[QuoteTick], now_ms: int) -> None:
        threshold = now_ms - self.window_ms
        while series and series[0].timestamp_ms < threshold:
            series.popleft()
