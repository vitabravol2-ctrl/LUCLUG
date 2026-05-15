from __future__ import annotations

from bisect import bisect_left
from typing import Iterable, List

from app.core.models import LagResult, QuoteTick


DEFAULT_LAGS_MS = [50, 100, 200, 300, 500, 800, 1100, 1500, 2000]


class PriceLeadLagAnalyzer:
    def __init__(self, lags_ms: Iterable[int] | None = None) -> None:
        self.lags_ms = list(lags_ms or DEFAULT_LAGS_MS)

    def compute(self, btcusdt_ticks: List[QuoteTick], btcu_ticks: List[QuoteTick]) -> List[LagResult]:
        if len(btcusdt_ticks) < 2 or len(btcu_ticks) < 2:
            return []

        btcu_times = [t.timestamp_ms for t in btcu_ticks]
        results: List[LagResult] = []

        for lag_ms in self.lags_ms:
            samples = 0
            dir_matches = 0
            sum_lead_move = 0.0
            sum_future_move = 0.0

            for i in range(1, len(btcusdt_ticks)):
                lead_prev = btcusdt_ticks[i - 1]
                lead_cur = btcusdt_ticks[i]
                lead_move = lead_cur.mid - lead_prev.mid
                if lead_move == 0:
                    continue

                t0 = lead_cur.timestamp_ms
                t1 = t0 + lag_ms

                idx0 = bisect_left(btcu_times, t0)
                idx1 = bisect_left(btcu_times, t1)
                if idx0 >= len(btcu_ticks) or idx1 >= len(btcu_ticks):
                    continue

                btcu_now = btcu_ticks[idx0]
                btcu_future = btcu_ticks[idx1]
                future_move = btcu_future.mid - btcu_now.mid

                samples += 1
                sum_lead_move += lead_move
                sum_future_move += future_move
                if (lead_move > 0 and future_move > 0) or (lead_move < 0 and future_move < 0):
                    dir_matches += 1

            direction_match_pct = (dir_matches / samples * 100.0) if samples else 0.0
            lead_avg = (sum_lead_move / samples) if samples else 0.0
            future_avg = (sum_future_move / samples) if samples else 0.0
            stability_pct = direction_match_pct * min(samples / 100.0, 1.0)

            signal_quality = "BAD"
            if samples >= 50 and direction_match_pct > 60:
                signal_quality = "HOT"
            elif 56 <= direction_match_pct <= 60:
                signal_quality = "GOOD"
            elif 52 <= direction_match_pct < 56:
                signal_quality = "WATCH"

            if samples < 30 or direction_match_pct < 52:
                signal_quality = "BAD"

            results.append(
                LagResult(
                    lag_ms=lag_ms,
                    samples=samples,
                    btcusdt_move_avg=lead_avg,
                    btcu_future_move_avg=future_avg,
                    direction_match_pct=direction_match_pct,
                    avg_edge_u=future_avg,
                    stability_pct=stability_pct,
                    signal_quality=signal_quality,
                )
            )

        return results
