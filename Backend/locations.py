"""Validate complete GeoNames/Open-Meteo records without mixing locations."""
import math


def normalize_map_regions(records):
    """Keep administrative labels, point and map extent from the same OSM record."""
    results = []
    if not isinstance(records, list):
        raise ValueError('Invalid map search results')
    for record in records:
        try:
            lat, lon = float(record['lat']), float(record['lon'])
            bounds = [float(v) for v in record['boundingbox']]
            address = record['address']
            country = address['country']
            code = address['country_code']
            label = record['display_name']
            if not all(math.isfinite(v) for v in [lat, lon, *bounds]):
                continue
            if not (-90 <= lat <= 90 and -180 <= lon <= 180 and len(bounds) == 4):
                continue
            if not (-90 <= bounds[0] <= bounds[1] <= 90 and -180 <= bounds[2] <= bounds[3] <= 180):
                continue
            if not all(isinstance(v, str) and v.strip() for v in [country, code, label]):
                continue
            results.append(dict(name=label, label=label, country=country, country_code=code,
                                admin1=address.get('state'), latitude=lat, longitude=lon, bounds=bounds))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    return results


def normalize_locations(records):
    if not isinstance(records, list):
        raise ValueError('Invalid location results')
    results = []
    for record in records:
        if not isinstance(record, dict):
            continue
        lat, lon = record.get('latitude'), record.get('longitude')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (lat, lon)):
            continue
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            continue
        if not isinstance(record.get('id'), int) or not all(isinstance(record.get(k), str) and record[k].strip() for k in ('name', 'country')):
            continue
        item = {k: record.get(k) for k in ('id', 'name', 'admin1', 'admin2', 'country', 'country_code', 'feature_code', 'latitude', 'longitude')}
        item['label'] = ', '.join(dict.fromkeys(v for v in (item['name'], item['admin1'], item['country']) if isinstance(v, str) and v))
        item['kind'] = 'Administrative region reference point' if str(item['feature_code']).startswith('ADM') else 'Place reference point'
        results.append(item)
    return results
