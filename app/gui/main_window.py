from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.analysis.price_lead_lag import PriceLeadLagAnalyzer
from app.core.history import RollingHistory
from app.core.models import QuoteTick
from app.data.binance_ws import BinanceBookTickerClient


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LUC v0.1.0 — Lead-Lag Analyzer")
        self.resize(1100, 700)
        self.setStyleSheet("QWidget { background-color: #1e1e1e; color: #e6e6e6; } QPushButton { padding: 6px 12px; }")

        self.history = RollingHistory()
        self.analyzer = PriceLeadLagAnalyzer()
        self.start_ts = 0.0
        self.running = False
        self.ticks = deque(maxlen=1000)
        self.best_lag = None

        self.ws_clients = {}

        self._build_ui()

        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._refresh)
        self.ui_timer.start(500)

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
        self.btn_start.clicked.connect(self.start_analyzer)
        self.btn_stop.clicked.connect(self.stop_analyzer)
        self.btn_clear.clicked.connect(self.clear_all)
        for w in [self.ws_btcusdt, self.ws_btcu, self.tps_label, self.uptime_label, self.btn_start, self.btn_stop, self.btn_clear]:
            top.addWidget(w)
        layout.addLayout(top)

        cards = QGridLayout()
        self.btcusdt_values = {k: QLabel("-") for k in ["bid", "ask", "mid", "spread"]}
        self.btcu_values = {k: QLabel("-") for k in ["bid", "ask", "mid", "spread"]}
        self._add_symbol_card(cards, 0, "BTCUSDT", self.btcusdt_values)
        self._add_symbol_card(cards, 1, "BTCU", self.btcu_values)
        layout.addLayout(cards)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "lag_ms", "samples", "btcusdt_move_avg", "btcu_future_move_avg", "direction_match_pct", "avg_edge_u", "stability_pct", "signal_quality"
        ])
        layout.addWidget(self.table)

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
        self._append_log("analyzer started")

        self.ws_clients = {
            "BTCUSDT": BinanceBookTickerClient("BTCUSDT", self._on_tick, self._on_status, self._append_log),
            "BTCU": BinanceBookTickerClient("BTCU", self._on_tick, self._on_status, self._append_log),
        }
        for client in self.ws_clients.values():
            client.start()

    def stop_analyzer(self) -> None:
        if not self.running:
            return
        for client in self.ws_clients.values():
            client.stop()
        self.ws_clients.clear()
        self.running = False
        self._append_log("analyzer stopped")

    def clear_all(self) -> None:
        self.history.clear()
        self.table.setRowCount(0)
        self.ticks.clear()
        self.best_lag = None
        self._append_log("history cleared")

    def _on_tick(self, tick: QuoteTick) -> None:
        self.history.add_tick(tick)
        self.ticks.append(time.time())
        self._append_log(f"tick accepted: {tick.symbol} mid={tick.mid:.6f}")

    def _on_status(self, symbol: str, status: str) -> None:
        if symbol == "BTCUSDT":
            self.ws_btcusdt.setText(f"BTCUSDT: {status}")
        elif symbol == "BTCU":
            self.ws_btcu.setText(f"BTCU: {status}")

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

        btcusdt_hist = self.history.snapshot("BTCUSDT")
        btcu_hist = self.history.snapshot("BTCU")
        results = self.analyzer.compute(btcusdt_hist, btcu_hist)
        if not results:
            self._append_log("not enough samples")
            return

        self.table.setRowCount(len(results))
        best = None
        for r, row in enumerate(results):
            values = [
                str(row.lag_ms), str(row.samples), f"{row.btcusdt_move_avg:.8f}", f"{row.btcu_future_move_avg:.8f}",
                f"{row.direction_match_pct:.2f}", f"{row.avg_edge_u:.8f}", f"{row.stability_pct:.2f}", row.signal_quality,
            ]
            for c, val in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(val))
            if best is None or row.stability_pct > best.stability_pct:
                best = row

        if best and (self.best_lag != best.lag_ms):
            self.best_lag = best.lag_ms
            self._append_log(f"best lag updated: {best.lag_ms}ms {best.signal_quality}")

    def _append_log(self, message: str) -> None:
        lines = self.log.toPlainText().splitlines()
        lines.append(message)
        if len(lines) > 300:
            lines = lines[-300:]
        self.log.setPlainText("\n".join(lines))
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
