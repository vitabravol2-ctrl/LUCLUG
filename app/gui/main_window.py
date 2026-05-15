from __future__ import annotations

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
        self.setWindowTitle("LUC v0.1.1 — Lead-Lag Analyzer")
        self.resize(1280, 760)
        self.setStyleSheet("QWidget { background-color: #1e1e1e; color: #e6e6e6; } QPushButton { padding: 6px 12px; }")

        self.history = RollingHistory(window_ms=5 * 60 * 1000)
        self.analyzer = PriceLeadLagAnalyzer(PriceLeadLagConfig())
        self.start_ts = 0.0
        self.running = False
        self.ticks = deque(maxlen=1000)
        self.best_lag = None
        self.ws_clients = {}
        self.selected_lag_ms: int | None = None
        self.last_results_by_lag: dict[int, LagResult] = {}

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

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels([
            "Quality", "Lag ms", "Samples", "Match %", "Avg Edge U", "Median Edge U",
            "Stability %", "Confidence", "Last Leader Move", "Last Follower Move", "Reason"
        ])
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        splitter.addWidget(self.table)

        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("Lag details will appear here")
        splitter.addWidget(self.details)
        splitter.setSizes([900, 380])
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
        self.selected_lag_ms = None
        self.last_results_by_lag.clear()
        self.details.clear()
        self._append_log("history cleared")

    def _on_tick(self, tick: QuoteTick) -> None:
        self.history.add_tick(tick)
        self.ticks.append(time.time())

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

        results = self.analyzer.compute(self.history.snapshot("BTCUSDT"), self.history.snapshot("BTCU"))
        if not results:
            return

        self.last_results_by_lag = {r.lag_ms: r for r in results}
        self._render_table(results)
        if self.selected_lag_ms in self.last_results_by_lag:
            self._render_details(self.last_results_by_lag[self.selected_lag_ms])
        elif results:
            self.selected_lag_ms = results[0].lag_ms
            self._select_lag_row(self.selected_lag_ms)
            self._render_details(results[0])

    def _render_table(self, results: list[LagResult]) -> None:
        self.table.setSortingEnabled(False)
        selected = self.selected_lag_ms
        self.table.setRowCount(len(results))
        for r, row in enumerate(results):
            values = [
                row.signal_quality,
                str(row.lag_ms),
                str(row.samples),
                f"{row.direction_match_pct:.2f}",
                f"{row.avg_edge_u:.8f}",
                f"{row.median_edge_u:.8f}",
                f"{row.stability_pct:.2f}",
                f"{row.confidence_score:.2f}",
                f"{row.last_leader_move:.8f}",
                f"{row.last_follower_move:.8f}",
                row.reason,
            ]
            for c, val in enumerate(values):
                item = QTableWidgetItem(val)
                if c == 1:
                    item.setData(Qt.ItemDataRole.UserRole, row.lag_ms)
                self.table.setItem(r, c, item)

        self.table.setSortingEnabled(True)
        self._select_lag_row(selected)

    def _select_lag_row(self, lag_ms: int | None) -> None:
        if lag_ms is None:
            return
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item and int(item.text()) == lag_ms:
                self.table.selectRow(row)
                return

    def _on_row_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        lag_item = self.table.item(row, 1)
        if not lag_item:
            return
        lag_ms = int(lag_item.text())
        self.selected_lag_ms = lag_ms
        result = self.last_results_by_lag.get(lag_ms)
        if result:
            self._render_details(result)

    def _render_details(self, result: LagResult) -> None:
        lines = [
            f"selected lag_ms: {result.lag_ms}",
            f"samples: {result.samples}",
            f"direction_match_pct: {result.direction_match_pct:.2f}",
            f"btcusdt_move_avg: {result.btcusdt_move_avg:.8f}",
            f"btcu_future_move_avg: {result.btcu_future_move_avg:.8f}",
            f"avg_edge_u: {result.avg_edge_u:.8f}",
            f"median_edge_u: {result.median_edge_u:.8f}",
            f"max_edge_u: {result.max_edge_u:.8f}",
            f"min_edge_u: {result.min_edge_u:.8f}",
            f"stability_pct: {result.stability_pct:.2f}",
            f"signal_quality: {result.signal_quality}",
            f"last_signal_time: {result.last_signal_time}",
            f"last_leader_move: {result.last_leader_move:.8f}",
            f"last_follower_move: {result.last_follower_move:.8f}",
            f"confidence_score: {result.confidence_score:.2f}",
            f"reason: {result.reason}",
            "",
            "last 20 matched samples:",
        ]
        for d in result.details:
            lines.append(
                " | ".join([
                    f"leader_ts={d.leader_timestamp_ms}", f"follower_ts={d.follower_timestamp_ms}",
                    f"leader_before={d.leader_mid_before:.6f}", f"leader_after={d.leader_mid_after:.6f}",
                    f"follower_before={d.follower_mid_before:.6f}", f"follower_after={d.follower_mid_after:.6f}",
                    f"leader_move={d.leader_move:.6f}", f"follower_move={d.follower_move:.6f}",
                    f"matched={'yes' if d.direction_matched else 'no'}", f"edge_u={d.edge_u:.6f}",
                    f"detected_delay_ms={d.detected_delay_ms}",
                ])
            )
        self.details.setPlainText("\n".join(lines))

    def _append_log(self, message: str) -> None:
        lines = self.log.toPlainText().splitlines()
        if lines and lines[-1] == message:
            return
        lines.append(message)
        if len(lines) > 300:
            lines = lines[-300:]
        self.log.setPlainText("\n".join(lines))
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
