from app.analysis.price_lead_lag import PriceLeadLagAnalyzer, PriceLeadLagConfig
from app.core.lag_settings import LagSettingsStore
from app.core.models import QuoteTick


def _tick(symbol: str, ts: int, mid: float) -> QuoteTick:
    return QuoteTick(symbol=symbol, timestamp_ms=ts, bid=mid - 0.05, ask=mid + 0.05)


def test_settings_save_load(tmp_path):
    path = tmp_path / "lag_settings.json"
    store = LagSettingsStore(str(path))
    settings = store.load()
    settings["PRICE_LEAD_LAG"]["selected_lag_ms"] = 800
    store.save(settings)
    loaded = store.load()
    assert loaded["PRICE_LEAD_LAG"]["selected_lag_ms"] == 800


def test_disabled_lag_excluded_from_analysis():
    leader = [_tick("BTCUSDT", i * 100, 100 + i * 0.2) for i in range(20)]
    follower = [_tick("BTCU", i * 100, 50 + i * 0.2) for i in range(20)]
    cfg = PriceLeadLagConfig(lags_ms=[100, 200], enabled_lags={100: True, 200: False})
    results = PriceLeadLagAnalyzer(cfg).compute(leader, follower)
    assert {r.lag_ms for r in results} == {100}


def test_selected_lag_saved(tmp_path):
    path = tmp_path / "lag_settings.json"
    store = LagSettingsStore(str(path))
    s = store.load()
    s["PRICE_LEAD_LAG"]["selected_lag_ms"] = 500
    store.save(s)
    assert store.load()["PRICE_LEAD_LAG"]["selected_lag_ms"] == 500
