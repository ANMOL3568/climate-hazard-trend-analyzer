"""Pure, deterministic climate calculations; temperatures are Celsius."""
import math
from datetime import date, timedelta


def clean(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and -90 <= value <= 65 else None


def percentile(values, p=.95):
    ordered = sorted(v for v in values if v is not None)
    if not ordered:
        raise ValueError('No valid baseline observations')
    index = (len(ordered) - 1) * p
    lower = int(index)
    return ordered[lower] + (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]) * (index - lower)


def clean_precipitation(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and value >= 0 else None


def analyze(records, threshold, start, end, hazard='heatwave'):
    if hazard not in ('heatwave', 'drought', 'heavy_rainfall'):
        raise ValueError('Unsupported hazard')
    field = 'temperature' if hazard == 'heatwave' else 'precipitation'
    cleaner = clean if hazard == 'heatwave' else clean_precipitation
    minimum = {'heatwave': 3, 'drought': 15, 'heavy_rainfall': 1}[hazard]
    # Fill absent dates explicitly: a gap must never connect two events.
    by_day = {r['date']: cleaner(r.get(field)) for r in records}
    daily, events, run = [], [], []
    def flush():
        if len(run) >= minimum:
            events.append({'start': run[0]['date'], 'end': run[-1]['date'], 'duration': len(run), 'peak': max(r[field] for r in run)})
        run.clear()
    day = date(start, 1, 1)
    while day <= date(end, 12, 31):
        row = {'date': day.isoformat(), field: by_day.get(day.isoformat())}
        daily.append(row)
        if row[field] is not None and (row[field] < threshold if hazard == 'drought' else row[field] > threshold):
            run.append(row)
        else:
            flush()
        day += timedelta(days=1)
    flush()
    annual = []
    for year in range(start, end + 1):
        rows = [r for r in daily if r['date'].startswith(str(year))]
        days = sum(max(0, (min(date.fromisoformat(e['end']), date(year, 12, 31)) - max(date.fromisoformat(e['start']), date(year, 1, 1))).days + 1) for e in events)
        annual.append({'year': year, 'events': sum(e['start'].startswith(str(year)) for e in events), 'days': days, 'coverage': round(sum(r[field] is not None for r in rows) / len(rows) * 100, 2)})
    for i, row in enumerate(annual):
        row['rollingDays'] = round(sum(r['days'] for r in annual[max(0, i-4):i+1]) / len(annual[max(0, i-4):i+1]), 2)
    n = len(annual)
    mean_x = sum(r['year'] for r in annual) / n
    mean_y = sum(r['days'] for r in annual) / n
    denominator = sum((r['year'] - mean_x)**2 for r in annual)
    slope = sum((r['year'] - mean_x)*(r['days'] - mean_y) for r in annual) / denominator if denominator else None
    coverage = round(sum(r[field] is not None for r in daily) / len(daily) * 100, 2)
    if coverage < 95:
        slope = None
    return {'threshold': round(threshold, 3), 'events': events, 'annual': annual, 'daily': daily,
            'summary': {'events': len(events), 'days': sum(e['duration'] for e in events), 'longest': max((e['duration'] for e in events), default=0), 'coverage': coverage, 'slope': round(slope, 3) if slope is not None else None}}
