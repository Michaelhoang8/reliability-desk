import re
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from .data_apps import parse
from .validation import ValidationError
from .ml_apps import number

def reliability(data):
    headers, rows = parse(data)
    if not all((name in headers for name in ('timestamp', 'total', 'bad'))):
        raise ValidationError('CSV requires timestamp,total,bad columns')
    target = number(data.get('target', 99.9), 'SLO percentage', 90, 99.9999)
    buckets = []
    seen = set()
    for index, row in enumerate(rows, 2):
        try:
            stamp = datetime.fromisoformat(row[headers.index('timestamp')].replace('Z', '+00:00'))
            if stamp.utcoffset() is None:
                raise ValueError()
            stamp = stamp.astimezone(timezone.utc)
            if stamp.minute or stamp.second or stamp.microsecond or (stamp in seen):
                raise ValueError()
            counts = []
            for name in ('total', 'bad'):
                raw = row[headers.index(name)].strip()
                if not re.fullmatch('[0-9]{1,12}', raw):
                    raise ValueError()
                counts.append(int(raw))
            total, bad = counts
            if bad > total:
                raise ValueError()
        except (ValueError, OverflowError):
            raise ValidationError(f'Record {index}: use a unique UTC-hour-aligned timestamp with timezone and integer counts 0 ≤ bad ≤ total') from None
        seen.add(stamp)
        buckets.append({'timestamp': stamp, 'total': total, 'bad': bad})
    buckets.sort(key=lambda b: b['timestamp'])
    total = sum((b['total'] for b in buckets))
    bad = sum((b['bad'] for b in buckets))
    allowance = Decimal(1) - Decimal(str(target)) / 100
    budget = Decimal(total) * allowance

    def burn(selected):
        requests = sum((b['total'] for b in selected))
        return float(Decimal(sum((b['bad'] for b in selected))) / requests / allowance) if requests else None
    last = buckets[-1]['timestamp']
    recent = [b for b in buckets if last - b['timestamp'] <= timedelta(hours=5)]
    missing_ranges = []
    for previous, current in zip(buckets, buckets[1:]):
        missing = (current['timestamp'] - previous['timestamp']) // timedelta(hours=1) - 1
        if missing:
            missing_ranges.append({'first_missing': (previous['timestamp'] + timedelta(hours=1)).isoformat(), 'last_missing': (current['timestamp'] - timedelta(hours=1)).isoformat(), 'hours': missing})
    gaps = sum((item['hours'] for item in missing_ranges))
    return {'target': target, 'total': total, 'bad': bad, 'success_rate': (total - bad) / total if total else None, 'allowed_bad': float(budget), 'remaining_bad': float(budget - bad), 'budget_used': float(Decimal(bad) / budget) if budget else None, 'burn_rate': burn(buckets), 'latest_hour_burn': burn([buckets[-1]]), 'recent_six_hour_burn': burn(recent) if len(recent) == 6 else None, 'missing_hours': gaps, 'missing_ranges': missing_ranges, 'coverage': {'first_bucket': buckets[0]['timestamp'].isoformat(), 'last_bucket': last.isoformat(), 'observed_hours': len(buckets), 'expected_hours': len(buckets) + gaps}, 'buckets': [{**b, 'timestamp': b['timestamp'].isoformat(), 'burn_rate': burn([b])} for b in buckets], 'note': 'Request-based SLO for the supplied hourly buckets only. Missing hours are not assumed healthy. Six-hour burn is unavailable without six consecutive buckets. Zero traffic gives undefined rates; no forecast or live alerting is performed.'}
