import copy
from datetime import date, datetime, timedelta, timezone
import httpx
import pytest
from fastapi.testclient import TestClient
import main
from locations import normalize_locations

LOCATIONS = [
    {'id': 1273294, 'name': 'Delhi', 'admin1': 'National Capital Territory of Delhi', 'country': 'India', 'latitude': 28.65195, 'longitude': 77.23149},
    {'id': 1275339, 'name': 'Mumbai', 'admin1': 'Maharashtra', 'country': 'India', 'latitude': 19.07283, 'longitude': 72.88261},
    {'id': 10470188, 'name': 'Bihar', 'admin1': 'Uttar Pradesh', 'country': 'India', 'latitude': 27.29201, 'longitude': 79.32543},
    {'id': 5114824, 'name': 'Delhi', 'admin1': 'New York', 'country': 'United States', 'latitude': 42.27814, 'longitude': -74.91599},
]


@pytest.mark.parametrize('record', LOCATIONS)
def test_location_identity(record):
    result = normalize_locations([record])[0]
    for field in record:
        assert result[field] == record[field]
    assert result['label'] == ', '.join([record['name'], record['admin1'], record['country']])


@pytest.mark.parametrize('latitude,longitude', [(91, 0), (0, -181), (float('nan'), 0), (True, 0), ('19', 72)])
def test_invalid_geocoder_coordinates(latitude, longitude):
    record = {**LOCATIONS[0], 'latitude': latitude, 'longitude': longitude}
    assert normalize_locations([record]) == []


def test_ambiguous_results_not_merged():
    results = normalize_locations(LOCATIONS)
    assert len(results) == 4
    assert results[0]['label'] != results[3]['label']
    assert results[2]['admin1'] == 'Uttar Pradesh'


@pytest.mark.parametrize('changes', [{'latitude': -91}, {'latitude': True}, {'longitude': '72'}, {'longitude': 181}, {'start_year': 1939}, {'end_year': date.today().year}, {'start_year': 2021, 'end_year': 2020}, {'start_year': 1940, 'end_year': 2025}])
def test_analysis_validation(changes):
    main.limits.clear()
    client = TestClient(main.app, raise_server_exceptions=False)
    response = client.post('/api/analyze', json={**{'latitude': 19, 'longitude': 72, 'start_year': 2020, 'end_year': 2021}, **changes})
    assert response.status_code == 422
    if changes == {'start_year': 2021, 'end_year': 2020}:
        assert 'Start year' in response.json()['detail'][0]['msg']


class Collection:
    def __init__(self):
        self.documents = {}

    def find_one(self, query):
        record = self.documents.get(query['_id'])
        if record and ('expiresAt' not in query or record['expiresAt'] > query['expiresAt']['$gt']):
            return copy.deepcopy(record)

    def replace_one(self, query, document, upsert=False):
        self.documents[query['_id']] = copy.deepcopy(document)


def test_cache_hits_misses_and_expiration(monkeypatch):
    class Database:
        cache = Collection()
    database = Database()
    monkeypatch.setattr(main, 'db', database)
    calls = []

    async def weather(lat, lon, start, end):
        calls.append((lat, lon, start, end))
        first = date(start, 1, 1)
        return [{'date': (first+timedelta(days=i)).isoformat(), 'temperature': 20} for i in range((date(end+1, 1, 1)-first).days)]

    monkeypatch.setattr(main, 'fetch_weather', weather)
    client = TestClient(main.app)
    body = {'latitude': 19.07283, 'longitude': 72.88261, 'start_year': 2020, 'end_year': 2021}
    main.limits.clear()
    first = client.post('/api/analyze', json=body).json()
    second = client.post('/api/analyze', json=body).json()
    assert first['cached'] is False and second['cached'] is True
    assert first['summary'] == second['summary']
    assert len(calls) == 2
    for change in ({'latitude': 20}, {'longitude': 73}, {'start_year': 2019}, {'end_year': 2020}):
        assert client.post('/api/analyze', json={**body, **change}).json()['cached'] is False
    monkeypatch.setattr(main, 'BASELINE', (1991, 2020))
    assert client.post('/api/analyze', json=body).json()['cached'] is False
    monkeypatch.setattr(main, 'SOURCE', {**main.SOURCE, 'models': 'era5_land'})
    assert client.post('/api/analyze', json=body).json()['cached'] is False
    for row in database.cache.documents.values():
        row['expiresAt'] = datetime.now(timezone.utc)-timedelta(seconds=1)
    assert client.post('/api/analyze', json=body).json()['cached'] is False


def test_all_relevant_source_parameters_in_keys():
    params = {'latitude': 19, 'longitude': 72, 'start_year': 2020, 'end_year': 2021}
    original = main.cache_key(params)
    assert main.cache_key(params, baseline=(1991, 2020)) != original
    assert main.cache_key(params, algorithm='future') != original
    for name in main.SOURCE:
        assert main.cache_key(params, source={**main.SOURCE, name: 'different'}) != original


def test_upstream_failure_and_empty_regions(monkeypatch):
    class Upstream:
        fail = False
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, *args, **kwargs):
            if self.fail: raise httpx.ConnectError('unavailable')
            return httpx.Response(200, json={'results': []}, request=httpx.Request('GET', 'https://example.test'))
    upstream = Upstream()
    monkeypatch.setattr(main.httpx, 'AsyncClient', lambda **kwargs: upstream)
    main.limits.clear()
    client = TestClient(main.app)
    assert client.get('/api/regions?q=unknown').json() == []
    upstream.fail = True
    assert client.get('/api/regions?q=Mumbai').status_code == 502


def test_map_region_identity_and_bounds():
    from locations import normalize_map_regions
    record = {'lat': '25.7', 'lon': '85.4', 'boundingbox': ['24', '28', '83', '89'], 'display_name': 'Bihar, India', 'address': {'state': 'Bihar', 'country': 'India', 'country_code': 'in'}}
    result = normalize_map_regions([record])[0]
    assert result['label'] == 'Bihar, India'
    assert result['country_code'] == 'in'
    assert result['bounds'] == [24, 28, 83, 89]
    for invalid in [{'lat': 'nan'}, {'lon': '181'}, {'boundingbox': ['28','24','83','89']}, {'address': {}}]:
        assert normalize_map_regions([{**record, **invalid}]) == []


def test_map_search_country_filter_cache_and_error(monkeypatch):
    calls = []
    class Upstream:
        fail = False
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url, **kwargs):
            calls.append(kwargs)
            if self.fail: raise httpx.ConnectError('unavailable')
            return httpx.Response(200, json=[], request=httpx.Request('GET', url))
    upstream = Upstream()
    monkeypatch.setattr(main.httpx, 'AsyncClient', lambda **kwargs: upstream)
    async def no_wait(_): pass
    monkeypatch.setattr(main.asyncio, 'sleep', no_wait)
    main.map_search_cache.clear()
    main.limits.clear()
    client = TestClient(main.app)
    assert client.get('/api/map-regions?q=Bihar&kind=state&country=in').json() == []
    assert calls[0]['params']['countrycodes'] == 'in'
    assert calls[0]['params']['featureType'] == 'state'
    assert 'User-Agent' in calls[0]['headers']
    assert client.get('/api/map-regions?q=Bihar&kind=state&country=in').status_code == 200
    assert len(calls) == 1
    assert client.get('/api/map-regions?q=Bihar&kind=state&country=us').status_code == 200
    assert len(calls) == 2
    assert client.get('/api/map-regions?q=x').status_code == 422
    assert client.get('/api/map-regions?q=India&kind=town').status_code == 422
    upstream.fail = True
    assert client.get('/api/map-regions?q=France').status_code == 502


def test_hazard_api_cache_isolation_and_precipitation_source(monkeypatch):
    class Database:
        cache = Collection()
    monkeypatch.setattr(main, 'db', Database())
    calls = []
    async def weather(lat, lon, start, end, variable='temperature_2m_max'):
        calls.append(variable)
        field = 'temperature' if variable == 'temperature_2m_max' else 'precipitation'
        first = date(start,1,1)
        return [{'date':(first+timedelta(days=i)).isoformat(),field:20 if field=='temperature' else (10 if start==1981 else 0)} for i in range((date(end+1,1,1)-first).days)]
    monkeypatch.setattr(main, 'fetch_weather', weather)
    main.limits.clear()
    client = TestClient(main.app)
    body = {'latitude':28.614,'longitude':77.209,'start_year':2020,'end_year':2020}
    for hazard in ['heatwave','heavy_rainfall','drought']:
        response = client.post('/api/analyze',json={**body,'hazard':hazard})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['hazard'] == hazard and result['cached'] is False
        assert client.post('/api/analyze',json={**body,'hazard':hazard}).json()['cached'] is True
        if hazard!='heatwave':
            assert result['source_parameters']['daily']=='precipitation_sum'
            assert result['unit']=='mm'
        if hazard=='drought':
            assert result['summary']['days']==366
            assert result['baseline']==[]
    assert calls.count('precipitation_sum')==3
    assert client.post('/api/analyze',json={**body,'hazard':'invalid'}).status_code==422


def test_hosted_readiness_requires_working_database(monkeypatch):
    main.limits.clear()
    client = TestClient(main.app)
    monkeypatch.setattr(main, 'db', None)
    assert client.get('/api/ready').status_code == 503
    class Database:
        fail = False
        def command(self, name):
            assert name == 'ping'
            if self.fail: raise RuntimeError('connection lost')
            return {'ok': 1}
    database = Database()
    monkeypatch.setattr(main, 'db', database)
    assert client.get('/api/ready').json() == {'status':'ready'}
    database.fail = True
    assert client.get('/api/ready').status_code == 503


@pytest.mark.parametrize('status,message', [(429,'rate limit'),(403,'denied access'),(500,'HTTP 500')])
def test_weather_provider_status_diagnostic(monkeypatch, status, message):
    import asyncio
    from fastapi import HTTPException
    class Database:
        weather = Collection()
    class Upstream:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url, **kwargs):
            return httpx.Response(status, json={'reason':'provider rejection'}, request=httpx.Request('GET',url))
    monkeypatch.setattr(main,'db',Database())
    monkeypatch.setattr(main.httpx,'AsyncClient',lambda **kwargs:Upstream())
    with pytest.raises(HTTPException) as error:
        asyncio.run(main.fetch_weather(28.6,77.2,2020,2021))
    assert error.value.status_code == 502
    assert message in error.value.detail
