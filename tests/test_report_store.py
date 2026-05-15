import json

from app.analysis.lag_manager import LagManager
from app.analysis.price_lead_lag import PriceLeadLagAnalyzer, PriceLeadLagConfig
from app.core.models import QuoteTick
from app.report.report_store import ReportStore


def _tick(symbol, ts, mid):
    return QuoteTick(symbol=symbol, timestamp_ms=ts, local_received_ms=ts, bid=mid - 0.05, ask=mid + 0.05)


def test_report_jsonl_created(tmp_path):
    leader=[_tick('BTCUSDT',0,100.0),_tick('BTCUSDT',100,100.2),_tick('BTCUSDT',200,100.4)]
    follower=[_tick('BTCU',0,50.0),_tick('BTCU',180,50.2),_tick('BTCU',280,50.4)]
    rows=PriceLeadLagAnalyzer(PriceLeadLagConfig(lags_ms=[100], tolerance_ms=90)).compute(leader,follower)
    rs=ReportStore(str(tmp_path))
    rs.append_snapshot('PRICE_LEAD_LAG', rows, 'TEST', 'TEST')
    assert rs.session_file.exists()
    line=rs.session_file.read_text(encoding='utf-8').strip().splitlines()[0]
    payload=json.loads(line)
    assert payload['module_id']=='PRICE_LEAD_LAG'


def test_export_selected_lag_creates_file(tmp_path):
    rs=ReportStore(str(tmp_path))
    m=LagManager(price_config=PriceLeadLagConfig(lags_ms=[500]))
    leader=[_tick('BTCUSDT',0,100.0)] + [_tick('BTCUSDT',i*100,100+i*0.2) for i in range(1,120)]
    follower=[_tick('BTCU',i*100+500,50+i*0.2) for i in range(1,120)]
    m.analyze_all({'BTCUSDT':leader,'BTCU':follower},{},{})
    m.select_lag('PRICE_LEAD_LAG',500)
    out=rs.export_selected_lag(str(tmp_path / 'selected.txt'), m.get_selected_details())
    assert out.exists()
