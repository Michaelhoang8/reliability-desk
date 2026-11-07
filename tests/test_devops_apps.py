import json
import unittest
from portfolio import devops_apps as d
from portfolio.validation import ValidationError

def manifest():
    return {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'spec': {'replicas': 2, 'selector': {'matchLabels': {'app': 'demo'}}, 'template': {'metadata': {'labels': {'app': 'demo'}}, 'spec': {'securityContext': {'runAsNonRoot': True, 'seccompProfile': {'type': 'RuntimeDefault'}}, 'containers': [{'name': 'api', 'image': 'example.invalid/api@sha256:' + 'a' * 64, 'resources': {'requests': {'cpu': '100m', 'memory': '64Mi'}, 'limits': {'cpu': '500m', 'memory': '128Mi'}}, 'readinessProbe': {'httpGet': {}}, 'livenessProbe': {'exec': {}}, 'securityContext': {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True, 'capabilities': {'drop': ['ALL']}}}]}}}}

class DevOpsTests(unittest.TestCase):

    def test_budget_and_weighted_burn(self):
        r = d.reliability({'csv': 'timestamp,total,bad\n2026-01-01T00:00:00Z,1000,1\n2026-01-01T01:00:00Z,9000,18', 'target': 99.9})
        self.assertEqual((r['allowed_bad'], r['remaining_bad']), (10, -9))
        self.assertAlmostEqual(r['burn_rate'], 1.9)
        self.assertAlmostEqual(r['latest_hour_burn'], 2)

    def test_gaps_zero_traffic_and_complete_six_hour_window(self):
        csv = 'timestamp,total,bad\n' + '\n'.join((f'2026-01-01T0{i}:00:00Z,1000,1' for i in range(6)))
        self.assertEqual(d.reliability({'csv': csv})['recent_six_hour_burn'], 1)
        gap = d.reliability({'csv': 'timestamp,total,bad\n2026-01-01T00:00:00Z,0,0\n2026-01-01T02:00:00Z,0,0'})
        self.assertEqual(gap['missing_hours'], 1)
        self.assertIsNone(gap['burn_rate'])
        self.assertIsNone(gap['recent_six_hour_burn'])

    def test_gap_ranges_are_normalized_sorted_and_inclusive(self):
        result = d.reliability({'csv': 'timestamp,total,bad\n2026-01-02T05:00:00Z,1000,0\n2026-01-02T00:00:00+01:00,1000,0\n2026-01-02T01:00:00Z,1000,0'})
        self.assertEqual(result['missing_ranges'], [{'first_missing': '2026-01-02T00:00:00+00:00', 'last_missing': '2026-01-02T00:00:00+00:00', 'hours': 1}, {'first_missing': '2026-01-02T02:00:00+00:00', 'last_missing': '2026-01-02T04:00:00+00:00', 'hours': 3}])
        self.assertEqual(result['missing_hours'], 4)
        self.assertEqual(result['coverage']['observed_hours'], 3)
        self.assertEqual(result['coverage']['expected_hours'], 7)
        self.assertIsNone(result['recent_six_hour_burn'])

    def test_gap_ranges_do_not_expand_large_spans_or_infer_outer_coverage(self):
        result = d.reliability({'csv': 'timestamp,total,bad\n0001-01-01T00:00:00Z,1,0\n9999-12-31T23:00:00Z,1,0'})
        self.assertEqual(len(result['missing_ranges']), 1)
        self.assertEqual(result['missing_ranges'][0]['hours'], result['missing_hours'])
        self.assertEqual(result['coverage']['expected_hours'], 87649416)
        single = d.reliability({'csv': 'timestamp,total,bad\n2026-01-01T00:00:00Z,0,0'})
        self.assertEqual(single['missing_ranges'], [])
        self.assertEqual(single['coverage']['expected_hours'], 1)

    def test_invalid_metric_timestamps_counts_and_duplicates(self):
        for records in ['2026-01-01T00:30:00Z,10,1', '2026-01-01T00:00:00,10,1', '2026-01-01T00:00:00Z,10,11', '2026-01-01T00:00:00Z,10,1\n2026-01-01T01:00:00+01:00,10,1']:
            with self.assertRaises(ValidationError):
                d.reliability({'csv': 'timestamp,total,bad\n' + records})
