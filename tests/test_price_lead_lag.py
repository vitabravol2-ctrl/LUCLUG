from app.analysis.price_lead_lag import PriceLeadLagAnalyzer, PriceLeadLagConfig
from app.core.models import QuoteTick


def _tick(symbol: str, ts: int, mid: float) -> QuoteTick:
    return QuoteTick(symbol=symbol, timestamp_ms=ts, bid=mid - 0.05, ask=mid + 0.05)


def _build_stable_series(samples: int = 100, lag_ms: int = 100):
    leader = [_tick("BTCUSDT", 0, 100.0)]
    for i in range(1, samples + 1):
        leader.append(_tick("BTCUSDT", i * 100, 100.0 + i * 0.2))

    follower = []
    for i in range(samples + 3):
        ts = i * 100
        follower.append(_tick("BTCU", ts, 50.0 + max(0, i - 1) * 0.2))
    return leader, follower


def test_hot_lag_detected_for_stable_direction_match():
    leader, follower = _build_stable_series(samples=100, lag_ms=100)
    analyzer = PriceLeadLagAnalyzer(PriceLeadLagConfig(lags_ms=[100], min_leader_move_u=0.1))
    results = analyzer.compute(leader, follower)
    assert results[0].signal_quality == "HOT"


def test_bad_when_samples_below_30():
    leader, follower = _build_stable_series(samples=20)
    analyzer = PriceLeadLagAnalyzer(PriceLeadLagConfig(lags_ms=[100], min_leader_move_u=0.1))
    results = analyzer.compute(leader, follower)
    assert results[0].samples < 30
    assert results[0].signal_quality == "BAD"


def test_default_sorting_returns_best_first():
    analyzer = PriceLeadLagAnalyzer(PriceLeadLagConfig(lags_ms=[50, 100], min_leader_move_u=0.1))
    leader, follower = _build_stable_series(samples=100)
    results = analyzer.compute(leader, follower)
    assert results[0].signal_quality in {"HOT", "GOOD"}
    assert results[0].stability_pct >= results[1].stability_pct


def test_detail_samples_created():
    leader, follower = _build_stable_series(samples=35)
    analyzer = PriceLeadLagAnalyzer(PriceLeadLagConfig(lags_ms=[100]))
    results = analyzer.compute(leader, follower)
    assert len(results[0].details) > 0
    assert len(results[0].details) <= 20


def test_zero_leader_moves_ignored():
    leader = [
        _tick("BTCUSDT", 0, 100.0),
        _tick("BTCUSDT", 100, 100.0),
        _tick("BTCUSDT", 200, 100.3),
    ]
    follower = [
        _tick("BTCU", 100, 50.0),
        _tick("BTCU", 200, 50.0),
        _tick("BTCU", 300, 50.2),
    ]
    analyzer = PriceLeadLagAnalyzer(PriceLeadLagConfig(lags_ms=[100], min_leader_move_u=0.1))
    results = analyzer.compute(leader, follower)
    assert results[0].samples == 1
