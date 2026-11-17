"""Provider Retry-After is a minimum retry hint, independent of worker deadline."""
import json
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

from nox_advisors import Consultation
from nox_advisors.client import AdvisoryClient, CircuitBreaker, retry_delay
from nox_advisors.transport import CancelToken, HTTPReply


class NoWait(CancelToken):
    def wait(self, delay):
        raise AssertionError('A long provider cooldown must return to the existing host')


class RetryAfterContractTests(unittest.TestCase):
    def test_long_429_hint_reaches_host_unchanged_without_wait_or_retry(self):
        class QuotaReply:
            calls = 0

            def post(self, *args, **kwargs):
                self.calls += 1
                return HTTPReply(429, {'retry-after': '3600'}, b'{}')

        transport = QuotaReply()
        client = AdvisoryClient(
            transport=transport,
            environ={'OPENROUTER_API_KEY': 'offline-fixture-only'},
            breaker=CircuitBreaker(),
        )
        request = Consultation(
            'openrouter', 'openrouter/free', 'Compare two bounded index designs.',
            'retry-after-regression', True, deadline_seconds=0.2,
        )
        reply = client.consult(request, cancel=NoWait())
        self.assertEqual(reply.status, 'RATE_LIMITED')
        self.assertEqual(reply.attempts, 1)
        self.assertEqual(transport.calls, 1)
        self.assertEqual(reply.retry_after_seconds, 3600.0)

    def test_http_date_cooldown_is_not_shortened_to_five_minutes(self):
        later = datetime.now(timezone.utc) + timedelta(hours=1)
        delay = retry_delay({'retry-after': format_datetime(later, usegmt=True)}, 1)
        self.assertGreater(delay, 3590.0)
        self.assertLessEqual(delay, 3600.0)

    def test_nonfinite_header_does_not_enter_receipt(self):
        for value in ('NaN', 'inf', '-inf', '1e9999'):
            with self.subTest(value=value):
                delay = retry_delay({'retry-after': value}, 1)
                self.assertEqual(delay, 2.0)
                json.dumps({'retry_after_seconds': delay}, allow_nan=False)


if __name__ == '__main__':
    unittest.main()
