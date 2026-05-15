from __future__ import annotations

import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QPushButton, QSplitter, QTextEdit, QVBoxLayout, QWidget

from app.analysis.price_lead_lag import PriceLeadLagAnalyzer, PriceLeadLagConfig
from app.core.lag_settings import LagSettingsStore
from app.core.models import LagResult
from app.data.data_hub import DataHub
from app.data.test_feed import TestFeed

QUALITY_COLOR = {"WAIT": "#7f8c8d", "BAD": "#e74c3c", "WATCH": "#f1c40f", "GOOD": "#1abc9c", "HOT": "#2ecc71"}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LUC Terminal")
        self.resize(1400, 850)
        self.settings_store = LagSettingsStore(); self.settings = self.settings_store.load(); ms = self.settings["PRICE_LEAD_LAG"]
        self.analyzer = PriceLeadLagAnalyzer(PriceLeadLagConfig(enabled=ms["enabled"], min_leader_move_u=ms.get("min_leader_move_u", 0.1), sort_by=ms["sort_by"], sort_desc=ms["sort_desc"], enabled_lags={int(k): bool(v) for k, v in ms["lags"].items()}))
        self.data_hub = DataHub(logger=self._append_log)
        self.test_feed = TestFeed(on_tick=self.data_hub.on_tick, on_status=self.data_hub._on_status, logger=self._append_log)
        self.selected_lag_ms = ms.get("selected_lag_ms")
        self.start_ts = 0.0
        self._build_ui(); self.ui_timer = QTimer(self); self.ui_timer.timeout.connect(self._refresh); self.ui_timer.start(500)

    def _build_ui(self):
        root = QWidget(); layout = QVBoxLayout(root); top = QHBoxLayout()
        self.data_label = QLabel("DATA: STOPPED"); self.src1 = QLabel("SOURCE BTCUSDT: -"); self.src2 = QLabel("SOURCE BTCU: -"); self.age1 = QLabel("BTCUSDT age ms: -"); self.age2 = QLabel("BTCU age ms: -"); self.tps = QLabel("ticks/sec: 0"); self.uptime = QLabel("uptime: 00:00")
        self.btn_start = QPushButton("START"); self.btn_stop = QPushButton("STOP"); self.btn_clear = QPushButton("CLEAR"); self.btn_test = QPushButton("TEST FEED")
        self.btn_start.clicked.connect(self.start_analyzer); self.btn_stop.clicked.connect(self.stop_analyzer); self.btn_clear.clicked.connect(self.clear_all); self.btn_test.clicked.connect(self.start_test_feed)
        for w in [QLabel("LUC Terminal"), self.data_label, self.src1, self.src2, self.age1, self.age2, self.tps, self.uptime, self.btn_start, self.btn_stop, self.btn_clear, self.btn_test]: top.addWidget(w)
        layout.addLayout(top)
        self.btcusdt_card = self._mk_market_card("LEADER BTCUSDT"); self.btcu_card = self._mk_market_card("FOLLOWER BTCU"); mk=QHBoxLayout(); mk.addWidget(self.btcusdt_card[0]); mk.addWidget(self.btcu_card[0]); layout.addLayout(mk)
        split=QSplitter(Qt.Orientation.Horizontal); left=QFrame(); ll=QVBoxLayout(left); self.module_enabled=QCheckBox("PRICE_LEAD_LAG ON"); self.module_enabled.setChecked(self.analyzer.config.enabled); self.module_enabled.toggled.connect(self._toggle_module); self.module_info=QLabel("WAIT"); ll.addWidget(self.module_enabled); ll.addWidget(self.module_info)
        center=QFrame(); cl=QVBoxLayout(center); self.lag_list=QListWidget(); self.lag_list.itemClicked.connect(self._on_lag_clicked); cl.addWidget(self.lag_list)
        right=QFrame(); rl=QVBoxLayout(right); self.details=QTextEdit(); self.details.setReadOnly(True); rl.addWidget(self.details)
        split.addWidget(left); split.addWidget(center); split.addWidget(right); layout.addWidget(split)
        self.log=QTextEdit(); self.log.setReadOnly(True); self.log.setFixedHeight(180); layout.addWidget(self.log); self.setCentralWidget(root)

    def _mk_market_card(self, title):
        frame=QFrame(); lay=QVBoxLayout(frame); lay.addWidget(QLabel(title)); vals={k: QLabel("-") for k in ["bid","ask","mid","spread","age"]}
        for k in ["bid","ask","mid","spread","age"]: lay.addWidget(QLabel(f"{k}:")); lay.addWidget(vals[k])
        return frame, vals

    def start_analyzer(self): self.test_feed.stop(); self.data_hub.start(); self.start_ts=time.time()
    def stop_analyzer(self): self.test_feed.stop(); self.data_hub.stop()
    def clear_all(self): self.data_hub.clear(); self.lag_list.clear(); self.details.clear()
    def start_test_feed(self): self.data_hub.stop(); self.data_hub.clear(); self.test_feed.start(); self.start_ts=time.time()
    def closeEvent(self, e): self.stop_analyzer(); self._save_settings(); super().closeEvent(e)
    def _toggle_module(self,v): self.analyzer.config.enabled=v; self._save_settings()
    def _save_settings(self):
        s=self.settings["PRICE_LEAD_LAG"]; s["enabled"]=self.analyzer.config.enabled; s["selected_lag_ms"]=self.selected_lag_ms; self.settings_store.save(self.settings)

    def _refresh(self):
        m=self.data_hub.get_metrics(); b1=m.get("BTCUSDT",{}); b2=m.get("BTCU",{})
        data_state = "LIVE" if self.data_hub.is_live() else ("TEST" if b1.get("status")=="TEST" or b2.get("status")=="TEST" else "STOPPED")
        self.data_label.setText(f"DATA: {data_state}"); self.src1.setText(f"SOURCE BTCUSDT: {b1.get('source','-')}"); self.src2.setText(f"SOURCE BTCU: {b2.get('source','-')}")
        self.age1.setText(f"BTCUSDT age ms: {b1.get('age_ms','-')}"); self.age2.setText(f"BTCU age ms: {b2.get('age_ms','-')}"); self.tps.setText(f"ticks/sec: {b1.get('ticks_per_sec',0)+b2.get('ticks_per_sec',0)}")
        if self.start_ts: e=int(time.time()-self.start_ts); self.uptime.setText(f"uptime: {e//60:02d}:{e%60:02d}")
        for symbol, card in [("BTCUSDT", self.btcusdt_card[1]), ("BTCU", self.btcu_card[1])]:
            t=self.data_hub.get_latest(symbol)
            if t: card["bid"].setText(f"{t.bid:.4f}"); card["ask"].setText(f"{t.ask:.4f}"); card["mid"].setText(f"{t.mid:.4f}"); card["spread"].setText(f"{t.spread:.5f}"); card["age"].setText(str(max(0,int(time.time()*1000)-t.local_received_ms)))
        results=self.analyzer.analyze(self.data_hub.get_snapshot(), self.data_hub.get_latest_all(), m); self._render_rows(results)

    def _render_rows(self, results: list[LagResult]):
        self.lag_list.clear(); self.module_info.setText("LIVE" if results else "WAIT")
        for row in results:
            it=QListWidgetItem(f"lag {row.lag_ms}ms | {row.signal_quality} | S:{row.samples} | M:{row.direction_match_pct:.1f}% | E:{row.avg_edge_u:.6f}"); it.setData(Qt.ItemDataRole.UserRole,row.lag_ms); it.setForeground(QUALITY_COLOR.get(row.signal_quality, "#d8deea")); self.lag_list.addItem(it)

    def _on_lag_clicked(self, item): self.selected_lag_ms=int(item.data(Qt.ItemDataRole.UserRole)); self._save_settings()
    def _append_log(self,m): self.log.append(m)
