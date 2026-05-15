from app.analysis.lag_manager import LagManager
from app.analysis.price_lead_lag import PriceLeadLagConfig
from app.core.models import QuoteTick


def _tick(symbol, ts, mid):
    return QuoteTick(symbol=symbol, timestamp_ms=ts, local_received_ms=ts, bid=mid - 0.05, ask=mid + 0.05)


def _snap():
    leader=[_tick('BTCUSDT',0,100.0)]
    follower=[]
    for i in range(1,120):
        t=i*100
        leader.append(_tick('BTCUSDT',t,100+i*0.2))
        follower.append(_tick('BTCU',t+500,50+i*0.2))
    return {'BTCUSDT':leader,'BTCU':follower}


def test_registers_price_module():
    m=LagManager(price_config=PriceLeadLagConfig())
    assert 'PRICE_LEAD_LAG' in m.modules


def test_analyze_all_and_selected_details():
    m=LagManager(price_config=PriceLeadLagConfig(lags_ms=[500]))
    rows=m.analyze_all(_snap(),{},{} )['PRICE_LEAD_LAG']
    assert rows
    m.select_lag('PRICE_LEAD_LAG',500)
    assert m.get_selected_details().result is not None


def test_disabled_lag_not_counted():
    cfg=PriceLeadLagConfig(lags_ms=[100,500], enabled_lags={100:False,500:True})
    m=LagManager(price_config=cfg)
    rows=m.analyze_all(_snap(),{},{} )['PRICE_LEAD_LAG']
    assert {r.lag_ms for r in rows} == {500}
