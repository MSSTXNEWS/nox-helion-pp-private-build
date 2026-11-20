import asyncio
import copy
import json
import inspect
import pathlib
import tempfile
import unittest

from b3_frame_probe_20261120 import _measure_async, compare_baseline, measure, summarize, verify_url, require_landing_url, renderer_resource_identity, sample_frames, evidence_hash, url_identity_sha256


class TestProbe(unittest.TestCase):
    def test_renderer_resource_identity_fail_closed(self):
        a = renderer_resource_identity([('script', 'const NOX = true;')],
                                       [('stylesheet', 'https://nox.invalid/res.css', b'body{}')])
        b = renderer_resource_identity([('script', 'const NOX = true;')],
                                       [('stylesheet', 'https://nox.invalid/res.css', b'body{opacity:0}')])
        self.assertRegex(a['sha256'], r'^[a-f0-9]{64}$')
        self.assertEqual(a['count'], 2)
        self.assertNotEqual(a['sha256'], b['sha256'])
        with self.assertRaisesRegex(ValueError, 'HOLD_LIVE_RENDER_RESOURCES_MISSING'):
            renderer_resource_identity([], [])
        with self.assertRaisesRegex(ValueError, 'HOLD_LIVE_RENDER_RESOURCE_INVALID'):
            renderer_resource_identity([], [('stylesheet', 'x', 'not bytes')])

    def test_source_contract(self):
        self.assertEqual(summarize([16.0] * 90)['p95_ms'], 16.0)
        with self.assertRaises(ValueError):
            summarize([1, 2])
        with self.assertRaises(ValueError):
            verify_url('file:///etc/passwd')
        with self.assertRaises(ValueError):
            verify_url('https://user:pass@nox.example/')
        live = 'http://127.0.0.1:8765/resonance.html'
        self.assertEqual(require_landing_url(live, live), live)
        spa = live + '#/resonance'
        self.assertEqual(require_landing_url(spa, spa), spa)
        with self.assertRaisesRegex(ValueError, 'HOLD_LIVE_LANDING_URL_MISMATCH'):
            require_landing_url(spa, live + '#/login')
        with self.assertRaisesRegex(ValueError, 'HOLD_LIVE_LANDING_URL_MISMATCH'):
            require_landing_url(spa, live)
        for redirect in (
            'http://127.0.0.1:8765/login.html',
            'http://127.0.0.1:8765/resonance.html?session=other',
            'https://127.0.0.1:8765/resonance.html',
            'http://127.0.0.1:9999/resonance.html',
            'https://example.com/resonance.html',
        ):
            with self.subTest(redirect=redirect), self.assertRaisesRegex(
                    ValueError, 'HOLD_LIVE_LANDING_URL_MISMATCH'):
                require_landing_url(live, redirect)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'HOLD_LIVE_SELECTOR_REQUIRED'):
                measure(live, temp, chromium='/usr/bin/chromium')


    def test_post_screenshot_spa_route_fence_wired(self):
        code = inspect.getsource(_measure_async)
        self.assertGreater(code.rfind('require_landing_url(url, page.url)'),
                           code.index('await page.screenshot('))
        self.assertLess(code.rfind('require_landing_url(url, page.url)'),
                        code.index("result['landing_url_verified'] = True"))

    def test_baseline_provenance_and_six_frame_modes(self):
        rows = [
            {'width': width, 'height': height, 'mode': mode,
             'frame_time': {'frames': 90, 'p95_ms': 16.0},
             'renderer_resource_sha256': 'a' * 64, 'renderer_resource_count': 2,
             'landing_url_sha256': url_identity_sha256('http://127.0.0.1:8765/resonance.html')}
            for width, height in ((320, 720), (390, 844), (1440, 900))
            for mode in ('normal', 'reduced')
        ]
        baseline = {
            'schema': 'NOX_B3_READONLY_BROWSER_FRAME_EVIDENCE_V4',
            'url_sha256': url_identity_sha256('http://127.0.0.1:8765/resonance.html'),
            'chromium_version_sha256': 'c' * 64,
            'sample_js': '90 consecutive real requestAnimationFrame intervals',
            'synthetic_fixture': False, 'expected_selector_checked': True,
            'expected_selector_sha256': evidence_hash('#resonance'), 'landing_url_verified': True,
            'runs': rows,
        }
        measured = copy.deepcopy(baseline)
        self.assertEqual(len(compare_baseline(measured, baseline)), 6)
        for change in (
            {'synthetic_fixture': True},
            {'url_sha256': url_identity_sha256('http://127.0.0.1:8765/login.html')},
            {'expected_selector_sha256': evidence_hash('#login')},
            {'expected_selector_checked': False},
            {'landing_url_verified': False},
            {'chromium_version_sha256': 'd' * 64},
        ):
            wrong = copy.deepcopy(baseline)
            wrong.update(change)
            with self.subTest(change=change), self.assertRaisesRegex(
                    ValueError, 'HOLD_BASELINE_PROVENANCE_MISMATCH|HOLD_BASELINE_MISSING_LIVE_SELECTOR|HOLD_BASELINE_LANDING_URL_UNVERIFIED'):
                compare_baseline(measured, wrong)
        missing_engine = copy.deepcopy(baseline)
        missing_engine['chromium_version_sha256'] = None
        with self.assertRaisesRegex(ValueError, 'HOLD_BASELINE_BROWSER_ENGINE_MISSING'):
            compare_baseline(missing_engine, missing_engine)
        landing_changed = copy.deepcopy(baseline)
        landing_changed['runs'][0]['landing_url_sha256'] = url_identity_sha256('http://127.0.0.1:8765/login.html')
        with self.assertRaisesRegex(ValueError, 'HOLD_BASELINE_LANDING_HASH_MISMATCH'):
            compare_baseline(measured, landing_changed)
        drift = copy.deepcopy(baseline)
        drift['runs'][0]['renderer_resource_sha256'] = 'b' * 64
        with self.assertRaisesRegex(ValueError, 'HOLD_BASELINE_RENDER_IDENTITY_DRIFT'):
            compare_baseline(measured, drift)
        absent = copy.deepcopy(baseline)
        absent['runs'][0].pop('renderer_resource_sha256')
        with self.assertRaisesRegex(ValueError, 'HOLD_BASELINE_RENDER_IDENTITY_MISSING'):
            compare_baseline(measured, absent)
        changed_count = copy.deepcopy(baseline)
        changed_count['runs'][0]['renderer_resource_count'] = 1
        with self.assertRaisesRegex(ValueError, 'HOLD_BASELINE_RENDER_IDENTITY_DRIFT'):
            compare_baseline(measured, changed_count)
        missing = copy.deepcopy(baseline)
        missing['runs'].pop()
        with self.assertRaisesRegex(ValueError, 'HOLD_BASELINE_FRAME_COVERAGE'):
            compare_baseline(measured, missing)
        broken = copy.deepcopy(baseline)
        broken['runs'][0]['frame_time']['p95_ms'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'HOLD_BASELINE_FRAME_INVALID'):
            compare_baseline(measured, broken)
        browser_no_selector = copy.deepcopy(measured)
        browser_no_selector['expected_selector_checked'] = False
        browser_no_selector['expected_selector'] = None
        with self.assertRaisesRegex(ValueError, 'HOLD_BASELINE_MISSING_LIVE_SELECTOR'):
            compare_baseline(browser_no_selector, browser_no_selector)
        synthetic = copy.deepcopy(measured)
        synthetic['synthetic_fixture'] = True
        synthetic['landing_url_verified'] = False
        self.assertEqual(len(compare_baseline(synthetic, synthetic)), 6)
        with self.assertRaisesRegex(ValueError, 'HOLD_BASELINE_PROVENANCE_MISMATCH'):
            compare_baseline(measured, synthetic)

    def test_stalled_raf_fails_closed_without_frame_evidence(self):
        from playwright.async_api import async_playwright

        async def run():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True, executable_path='/usr/bin/chromium')
                try:
                    page = await browser.new_page()
                    await page.goto('about:blank')
                    await page.evaluate('() => { window.requestAnimationFrame = () => 1; }')
                    with self.assertRaisesRegex(ValueError, 'HOLD_FRAME_SAMPLE_TIMEOUT'):
                        await sample_frames(page, timeout_seconds=0.15)
                finally:
                    await browser.close()

        asyncio.run(run())

    def test_reused_output_refused_before_browser_or_network(self):
        # A prior success report must remain intact; a new measurement may not
        # overwrite its PNGs then fail and leave misleading old/new evidence.
        with tempfile.TemporaryDirectory() as root:
            existing = pathlib.Path(root) / 'prior'
            existing.mkdir()
            stale = existing / 'b3_frame_report.json'
            stale.write_text('prior-success', encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'HOLD_EVIDENCE_DIRECTORY_REUSED'):
                measure('http://127.0.0.1:8765/resonance.html', str(existing),
                        chromium='/definitely/missing/chromium',
                        fixture_html='<main id="resonance">synthetic</main>',
                        expected_selector='#resonance')
            self.assertEqual(stale.read_text(encoding='utf8'), 'prior-success')
            self.assertEqual(sorted(p.name for p in existing.iterdir()),
                             ['b3_frame_report.json'])

    def test_same_url_spa_target_disappears_mid_frames(self):
        # A SPA can replace the UI without changing the URL or hash. Losing
        # the visible target *during* the 90-frame measurement must HOLD.
        fixture = (
            '<main id="resonance">Original NOX panel</main>'
            '<script>'
            'const raf = requestAnimationFrame.bind(window);'
            'let sampled=0;'
            'window.requestAnimationFrame=(callback)=>{'
            '  if (++sampled === 12) document.querySelector("#resonance").remove();'
            '  return raf(callback);'
            '};'
            '</script>'
        )
        with tempfile.TemporaryDirectory() as temp:
            out = pathlib.Path(temp) / 'removed_during_sampling'
            with self.assertRaisesRegex(ValueError, 'HOLD_LIVE_SELECTOR_DISAPPEARED'):
                measure('http://127.0.0.1:8765/resonance.html', str(out),
                        chromium='/usr/bin/chromium', fixture_html=fixture,
                        expected_selector='#resonance')
            self.assertFalse((out / 'b3_frame_report.json').exists())

    def test_headless_real_chromium_mock_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence_dir = pathlib.Path(tmp) / 'first_probe'
            secret_url = 'http://127.0.0.1:8765/resonance.html?auth=SECRET_URL_ABC#/resonance'
            secret_selector = '#resonance[data-session="SECRET_SELECTOR_XYZ"]'
            result = measure(secret_url, str(evidence_dir),
                chromium='/usr/bin/chromium', expected_selector=secret_selector,
                fixture_html=(
                    '<html><body><main id="resonance" data-session="SECRET_SELECTOR_XYZ">NOX synthetic local page</main>'
                    '<script>fetch("https://example.invalid/api/nox/chat",'
                    '{method:"POST",body:"x"}).catch(()=>{});'
                    'try{const ws=new WebSocket("wss://example.invalid/nox/stream");'
                    'ws.onerror=()=>{};}catch(e){}'
                    '</script></body></html>'))
            self.assertEqual(len(result['runs']), 6)
            self.assertEqual(result['blocked_mutating_requests'], 6)
            self.assertEqual(result['blocked_model_posts'], 6)
            self.assertEqual(result['blocked_websocket_connections'], 6)
            self.assertTrue(result['service_workers_blocked'])
            self.assertRegex(result['chromium_version_sha256'], r'^[a-f0-9]{64}
            self.assertFalse(result['native_s03_verified'])
            self.assertTrue(result['synthetic_fixture'])
            self.assertTrue(all(r['renderer_resource_sha256'] is None for r in result['runs']))
            self.assertTrue(result['expected_selector_checked'])
            self.assertFalse(result['landing_url_verified'])
            self.assertFalse(result['installed_model_identity_verified'])
            self.assertEqual({r['width'] for r in result['runs']}, {320, 390, 1440})
            self.assertEqual({r['mode'] for r in result['runs']}, {'normal', 'reduced'})
            for row in result['runs']:
                self.assertEqual(row['frame_time']['frames'], 90)
                contents = (evidence_dir / row['screenshot']).read_bytes()
                self.assertEqual(contents[:8], b'\x89PNG\r\n\x1a\n')
                self.assertGreater(len(contents), 200)
            report_text = (evidence_dir / 'b3_frame_report.json').read_text()
            self.assertNotIn('SECRET_URL_ABC', report_text)
            self.assertNotIn('SECRET_SELECTOR_XYZ', report_text)
            self.assertNotIn('resonance.html?auth=', report_text)
            self.assertEqual(result['url_sha256'], url_identity_sha256(secret_url))
            self.assertEqual(result['expected_selector_sha256'], evidence_hash(secret_selector))
            self.assertEqual(json.loads(report_text)['schema'],
                'NOX_B3_READONLY_BROWSER_FRAME_EVIDENCE_V4')


if __name__ == '__main__':
    unittest.main()
)
            self.assertFalse(result['native_s03_verified'])
            self.assertTrue(result['synthetic_fixture'])
            self.assertTrue(all(r['renderer_resource_sha256'] is None for r in result['runs']))
            self.assertTrue(result['expected_selector_checked'])
            self.assertFalse(result['landing_url_verified'])
            self.assertFalse(result['installed_model_identity_verified'])
            self.assertEqual({r['width'] for r in result['runs']}, {320, 390, 1440})
            self.assertEqual({r['mode'] for r in result['runs']}, {'normal', 'reduced'})
            for row in result['runs']:
                self.assertEqual(row['frame_time']['frames'], 90)
                contents = (evidence_dir / row['screenshot']).read_bytes()
                self.assertEqual(contents[:8], b'\x89PNG\r\n\x1a\n')
                self.assertGreater(len(contents), 200)
            report_text = (evidence_dir / 'b3_frame_report.json').read_text()
            self.assertNotIn('SECRET_URL_ABC', report_text)
            self.assertNotIn('SECRET_SELECTOR_XYZ', report_text)
            self.assertNotIn('resonance.html?auth=', report_text)
            self.assertEqual(result['url_sha256'], url_identity_sha256(secret_url))
            self.assertEqual(result['expected_selector_sha256'], evidence_hash(secret_selector))
            self.assertEqual(json.loads(report_text)['schema'],
                'NOX_B3_READONLY_BROWSER_FRAME_EVIDENCE_V4')


if __name__ == '__main__':
    unittest.main()
