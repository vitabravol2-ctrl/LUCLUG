from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class ReportStore:
    def __init__(self, reports_dir: str = "reports", logger=None) -> None:
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.session_start = datetime.now(timezone.utc)
        self.session_file = self.reports_dir / f"luc_session_{self.session_start.strftime('%Y%m%d_%H%M%S')}.jsonl"
        self._log = logger or (lambda _m: None)

    def append_snapshot(self, module_id: str, rows: list, source_leader: str, source_follower: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        with self.session_file.open("a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps({"ts": ts, "module_id": module_id, "lag_ms": row.lag_ms, "quality": row.signal_quality, "samples": row.samples, "match_pct": row.direction_match_pct, "avg_edge_u": row.avg_edge_u, "stability_pct": row.stability_pct, "confidence": row.confidence_score, "reason": row.reason, "source_leader": source_leader, "source_follower": source_follower}, ensure_ascii=False) + "\n")
        self._log(f"[REPORT] saved {self.session_file}")

    def export_summary(self, path: str, module_id: str, rows: list, selected_details_text: str) -> Path:
        out = Path(path)
        end = datetime.now(timezone.utc)
        best_conf = max(rows, key=lambda r: r.confidence_score) if rows else None
        best_stab = max(rows, key=lambda r: r.stability_pct) if rows else None
        lines = [f"session_start={self.session_start.isoformat()}", f"session_end={end.isoformat()}", f"module={module_id}", f"best_confidence={best_conf.lag_ms if best_conf else '-'}", f"best_stability={best_stab.lag_ms if best_stab else '-'}", "rows:"]
        for r in rows:
            lines.append(f"{r.lag_ms}, {r.signal_quality}, {r.samples}, {r.direction_match_pct:.2f}, {r.avg_edge_u:.6f}, {r.stability_pct:.2f}, {r.confidence_score:.2f}, {r.reason}")
        lines += ["", "selected_details:", selected_details_text]
        out.write_text("\n".join(lines), encoding="utf-8")
        return out
