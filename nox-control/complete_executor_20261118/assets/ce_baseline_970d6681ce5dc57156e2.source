"""Source-only regression for read-only 0B04 receipt snapshot."""
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import work_progress as progress


class RecentVerifiedChangesTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.old = (self.now - timedelta(days=3)).isoformat()
        self.recent = (self.now - timedelta(minutes=2)).isoformat()
        self.since = (self.now - timedelta(days=1)).isoformat()
        self.tasks = {
            '0A01': {'id': '0A01', 'title': 'Native confirmation', 'evidence': 'native'},
            '0A02': {'id': '0A02', 'title': 'Source patch', 'evidence': 'source'},
            '0A03': {'id': '0A03', 'title': 'Wrong scope', 'evidence': 'native'},
            '0A04': {'id': '0A04', 'title': 'Old change', 'evidence': 'source'},
        }
        self.receipts = {
            '0A01': {'state': 'verified', 'scope': 'native', 'evidence': 'https://example.org/live', 'updated_at': self.recent},
            '0A02': {'state': 'verified', 'scope': 'source', 'evidence': 'https://example.org/code', 'updated_at': self.recent},
            '0A03': {'state': 'verified', 'scope': 'source', 'evidence': 'https://example.org/wrong', 'updated_at': self.recent},
            '0A04': {'state': 'verified', 'scope': 'source', 'evidence': 'https://example.org/old', 'updated_at': self.old},
            '0B01': {'state': 'verified', 'scope': 'native', 'evidence': 'https://example.org/unknown', 'updated_at': self.recent},
        }

    def check(self, since=None, limit=100):
        with patch.object(progress, 'registries', return_value=(self.tasks, {})), \
             patch.object(progress, 'read_receipt_payload', return_value={'tasks': self.receipts}):
            return progress.recent_verified_changes(Path('/not-read'), since or self.since, limit)

    def test_only_matching_verified_receipts_in_window(self):
        result = self.check()
        self.assertEqual({r['task_id'] for r in result['changes']}, {'0A01', '0A02'})
        self.assertEqual(result['count'], 2)
        self.assertFalse(result['history_complete'])

    def test_no_fabricated_changes_or_native_live(self):
        result = self.check()
        self.assertTrue(all(r['metric_delta'] is None and r['rollback_url'] is None
                            and r['experiment'] is None and not r['native_live_proven']
                            for r in result['changes']))
        self.assertEqual({r['verification_scope'] for r in result['changes']}, {'source','native'})

    def test_rejects_nonverified_and_invalid_evidence(self):
        self.receipts['0A02']['state'] = 'blocked'
        self.receipts['0A01']['evidence'] = 'file:///local/no_proof'
        self.assertEqual(self.check()['changes'], [])

    def test_sort_and_bounded_limit(self):
        self.receipts['0A02']['updated_at'] = (self.now - timedelta(minutes=1)).isoformat()
        result = self.check(limit=1)
        self.assertTrue(result['truncated'])
        self.assertEqual(result['changes'][0]['task_id'], '0A02')

    def test_naive_datetime_rejected(self):
        with self.assertRaisesRegex(ValueError, 'TZ_REQUIRED'):
            self.check('2026-11-17T00:00:00')

    def test_nonfinite_future_since_rejected(self):
        with self.assertRaisesRegex(ValueError, 'WORK_CHANGES_FUTURE_SINCE'):
            self.check((self.now + timedelta(hours=2)).isoformat())

    def test_bad_limit_rejected(self):
        for limit in (-1, 0, True, 201):
            with self.subTest(limit=limit), self.assertRaisesRegex(ValueError,'WORK_CHANGES_LIMIT'):
                self.check(limit=limit)

    def test_empty_latest_snapshot_is_not_full_history(self):
        self.receipts.clear()
        result = self.check()
        self.assertEqual(result['changes'], [])
        self.assertFalse(result['history_complete'])


if __name__ == '__main__':
    unittest.main()
