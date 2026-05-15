from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
from statistics import median
from typing import Iterable

from app.core.models import LagResult, PriceLeadLagDetail, QuoteTick


DEFAULT_LAGS_MS = [50, 100, 200, 300, 500, 800, 1100, 1500, 2000]
QUALITY_ORDER = {"HOT": 0, "GOOD": 1, "WATCH": 2, "WAIT": 3, "BAD": 4}


@dataclass(slots=True)
class PriceLeadLagConfig:
    lags_ms: list[int] = field(default_factory=lambda: list(DEFAULT_LAGS_MS))
    min_leader_move_u: float = 0.1


class PriceLeadLagAnalyzer:
    def __init__(self, config: PriceLeadLagConfig | None = None) -> None:
        self.config = config or PriceLeadLagConfig()

    def compute(self, btcusdt_ticks: list[QuoteTick], btcu_ticks: list[QuoteTick]) -> list[LagResult]:
        btcu_times = [t.timestamp_ms for t in btcu_ticks]
        results: list[LagResult] = []

        for lag_ms in self.config.lags_ms:
            details: list[PriceLeadLagDetail] = []
            lead_moves: list[float] = []
            follower_moves: list[float] = []
            edges: list[float] = []
            dir_matches = 0

            for i in range(1, len(btcusdt_ticks)):
                lead_prev = btcusdt_ticks[i - 1]
                lead_cur = btcusdt_ticks[i]
                lead_move = lead_cur.mid - lead_prev.mid
                if lead_move == 0.0 or abs(lead_move) < self.config.min_leader_move_u:
                    continue

                t0 = lead_cur.timestamp_ms
                t1 = t0 + lag_ms
                idx0 = bisect_left(btcu_times, t0)
                idx1 = bisect_left(btcu_times, t1)
                if idx0 >= len(btcu_ticks) or idx1 >= len(btcu_ticks):
                    continue

                btcu_now = btcu_ticks[idx0]
                btcu_future = btcu_ticks[idx1]
                follower_move = btcu_future.mid - btcu_now.mid
                matched = (lead_move > 0 and follower_move > 0) or (lead_move < 0 and follower_move < 0)

                if matched:
                    dir_matches += 1

                edge_u = follower_move if matched else -abs(follower_move)
                lead_moves.append(lead_move)
                follower_moves.append(follower_move)
                edges.append(edge_u)
                details.append(
                    PriceLeadLagDetail(
                        leader_timestamp_ms=lead_cur.timestamp_ms,
                        follower_timestamp_ms=btcu_future.timestamp_ms,
                        leader_mid_before=lead_prev.mid,
                        leader_mid_after=lead_cur.mid,
                        follower_mid_before=btcu_now.mid,
                        follower_mid_after=btcu_future.mid,
                        leader_move=lead_move,
                        follower_move=follower_move,
                        direction_matched=matched,
                        edge_u=edge_u,
                        detected_delay_ms=max(0, btcu_future.timestamp_ms - lead_cur.timestamp_ms),
                    )
                )

            samples = len(details)
            direction_match_pct = (dir_matches / samples * 100.0) if samples else 0.0
            btcusdt_move_avg = (sum(lead_moves) / samples) if samples else 0.0
            btcu_future_move_avg = (sum(follower_moves) / samples) if samples else 0.0
            avg_edge_u = (sum(edges) / samples) if samples else 0.0
            median_edge_u = median(edges) if samples else 0.0
            max_edge_u = max(edges) if samples else 0.0
            min_edge_u = min(edges) if samples else 0.0
            stability_pct = direction_match_pct * min(samples / 100.0, 1.0)
            confidence_score = round(
                direction_match_pct * 0.45 + stability_pct * 0.35 + min(samples / 200.0, 1.0) * 100.0 * 0.20,
                2,
            )

            signal_quality = self._classify(samples, direction_match_pct, stability_pct, avg_edge_u)
            reason = self._reason(samples, direction_match_pct, stability_pct, avg_edge_u, confidence_score)

            last = details[-1] if details else None
            results.append(
                LagResult(
                    lag_ms=lag_ms,
                    samples=samples,
                    direction_match_pct=direction_match_pct,
                    btcusdt_move_avg=btcusdt_move_avg,
                    btcu_future_move_avg=btcu_future_move_avg,
                    avg_edge_u=avg_edge_u,
                    median_edge_u=median_edge_u,
                    max_edge_u=max_edge_u,
                    min_edge_u=min_edge_u,
                    stability_pct=stability_pct,
                    signal_quality=signal_quality,
                    last_signal_time=last.leader_timestamp_ms if last else None,
                    last_leader_move=last.leader_move if last else 0.0,
                    last_follower_move=last.follower_move if last else 0.0,
                    confidence_score=confidence_score,
                    reason=reason,
                    details=details[-20:],
                )
            )

        return self.sort_results(results)

    @staticmethod
    def sort_results(results: list[LagResult]) -> list[LagResult]:
        return sorted(
            results,
            key=lambda r: (QUALITY_ORDER.get(r.signal_quality, 99), -r.stability_pct, -r.samples),
        )

    @staticmethod
    def _classify(samples: int, direction_match_pct: float, stability_pct: float, avg_edge_u: float) -> str:
        if samples == 0:
            return "WAIT"
        if samples < 30 or direction_match_pct < 52:
            return "BAD"
        if samples >= 80 and direction_match_pct >= 60 and stability_pct >= 55 and avg_edge_u > 0:
            return "HOT"
        if samples >= 50 and direction_match_pct >= 56 and stability_pct >= 40 and avg_edge_u > 0:
            return "GOOD"
        if samples >= 30 and direction_match_pct >= 52 and stability_pct >= 20:
            return "WATCH"
        return "BAD"

    @staticmethod
    def _reason(samples: int, direction_match_pct: float, stability_pct: float, avg_edge_u: float, confidence: float) -> str:
        if samples == 0:
            return "not enough samples"
        if samples < 30:
            return "not enough samples"
        if direction_match_pct < 52:
            return "weak direction match"
        if confidence >= 70:
            return "high confidence lag"
        if avg_edge_u > 0 and samples < 50:
            return "positive edge but low samples"
        if stability_pct >= 40 and avg_edge_u > 0:
            return "stable positive lag"
        return "unstable/noisy"
