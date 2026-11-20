"""One focused 2A05 receipt-contract regression, no inference or host effects."""
import unittest
from owner_latency_2a05 import summarize

M = 'a' * 64
R = 'b' * 64
S = 'c' * 64
A = 'd' * 64


def fixture(i):
    return {
        'schema': 'NOX_OWNER_BROWSER_STREAM_ONLY_QA_V2',
        'state': 'STREAM_ONLY_ACCEPTED', 'native_posts_admitted': 2,
        'both_terminal_sse_done_records_saved_s03_integrated': True,
        'authenticated_s03_history_readback_verified': True,
        'first_turn_terminal_sse_verified': True,
        'verified_model_sha256': M, 'verified_route_sha256': R,
        'request': str(i), 'source_sha': S, 'served_asset_sha256': A,
        'stream': {'native_first_ms': i * 10, 'ui_first_ms': i * 20},
        'elapsed_turn_ms': i * 100, 'multiturn_second_elapsed_ms': i * 200,
        'private_dialog': 'must-never-be-echoed',
    }


class NativeLatencyContract(unittest.TestCase):
    def test_quantiles_and_fail_closed(self):
        rows = [fixture(i) for i in range(1, 21)]
        v = summarize(rows, model_sha256=M, route_sha256=R)
        self.assertEqual(v['state'], 'SOURCE_BASELINE_READY_NOT_NATIVE_ACCEPTED')
        self.assertEqual(v['latency_ms']['ttft_ms'], {'p50': 100.0, 'p95': 190.0})
        self.assertEqual(v['latency_ms']['second_turn_ms'], {'p50': 2000.0, 'p95': 3800.0})
        self.assertNotIn('must-never-be-echoed', repr(v))
        self.assertEqual(v['original295_accepted_increment'], 0)
        self.assertIsNone(summarize(rows[:19], model_sha256=M,
                                    route_sha256=R)['latency_ms']['ttft_ms'])
        for bad in (rows + [fixture(1)], [dict(rows[0], verified_model_sha256='e'*64)]):
            with self.assertRaisesRegex(ValueError, 'HOLD_2A05_'):
                summarize(bad, model_sha256=M, route_sha256=R)
        # Python int > 1e308 must fail closed; math.isfinite(int) overflows.
        huge = fixture(21)
        huge['stream']['native_first_ms'] = 10 ** 401
        with self.assertRaisesRegex(ValueError, 'HOLD_2A05_BAD_LATENCY'):
            summarize([huge], model_sha256=M, route_sha256=R)


if __name__ == '__main__':
    unittest.main()
