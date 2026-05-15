from __future__ import annotations

import json
import threading
import time
from typing import Callable

from websocket import WebSocketApp

from app.core.models import QuoteTick


class BinanceBookTickerClient:
    def __init__(self, symbol: str, on_tick: Callable[[QuoteTick, str], None], on_status: Callable[[str, str], None], on_log: Callable[[str], None]) -> None:
        self.symbol = symbol.upper()
        self._on_tick = on_tick
        self._on_status = on_status
        self._on_log = on_log
        self._thread: threading.Thread | None = None
        self._ws: WebSocketApp | None = None
        self._stop = threading.Event()
        self._ticks_since_connect = 0

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

    def _connect(self, url: str, source: str, fallback_filter: bool = False) -> None:
        self._ticks_since_connect = 0
        self._on_status(self.symbol, "CONNECTING")

        def on_message(_: WebSocketApp, message: str) -> None:
            try:
                data = json.loads(message)
                if fallback_filter and data.get("s") != self.symbol:
                    return
                local_ms = int(time.time() * 1000)
                tick = QuoteTick(
                    symbol=self.symbol,
                    timestamp_ms=local_ms,
                    local_received_ms=local_ms,
                    event_time_ms=int(data["E"]) if data.get("E") else None,
                    bid=float(data["b"]),
                    ask=float(data["a"]),
                    source=source,
                )
                self._ticks_since_connect += 1
                self._on_status(self.symbol, "FALLBACK_LIVE" if source == "FALLBACK" else "LIVE")
                self._on_tick(tick, source)
            except Exception as exc:
                self._on_log(f"[WS_ERROR] symbol={self.symbol} url={url} type={type(exc).__name__} message={exc}")

        def on_error(_: WebSocketApp, error: object) -> None:
            self._on_status(self.symbol, "ERROR")
            self._on_log(f"[WS_ERROR] symbol={self.symbol} url={url} type={type(error).__name__} message={error}")

        self._ws = WebSocketApp(url, on_message=on_message, on_error=on_error)
        timer = None
        if self.symbol == "BTCU" and source == "DIRECT":
            timer = threading.Timer(5.0, lambda: self._ws and self._ticks_since_connect == 0 and self._ws.close())
            timer.daemon = True
            timer.start()
        self._ws.run_forever(ping_interval=20, ping_timeout=10)
        if timer:
            timer.cancel()

    def _run(self) -> None:
        direct_url = f"wss://stream.binance.com:9443/ws/{self.symbol.lower()}@bookTicker"
        fallback_url = "wss://stream.binance.com:9443/ws/!bookTicker"
        while not self._stop.is_set():
            self._connect(direct_url, "DIRECT")
            if self._stop.is_set():
                return
            if self.symbol == "BTCU" and self._ticks_since_connect == 0:
                self._on_log("[WS] BTCU direct no ticks -> fallback allBookTicker")
                self._connect(fallback_url, "FALLBACK", fallback_filter=True)
                if self._ticks_since_connect > 0:
                    self._on_log("[WS] BTCU fallback live")
            if not self._stop.is_set():
                time.sleep(1.0)
