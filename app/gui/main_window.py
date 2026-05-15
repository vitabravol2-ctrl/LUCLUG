from __future__ import annotations

import random
import threading
import time
from collections import deque

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.analysis.price_lead_lag import PriceLeadLagAnalyzer, PriceLeadLagConfig
from app.core.history import RollingHistory
from app.core.lag_settings import LagSettingsStore
from app.core.models import LagResult, QuoteTick
from app.data.binance_ws import BinanceBookTickerClient

QUALITY_COLOR = {"WAIT": "#7f8c8d", "BAD": "#e74c3c", "WATCH": "#f1c40f", "GOOD": "#1abc9c", "HOT": "#2ecc71"}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LUC Terminal")
        self.resize(1400, 850)
        self.setStyleSheet("QWidget { background:#11161f; color:#d8deea; } QFrame{border:1px solid #2b3342; border-radius:8px;}")

        self.history = RollingHistory(window_ms=5 * 60 * 1000)
        self.settings_store = LagSettingsStore()
        self.settings = self.settings_store.load()
        module_settings = self.settings["PRICE_LEAD_LAG"]
        cfg = PriceLeadLagConfig(enabled=module_settings["enabled"], min_leader_move_u=module_settings.get("min_leader_move_u", 0.1), sort_by=module_settings["sort_by"], sort_desc=module_settings["sort_desc"], enabled_lags={k: bool(v) for k, v in {int(k): v for k, v in module_settings["lags"].items()}.items()})
        self.analyzer = PriceLeadLagAnalyzer(cfg)
        self.selected_lag_ms = module_settings.get("selected_lag_ms")
        self.running = False
        self.start_ts = 0.0
        self.ticks = deque(maxlen=2000)
        self.tick_meta = {"BTCUSDT": {"count": 0, "last_ms": 0, "source": "DIRECT", "status": "WAIT"}, "BTCU": {"count": 0, "last_ms": 0, "source": "DIRECT", "status": "WAIT"}}
        self.last_results_by_lag: dict[int, LagResult] = {}
        self.ws_clients = {}
        self.test_feed_stop = threading.Event()
        self.test_feed_thread = None
        self._build_ui()
        self.ui_timer = QTimer(self); self.ui_timer.timeout.connect(self._refresh); self.ui_timer.start(500)

    def _build_ui(self) -> None:
        root = QWidget(); layout = QVBoxLayout(root)
        top = QHBoxLayout();
        self.title = QLabel("LUC Terminal"); self.ws_btcusdt = QLabel("BTCUSDT: WAIT"); self.ws_btcu = QLabel("BTCU: WAIT"); self.source = QLabel("source: -"); self.tps = QLabel("ticks/sec: 0"); self.uptime = QLabel("uptime: 00:00")
        self.btn_start = QPushButton("START"); self.btn_stop = QPushButton("STOP"); self.btn_clear = QPushButton("CLEAR"); self.btn_test = QPushButton("TEST FEED")
        self.btn_start.clicked.connect(self.start_analyzer); self.btn_stop.clicked.connect(self.stop_analyzer); self.btn_clear.clicked.connect(self.clear_all); self.btn_test.clicked.connect(self.start_test_feed)
        for w in [self.title, self.ws_btcusdt, self.ws_btcu, self.source, self.tps, self.uptime, self.btn_start, self.btn_stop, self.btn_clear, self.btn_test]: top.addWidget(w)
        layout.addLayout(top)

        market = QHBoxLayout(); self.btcusdt_card = self._mk_market_card("LEADER BTCUSDT"); self.btcu_card = self._mk_market_card("FOLLOWER BTCU"); market.addWidget(self.btcusdt_card[0]); market.addWidget(self.btcu_card[0]); layout.addLayout(market)

        main_split = QSplitter(Qt.Orientation.Horizontal)
        left = QFrame(); ll = QVBoxLayout(left); ll.addWidget(QLabel("Lag Modules")); self.module_enabled = QCheckBox("PRICE_LEAD_LAG ON"); self.module_enabled.setChecked(self.analyzer.config.enabled); self.module_enabled.toggled.connect(self._toggle_module); self.module_info = QLabel("WAIT"); ll.addWidget(self.module_enabled); ll.addWidget(self.module_info)

        center = QFrame(); cl = QVBoxLayout(center); cl.addWidget(QLabel("Lag Rows")); self.lag_list = QListWidget(); self.lag_list.itemClicked.connect(self._on_lag_clicked); cl.addWidget(self.lag_list)
        right = QFrame(); rl = QVBoxLayout(right); rl.addWidget(QLabel("Selected Lag Details")); self.details = QTextEdit(); self.details.setReadOnly(True); rl.addWidget(self.details)
        main_split.addWidget(left); main_split.addWidget(center); main_split.addWidget(right); main_split.setSizes([220, 760, 420]); layout.addWidget(main_split)

        self.log = QTextEdit(); self.log.setReadOnly(True); self.log.setFixedHeight(190); layout.addWidget(self.log)
        self.setCentralWidget(root)

    def _mk_market_card(self, title: str):
        frame = QFrame(); lay = QVBoxLayout(frame); lay.addWidget(QLabel(title)); vals = {k: QLabel("-") for k in ["bid", "ask", "mid", "spread", "age"]}
        for k in ["bid", "ask", "mid", "spread", "age"]: lay.addWidget(QLabel(f"{k}:")); lay.addWidget(vals[k])
        return frame, vals

    def _toggle_module(self, v: bool) -> None:
        self.analyzer.config.enabled = v; self._save_settings()

    def _save_settings(self) -> None:
        s = self.settings["PRICE_LEAD_LAG"]
        s["enabled"] = self.analyzer.config.enabled; s["selected_lag_ms"] = self.selected_lag_ms; s["sort_by"] = self.analyzer.config.sort_by; s["sort_desc"] = self.analyzer.config.sort_desc; s["min_leader_move_u"] = self.analyzer.config.min_leader_move_u
        s["lags"] = {str(k): bool(v) for k, v in self.analyzer.config.enabled_lags.items()}
        self.settings_store.save(self.settings)

    def closeEvent(self, event):
        self._save_settings(); self.stop_analyzer(); super().closeEvent(event)

    def start_analyzer(self):
        if self.running: return
        self.running = True; self.start_ts = time.time(); self._append_log("[APP] START")
        self.ws_clients = {"BTCUSDT": BinanceBookTickerClient("BTCUSDT", self._on_tick, self._on_status, self._append_log), "BTCU": BinanceBookTickerClient("BTCU", self._on_tick, self._on_status, self._append_log)}
        for c in self.ws_clients.values(): c.start()

    def stop_analyzer(self):
        self.test_feed_stop.set()
        if self.test_feed_thread and self.test_feed_thread.is_alive(): self.test_feed_thread.join(timeout=1.0)
        for c in self.ws_clients.values(): c.stop()
        self.ws_clients = {}; self.running = False

    def clear_all(self): self.history.clear(); self.lag_list.clear(); self.details.clear(); self._append_log("history cleared")

    def start_test_feed(self):
        self.stop_analyzer(); self.running = True; self.start_ts = time.time(); self.test_feed_stop.clear()
        def _run():
            base = 100000.0; lag_queue = deque()
            while not self.test_feed_stop.is_set():
                tms = int(time.time() * 1000); base += random.uniform(-2.0, 2.0)
                usdt = QuoteTick("BTCUSDT", tms, base - 0.5, base + 0.5); self._on_status("BTCUSDT", "LIVE"); self._on_tick(usdt, "DIRECT")
                lag_queue.append((tms + 500, usdt.mid + random.uniform(-0.2, 0.2)))
                while lag_queue and lag_queue[0][0] <= int(time.time() * 1000):
                    _, mid = lag_queue.popleft(); btcu = QuoteTick("BTCU", int(time.time() * 1000), mid - 0.5, mid + 0.5); self._on_status("BTCU", "FALLBACK_LIVE"); self._on_tick(btcu, "FALLBACK")
                time.sleep(0.05)
        self.test_feed_thread = threading.Thread(target=_run, daemon=True); self.test_feed_thread.start()

    def _on_tick(self, tick: QuoteTick, source: str):
        self.history.add_tick(tick); self.ticks.append(time.time()); m = self.tick_meta[tick.symbol]; m["count"] += 1; m["last_ms"] = tick.timestamp_ms; m["source"] = source

    def _on_status(self, symbol: str, status: str):
        self.tick_meta[symbol]["status"] = status; self.ws_btcusdt.setText(f"BTCUSDT: {self.tick_meta['BTCUSDT']['status']}"); self.ws_btcu.setText(f"BTCU: {self.tick_meta['BTCU']['status']}")

    def _refresh(self):
        now = time.time()
        while self.ticks and now - self.ticks[0] > 1.0: self.ticks.popleft()
        self.tps.setText(f"ticks/sec: {len(self.ticks):.1f}"); self.source.setText(f"source: {self.tick_meta['BTCU']['source']}")
        if self.running: elapsed = int(now - self.start_ts); self.uptime.setText(f"uptime: {elapsed//60:02d}:{elapsed%60:02d}")
        for symbol, card in [("BTCUSDT", self.btcusdt_card[1]), ("BTCU", self.btcu_card[1])]:
            t = self.history.latest(symbol)
            if not t: continue
            card["bid"].setText(f"{t.bid:.4f}"); card["ask"].setText(f"{t.ask:.4f}"); card["mid"].setText(f"{t.mid:.4f}"); card["spread"].setText(f"{t.spread:.5f}"); card["age"].setText(str(int(time.time()*1000)-t.timestamp_ms))
        results = self.analyzer.compute(self.history.snapshot("BTCUSDT"), self.history.snapshot("BTCU"))
        self.last_results_by_lag = {r.lag_ms: r for r in results}; self._render_rows(results)

    def _render_rows(self, results: list[LagResult]):
        self.lag_list.clear()
        if not self.analyzer.config.enabled:
            self.module_info.setText("OFF"); return
        self.module_info.setText("LIVE" if results else "WAIT")
        for row in results:
            text = f"lag {row.lag_ms}ms | {row.signal_quality} | S:{row.samples} | M:{row.direction_match_pct:.1f}% | E:{row.avg_edge_u:.6f} | St:{row.stability_pct:.1f} | C:{row.confidence_score:.1f} | {row.reason}"
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, row.lag_ms)
            it.setForeground(QUALITY_COLOR.get(row.signal_quality, "#d8deea"))
            self.lag_list.addItem(it)
            if self.selected_lag_ms == row.lag_ms:
                self.lag_list.setCurrentItem(it)
        if not self.selected_lag_ms and results:
            self.selected_lag_ms = results[0].lag_ms; self._save_settings()

    def _on_lag_clicked(self, item: QListWidgetItem):
        self.selected_lag_ms = int(item.data(Qt.ItemDataRole.UserRole)); self._save_settings(); r = self.last_results_by_lag.get(self.selected_lag_ms)
        if not r: return
        lines = [f"module: {self.analyzer.module_id}", f"selected lag: {r.lag_ms}ms", f"status: {r.signal_quality}", f"samples: {r.samples}", f"match: {r.direction_match_pct:.2f}%", f"avg edge: {r.avg_edge_u:.8f}", f"stability: {r.stability_pct:.2f}", f"confidence: {r.confidence_score:.2f}", "BTCUSDT move -> BTCU response after lag", "last 20 samples:"]
        for d in r.details[-20:]: lines.append(f"{d.leader_timestamp_ms} -> {d.follower_timestamp_ms}; direction matched: {'yes' if d.direction_matched else 'no'}; edge_u: {d.edge_u:.8f}; detected_delay_ms: {d.detected_delay_ms}")
        self.details.setPlainText("\n".join(lines))

    def _append_log(self, m: str):
        lines = self.log.toPlainText().splitlines();
        if lines and lines[-1] == m: return
        lines.append(m); self.log.setPlainText("\n".join(lines[-200:]))
