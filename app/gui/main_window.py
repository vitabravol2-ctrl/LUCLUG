from __future__ import annotations

import random
import threading
import time
from collections import deque

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.analysis.price_lead_lag import PriceLeadLagAnalyzer, PriceLeadLagConfig
from app.core.history import RollingHistory
from app.core.models import LagResult, QuoteTick
from app.data.binance_ws import BinanceBookTickerClient


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LUC v0.1.2 — Lead-Lag Analyzer")
        self.resize(1280, 760)
        self.setStyleSheet(
            "QWidget { background-color: #1e1e1e; color: #e6e6e6; }"
            "QPushButton { padding: 6px 12px; }"
            "QHeaderView::section { background-color: #2a2f3a; color: #f5f5f5; font-weight: 600; }"
        )

        self.history = RollingHistory(window_ms=5 * 60 * 1000)
        self.analyzer = PriceLeadLagAnalyzer(PriceLeadLagConfig())
        self.start_ts = 0.0
        self.running = False
        self.ticks = deque(maxlen=2000)
        self.tick_meta: dict[str, dict[str, float | str | int]] = {
            "BTCUSDT": {"count": 0, "last_ms": 0, "source": "DIRECT"},
            "BTCU": {"count": 0, "last_ms": 0, "source": "DIRECT"},
        }
        self.best_lag = None
        self.ws_clients = {}
        self.selected_lag_ms: int | None = None
        self.last_results_by_lag: dict[int, LagResult] = {}
        self.test_feed_stop = threading.Event()
        self.test_feed_thread: threading.Thread | None = None

        self._build_ui()

        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._refresh)
        self.ui_timer.start(500)

        self.diag_timer = QTimer(self)
        self.diag_timer.timeout.connect(self._log_tick_diagnostics)
        self.diag_timer.start(2000)

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)

        top = QHBoxLayout()
        self.ws_btcusdt = QLabel("BTCUSDT: DISCONNECTED")
        self.ws_btcu = QLabel("BTCU: DISCONNECTED")
        self.tps_label = QLabel("ticks/sec: 0.0")
        self.uptime_label = QLabel("uptime: 00:00")
        self.btn_start = QPushButton("START")
        self.btn_stop = QPushButton("STOP")
        self.btn_clear = QPushButton("CLEAR")
        self.btn_test = QPushButton("TEST FEED")
        self.btn_start.clicked.connect(self.start_analyzer)
        self.btn_stop.clicked.connect(self.stop_analyzer)
        self.btn_clear.clicked.connect(self.clear_all)
        self.btn_test.clicked.connect(self.start_test_feed)
        for w in [self.ws_btcusdt, self.ws_btcu, self.tps_label, self.uptime_label, self.btn_start, self.btn_stop, self.btn_clear, self.btn_test]:
            top.addWidget(w)
        layout.addLayout(top)

        cards = QGridLayout()
        self.btcusdt_values = {k: QLabel("-") for k in ["bid", "ask", "mid", "spread"]}
        self.btcu_values = {k: QLabel("-") for k in ["bid", "ask", "mid", "spread"]}
        self._add_symbol_card(cards, 0, "BTCUSDT", self.btcusdt_values)
        self._add_symbol_card(cards, 1, "BTCU", self.btcu_values)
        layout.addLayout(cards)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels([
            "Quality", "Lag ms", "Samples", "Match %", "Avg Edge U", "Median Edge U",
            "Stability %", "Confidence", "Last Leader Move", "Last Follower Move", "Reason"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setDefaultSectionSize(110)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        splitter.addWidget(self.table)

        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("Lag details will appear here")
        splitter.addWidget(self.details)
        splitter.setSizes([980, 280])
        layout.addWidget(splitter)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)
        self.setCentralWidget(root)

    def _add_symbol_card(self, grid: QGridLayout, row: int, symbol: str, target: dict[str, QLabel]) -> None:
        grid.addWidget(QLabel(f"{symbol}"), row, 0)
        for i, key in enumerate(["bid", "ask", "mid", "spread"], start=1):
            grid.addWidget(QLabel(key), row, i * 2 - 1)
            grid.addWidget(target[key], row, i * 2)

    def start_analyzer(self) -> None:
        if self.running:
            return
        self.running = True
        self.start_ts = time.time()
        self._append_log("[APP] START clicked")
        self.ws_clients = {
            "BTCUSDT": BinanceBookTickerClient("BTCUSDT", self._on_tick, self._on_status, self._append_log),
            "BTCU": BinanceBookTickerClient("BTCU", self._on_tick, self._on_status, self._append_log),
        }
        for client in self.ws_clients.values():
            client.start()

    def start_test_feed(self) -> None:
        self._append_log("[APP] TEST FEED clicked")
        self.stop_analyzer()
        self.running = True
        self.start_ts = time.time()
        self.test_feed_stop.clear()

        def _run() -> None:
            base = 100000.0
            lag_queue = deque()
            while not self.test_feed_stop.is_set():
                tms = int(time.time() * 1000)
                base += random.uniform(-2.0, 2.0)
                usdt = QuoteTick("BTCUSDT", tms, base - 0.5, base + 0.5)
                self._on_status("BTCUSDT", "LIVE")
                self._on_tick(usdt, "DIRECT")
                lag_queue.append((tms + 500, usdt.mid + random.uniform(-0.2, 0.2)))
                while lag_queue and lag_queue[0][0] <= int(time.time() * 1000):
                    _, mid = lag_queue.popleft()
                    btcu = QuoteTick("BTCU", int(time.time() * 1000), mid - 0.5, mid + 0.5)
                    self._on_status("BTCU", "FALLBACK_LIVE")
                    self._on_tick(btcu, "FALLBACK")
                time.sleep(0.05)

        self.test_feed_thread = threading.Thread(target=_run, daemon=True)
        self.test_feed_thread.start()

    def stop_analyzer(self) -> None:
        self.test_feed_stop.set()
        if self.test_feed_thread and self.test_feed_thread.is_alive():
            self.test_feed_thread.join(timeout=1.0)
        if self.running:
            for client in self.ws_clients.values():
                client.stop()
            self.ws_clients.clear()
            self.running = False
            self._append_log("analyzer stopped")

    def clear_all(self) -> None:
        self.history.clear()
        self.table.setRowCount(0)
        self.ticks.clear()
        self.last_results_by_lag.clear()
        self.details.clear()
        self._append_log("history cleared")

    def _on_tick(self, tick: QuoteTick, source: str) -> None:
        self.history.add_tick(tick)
        self.ticks.append(time.time())
        meta = self.tick_meta[tick.symbol]
        meta["count"] = int(meta["count"]) + 1
        meta["last_ms"] = tick.timestamp_ms
        meta["source"] = source

    def _on_status(self, symbol: str, status: str) -> None:
        if symbol == "BTCUSDT":
            self.ws_btcusdt.setText(f"BTCUSDT: {status}")
        elif symbol == "BTCU":
            self.ws_btcu.setText(f"BTCU: {status}")

    def _log_tick_diagnostics(self) -> None:
        now_ms = int(time.time() * 1000)
        for symbol in ["BTCUSDT", "BTCU"]:
            meta = self.tick_meta[symbol]
            last_ms = int(meta["last_ms"])
            age = now_ms - last_ms if last_ms else -1
            self._append_log(f"[DATA] {symbol} ticks={int(meta['count'])} last_age_ms={age} source={meta['source']}")

    def _refresh(self) -> None:
        now = time.time()
        while self.ticks and now - self.ticks[0] > 1.0:
            self.ticks.popleft()
        self.tps_label.setText(f"ticks/sec: {len(self.ticks):.1f}")
        if self.running and self.start_ts:
            elapsed = int(now - self.start_ts)
            self.uptime_label.setText(f"uptime: {elapsed // 60:02d}:{elapsed % 60:02d}")

        for symbol, labels in [("BTCUSDT", self.btcusdt_values), ("BTCU", self.btcu_values)]:
            tick = self.history.latest(symbol)
            if tick:
                labels["bid"].setText(f"{tick.bid:.6f}")
                labels["ask"].setText(f"{tick.ask:.6f}")
                labels["mid"].setText(f"{tick.mid:.6f}")
                labels["spread"].setText(f"{tick.spread:.6f}")

        results = self.analyzer.compute(self.history.snapshot("BTCUSDT"), self.history.snapshot("BTCU"))
        self.last_results_by_lag = {r.lag_ms: r for r in results}
        self._render_table(results)

    def _render_table(self, results: list[LagResult]) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(results))
        for r, row in enumerate(results):
            values = [row.signal_quality, str(row.lag_ms), str(row.samples), f"{row.direction_match_pct:.2f}", f"{row.avg_edge_u:.8f}", f"{row.median_edge_u:.8f}", f"{row.stability_pct:.2f}", f"{row.confidence_score:.2f}", f"{row.last_leader_move:.8f}", f"{row.last_follower_move:.8f}", row.reason]
            for c, val in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(val))
        self.table.setSortingEnabled(True)

    def _on_row_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        lag_item = self.table.item(row, 1)
        if not lag_item:
            return
        lag_ms = int(lag_item.text())
        result = self.last_results_by_lag.get(lag_ms)
        if result:
            self._render_details(result)

    def _render_details(self, result: LagResult) -> None:
        self.details.setPlainText(f"selected lag_ms: {result.lag_ms}\nsamples: {result.samples}\nreason: {result.reason}")

    def _append_log(self, message: str) -> None:
        lines = self.log.toPlainText().splitlines()
        if lines and lines[-1] == message:
            return
        lines.append(message)
        self.log.setPlainText("\n".join(lines[-300:]))
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
