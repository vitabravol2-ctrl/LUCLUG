from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_SETTINGS = {
    "PRICE_LEAD_LAG": {
        "enabled": True,
        "selected_lag_ms": 500,
        "sort_by": "stability_pct",
        "sort_desc": True,
        "min_leader_move_u": 0.1,
        "lags": {str(k): True for k in [50, 100, 200, 300, 500, 800, 1100, 1500, 2000]},
    }
}


class LagSettingsStore:
    def __init__(self, path: str = "config/lag_settings.json") -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return json.loads(json.dumps(DEFAULT_SETTINGS))
        data = json.loads(self.path.read_text(encoding="utf-8"))
        merged = json.loads(json.dumps(DEFAULT_SETTINGS))
        merged.update(data)
        return merged

    def save(self, settings: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
