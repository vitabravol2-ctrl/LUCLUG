from __future__ import annotations

from collections import deque
from threading import Lock
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
            if not series:
                return None
            return series[-1]

    def snapshot(self, symbol: str) -> List[QuoteTick]:
        with self._lock:
            series = self._data.get(symbol)
            if not series:
                return []
            return list(series)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def _trim(self, series: deque[QuoteTick], now_ms: int) -> None:
        threshold = now_ms - self.window_ms
        while series and series[0].timestamp_ms < threshold:
            series.popleft()
