import asyncio
import hashlib
import json
import logging
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from pymongo import MongoClient
from climate import analyze, clean, clean_precipitation, percentile
from locations import normalize_locations, normalize_map_regions
from typing import Literal

logger = logging.getLogger('uvicorn.error')

load_dotenv()
BASELINE = (1981, 2010)
SOURCE = {'provider': 'open-meteo', 'models': 'era5', 'daily': 'temperature_2m_max', 'timezone': 'auto', 'temperature_unit': 'celsius'}
ALGORITHM_VERSION = 'multi-hazard-v3'


def cache_key(params, *, baseline=None, source=None, algorithm=None):
    identity = {'params': params, 'baseline': BASELINE if baseline is None else baseline, 'source': SOURCE if source is None else source, 'algorithm': ALGORITHM_VERSION if algorithm is None else algorithm}
    return hashlib.sha256(json.dumps(identity, sort_keys=True, allow_nan=False).encode()).hexdigest()


def weather_key(latitude, longitude, start, end):
    return cache_key({'latitude': latitude, 'longitude': longitude, 'start_year': start, 'end_year': end}, baseline=(), algorithm='weather-v2')
db = None
client = None
limits = defaultdict(deque)
slots = asyncio.Semaphore(3)
map_search_lock = asyncio.Lock()
map_search_cache = {}
map_search_last = 0.0


@asynccontextmanager
async def lifespan(app):
    global db, client
    client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://localhost:27017'), serverSelectionTimeoutMS=3000)
    try:
        await asyncio.to_thread(client.admin.command, 'ping')
        db = client.climate_hazard
        await asyncio.to_thread(db.cache.create_index, 'expiresAt', expireAfterSeconds=0)
    except Exception:
        db = None
    yield
    client.close()
    db = None


app = FastAPI(title='Climate Hazard API', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(','), allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])


@app.middleware('http')
async def rate_limit(request: Request, call_next):
    from starlette.responses import JSONResponse
    now = time.monotonic()
    key = request.client.host if request.client else 'unknown'
    if len(limits) > 10000:
        for old in list(limits):
            if not limits[old] or now - limits[old][-1] > 60:
                del limits[old]
    queue = limits[key]
    while queue and now - queue[0] > 60:
        queue.popleft()
    if len(queue) >= 30:
        return JSONResponse({'detail': 'Too many requests. Try again in one minute.'}, status_code=429, headers={'Retry-After': '60'})
    queue.append(now)
    return await call_next(request)


class AnalysisRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90, strict=True)
    longitude: float = Field(ge=-180, le=180, strict=True)
    start_year: int = Field(ge=1940, strict=True)
    end_year: int = Field(strict=True)
    hazard: Literal['heatwave', 'drought', 'heavy_rainfall'] = 'heatwave'

    @model_validator(mode='after')
    def years(self):
        if self.start_year > self.end_year:
            raise ValueError('Start year must be less than or equal to end year')
        if not self.start_year <= self.end_year < date.today().year:
            raise ValueError('Choose complete years from 1940 through the previous year')
        if self.end_year - self.start_year > 59:
            raise ValueError('Select at most 60 years')
        return self


@app.get('/api/health')
def health():
    return {'status': 'ok' if db is not None else 'database_unavailable', 'database': db is not None}


@app.get('/api/ready')
async def ready():
    if db is None:
        raise HTTPException(503, 'Database unavailable')
    try:
        await asyncio.to_thread(db.command, 'ping')
    except Exception:
        raise HTTPException(503, 'Database unavailable')
    return {'status': 'ready'}


@app.get('/api/regions')
async def regions(q: str = ''):
    if not 2 <= len(q.strip()) <= 80:
        raise HTTPException(422, 'Search must contain 2–80 characters')
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            response = await http.get('https://geocoding-api.open-meteo.com/v1/search', params={'name': q.strip(), 'count': 20, 'language': 'en'})
            response.raise_for_status()
            return normalize_locations(response.json().get('results', []))
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        raise HTTPException(502, 'Location search unavailable. Enter coordinates instead.')


@app.get('/api/map-regions')
async def map_regions(q: str, kind: Literal['country', 'state'] = 'country', country: str = ''):
    global map_search_last
    q = q.strip()
    if not 2 <= len(q) <= 80 or (country and (len(country) != 2 or not country.isalpha())):
        raise HTTPException(422, 'Enter a country/state name (2-80 characters) and a valid country code.')
    key = (q.casefold(), kind, country.lower())
    async with map_search_lock:
        cached = map_search_cache.get(key)
        if cached and time.monotonic() - cached[0] < 86400:
            return cached[1]
        await asyncio.sleep(max(0, 1.1 - (time.monotonic() - map_search_last)))
        map_search_last = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=15) as http:
                params = {'q': q, 'featureType': kind, 'format': 'jsonv2', 'addressdetails': 1, 'limit': 8, 'accept-language': 'en'}
                if country:
                    params['countrycodes'] = country.lower()
                response = await http.get(os.getenv('MAP_GEOCODER_URL', 'https://nominatim.openstreetmap.org/search'),
                                          params=params, headers={'User-Agent': 'HeatWaveTrendAnalyzer/1.0 (interactive region picker)'})
                response.raise_for_status()
                results = normalize_map_regions(response.json())
                if len(map_search_cache) >= 256:
                    map_search_cache.pop(next(iter(map_search_cache)))
                map_search_cache[key] = (time.monotonic(), results)
                return results
        except (httpx.HTTPError, ValueError, TypeError):
            raise HTTPException(502, 'Country/state search unavailable. Retry or select a point on the map.')


async def fetch_weather(latitude, longitude, start, end, variable='temperature_2m_max'):
    source = {**SOURCE, 'daily': variable}
    if variable == 'precipitation_sum':
        source['precipitation_unit'] = 'mm'
    key = weather_key(latitude, longitude, start, end) if variable == 'temperature_2m_max' else cache_key({'latitude': latitude, 'longitude': longitude, 'start_year': start, 'end_year': end}, baseline=(), source=source, algorithm='precipitation-v1')
    cached = await asyncio.to_thread(db.weather.find_one, {'_id': key})
    if cached:
        return cached['records']
    try:
        async with httpx.AsyncClient(timeout=90) as http:
            response = await http.get('https://archive-api.open-meteo.com/v1/archive', params={'latitude': latitude, 'longitude': longitude, 'start_date': f'{start}-01-01', 'end_date': f'{end}-12-31', **{k: v for k, v in source.items() if k != 'provider'}})
            response.raise_for_status()
            daily = response.json()['daily']
            if len(daily['time']) != len(daily[variable]):
                raise ValueError('Mismatched daily arrays')
            field = 'temperature' if variable == 'temperature_2m_max' else 'precipitation'
            cleaner = clean if field == 'temperature' else clean_precipitation
            records = [{'date': day, field: cleaner(value)} for day, value in zip(daily['time'], daily[variable])]
            days = [date.fromisoformat(r['date']) for r in records]
            if len(set(days)) != len(days) or any(not date(start, 1, 1) <= d <= date(end, 12, 31) for d in days):
                raise ValueError('Invalid weather dates')
        await asyncio.to_thread(db.weather.replace_one, {'_id': key}, {'_id': key, 'records': records}, upsert=True)
        return records
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        # Only this fixed, unauthenticated weather endpoint is involved.
        # Do not log environment variables, DB exceptions or connection URIs.
        reason = ''
        try:
            reason = str(exc.response.json().get('reason', ''))[:300]
        except (ValueError, AttributeError):
            pass
        logger.warning('Open-Meteo weather request rejected: HTTP %s; reason=%r', status, reason)
        if status == 429:
            detail = 'Historical weather provider rate limit reached. Please wait and retry.'
        elif status in (401, 403):
            detail = 'Historical weather provider denied access from the hosted backend. Provider configuration must be checked.'
        else:
            detail = f'Historical weather provider returned HTTP {status}. Please retry; if it persists, check backend logs.'
        raise HTTPException(502, detail)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        logger.warning('Open-Meteo weather request failed: %s', type(exc).__name__)
        raise HTTPException(502, 'Historical weather service unavailable or returned invalid data. Please retry.')


@app.post('/api/analyze')
async def analysis(body: AnalysisRequest):
    if db is None:
        raise HTTPException(503, 'MongoDB is unavailable. Start MongoDB and restart the backend.')
    params = body.model_dump()
    params['latitude'] = round(params['latitude'], 3)
    params['longitude'] = round(params['longitude'], 3)
    key = cache_key(params)
    async with slots:
        try:
            cached = await asyncio.to_thread(db.cache.find_one, {'_id': key, 'expiresAt': {'$gt': datetime.now(timezone.utc)}})
            if cached:
                return {**cached['result'], 'cached': True}
            hazard = body.hazard
            field = 'temperature' if hazard == 'heatwave' else 'precipitation'
            variable = 'temperature_2m_max' if hazard == 'heatwave' else 'precipitation_sum'
            async def weather(start, end):
                if hazard == 'heatwave':
                    return await fetch_weather(params['latitude'], params['longitude'], start, end)
                return await fetch_weather(params['latitude'], params['longitude'], start, end, variable)
            threshold = 1.0
            if hazard != 'drought':
                baseline = await weather(*BASELINE)
                cleaner = clean if hazard == 'heatwave' else clean_precipitation
                valid = [cleaner(r.get(field)) for r in baseline]
                valid = [v for v in valid if v is not None]
                if len(valid) < (date(BASELINE[1] + 1, 1, 1) - date(BASELINE[0], 1, 1)).days * .95:
                    raise HTTPException(422, 'Baseline coverage below 95%; a reliable threshold cannot be calculated.')
                wet = valid if hazard == 'heatwave' else [v for v in valid if v >= 1]
                if not wet:
                    raise HTTPException(422, 'No wet baseline days; a heavy-rainfall percentile cannot be calculated.')
                threshold = percentile(wet)
            records = await weather(body.start_year, body.end_year)
            result = await asyncio.to_thread(analyze, records, threshold, body.start_year, body.end_year, hazard)
            definition = {'heatwave': '3+ consecutive days above the baseline 95th percentile of daily maximum temperature.', 'heavy_rainfall': '1+ consecutive days above the baseline wet-day (precipitation >=1 mm) 95th percentile.', 'drought': 'Dry-spell proxy: 15+ consecutive days with precipitation <1 mm/day; not SPI/SPEI or a drought diagnosis.'}[hazard]
            result.update({'hazard': hazard, 'unit': 'C' if hazard == 'heatwave' else 'mm', 'definition': definition, 'region': params, 'baseline': list(BASELINE) if hazard != 'drought' else [], 'source': 'Open-Meteo / ERA5', 'source_parameters': {**SOURCE, 'daily': variable, **({'precipitation_unit': 'mm'} if hazard != 'heatwave' else {})}, 'algorithm_version': ALGORITHM_VERSION, 'scope': 'single_grid_cell', 'cached': False})
            await asyncio.to_thread(db.cache.replace_one, {'_id': key}, {'_id': key, 'result': result, 'expiresAt': datetime.now(timezone.utc) + timedelta(days=30)}, upsert=True)
            return result
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, 'Analysis storage unavailable. Please retry when the database is healthy.')
