"""Explicit live integration check; writes reviewable evidence, never credentials."""
import asyncio
import json
from pathlib import Path
import httpx
import main


async def verify():
    output = Path(__file__).resolve().parent.parent / 'verification'
    output.mkdir(exist_ok=True)
    evidence = {'geocoding': {}, 'analyses': []}
    async with main.app.router.lifespan_context(main.app):
        assert main.db is not None, 'MongoDB unavailable'
        async with httpx.AsyncClient(transport=httpx.ASGITransport(main.app), base_url='http://test', timeout=240) as client:
            for query in ('Delhi', 'Mumbai', 'Bihar'):
                response = await client.get('/api/regions', params={'q': query})
                assert response.status_code == 200, response.text
                evidence['geocoding'][query] = response.json()
            bihar = next(r for r in evidence['geocoding']['Bihar'] if r['id'] == 10470188)
            assert bihar['admin1'] == 'Uttar Pradesh' and bihar['country'] == 'India'
            assert (bihar['latitude'], bihar['longitude']) == (27.29201, 79.32543)
            bodies = [
                ('delhi', {'latitude': 28.614, 'longitude': 77.209, 'start_year': 1990, 'end_year': 2021}),
                ('mumbai', {'latitude': 19.07283, 'longitude': 72.88261, 'start_year': 1990, 'end_year': 2021}),
                ('mumbai-short', {'latitude': 19.07283, 'longitude': 72.88261, 'start_year': 2020, 'end_year': 2021}),
            ]
            for name, body in bodies:
                first = await client.post('/api/analyze', json=body)
                assert first.status_code == 200, first.text
                second = await client.post('/api/analyze', json=body)
                assert second.status_code == 200 and second.json()['cached'] is True
                a, b = first.json(), second.json()
                assert {k:v for k,v in a.items() if k != 'cached'} == {k:v for k,v in b.items() if k != 'cached'}
                assert len(a['annual']) == body['end_year']-body['start_year']+1
                assert sum(r['events'] for r in a['annual']) == a['summary']['events']
                assert sum(r['days'] for r in a['annual']) == a['summary']['days']
                assert a['region']['start_year'] == body['start_year']
                assert a['region']['latitude'] == round(body['latitude'], 3)
                (output / f'{name}.json').write_text(json.dumps(a), encoding='utf-8')
                record = {'case': name, 'first_cached': a['cached'], 'second_cached': b['cached'], 'annual_rows': len(a['annual']), 'threshold': a['threshold'], 'summary': a['summary']}
                evidence['analyses'].append(record)
                print(json.dumps(record), flush=True)
    (output / 'live-results.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')


if __name__ == '__main__':
    asyncio.run(verify())
