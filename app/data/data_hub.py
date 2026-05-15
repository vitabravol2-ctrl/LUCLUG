from __future__ import annotations

import threading
import time
from collections import deque

from app.core.history import RollingHistory
from app.core.models import QuoteTick
from app.data.binance_ws import BinanceBookTickerClient


class DataHub:
    SYMBOLS = ("BTCUSDT", "BTCU")

    def __init__(self, history: RollingHistory | None = None, logger=None) -> None:
        self.history = history or RollingHistory()
        self._log = logger or (lambda _m: None)
        self._lock = threading.Lock()
        self._latest: dict[str, QuoteTick] = {}
        self._status = {s: "WAIT" for s in self.SYMBOLS}
        self._source = {s: "-" for s in self.SYMBOLS}
        self._tick_times = {s: deque(maxlen=500) for s in self.SYMBOLS}
        self._clients: dict[str, BinanceBookTickerClient] = {}
        self._running = False
        self._diag_stop = threading.Event()
        self._diag_thread: threading.Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._diag_stop.clear()
            if not self._diag_thread or not self._diag_thread.is_alive():
                self._diag_thread = threading.Thread(target=self._diag_loop, daemon=True)
                self._diag_thread.start()
            if not self._clients:
                for s in self.SYMBOLS:
                    self._clients[s] = BinanceBookTickerClient(s, self.on_tick, self._on_status, self._log)
            clients = list(self._clients.values())
        for c in clients:
            c.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False
            self._diag_stop.set()
            clients = list(self._clients.values())
        for c in clients:
            c.stop()

    def clear(self) -> None:
        self.history.clear()
        with self._lock:
            self._latest.clear()
            for s in self.SYMBOLS:
                self._tick_times[s].clear()

    def on_tick(self, tick: QuoteTick, source: str | None = None) -> None:
        if source:
            tick.source = source
        if tick.local_received_ms is None:
            tick.local_received_ms = int(time.time() * 1000)
        if tick.timestamp_ms is None:
            tick.timestamp_ms = tick.local_received_ms
        self.history.add_tick(tick)
        now = time.time()
        with self._lock:
            self._latest[tick.symbol] = tick
            self._source[tick.symbol] = tick.source
            self._status[tick.symbol] = "LIVE" if tick.source != "TEST" else "TEST"
            self._tick_times[tick.symbol].append(now)

    def get_latest(self, symbol: str):
        with self._lock:
            return self._latest.get(symbol)

    def get_latest_all(self):
        with self._lock:
            return dict(self._latest)

    def get_snapshot(self):
        return self.history.snapshot()

    def get_status(self, symbol: str):
        with self._lock:
            return self._status.get(symbol, "WAIT")

    def get_metrics(self):
        now = time.time()
        out = {}
        with self._lock:
            for s in self.SYMBOLS:
                q = self._latest.get(s)
                ages = None if not q else max(0, int(now * 1000) - q.local_received_ms)
                times = [t for t in self._tick_times[s] if now - t <= 1.0]
                out[s] = {
                    "status": self._status[s],
                    "source": self._source[s],
                    "ticks_per_sec": len(times),
                    "ticks": self.history.count(s),
                    "age_ms": ages,
                }
        return out

    def is_live(self) -> bool:
        with self._lock:
            return self._running

    def _on_status(self, symbol: str, status: str) -> None:
        with self._lock:
            self._status[symbol] = status

    def _diag_loop(self) -> None:
        while not self._diag_stop.wait(2.0):
            m = self.get_metrics()
            b1 = m.get("BTCUSDT", {})
            b2 = m.get("BTCU", {})
            self._log(f"[DATA] BTCUSDT status={b1.get('status')} source={b1.get('source')} ticks={b1.get('ticks')} age_ms={b1.get('age_ms')}")
            self._log(f"[DATA] BTCU status={b2.get('status')} source={b2.get('source')} ticks={b2.get('ticks')} age_ms={b2.get('age_ms')}")
            snap = self.get_snapshot()
            self._log(f"[DATAHUB] snapshot leader={len(snap.get('BTCUSDT', []))} follower={len(snap.get('BTCU', []))} total_ticks={sum(len(v) for v in snap.values())}")
