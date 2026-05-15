from __future__ import annotations

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
        self._last_analyze_state: dict[str, tuple] = {}
        self.register_module(PriceLeadLagAnalyzer(price_config or PriceLeadLagConfig()))

    def register_module(self, module: LagModuleBase) -> None:
        self.modules[module.module_id] = module

    def analyze_all(self, history_snapshot, latest_quotes, data_metrics) -> dict[str, list[LagResult]]:
        out: dict[str, list[LagResult]] = {}
        for module_id, module in self.modules.items():
            rows = module.analyze(history_snapshot, latest_quotes, data_metrics) if module.enabled else []
            out[module_id] = rows
            if module.enabled:
                self._log_analyze_if_changed(module_id, rows)
        self.latest_results = out
        return out

    def _log_analyze_if_changed(self, module_id: str, rows: list[LagResult]) -> None:
        best = rows[0] if rows else None
        state = (
            best.lag_ms if best else None,
            best.signal_quality if best else "WAIT",
            round(best.confidence_score, 2) if best else 0.0,
            best.samples if best else 0,
        )
        prev = self._last_analyze_state.get(module_id)
        should_log = prev is None
        if prev is not None:
            best_changed = prev[0] != state[0]
            quality_changed = prev[1] != state[1]
            confidence_changed = abs(prev[2] - state[2]) > 2.0
            samples_changed = (state[3] - prev[3]) >= 500
            should_log = best_changed or quality_changed or confidence_changed or samples_changed
        if should_log:
            self._log(
                f"[ANALYZE] {module_id} best={best.lag_ms if best else '-'}ms {best.signal_quality if best else 'WAIT'} "
                f"conf={best.confidence_score if best else 0:.2f} samples={best.samples if best else 0} edge={best.avg_edge_u if best else 0:+.2f}U"
            )
            self._last_analyze_state[module_id] = state

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
