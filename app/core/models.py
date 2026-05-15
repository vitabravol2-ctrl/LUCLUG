from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class QuoteTick:
    symbol: str
    timestamp_ms: int
    bid: float
    ask: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass(slots=True)
class LagResult:
    lag_ms: int
    samples: int
    btcusdt_move_avg: float
    btcu_future_move_avg: float
    direction_match_pct: float
    avg_edge_u: float
    stability_pct: float
    signal_quality: str
