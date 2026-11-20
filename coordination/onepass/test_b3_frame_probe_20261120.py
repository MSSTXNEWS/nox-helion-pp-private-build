import json
import pathlib
import tempfile
import unittest

from b3_frame_probe_20261120 import measure, summarize, verify_url


class TestProbe(unittest.TestCase):
    def test_source_contract(self):
        self.assertEqual(summarize([16.0] * 90)['p95_ms'], 16.0)
        with self.assertRaises(ValueError):
            summarize([1, 2])
        with self.assertRaises(ValueError):
            verify_url('file:///etc/passwd')
        with self.assertRaises(ValueError):
            verify_url('https://user:pass@nox.example/')

    def test_headless_real_chromium_mock_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = measure('http://127.0.0.1:8765/resonance.html', tmp,
                chromium='/usr/bin/chromium', expected_selector='#resonance',
                fixture_html='<html><body><main id="resonance">NOX synthetic local page</main></body></html>')
            self.assertEqual(len(result['runs']), 6)
            self.assertEqual(result['blocked_mutating_requests'], 0)
            self.assertEqual(result['blocked_model_posts'], 0)
            self.assertFalse(result['native_s03_verified'])
            self.assertTrue(result['synthetic_fixture'])
            self.assertTrue(result['expected_selector_checked'])
            self.assertFalse(result['installed_model_identity_verified'])
            self.assertEqual({r['width'] for r in result['runs']}, {320, 390, 1440})
            self.assertEqual({r['mode'] for r in result['runs']}, {'normal', 'reduced'})
            for row in result['runs']:
                self.assertEqual(row['frame_time']['frames'], 90)
                contents = (pathlib.Path(tmp) / row['screenshot']).read_bytes()
                self.assertEqual(contents[:8], b'\x89PNG\r\n\x1a\n')
                self.assertGreater(len(contents), 200)
            self.assertEqual(json.loads((pathlib.Path(tmp) / 'b3_frame_report.json').read_text())['schema'],
                'NOX_B3_READONLY_BROWSER_FRAME_EVIDENCE_V1')


if __name__ == '__main__':
    unittest.main()
