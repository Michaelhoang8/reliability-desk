from . import data_apps, ml_apps

def table(title, headers, rows):
    return {'title': title, 'headers': headers, 'rows': rows}

def enrich(path, data, result):
    """Attach diagnostics without changing existing response fields."""
    tables, notes = ([], [])
    threshold = ml_apps.number(data.get('burn_threshold', 2), 'Burn threshold', 0.01, 10000)
    short, long = (result['latest_hour_burn'], result['recent_six_hour_burn'])
    state = 'insufficient data' if short is None or long is None else 'firing' if short >= threshold and long >= threshold else 'not firing'
    result['burn_alert'] = {'threshold': threshold, 'state': state, 'short_hours': 1, 'long_hours': 6}
    tables = [table('Two-window burn check', ['1-hour burn', '6-hour burn', 'Threshold', 'Status'], [[short if short is not None else 'N/A', long if long is not None else 'N/A', threshold, state]])]
    notes = ['Both windows must reach the threshold. Missing buckets or zero traffic can make the check unavailable. This evaluates the end of the supplied dataset; no live monitor or notification is configured.']
    coverage = result['coverage']
    tables.append(table('Observed coverage', ['First UTC bucket', 'Last UTC bucket', 'Observed hours', 'Expected hours'], [[coverage[key] for key in ('first_bucket', 'last_bucket', 'observed_hours', 'expected_hours')]]))
    gaps = result['missing_ranges']
    if gaps:
        rows = [[gap['first_missing'], gap['last_missing'], gap['hours']] for gap in gaps]
        tables.append(table(f'Missing-hour ranges · {min(20, len(gaps))} of {len(gaps)} shown', ['First missing UTC bucket', 'Last missing UTC bucket', 'Hours'], rows[:20]))
        result['missing_ranges_csv'] = data_apps.safe_csv(['first_missing_utc', 'last_missing_utc', 'hours'], [[str(value) for value in row] for row in rows])
    worst = sorted((bucket for bucket in result['buckets'] if bucket['bad'] > 0), key=lambda bucket: (-bucket['burn_rate'], -bucket['bad'], bucket['timestamp']))[:10]
    tables.append(table('Hours with highest observed error ratios · up to 10', ['UTC bucket', 'Requests', 'Bad requests', 'Burn rate'], [[bucket['timestamp'], bucket['total'], bucket['bad'], bucket['burn_rate']] for bucket in worst]))
    result['hourly_metrics_csv'] = data_apps.safe_csv(['timestamp_utc', 'total', 'bad', 'success_rate', 'burn_rate', 'target_slo_percent'], [[str(value) if value is not None else '' for value in [bucket['timestamp'], bucket['total'], bucket['bad'], (bucket['total'] - bucket['bad']) / bucket['total'] if bucket['total'] else None, bucket['burn_rate'], result['target']]] for bucket in result['buckets']])
    notes.append('The historical table ranks supplied hours with errors by error ratio (equivalently burn rate for this target), then bad-request count and UTC time. Low-traffic ratios can be noisy; request counts are shown for context. The hourly CSV includes all supplied buckets, including zero-traffic buckets with undefined rates left empty. Missing hours are not fabricated. Success rates in the CSV are fractions from 0 to 1.')
    notes.append('Coverage spans the first through last supplied bucket, inclusive. Gap endpoints are missing bucket start times, also inclusive. No coverage is inferred before or after this span; missing hours are not treated as healthy or zero traffic.')
    if tables or notes:
        result['capabilities'] = {'tables': tables, 'notes': notes}
    return result
