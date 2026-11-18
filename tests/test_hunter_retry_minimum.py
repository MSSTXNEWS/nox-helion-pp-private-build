"""3B01 source-only focused regression: HTTP Retry-After may not bypass owner backoff.

Run on the existing patched Worm providers source as:
    PYTHONPATH=src python -m unittest -v test_hunter_retry_minimum.py
No internet, external poll, server startup, or model operation is required.
"""
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from nox_selfbuilder import worm_providers as p

class HunterRetryMinimumTests(unittest.TestCase):
    def setUp(self):
        self.now=[0.0]
        self.wall=datetime(2026,11,18,tzinfo=timezone.utc)
        self.cache=p.HTTPSourceCache(clock=lambda:self.now[0],wall_clock=lambda:self.wall.timestamp()+self.now[0])
        self.key=('https://api.github.com/test','application/json',131072)

    def defer(self,headers=None):
        self.cache.defer(self.key,headers)
        return self.cache.entry(self.key)['retry_at']-self.now[0]

    def test_zero_header_keeps_10s_minimum(self):
        self.assertEqual(self.defer({'Retry-After':'0'}),10)

    def test_second_zero_header_keeps_30s_minimum(self):
        self.assertEqual(self.defer({'Retry-After':'0'}),10)
        self.now[0]=10
        self.assertEqual(self.defer({'Retry-After':'0'}),30)

    def test_past_http_date_does_not_force_instant_retry(self):
        past=format_datetime(self.wall-timedelta(seconds=1),usegmt=True)
        self.assertEqual(self.defer({'Retry-After':past}),10)

    def test_future_retry_after_60_is_respected(self):
        self.assertEqual(self.defer({'Retry-After':'60'}),60)

    def test_future_http_date_120_is_respected(self):
        future=format_datetime(self.wall+timedelta(seconds=120),usegmt=True)
        self.assertEqual(self.defer({'Retry-After':future}),120)

    def test_missing_header_bounded_backoff(self):
        delays=[]
        for _ in range(8):
            d=self.defer();delays.append(d);self.now[0]+=d
        self.assertEqual(delays[:3],[10,30,90])
        self.assertTrue(all(0<d<=300 for d in delays))

if __name__=='__main__': unittest.main(verbosity=2)
