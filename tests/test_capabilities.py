import json
import csv
import io
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from portfolio import capabilities as c, data_apps as d, ml_apps as ml, devops_apps as ops
from portfolio.db import initialize, connect, SCHEMA
from portfolio.validation import ValidationError, NotFoundError

def enhanced(path, data, function):
    return c.enrich(path, data, function(data))

class AnalysisCapabilities(unittest.TestCase):

    def test_reliability_gap_export_keeps_all_ranges_beyond_preview(self):
        from datetime import datetime, timedelta, timezone
        first = datetime(2026, 1, 1, tzinfo=timezone.utc)
        source = 'timestamp,total,bad\n' + '\n'.join((f'{(first + timedelta(hours=i * 2)).isoformat()},100,0' for i in range(26)))
        result = enhanced('/api/devops/reliability', {'csv': source}, ops.reliability)
        rows = list(csv.DictReader(io.StringIO(result['missing_ranges_csv'])))
        self.assertEqual(len(rows), 25)
        self.assertEqual(sum((int(row['hours']) for row in rows)), result['missing_hours'])
        self.assertEqual(rows[-1]['last_missing_utc'], '2026-01-03T01:00:00+00:00')
        gaps = next((table for table in result['capabilities']['tables'] if table['title'].startswith('Missing-hour ranges')))
        self.assertEqual(len(gaps['rows']), 20)
        self.assertEqual(result['burn_alert']['state'], 'insufficient data')

    def test_reliability_history_ranks_earlier_errors_and_exports_every_bucket(self):
        from datetime import datetime, timedelta, timezone
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        lines = ['timestamp,total,bad']
        for index in range(60):
            total, bad = (0, 0) if index == 59 else (1000, 50 if index == 0 else 1)
            lines.append(f'{(start + timedelta(hours=index)).isoformat()},{total},{bad}')
        result = enhanced('/api/devops/reliability', {'csv': '\n'.join(lines), 'target': 99.9}, ops.reliability)
        worst = next((table for table in result['capabilities']['tables'] if table['title'].startswith('Hours with highest')))
        self.assertEqual(len(worst['rows']), 10)
        self.assertEqual(worst['rows'][0], [start.isoformat(), 1000, 50, 50.0])
        exported = list(csv.DictReader(io.StringIO(result['hourly_metrics_csv'])))
        self.assertEqual(len(exported), 60)
        self.assertEqual(exported[0]['success_rate'], '0.95')
        self.assertEqual(exported[0]['target_slo_percent'], '99.9')
        self.assertEqual((exported[-1]['total'], exported[-1]['success_rate'], exported[-1]['burn_rate']), ('0', '', ''))

    def test_reliability_history_keeps_gaps_and_handles_no_errors(self):
        source = 'timestamp,total,bad\n2026-01-01T02:00:00Z,1000,0\n2026-01-01T00:00:00Z,0,0'
        result = enhanced('/api/devops/reliability', {'csv': source}, ops.reliability)
        worst = next((table for table in result['capabilities']['tables'] if table['title'].startswith('Hours with highest')))
        self.assertEqual(worst['rows'], [])
        exported = list(csv.DictReader(io.StringIO(result['hourly_metrics_csv'])))
        self.assertEqual(len(exported), 2)
        self.assertEqual(exported[0]['timestamp_utc'], '2026-01-01T00:00:00+00:00')
        self.assertEqual(exported[1]['burn_rate'], '0.0')
        self.assertEqual(result['missing_hours'], 1)

    def test_burn_zero_traffic_is_insufficient_even_with_six_buckets(self):
        csv = 'timestamp,total,bad\n' + '\n'.join((f'2026-01-01T0{i}:00:00Z,0,0' for i in range(6)))
        r = enhanced('/api/devops/reliability', {'csv': csv}, ops.reliability)
        self.assertEqual(r['burn_alert']['state'], 'insufficient data')

    def test_burn_requires_both_windows_and_complete_data(self):
        csv = 'timestamp,total,bad\n' + '\n'.join((f'2026-01-01T0{i}:00:00Z,1000,10' for i in range(6)))
        data = {'csv': csv, 'target': 99.9, 'burn_threshold': 2}
        self.assertEqual(enhanced('/api/devops/reliability', data, ops.reliability)['burn_alert']['state'], 'firing')
        data['csv'] = csv.rsplit('\n', 1)[0]
        self.assertEqual(enhanced('/api/devops/reliability', data, ops.reliability)['burn_alert']['state'], 'insufficient data')
if __name__ == '__main__':
    unittest.main()
