from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QPushButton, QSplitter, QTextEdit, QVBoxLayout, QWidget

from app.analysis.lag_manager import LagManager
from app.analysis.price_lead_lag import PriceLeadLagConfig
from app.core.lag_settings import LagSettingsStore
from app.core.models import LagResult
from app.data.data_hub import DataHub
from app.data.test_feed import TestFeed
from app.report.report_store import ReportStore

QUALITY_COLOR = {"WAIT": "#9aa7b3", "BAD": "#e74c3c", "WATCH": "#f1c40f", "GOOD": "#1abc9c", "HOT": "#2ecc71"}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__(); self.setWindowTitle("LUC Terminal"); self.resize(1500, 900)
        self.settings_store = LagSettingsStore(); self.settings = self.settings_store.load(); ms = self.settings["PRICE_LEAD_LAG"]
        cfg = PriceLeadLagConfig(enabled=ms["enabled"], min_leader_move_u=ms.get("min_leader_move_u", 0.1), tolerance_ms=ms.get("tolerance_ms", 80), sort_by=ms["sort_by"], sort_desc=ms["sort_desc"], enabled_lags={int(k): bool(v) for k, v in ms["lags"].items()})
        self.lag_manager = LagManager(logger=self._append_log, price_config=cfg)
        self.lag_manager.selected_lag_ms = ms.get("selected_lag_ms", 500)
        self.data_hub = DataHub(logger=self._append_log); self.test_feed = TestFeed(on_tick=self.data_hub.on_tick, on_status=self.data_hub._on_status, logger=self._append_log)
        self.report_store = ReportStore(logger=self._append_log); self._last_report = 0.0; self.start_ts = 0.0
        self._build_ui(); self._apply_dark()
        self.ui_timer = QTimer(self); self.ui_timer.timeout.connect(self._refresh); self.ui_timer.start(500)

    def _build_ui(self):
        root = QWidget(); v = QVBoxLayout(root)
        top = QHBoxLayout(); self.data_label=QLabel(); self.src=QLabel(); self.age=QLabel(); self.tps=QLabel(); self.uptime=QLabel();
        self.btn_start=QPushButton("START"); self.btn_stop=QPushButton("STOP"); self.btn_test=QPushButton("TEST FEED"); self.btn_export=QPushButton("EXPORT REPORT")
        self.btn_start.clicked.connect(self.start_analyzer); self.btn_stop.clicked.connect(self.stop_analyzer); self.btn_test.clicked.connect(self.start_test_feed); self.btn_export.clicked.connect(self._export_report)
        for w in [QLabel("LUC"), self.data_label, self.src, self.age, self.tps, self.uptime, self.btn_start, self.btn_stop, self.btn_test, self.btn_export]: top.addWidget(w)
        v.addLayout(top)
        mk=QHBoxLayout(); self.btcusdt=self._mk_card("LEADER BTCUSDT"); self.btcu=self._mk_card("FOLLOWER BTCU"); mk.addWidget(self.btcusdt[0]); mk.addWidget(self.btcu[0]); v.addLayout(mk)
        split=QSplitter(Qt.Orientation.Horizontal); left=QFrame(); l=QVBoxLayout(left); self.module_enabled=QCheckBox("PRICE_LEAD_LAG ON"); self.module_enabled.toggled.connect(self._toggle_module); self.module_info=QLabel(); l.addWidget(self.module_enabled); l.addWidget(self.module_info)
        center=QFrame(); c=QVBoxLayout(center); self.lag_list=QListWidget(); self.lag_list.itemClicked.connect(self._on_lag_clicked); c.addWidget(self.lag_list)
        right=QFrame(); r=QVBoxLayout(right); self.details=QTextEdit(); self.details.setReadOnly(True); r.addWidget(self.details)
        split.addWidget(left); split.addWidget(center); split.addWidget(right); split.setSizes([240, 780, 450]); v.addWidget(split)
        self.log=QTextEdit(); self.log.setReadOnly(True); self.log.setFixedHeight(180); v.addWidget(self.log); self.setCentralWidget(root)

    def _mk_card(self, title):
        f=QFrame(); h=QHBoxLayout(f); h.addWidget(QLabel(title)); vals={k: QLabel("-") for k in ["bid","ask","mid","spread","age"]}
        for k in ["bid","ask","mid","spread","age"]: h.addWidget(QLabel(k.upper())); h.addWidget(vals[k])
        return f, vals

    def _apply_dark(self):
        self.setStyleSheet("QWidget{background:#0b1118;color:#e8eef5;}QFrame,QListWidget,QTextEdit{background:#111a24;border:1px solid #263445;}QPushButton,QCheckBox{background:#111a24;border:1px solid #263445;padding:4px;}QListWidget::item:selected{background:#1d3b5f;}")

    def _refresh(self):
        m=self.data_hub.get_metrics(); snap=self.data_hub.get_snapshot(); latest=self.data_hub.get_latest_all(); all_rows=self.lag_manager.analyze_all(snap, latest, m); rows=all_rows.get("PRICE_LEAD_LAG", [])
        b1,b2=m.get("BTCUSDT",{}),m.get("BTCU",{}); self.data_label.setText(f"DATA {b1.get('status')}/{b2.get('status')}"); self.src.setText(f"sources {b1.get('source')} | {b2.get('source')}"); self.age.setText(f"age {b1.get('age_ms')} / {b2.get('age_ms')}"); self.tps.setText(f"tps {b1.get('ticks_per_sec',0)+b2.get('ticks_per_sec',0)}")
        if self.start_ts: e=int(time.time()-self.start_ts); self.uptime.setText(f"uptime {e//60:02d}:{e%60:02d}")
        self.module_enabled.setChecked(self.lag_manager.modules['PRICE_LEAD_LAG'].enabled)
        best=rows[0] if rows else None; self.module_info.setText(f"status={best.signal_quality if best else 'WAIT'} best={best.lag_ms if best else '-'} conf={best.confidence_score if best else 0:.2f} samples={sum(r.samples for r in rows)} active={sum(1 for r in rows)}")
        for s, card in [("BTCUSDT", self.btcusdt[1]), ("BTCU", self.btcu[1])]:
            t=self.data_hub.get_latest(s)
            if t: card["bid"].setText(f"{t.bid:.4f}"); card["ask"].setText(f"{t.ask:.4f}"); card["mid"].setText(f"{t.mid:.4f}"); card["spread"].setText(f"{t.spread:.5f}"); card["age"].setText(str(max(0,int(time.time()*1000)-t.local_received_ms)))
        self._rows(rows); self._details()
        if time.time()-self._last_report >= 10 and rows:
            self.report_store.append_snapshot("PRICE_LEAD_LAG", rows, b1.get("source","-"), b2.get("source","-")); self._last_report=time.time()

    def _rows(self, rows: list[LagResult]):
        self.lag_list.clear(); enabled_map=self.lag_manager.modules["PRICE_LEAD_LAG"].config.enabled_lags
        all_lags=self.lag_manager.modules["PRICE_LEAD_LAG"].config.lags_ms; by={r.lag_ms:r for r in rows}
        for lag in all_lags:
            row=by.get(lag); en=enabled_map.get(lag,True)
            txt=f"[{'ON' if en else 'OFF'}] {lag} ms  Q:{row.signal_quality if row else 'WAIT'}  S:{row.samples if row else 0}  M:{row.direction_match_pct if row else 0:.1f}%  E:{row.avg_edge_u if row else 0:.5f}  St:{row.stability_pct if row else 0:.1f}%  C:{row.confidence_score if row else 0:.1f}  {row.reason if row else 'disabled/no data'}"
            it=QListWidgetItem(txt); it.setData(Qt.ItemDataRole.UserRole, lag); it.setForeground("#5f6c7a" if not en else QUALITY_COLOR.get(row.signal_quality if row else 'WAIT',"#e8eef5")); self.lag_list.addItem(it)
            if self.lag_manager.selected_lag_ms == lag: self.lag_list.setCurrentItem(it)

    def _details(self):
        sd=self.lag_manager.get_selected_details()
        if not sd or not sd.result:
            self.details.setText("Waiting for enough samples…")
            return
        r=sd.result
        lines=[f"{sd.module_id} / {sd.lag_ms} ms",f"Status: {r.signal_quality}",f"Samples: {r.samples}",f"Match: {r.direction_match_pct:.2f}%",f"Avg Edge: {r.avg_edge_u:.6f}",f"Median Edge: {r.median_edge_u:.6f}",f"Stability: {r.stability_pct:.2f}%",f"Confidence: {r.confidence_score:.2f}",f"Reason: {r.reason}","",f"Interpretation: BTCUSDT moved first. BTCU response checked after {sd.lag_ms} ms.","", "Last 20 samples:"]
        for d in r.details[-20:]: lines.append(f"{d.leader_timestamp_ms} | {d.follower_timestamp_ms} | {d.detected_delay_ms} | {d.leader_move:.4f} | {d.follower_move:.4f} | {d.direction_matched} | {d.edge_u:.5f}")
        self.details.setText("\n".join(lines))

    def _on_lag_clicked(self, item): self.lag_manager.select_lag("PRICE_LEAD_LAG", int(item.data(Qt.ItemDataRole.UserRole))); self._save_settings()
    def _toggle_module(self, v): self.lag_manager.set_module_enabled("PRICE_LEAD_LAG", v); self._save_settings()
    def _save_settings(self):
        s=self.settings["PRICE_LEAD_LAG"]; m=self.lag_manager.modules["PRICE_LEAD_LAG"].config
        s.update({"enabled": m.enabled, "selected_lag_ms": self.lag_manager.selected_lag_ms, "sort_by": m.sort_by, "sort_desc": m.sort_desc, "lags": {str(k): bool(v) for k,v in m.enabled_lags.items()}, "min_leader_move_u": m.min_leader_move_u, "tolerance_ms": m.tolerance_ms}); self.settings_store.save(self.settings)
    def _export_report(self):
        rows=self.lag_manager.get_module_results("PRICE_LEAD_LAG"); p=Path("reports") / "luc_summary.txt"; out=self.report_store.export_summary(str(p), "PRICE_LEAD_LAG", rows, self.details.toPlainText()); self._append_log(f"[REPORT] exported {out}")
    def start_analyzer(self): self.test_feed.stop(); self.data_hub.start(); self.start_ts=time.time()
    def stop_analyzer(self): self.test_feed.stop(); self.data_hub.stop()
    def start_test_feed(self): self.data_hub.stop(); self.data_hub.clear(); self.test_feed.start(); self.start_ts=time.time()
    def closeEvent(self, e): self.stop_analyzer(); self._save_settings(); super().closeEvent(e)
    def _append_log(self, m): self.log.append(m)
