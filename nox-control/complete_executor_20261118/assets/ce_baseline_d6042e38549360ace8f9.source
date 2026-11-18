"""6V14-04: receipt ordering follows instants, including different UTC offsets."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import unittest
from unittest.mock import patch

import work_progress as progress


class ReceiptTimeOrderTests(unittest.TestCase):
    def view(self, times, limit=100):
        tasks={key:{'id':key,'title':key,'evidence':'source'} for key in times}
        receipts={key:{'state':'verified','scope':'source','evidence':'https://example.org/'+key,
                       'updated_at':value} for key,value in times.items()}
        with patch.object(progress,'registries',return_value=(tasks,{})), \
             patch.object(progress,'read_receipt_payload',return_value={'tasks':receipts}):
            return progress.recent_verified_changes(Path('/not-read'),'2020-01-01T00:00:00+00:00',limit)

    def test_larger_local_clock_is_not_newer_absolute_time(self):
        result=self.view({'0A01':'2025-01-01T09:30:00+03:00',
                          '0A02':'2025-01-01T07:00:00+00:00'})
        self.assertEqual([x['task_id'] for x in result['changes']],['0A02','0A01'])

    def test_limit_keeps_the_truly_latest_receipt(self):
        result=self.view({'0A01':'2025-01-01T10:30:00+05:00',
                          '0A02':'2025-01-01T07:00:00+00:00'},limit=1)
        self.assertEqual(result['changes'][0]['task_id'],'0A02')
        self.assertTrue(result['truncated'])

    def test_equal_instants_use_existing_task_id_tiebreak(self):
        result=self.view({'0A01':'2025-01-01T10:00:00+03:00',
                          '0A02':'2025-01-01T07:00:00+00:00'})
        self.assertEqual([x['task_id'] for x in result['changes']],['0A02','0A01'])

    def test_original_offset_and_scope_stay_visible(self):
        original='2025-01-01T07:00:00-04:00'
        row=self.view({'0A01':original})['changes'][0]
        self.assertEqual(row['date'],original)
        self.assertEqual(row['verification_scope'],'source')
        self.assertFalse(row['native_live_proven'])


if __name__ == '__main__': unittest.main()
