from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class QuoteTick:
    symbol: str
    timestamp_ms: int
    bid: float
    ask: float
    local_received_ms: int | None = None
    source: str = "DIRECT"
    event_time_ms: int | None = None
    sequence: int | None = None

    def __post_init__(self) -> None:
        if self.local_received_ms is None:
            self.local_received_ms = self.timestamp_ms

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass(slots=True)
class PriceLeadLagDetail:
    leader_timestamp_ms: int
    follower_timestamp_ms: int
    leader_mid_before: float
    leader_mid_after: float
    follower_mid_before: float
    follower_mid_after: float
    leader_move: float
    follower_move: float
    direction_matched: bool
    edge_u: float
    detected_delay_ms: int


@dataclass(slots=True)
class LagResult:
    lag_ms: int
    samples: int
    direction_match_pct: float
    btcusdt_move_avg: float
    btcu_future_move_avg: float
    avg_edge_u: float
    median_edge_u: float
    max_edge_u: float
    min_edge_u: float
    stability_pct: float
    signal_quality: str
    last_signal_time: int | None
    last_leader_move: float
    last_follower_move: float
    confidence_score: float
    reason: str
    details: list[PriceLeadLagDetail] = field(default_factory=list)
