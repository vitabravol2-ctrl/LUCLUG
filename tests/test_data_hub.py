from app.core.models import QuoteTick
from app.data.data_hub import DataHub
from app.data.test_feed import TestFeed


def _tick(symbol="BTCUSDT", ts=1000):
    return QuoteTick(symbol=symbol, timestamp_ms=ts, local_received_ms=ts, bid=1.0, ask=2.0, source="TEST")


def test_on_tick_saves_latest_and_history():
    hub = DataHub()
    tick = _tick()
    hub.on_tick(tick)
    assert hub.get_latest("BTCUSDT") is tick
    assert hub.get_snapshot()["BTCUSDT"][-1] is tick


def test_snapshot_is_copy():
    hub = DataHub()
    hub.on_tick(_tick())
    snap = hub.get_snapshot()
    snap["BTCUSDT"].append(_tick(ts=1001))
    assert len(hub.get_snapshot()["BTCUSDT"]) == 1


def test_clear_empties_data():
    hub = DataHub()
    hub.on_tick(_tick())
    hub.clear()
    assert hub.get_latest("BTCUSDT") is None
    assert hub.get_snapshot() == {}


def test_repeated_start_no_duplicates():
    hub = DataHub()
    hub.start(); first = len(hub._clients)
    hub.start(); second = len(hub._clients)
    hub.stop()
    assert first == second == 2


def test_test_feed_uses_datahub_on_tick():
    class H(DataHub):
        def __init__(self):
            super().__init__(); self.called = 0
        def on_tick(self, tick, source=None):
            self.called += 1
            super().on_tick(tick, source)

    hub = H()
    feed = TestFeed(on_tick=hub.on_tick, on_status=hub._on_status)
    feed.start()
    import time; time.sleep(0.12)
    feed.stop()
    assert hub.called > 0
