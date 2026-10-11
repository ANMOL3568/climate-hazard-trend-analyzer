from datetime import date, timedelta
from fastapi.testclient import TestClient
from climate import analyze, clean, percentile
from main import app


def records(values, start=date(2020, 1, 1)):
    return [{'date': (start+timedelta(days=i)).isoformat(), 'temperature': v} for i,v in enumerate(values)]


def test_three_days_strictly_above_threshold():
    result = analyze(records([30,31,32,33,30,31,32]),30,2020,2020)
    assert result['summary']['events'] == 1
    assert result['events'][0]['duration'] == 3


def test_missing_and_invalid_days_break_runs():
    assert clean(float('nan')) is None
    assert clean(100) is None
    assert clean(True) is None
    assert analyze(records([32,33,None,34,35]),30,2020,2020)['events'] == []
    rows = records([32,33,34,35])
    del rows[2]
    assert analyze(rows,30,2020,2020)['events'] == []


def test_year_crossing_event_and_last_day_flush():
    result=analyze(records([32]*5,date(2020,12,30)),30,2020,2021)
    assert result['annual'][0]['events']==1
    assert result['annual'][1]['events']==0
    assert [r['days'] for r in result['annual']]==[2,3]
    result=analyze(records([32]*3,date(2020,12,29)),30,2020,2020)
    assert result['summary']['days']==3


def test_percentile_interpolates():
    assert percentile([0,10,None],.95)==9.5


def test_complete_zero_event_years_and_coverage():
    rows=records([20]*366)
    result=analyze(rows,30,2020,2020)
    assert result['summary']['coverage']==100
    assert result['annual'][0]['days']==0
    assert result['summary']['slope'] is None


def test_api_rejects_invalid_inputs():
    client=TestClient(app)
    assert client.post('/api/analyze',json={'latitude':91,'longitude':0,'start_year':2000,'end_year':2020}).status_code==422
    assert client.post('/api/analyze',json={'latitude':0,'longitude':0,'start_year':2020,'end_year':2000}).status_code==422
    assert client.get('/api/regions?q=x').status_code==422
    assert client.post('/api/analyze',json={'latitude':0,'longitude':0,'start_year':2000,'end_year':2020}).status_code==503


def test_drought_proxy_minimum_gap_and_strict_threshold():
    from climate import analyze
    from datetime import date, timedelta
    records = [{'date': (date(2020,1,1)+timedelta(days=i)).isoformat(), 'precipitation': 0} for i in range(31)]
    records[15]['precipitation'] = 1
    result = analyze(records, 1, 2020, 2020, 'drought')
    assert [e['duration'] for e in result['events']] == [15,15]
    assert result['summary']['days'] == 30
    records[7]['precipitation'] = None
    assert analyze(records, 1, 2020, 2020, 'drought')['summary']['events'] == 1


def test_heavy_rainfall_single_day_and_cross_year():
    from climate import analyze, clean_precipitation
    records = [{'date':'2020-12-31','precipitation':100}, {'date':'2021-01-01','precipitation':120}, {'date':'2021-01-02','precipitation':50}, {'date':'2021-01-03','precipitation':51}]
    result = analyze(records, 50, 2020, 2021, 'heavy_rainfall')
    assert [e['duration'] for e in result['events']] == [2,1]
    assert result['events'][0]['peak'] == 120
    assert [(r['events'],r['days']) for r in result['annual']] == [(1,1),(1,2)]
    assert result['daily'][0]['precipitation'] is None
    assert clean_precipitation(120) == 120
    for value in [-1, True, float('nan'),float('inf'),'5']:
        assert clean_precipitation(value) is None
