from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget

from app.analysis.lag_manager import LagManager
from app.analysis.price_lead_lag import PriceLeadLagConfig
from app.core.lag_settings import LagSettingsStore
from app.core.models import LagResult
from app.data.data_hub import DataHub
from app.data.test_feed import TestFeed
from app.gui.lag_details_dialog import LagDetailsDialog
from app.report.report_store import ReportStore


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__(); self.setWindowTitle("LUC Terminal"); self.resize(1500, 900)
        self.settings_store = LagSettingsStore(); self.settings = self.settings_store.load(); ms = self.settings["PRICE_LEAD_LAG"]
        cfg = PriceLeadLagConfig(enabled=ms["enabled"], min_leader_move_u=ms.get("min_leader_move_u", 0.1), tolerance_ms=ms.get("tolerance_ms", 80), sort_by=ms.get("sort_by", "confidence_score"), sort_desc=ms.get("sort_desc", True), enabled_lags={int(k): bool(v) for k, v in ms["lags"].items()})
        self.lag_manager = LagManager(logger=self._append_log, price_config=cfg)
        self.lag_manager.selected_lag_ms = ms.get("selected_lag_ms", 500)
        self.data_hub = DataHub(logger=self._append_log); self.test_feed = TestFeed(on_tick=self.data_hub.on_tick, on_status=self.data_hub._on_status, logger=self._append_log)
        self.report_store = ReportStore(logger=self._append_log); self._last_report = 0.0; self.start_ts = 0.0; self._logs_collapsed = ms.get("logs_collapsed", False)
        self._build_ui(); self._apply_dark(); self._apply_logs_state()
        self.ui_timer = QTimer(self); self.ui_timer.timeout.connect(self._refresh); self.ui_timer.start(500)

    def _build_ui(self):
        root = QWidget(); v = QVBoxLayout(root)
        top = QHBoxLayout(); self.data_label=QLabel(); self.src=QLabel(); self.age=QLabel(); self.tps=QLabel(); self.uptime=QLabel()
        self.btn_start=QPushButton("START"); self.btn_stop=QPushButton("STOP"); self.btn_test=QPushButton("TEST FEED"); self.btn_export=QPushButton("EXPORT REPORT")
        self.btn_start.clicked.connect(self.start_analyzer); self.btn_stop.clicked.connect(self.stop_analyzer); self.btn_test.clicked.connect(self.start_test_feed); self.btn_export.clicked.connect(self._export_report)
        for w in [QLabel("LUC"), self.data_label, self.src, self.age, self.tps, self.uptime, self.btn_start, self.btn_stop, self.btn_test, self.btn_export]: top.addWidget(w)
        v.addLayout(top)

        mk=QFrame(); mk.setMaximumHeight(80); mk_l=QHBoxLayout(mk); self.market_line = QLabel("LEADER ... | FOLLOWER ..."); mk_l.addWidget(self.market_line); v.addWidget(mk)
        split=QSplitter(Qt.Orientation.Horizontal)
        left=QFrame(); l=QVBoxLayout(left); self.module_enabled=QCheckBox("PRICE_LEAD_LAG"); self.module_enabled.toggled.connect(self._toggle_module); self.module_list=QListWidget(); l.addWidget(self.module_enabled); l.addWidget(self.module_list)
        center=QFrame(); c=QVBoxLayout(center); self.table=QTableWidget(0,10); self.table.setHorizontalHeaderLabels(["ON","Module","Lag","Quality","Confidence","Samples","Match %","Avg Edge","Stability","Reason"]); self.table.cellClicked.connect(self._on_row_clicked); self.table.cellDoubleClicked.connect(self._open_details); self.table.setSortingEnabled(True); self.table.verticalHeader().setVisible(False); c.addWidget(self.table)
        right=QFrame(); r=QVBoxLayout(right); self.details=QTextEdit(); self.details.setReadOnly(True); r.addWidget(QLabel("Selected Signal Summary")); r.addWidget(self.details)
        split.addWidget(left); split.addWidget(center); split.addWidget(right); split.setSizes([220, 860, 420]); v.addWidget(split)

        self.btn_logs=QPushButton("LOGS"); self.btn_logs.clicked.connect(self._toggle_logs); v.addWidget(self.btn_logs)
        self.log=QTextEdit(); self.log.setReadOnly(True); self.log.setFixedHeight(140); v.addWidget(self.log); self.setCentralWidget(root)

    def _apply_dark(self):
        self.setStyleSheet("QWidget{background:#0b1118;color:#e8eef5;}QFrame,QListWidget,QTextEdit,QTableWidget{background:#111a24;border:1px solid #263445;}QPushButton,QCheckBox{background:#111a24;border:1px solid #263445;padding:4px;}QTableWidget::item:selected{background:#1d3b5f;}")

    def _refresh(self):
        m=self.data_hub.get_metrics(); snap=self.data_hub.get_snapshot(); latest=self.data_hub.get_latest_all(); all_rows=self.lag_manager.analyze_all(snap, latest, m); rows=all_rows.get("PRICE_LEAD_LAG", [])
        b1,b2=m.get("BTCUSDT",{}),m.get("BTCU",{})
        self.data_label.setText(f"DATA {b1.get('status')}/{b2.get('status')}"); self.src.setText(f"sources {b1.get('source')} | {b2.get('source')}"); self.age.setText(f"age {b1.get('age_ms')} / {b2.get('age_ms')}"); self.tps.setText(f"tps {b1.get('ticks_per_sec',0)+b2.get('ticks_per_sec',0)}")
        if self.start_ts: e=int(time.time()-self.start_ts); self.uptime.setText(f"uptime {e//60:02d}:{e%60:02d}")
        self.market_line.setText(f"LEADER BTCUSDT | bid {self._fmt_tick('BTCUSDT','bid')} | ask {self._fmt_tick('BTCUSDT','ask')} | mid {self._fmt_tick('BTCUSDT','mid')} | spread {self._fmt_tick('BTCUSDT','spread')} | age {self._fmt_tick('BTCUSDT','age')}ms    FOLLOWER BTCU | bid {self._fmt_tick('BTCU','bid')} | ask {self._fmt_tick('BTCU','ask')} | mid {self._fmt_tick('BTCU','mid')} | spread {self._fmt_tick('BTCU','spread')} | age {self._fmt_tick('BTCU','age')}ms")
        self._render_module_card(rows); self._rows(rows); self._details()
        if time.time()-self._last_report >= 10 and rows: self.report_store.append_snapshot("PRICE_LEAD_LAG", rows, b1.get("source","-"), b2.get("source","-")); self._last_report=time.time()

    def _fmt_tick(self, symbol, field):
        t=self.data_hub.get_latest(symbol)
        if not t: return "-"
        if field == "age": return str(max(0,int(time.time()*1000)-t.local_received_ms))
        return f"{getattr(t,field):.5f}"

    def _render_module_card(self, rows: list[LagResult]):
        self.module_enabled.setChecked(self.lag_manager.modules['PRICE_LEAD_LAG'].enabled)
        best = max(rows, key=lambda r: (r.confidence_score, r.stability_pct), default=None)
        active = sum(1 for v in self.lag_manager.modules['PRICE_LEAD_LAG'].config.enabled_lags.values() if v)
        total = len(self.lag_manager.modules['PRICE_LEAD_LAG'].config.enabled_lags)
        self.module_list.clear()
        item = QListWidgetItem(f"☑ PRICE_LEAD_LAG\nstatus {best.signal_quality if best else 'WAIT'}\nbest {best.lag_ms if best else '-'}ms\nconf {best.confidence_score if best else 0:.2f}\nactive {active}/{total}")
        self.module_list.addItem(item)

    def _rows(self, rows: list[LagResult]):
        enabled_map=self.lag_manager.modules["PRICE_LEAD_LAG"].config.enabled_lags; by={r.lag_ms:r for r in rows}; all_lags=self.lag_manager.modules["PRICE_LEAD_LAG"].config.lags_ms
        self.table.setRowCount(len(all_lags))
        for i, lag in enumerate(all_lags):
            r = by.get(lag); enabled = enabled_map.get(lag, True)
            vals = ["☑" if enabled else "☐", "PRICE_LEAD_LAG", f"{lag}ms", r.signal_quality if r else "WAIT", f"{r.confidence_score:.2f}" if r else "0.00", str(r.samples if r else 0), f"{r.direction_match_pct:.2f}" if r else "0.00", f"{r.avg_edge_u:+.4f}" if r else "+0.0000", f"{r.stability_pct:.2f}%" if r else "0.00%", r.reason if r else "disabled/no data"]
            for j,v in enumerate(vals):
                it=QTableWidgetItem(v); it.setData(Qt.ItemDataRole.UserRole, lag)
                if not enabled: it.setForeground(Qt.GlobalColor.gray)
                self.table.setItem(i,j,it)
        self.table.sortItems(3, Qt.SortOrder.DescendingOrder)

    def _details(self):
        sd=self.lag_manager.get_selected_details();
        if not sd or not sd.result: self.details.setText("No lag selected."); return
        r=sd.result
        self.details.setText(f"module: {sd.module_id}\nlag: {sd.lag_ms}ms\nquality: {r.signal_quality}\nconfidence: {r.confidence_score:.2f}\nsamples: {r.samples}\nwhy it matters: {r.reason}\nlast update: {r.last_signal_time}")

    def _on_row_clicked(self, row, _col):
        lag=int(self.table.item(row,0).data(Qt.ItemDataRole.UserRole));
        if _col == 0:
            current = self.lag_manager.modules['PRICE_LEAD_LAG'].config.enabled_lags.get(lag, True); self.lag_manager.set_lag_enabled('PRICE_LEAD_LAG', lag, not current)
        self.lag_manager.select_lag("PRICE_LEAD_LAG", lag); self._save_settings()

    def _open_details(self, row, _col):
        lag=int(self.table.item(row,0).data(Qt.ItemDataRole.UserRole)); self.lag_manager.select_lag("PRICE_LEAD_LAG", lag)
        dlg=LagDetailsDialog(self.lag_manager.get_selected_details(), self.report_store, self); self._append_log(f"[GUI] opened details PRICE_LEAD_LAG {lag}ms"); dlg.exec()

    def _toggle_module(self, v): self.lag_manager.set_module_enabled("PRICE_LEAD_LAG", v); self._save_settings()
    def _toggle_logs(self): self._logs_collapsed = not self._logs_collapsed; self._apply_logs_state(); self._save_settings()
    def _apply_logs_state(self): self.log.setVisible(not self._logs_collapsed)
    def _save_settings(self):
        s=self.settings["PRICE_LEAD_LAG"]; m=self.lag_manager.modules["PRICE_LEAD_LAG"].config
        s.update({"enabled": m.enabled, "selected_lag_ms": self.lag_manager.selected_lag_ms, "sort_by": m.sort_by, "sort_desc": m.sort_desc, "lags": {str(k): bool(v) for k,v in m.enabled_lags.items()}, "min_leader_move_u": m.min_leader_move_u, "tolerance_ms": m.tolerance_ms, "logs_collapsed": self._logs_collapsed}); self.settings_store.save(self.settings)
    def _export_report(self):
        rows=self.lag_manager.get_module_results("PRICE_LEAD_LAG")
        p=Path("reports") / "luc_summary.txt"; terminal = f"{self.data_label.text()} | {self.src.text()} | {self.age.text()} | {self.tps.text()}"
        out=self.report_store.export_summary(str(p), terminal, {"PRICE_LEAD_LAG": rows}, self.details.toPlainText()); self._append_log(f"[REPORT] exported {out}")
    def start_analyzer(self): self.test_feed.stop(); self.data_hub.start(); self.start_ts=time.time()
    def stop_analyzer(self): self.test_feed.stop(); self.data_hub.stop()
    def start_test_feed(self): self.data_hub.stop(); self.data_hub.clear(); self.test_feed.start(); self.start_ts=time.time()
    def closeEvent(self, e): self.stop_analyzer(); self._save_settings(); super().closeEvent(e)
    def _append_log(self, m):
        if m.startswith("[ANALYZE]") and self.log.toPlainText().splitlines()[-1:] == [m]:
            return
        self.log.append(m)
