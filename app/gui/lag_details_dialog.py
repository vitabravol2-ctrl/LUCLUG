from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)

from app.analysis.lag_manager import SelectedLagDetails
from app.report.report_store import ReportStore


class LagDetailsDialog(QDialog):
    def __init__(self, details: SelectedLagDetails, report_store: ReportStore, parent=None) -> None:
        super().__init__(parent)
        self.details = details
        self.report_store = report_store
        self.setWindowTitle(f"Lag Details — {details.module_id} {details.lag_ms}ms")
        self.resize(980, 620)

        layout = QVBoxLayout(self)
        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        layout.addWidget(QLabel("Lag Summary"))
        layout.addWidget(self.summary)

        self.samples_table = QTableWidget(0, 7)
        self.samples_table.setHorizontalHeaderLabels(
            ["leader_time", "follower_time", "delay_ms", "leader_move", "follower_move", "matched", "edge_u"]
        )
        self.samples_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.samples_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.samples_table.verticalHeader().setVisible(False)
        layout.addWidget(QLabel("Last 20 samples"))
        layout.addWidget(self.samples_table)

        btns = QHBoxLayout()
        copy_btn = QPushButton("COPY SUMMARY")
        export_btn = QPushButton("EXPORT THIS LAG")
        close_btn = QPushButton("CLOSE")
        btns.addWidget(copy_btn)
        btns.addWidget(export_btn)
        btns.addStretch(1)
        btns.addWidget(close_btn)
        layout.addLayout(btns)

        copy_btn.clicked.connect(self._copy_summary)
        export_btn.clicked.connect(self._export_lag)
        close_btn.clicked.connect(self.accept)

        self._render()

    def _render(self) -> None:
        r = self.details.result
        if not r:
            self.summary.setText("No details available.")
            return
        summary = [
            f"Module: {self.details.module_id}",
            f"Lag: {self.details.lag_ms} ms",
            f"Quality: {r.signal_quality}",
            f"Confidence: {r.confidence_score:.2f}",
            f"Samples: {r.samples}",
            f"Match: {r.direction_match_pct:.2f}%",
            f"Avg edge: {r.avg_edge_u:.6f}",
            f"Median edge: {r.median_edge_u:.6f}",
            f"Stability: {r.stability_pct:.2f}%",
            f"Reason: {r.reason}",
            "",
            f"Interpretation: Leader move precedes follower by ~{self.details.lag_ms}ms.",
        ]
        self.summary.setText("\n".join(summary))

        rows = r.details[-20:]
        self.samples_table.setRowCount(len(rows))
        for i, d in enumerate(rows):
            vals = [
                str(d.leader_timestamp_ms),
                str(d.follower_timestamp_ms),
                str(d.detected_delay_ms),
                f"{d.leader_move:.6f}",
                f"{d.follower_move:.6f}",
                "yes" if d.direction_matched else "no",
                f"{d.edge_u:.6f}",
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.samples_table.setItem(i, j, item)

    def _copy_summary(self) -> None:
        self.summary.selectAll()
        self.summary.copy()

    def _export_lag(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export This Lag", str(Path("reports") / "selected_lag.txt"), "Text (*.txt)")
        if not path:
            return
        self.report_store.export_selected_lag(path, self.details)
