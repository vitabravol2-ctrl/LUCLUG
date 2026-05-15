from __future__ import annotations

import json
import threading
import time
from typing import Callable

from websocket import WebSocketApp

from app.core.models import QuoteTick


class BinanceBookTickerClient:
    def __init__(
        self,
        symbol: str,
        on_tick: Callable[[QuoteTick], None],
        on_status: Callable[[str, str], None],
        on_log: Callable[[str], None],
    ) -> None:
        self.symbol = symbol.upper()
        self._on_tick = on_tick
        self._on_status = on_status
        self._on_log = on_log
        self._thread: threading.Thread | None = None
        self._ws: WebSocketApp | None = None
        self._stop = threading.Event()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2.0)
        self._on_status(self.symbol, "DISCONNECTED")

    def _run(self) -> None:
        stream = f"{self.symbol.lower()}@bookTicker"
        url = f"wss://stream.binance.com:9443/ws/{stream}"

        def on_open(_: WebSocketApp) -> None:
            self._on_status(self.symbol, "CONNECTED")
            self._on_log(f"WS connected: {self.symbol}")

        def on_message(_: WebSocketApp, message: str) -> None:
            try:
                data = json.loads(message)
                tick = QuoteTick(
                    symbol=self.symbol,
                    timestamp_ms=int(data.get("E", int(time.time() * 1000))),
                    bid=float(data["b"]),
                    ask=float(data["a"]),
                )
                self._on_tick(tick)
            except Exception as exc:
                self._on_log(f"tick parse error {self.symbol}: {exc}")

        def on_error(_: WebSocketApp, error: object) -> None:
            self._on_status(self.symbol, "ERROR")
            self._on_log(f"WS error {self.symbol}: {error}")

        def on_close(_: WebSocketApp, __, ___) -> None:
            self._on_status(self.symbol, "DISCONNECTED")
            self._on_log(f"WS disconnected: {self.symbol}")

        while not self._stop.is_set():
            self._ws = WebSocketApp(url, on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
            self._ws.run_forever(ping_interval=20, ping_timeout=10)
            if not self._stop.is_set():
                time.sleep(1.0)
