from __future__ import annotations

import random
import threading
import time
from collections import deque

from app.core.models import QuoteTick


class TestFeed:
    def __init__(self, on_tick, on_status, logger=None, lag_ms: int = 500, ticks_per_sec: int = 20) -> None:
        self._on_tick = on_tick
        self._on_status = on_status
        self._log = logger or (lambda _m: None)
        self._lag_ms = lag_ms
        self._interval = 1.0 / ticks_per_sec
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        base = 100000.0
        lag_queue = deque()
        while not self._stop.is_set():
            now_ms = int(time.time() * 1000)
            base += random.uniform(-2.0, 2.0)
            leader = QuoteTick("BTCUSDT", now_ms, base - 0.5, base + 0.5, local_received_ms=now_ms, source="TEST")
            self._on_status("BTCUSDT", "TEST")
            self._on_tick(leader)
            lag_queue.append((now_ms + self._lag_ms, leader.mid + random.uniform(-0.2, 0.2)))
            cur = int(time.time() * 1000)
            while lag_queue and lag_queue[0][0] <= cur:
                _, mid = lag_queue.popleft()
                follower = QuoteTick("BTCU", cur, mid - 0.5, mid + 0.5, local_received_ms=cur, source="TEST")
                self._on_status("BTCU", "TEST")
                self._on_tick(follower)
            time.sleep(self._interval)
