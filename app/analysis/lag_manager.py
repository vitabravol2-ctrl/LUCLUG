from __future__ import annotations

import time
from dataclasses import dataclass

from app.analysis.base_lag import LagModuleBase
from app.analysis.price_lead_lag import PriceLeadLagAnalyzer, PriceLeadLagConfig
from app.core.models import LagResult


@dataclass(slots=True)
class SelectedLagDetails:
    module_id: str
    lag_ms: int
    result: LagResult | None
    details: list


class LagManager:
    def __init__(self, logger=None, price_config: PriceLeadLagConfig | None = None) -> None:
        self._log = logger or (lambda _m: None)
        self.modules: dict[str, LagModuleBase] = {}
        self.latest_results: dict[str, list[LagResult]] = {}
        self.selected_module_id: str = "PRICE_LEAD_LAG"
        self.selected_lag_ms: int | None = 500
        self._last_analyze_log_ts = 0.0
        self.register_module(PriceLeadLagAnalyzer(price_config or PriceLeadLagConfig()))

    def register_module(self, module: LagModuleBase) -> None:
        self.modules[module.module_id] = module

    def analyze_all(self, history_snapshot, latest_quotes, data_metrics) -> dict[str, list[LagResult]]:
        out: dict[str, list[LagResult]] = {}
        for module_id, module in self.modules.items():
            rows = module.analyze(history_snapshot, latest_quotes, data_metrics) if module.enabled else []
            out[module_id] = rows
            if module.enabled:
                best = rows[0] if rows else None
                now = time.time()
                if now - self._last_analyze_log_ts >= 2.0:
                    self._log(
                        f"[ANALYZE] {module_id} rows={len(rows)} best_lag={best.lag_ms if best else '-'} quality={best.signal_quality if best else 'WAIT'} confidence={best.confidence_score if best else 0:.2f}"
                    )
                    self._last_analyze_log_ts = now
        self.latest_results = out
        return out

    def get_module_results(self, module_id) -> list[LagResult]:
        return self.latest_results.get(module_id, [])

    def get_selected_details(self) -> SelectedLagDetails | None:
        if not self.selected_module_id or self.selected_lag_ms is None:
            return None
        rows = self.latest_results.get(self.selected_module_id, [])
        row = next((r for r in rows if r.lag_ms == self.selected_lag_ms), None)
        details = row.details if row else []
        return SelectedLagDetails(self.selected_module_id, self.selected_lag_ms, row, details)

    def set_module_enabled(self, module_id, enabled):
        module = self.modules.get(module_id)
        if not module:
            return
        module.enabled = bool(enabled)
        if module_id == "PRICE_LEAD_LAG":
            active = sum(1 for _lag, on in module.config.enabled_lags.items() if on)
            self._log(f"[MODULE] PRICE_LEAD_LAG enabled={str(module.enabled).lower()} active_lags={active}")

    def set_lag_enabled(self, module_id, lag_ms, enabled):
        module = self.modules.get(module_id)
        if not module or not hasattr(module.config, "enabled_lags"):
            return
        module.config.enabled_lags[int(lag_ms)] = bool(enabled)

    def select_lag(self, module_id, lag_ms):
        self.selected_module_id = module_id
        self.selected_lag_ms = int(lag_ms)
        self._log(f"[GUI] selected lag {module_id} {lag_ms}ms")
