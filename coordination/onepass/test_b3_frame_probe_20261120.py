import asyncio
import copy
import hashlib
import json
import inspect
import pathlib
import tempfile
import unittest

from b3_frame_probe_20261120 import _measure_async, compare_baseline, measure, summarize, verify_url, require_landing_url, renderer_resource_identity, sample_frames, evidence_hash, url_identity_sha256, is_model_chat_endpoint, verify_report_screenshots, capture_render_resource, capture_render_resources


class TestProbe(unittest.TestCase):
    def test_saved_baseline_screenshot_bytes_integrity(self):
        # A JSON hash alone does not prove the captured images still exist.
        # This deterministic fixture tests the evidence fence, not real NOX.
        with tempfile.TemporaryDirectory() as root:
            base = pathlib.Path(root)
            rows = []
            for width, height in ((320, 720), (390, 844), (1440, 900)):
                for mode in ('normal', 'reduced'):
                    name = f'b3_{width}x{height}_{mode}.png'
                    # Structural IHDR fixture (PNG decode not under test).
                    image = (b'\x89PNG\r\n\x1a\n'
                             + (13).to_bytes(4, 'big') + b'IHDR'
                             + width.to_bytes(4, 'big') + height.to_bytes(4, 'big')
                             + b'\x08\x06\x00\x00\x00' + b'\x00' * 4)
                    (base / name).write_bytes(image)
                    rows.append({'width': width, 'height': height, 'mode': mode,
                                 'screenshot': name, 'screenshot_bytes': len(image),
                                 'screenshot_sha256': hashlib.sha256(image).hexdigest()})
            report = {'runs': rows}
            self.assertIsNone(verify_report_screenshots(report, base))
            target = base / rows[0]['screenshot']
            original_header = target.read_bytes()
            # Attacker recomputes the image SHA: only IHDR dimensions/type differ.
            # Pre-fence these forged screenshot metadata pairs passed silently.
            for spoofed in (
                original_header[:16] + (390).to_bytes(4, 'big') + original_header[20:],
                original_header[:12] + b'JUNK' + original_header[16:],
            ):
                target.write_bytes(spoofed)
                altered = copy.deepcopy(report)
                altered['runs'][0]['screenshot_sha256'] = hashlib.sha256(spoofed).hexdigest()
                with self.subTest(spoofed=spoofed[12:24]), self.assertRaisesRegex(
                        ValueError, 'HOLD_BASELINE_SCREENSHOT_DIMENSIONS'):
                    verify_report_screenshots(altered, base)
            target.write_bytes(original_header)
            original = target.read_bytes()
            target.write_bytes(original + b'tampered')
            with self.assertRaisesRegex(ValueError, 'HOLD_BASELINE_SCREENSHOT_BYTES_MISMATCH'):
                verify_report_screenshots(report, base)
            target.write_bytes(original)
            target.unlink()
            with self.assertRaisesRegex(ValueError, 'HOLD_BASELINE_SCREENSHOT_MISSING'):
                verify_report_screenshots(report, base)
            target.write_bytes(original)
            for bad_name in ('../baseline.png', 'b3_390x844_normal.png'):
                altered = copy.deepcopy(report)
                altered['runs'][0]['screenshot'] = bad_name
                with self.subTest(name=bad_name), self.assertRaisesRegex(
                        ValueError, 'HOLD_BASELINE_SCREENSHOT_NAME'):
                    verify_report_screenshots(altered, base)
            altered = copy.deepcopy(report)
            altered['runs'][0]['screenshot_sha256'] = 'not-a-hash'
            with self.assertRaisesRegex(ValueError, 'HOLD_BASELINE_SCREENSHOT_METADATA'):
                verify_report_screenshots(altered, base)
            altered = copy.deepcopy(report)
            altered['runs'][0]['screenshot_bytes'] = True
            with self.assertRaisesRegex(ValueError, 'HOLD_BASELINE_SCREENSHOT_METADATA'):
                verify_report_screenshots(altered, base)
            altered = copy.deepcopy(report)
            altered['runs'].pop()
            with self.assertRaisesRegex(ValueError, 'HOLD_BASELINE_SCREENSHOT_COVERAGE'):
                verify_report_screenshots(altered, base)
        # The actual comparison entrypoint must check both evidence directories.
        source = inspect.getsource(_measure_async)
        self.assertLess(source.index('verify_report_screenshots(old, baseline_path.parent)'),
                        source.index('deltas = compare_baseline(result, old, transition)'))
        self.assertLess(source.index('verify_report_screenshots(result, out)'),
                        source.index('deltas = compare_baseline(result, old, transition)'))

    def test_render_asset_body_size_and_deadline_fail_closed(self):
        # Passive asset capture previously awaited response.body() forever
        # and accepted unbounded decompressed JS/CSS bytes.
        class Asset:
            def __init__(self, payload=b'body', length=None, delay=0, status=200):
                self.status = status
                self.url = 'http://127.0.0.1:18775/renderer.css'
                self.headers = {} if length is None else {'content-length': length}
                self.request = type('Request', (), {'resource_type': 'stylesheet'})()
                self.payload, self.delay, self.called = payload, delay, False

            async def body(self):
                self.called = True
                if self.delay:
                    await asyncio.sleep(self.delay)
                return self.payload

        async def check():
            captured = []
            await capture_render_resource(Asset(length='4'), captured,
                                          max_bytes=8, timeout=0.01)
            self.assertEqual(captured[0][2], b'body')
            self.assertEqual(len(captured), 1)
            too_big = Asset(length='9')
            with self.assertRaisesRegex(ValueError, 'HOLD_LIVE_RENDER_RESOURCE_OVERSIZE'):
                await capture_render_resource(too_big, captured, max_bytes=8)
            self.assertFalse(too_big.called)
            with self.assertRaisesRegex(ValueError, 'HOLD_LIVE_RENDER_RESOURCE_OVERSIZE'):
                await capture_render_resource(Asset(payload=b'x' * 9), captured,
                                              max_bytes=8)
            with self.assertRaisesRegex(ValueError, 'HOLD_LIVE_RENDER_RESOURCE_TIMEOUT'):
                await capture_render_resource(Asset(delay=0.05), captured,
                                              max_bytes=8, timeout=0.005)
            with self.assertRaisesRegex(ValueError, 'HOLD_LIVE_RENDER_RESOURCE_LENGTH'):
                await capture_render_resource(Asset(length='9junk'), captured,
                                              max_bytes=8)
            with self.assertRaisesRegex(ValueError, 'HOLD_LIVE_RENDER_RESOURCE_HTTP'):
                await capture_render_resource(Asset(status=404), captured,
                                              max_bytes=8)
            self.assertEqual(len(captured), 1)
        asyncio.run(check())

    def test_render_resource_aggregate_count_concurrency_and_cancel_budget(self):
        """Deterministic source budget; no native model or network calls."""
        class Asset:
            active = 0
            peak = 0

            def __init__(self, payload=b'xx', delay=0.002, status=200):
                self.status, self.payload, self.delay = status, payload, delay
                self.headers = {}
                self.url = 'http://127.0.0.1:18775/renderer.js'
                self.request = type('Request', (), {'resource_type': 'script'})()
                self.called = False

            async def body(self):
                self.called = True
                Asset.active += 1
                Asset.peak = max(Asset.peak, Asset.active)
                try:
                    await asyncio.sleep(self.delay)
                    return self.payload
                finally:
                    Asset.active -= 1

        async def check():
            assets = [Asset() for _ in range(6)]
            saved = []
            await capture_render_resources(assets, saved, max_responses=8,
                                           max_total_bytes=16, parallel=2, max_bytes=4)
            self.assertEqual(len(saved), 6)
            self.assertLessEqual(Asset.peak, 2)
            self.assertEqual(Asset.active, 0)

            overflow = [Asset() for _ in range(3)]
            with self.assertRaisesRegex(ValueError, 'HOLD_LIVE_RENDER_RESOURCE_COUNT'):
                await capture_render_resources(overflow, [], max_responses=2)
            self.assertTrue(all(not a.called for a in overflow))

            partial = []
            with self.assertRaisesRegex(ValueError, 'HOLD_LIVE_RENDER_RESOURCE_TOTAL_OVERSIZE'):
                await capture_render_resources([Asset(payload=b'xxxx') for _ in range(3)],
                                               partial, max_total_bytes=7,
                                               parallel=1, max_bytes=4)
            self.assertEqual(partial, [])
            failed = []
            with self.assertRaisesRegex(ValueError, 'HOLD_LIVE_RENDER_RESOURCE_HTTP'):
                await capture_render_resources([Asset(status=404), Asset(delay=0.1)],
                                               failed, parallel=2)
            self.assertEqual(failed, [])
            self.assertEqual(Asset.active, 0)

        asyncio.run(check())
        wiring = inspect.getsource(_measure_async)
        self.assertIn('await capture_render_resources(render_responses, network_assets)', wiring)
        self.assertIn('render_response_overflow', wiring)
        self.assertNotIn('asyncio.create_task(capture_resource(response))', wiring)

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


    def test_existing_serving_path_aliases_fenced_without_blocking_ui(self):
        # /nox/chat is an existing NOX model-serving entrypoint; this opt-in
        # browser probe must never issue even a GET to it.
        for url in (
            'http://127.0.0.1:18877/nox/chat',
            'http://127.0.0.1:18877/nox/chat/stream?prompt=no',
            'http://127.0.0.1:18877/nox%2Fchat/stream',
            'http://127.0.0.1:18877/nox%252Fchat/stream',
            'http://127.0.0.1:18877/api/nox/chat',
            'http://127.0.0.1:18877/api/nox%2Fchat/stream',
            'http://127.0.0.1:18877/API/NOX/CHAT',
            'http://127.0.0.1:18877/%2fapi/nox/chat',
            'http://127.0.0.1:18877/api%255CNOX%255CCHAT',
            'http://127.0.0.1:18877/nox/chat;rev=2',
            'http://127.0.0.1:18877/api/nox/chat%3Bsession=1',
            'http://127.0.0.1:18877/api//nox///chat/stream',
            # RFC dot-segments and encoded aliases can be normalized by
            # the browser/proxy before dispatch to the existing serving route.
            'http://127.0.0.1:18877/assets/../api/nox/chat',
            'http://127.0.0.1:18877/assets/%2e%2e/api/nox/chat/stream',
            'http://127.0.0.1:18877/api/./nox/chat',
            'http://127.0.0.1:18877/api/%2e/nox/chat/stream',
            'http://127.0.0.1:18877/assets/%252e%252e/nox/chat',
            'http://127.0.0.1:18877/assets/../nox/chat;rev=3',
            # Proxies may remove matrix qualifiers from an ancestor segment.
            'http://127.0.0.1:18877/api;trace=7/nox/chat',
            'http://127.0.0.1:18877/api/nox;rev=2/chat',
            'http://127.0.0.1:18877/nox;session=1/chat/stream',
            'http://127.0.0.1:18877/assets/../api;sid=1/nox;v=2/chat',
            'http://127.0.0.1:18877/%3Bsid=1/api/nox/chat',
            'http://127.0.0.1:18877/api%253Bsid=1/nox/chat',
            # Common model-serving API shapes must never be probed via GET.
            # These routes are guarded defensively, not asserted installed.
            'http://127.0.0.1:18877/v1/chat/completions',
            'http://127.0.0.1:18877/v1/completions',
            'http://127.0.0.1:18877/v1/responses',
            'http://127.0.0.1:18877/api/v1/chat/completions',
            'http://127.0.0.1:18877/api/chat',
            'http://127.0.0.1:18877/api/generate',
            'http://127.0.0.1:18877/v1/embeddings',
            'http://127.0.0.1:18877/api/embed',
            'http://127.0.0.1:18877/assets/%2e%2e/v1/chat/completions',
            'http://127.0.0.1:18877/v1;rev=1/chat/completions',
            'http://127.0.0.1:18877/v1%252fresponses',
        ):
            with self.subTest(block=url):
                self.assertTrue(is_model_chat_endpoint(url))
        for url in (
            'http://127.0.0.1:18877/resonance.html',
            'http://127.0.0.1:18877/nox/chat.html',
            'http://127.0.0.1:18877/api/nox/chatty',
            'http://127.0.0.1:18877/assets/chat.css',
            'http://127.0.0.1:18877/api/nox/chat.html',
            'http://127.0.0.1:18877/NOX/CHATTER',
            'http://127.0.0.1:18877/assets;rev=1/chat.css',
            'http://127.0.0.1:18877/api/nox/chat.html;v=2',
            'http://127.0.0.1:18877/v1/models',
            'http://127.0.0.1:18877/v1/chat/completions.html',
            'http://127.0.0.1:18877/api/chat.html',
            'http://127.0.0.1:18877/api/generate-ui',
            'http://127.0.0.1:18877/assets/v1/completions.css',
        ):
            with self.subTest(allow=url):
                self.assertFalse(is_model_chat_endpoint(url))


    def test_post_screenshot_spa_route_fence_wired(self):
        code = inspect.getsource(_measure_async)
        self.assertGreater(code.rfind('require_landing_url(url, page.url)'),
                           code.index('await page.screenshot('))
        self.assertLess(code.rfind('require_landing_url(url, page.url)'),
                        code.index("result['landing_url_verified'] = True"))

    def test_baseline_provenance_and_six_frame_modes(self):
        rows = [
            {'width': width, 'height': height, 'mode': mode,
             'frame_time': {'frames': 90, 'median_ms': 16.0,
                            'p95_ms': 16.0, 'over_50ms': 0},
             'renderer_resource_sha256': 'a' * 64, 'renderer_resource_count': 2,
             'landing_url_sha256': url_identity_sha256('http://127.0.0.1:8765/resonance.html')}
            for width, height in ((320, 720), (390, 844), (1440, 900))
            for mode in ('normal', 'reduced')
        ]
        baseline = {
            'schema': 'NOX_B3_READONLY_BROWSER_FRAME_EVIDENCE_V6',
            'url_sha256': url_identity_sha256('http://127.0.0.1:8765/resonance.html'),
            'chromium_version_sha256': 'c' * 64,
            'sample_js': '90 consecutive real requestAnimationFrame intervals',
            'synthetic_fixture': False, 'fixture_html_sha256': None,
            'expected_selector_checked': True,
            'expected_selector_sha256': evidence_hash('#resonance'), 'landing_url_verified': True,
            'blocked_mutating_requests': 0, 'blocked_model_posts': 0,
            'blocked_model_read_requests': 0, 'blocked_websocket_connections': 0, 'service_workers_blocked': True,
            'runs': rows,
        }
        measured = copy.deepcopy(baseline)
        self.assertEqual(len(compare_baseline(measured, baseline)), 6)
        for wrong_digest in ('f' * 64, '', False):
            live_wrong = copy.deepcopy(measured)
            live_wrong['fixture_html_sha256'] = wrong_digest
            with self.subTest(live_digest=wrong_digest), self.assertRaisesRegex(
                    ValueError, 'HOLD_BASELINE_UNEXPECTED_FIXTURE_HASH'):
                compare_baseline(live_wrong, live_wrong)
        missing_live = copy.deepcopy(measured)
        missing_live.pop('fixture_html_sha256')
        with self.assertRaisesRegex(ValueError, 'HOLD_BASELINE_UNEXPECTED_FIXTURE_HASH'):
            compare_baseline(missing_live, missing_live)
        # Both files may carry the same malformed 'synthetic' value. Before
        # this fence the truthy string "false" bypassed every live guard.
        for malformed in ('false', 'true', 0, 1, None):
            bad = copy.deepcopy(baseline)
            bad['synthetic_fixture'] = malformed
            with self.subTest(fixture=malformed), self.assertRaisesRegex(
                    ValueError, 'HOLD_BASELINE_FIXTURE_FLAG_INVALID'):
                compare_baseline(bad, bad)
        for malformed in ('true', 'false', 0, 1, None):
            bad = copy.deepcopy(baseline)
            bad['expected_selector_checked'] = malformed
            with self.subTest(selector=malformed), self.assertRaisesRegex(
                    ValueError, 'HOLD_BASELINE_SELECTOR_FLAG_INVALID'):
                compare_baseline(bad, bad)
        for malformed in ('not-sha256', 'G' * 64, None):
            bad = copy.deepcopy(baseline)
            bad['expected_selector_sha256'] = malformed
            with self.subTest(selector_hash=malformed), self.assertRaisesRegex(
                    ValueError, 'HOLD_BASELINE_MISSING_LIVE_SELECTOR'):
                compare_baseline(bad, bad)
        # A functioning-looking screenshot is not evidence that the
        # model/stream route works if this read-only probe had to block it.
        for counter in ('blocked_mutating_requests', 'blocked_model_posts',
                        'blocked_model_read_requests', 'blocked_websocket_connections'):
            for invalid in (1, True, None):
                unsafe = copy.deepcopy(baseline)
                unsafe[counter] = invalid
                with self.subTest(counter=counter, invalid=invalid), self.assertRaisesRegex(
                        ValueError, 'HOLD_BASELINE_LIVE_TRANSPORT_BLOCKED'):
                    compare_baseline(measured, unsafe)
        for counter in ('blocked_mutating_requests', 'blocked_model_posts',
                        'blocked_model_read_requests', 'blocked_websocket_connections'):
            missing = copy.deepcopy(measured)
            missing.pop(counter)
            with self.subTest(missing=counter), self.assertRaisesRegex(
                    ValueError, 'HOLD_BASELINE_LIVE_TRANSPORT_BLOCKED'):
                compare_baseline(missing, baseline)
        disabled_guard = copy.deepcopy(baseline)
        disabled_guard['service_workers_blocked'] = False
        with self.assertRaisesRegex(ValueError, 'HOLD_BASELINE_SERVICE_WORKER_GUARD_MISSING'):
            compare_baseline(measured, disabled_guard)
        disabled_guard.pop('service_workers_blocked')
        with self.assertRaisesRegex(ValueError, 'HOLD_BASELINE_SERVICE_WORKER_GUARD_MISSING'):
            compare_baseline(measured, disabled_guard)
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
        # Real optimized JS/CSS changes resource fingerprints. A six-viewport
        # exact owner-reviewed transition may be compared, never synthesized.
        reviewed = {'schema': 'NOX_B3_RENDER_TRANSITION_PINS_V1', 'rows': {
            f'{w}x{h}_{mode}': {
                'before_sha256': ('b' if (w, mode) == (320, 'normal') else 'a') * 64,
                'after_sha256': 'a' * 64, 'before_count': 2, 'after_count': 2,
            }
            for w, h in ((320, 720), (390, 844), (1440, 900))
            for mode in ('normal', 'reduced')
        }}
        self.assertEqual(len(compare_baseline(measured, drift, reviewed)), 6)
        incomplete = copy.deepcopy(reviewed)
        incomplete['rows'].pop('1440x900_reduced')
        with self.assertRaisesRegex(ValueError, 'HOLD_RENDER_TRANSITION_COVERAGE'):
            compare_baseline(measured, drift, incomplete)
        wrong_pin = copy.deepcopy(reviewed)
        wrong_pin['rows']['320x720_normal']['before_sha256'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'HOLD_RENDER_TRANSITION_PIN_MISMATCH'):
            compare_baseline(measured, drift, wrong_pin)
        wrong_count = copy.deepcopy(reviewed)
        wrong_count['rows']['320x720_normal']['after_count'] = True
        with self.assertRaisesRegex(ValueError, 'HOLD_RENDER_TRANSITION_PIN_MISMATCH'):
            compare_baseline(measured, drift, wrong_count)
        with self.assertRaisesRegex(ValueError, 'HOLD_RENDER_TRANSITION_MANIFEST'):
            compare_baseline(measured, drift, {'schema': 'NOX_B3_RENDER_TRANSITION_PINS_V1'})
        synthetic_review = copy.deepcopy(measured)
        synthetic_review['synthetic_fixture'] = True
        synthetic_review['fixture_html_sha256'] = evidence_hash('<main>same-fixture</main>')
        with self.assertRaisesRegex(ValueError, 'HOLD_RENDER_TRANSITION_REQUIRES_LIVE'):
            compare_baseline(synthetic_review, synthetic_review, reviewed)
        missing = copy.deepcopy(baseline)
        missing['runs'].pop()
        with self.assertRaisesRegex(ValueError, 'HOLD_BASELINE_FRAME_COVERAGE'):
            compare_baseline(measured, missing)
        # A forged True or numeric-looking string used to coerce into a
        # legitimate p95; reject it on both sides of a six-mode comparison.
        for field, bogus in (('p95_ms', True), ('p95_ms', '16.0'),
                             ('p95_ms', None), ('frames', 90.0)):
            for side in ('current', 'prior'):
                forged = copy.deepcopy(baseline)
                forged['runs'][0]['frame_time'][field] = bogus
                with self.subTest(field=field, bogus=bogus, side=side), self.assertRaisesRegex(
                        ValueError, 'HOLD_BASELINE_FRAME_INVALID'):
                    compare_baseline(forged, baseline) if side == 'current' else compare_baseline(
                        baseline, forged)
        # R20: invalid median and >50ms count must not masquerade as a
        # comparable six-viewport screenshot/frame receipt on EITHER side.
        for field, bogus in (('median_ms', True), ('median_ms', '16.0'),
                             ('median_ms', None), ('median_ms', 17.0),
                             ('median_ms', 0), ('median_ms', float('nan')),
                             ('over_50ms', True), ('over_50ms', '0'),
                             ('over_50ms', -1), ('over_50ms', 91),
                             ('over_50ms', 0.0)):
            for side in ('current', 'prior'):
                forged = copy.deepcopy(baseline)
                forged['runs'][0]['frame_time'][field] = bogus
                with self.subTest(metric=field, value=bogus, side=side), self.assertRaisesRegex(
                        ValueError, 'HOLD_BASELINE_FRAME_INVALID'):
                    compare_baseline(forged, baseline) if side == 'current' else compare_baseline(
                        baseline, forged)
        healthy = copy.deepcopy(baseline)
        healthy['runs'][0]['frame_time']['median_ms'] = 15.0
        healthy['runs'][0]['frame_time']['over_50ms'] = 2
        self.assertEqual(len(compare_baseline(healthy, baseline)), 6)
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
        synthetic['fixture_html_sha256'] = evidence_hash('<main>fixture-A</main>')
        self.assertEqual(len(compare_baseline(synthetic, synthetic)), 6)
        changed_fixture = copy.deepcopy(synthetic)
        changed_fixture['fixture_html_sha256'] = evidence_hash('<main>fixture-B</main>')
        with self.assertRaisesRegex(ValueError, 'HOLD_BASELINE_FIXTURE_DRIFT'):
            compare_baseline(synthetic, changed_fixture)
        for invalid_hash in (None, '', 'not-digest', 'F' * 64, True):
            invalid_fixture = copy.deepcopy(synthetic)
            invalid_fixture['fixture_html_sha256'] = invalid_hash
            with self.subTest(fixture_hash=invalid_hash), self.assertRaisesRegex(
                    ValueError, 'HOLD_BASELINE_FIXTURE_HASH_MISSING'):
                compare_baseline(invalid_fixture, invalid_fixture)
        missing_fixture = copy.deepcopy(synthetic)
        missing_fixture.pop('fixture_html_sha256')
        with self.assertRaisesRegex(ValueError, 'HOLD_BASELINE_FIXTURE_HASH_MISSING'):
            compare_baseline(missing_fixture, missing_fixture)
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
            fixture_html = (
                    '<html><body><main id="resonance" data-session="SECRET_SELECTOR_XYZ">NOX synthetic local page</main>'
                    '<script>fetch("https://example.invalid/api/nox/chat",'
                    '{method:"POST",body:"x"}).catch(()=>{});'
                    'fetch("https://example.invalid/api/nox/chat/stream?message=unsafe").catch(()=>{});'
                    'fetch("https://example.invalid/api/nox/chat",{method:"HEAD"}).catch(()=>{});'
                    'fetch("https://example.invalid/nox/chat?message=unsafe").catch(()=>{});'
                    'fetch("https://example.invalid/nox%2Fchat/stream",{method:"HEAD"}).catch(()=>{});'
                    'try{const ws=new WebSocket("wss://example.invalid/nox/stream");'
                    'ws.onerror=()=>{};}catch(e){}'
                    '</script></body></html>')
            result = measure(secret_url, str(evidence_dir),
                chromium='/usr/bin/chromium', expected_selector=secret_selector,
                fixture_html=fixture_html)
            self.assertEqual(result['fixture_html_sha256'], evidence_hash(fixture_html))
            self.assertEqual(len(result['runs']), 6)
            self.assertEqual(result['blocked_mutating_requests'], 6)
            self.assertEqual(result['blocked_model_posts'], 6)
            self.assertEqual(result['blocked_model_read_requests'], 24)
            self.assertEqual(result['blocked_websocket_connections'], 6)
            self.assertTrue(result['service_workers_blocked'])
            self.assertEqual(len(result['chromium_version_sha256']), 64)
            self.assertTrue(all(ch in '0123456789abcdef' for ch in result['chromium_version_sha256']))
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
            self.assertNotIn('message=unsafe', report_text)
            self.assertEqual(result['url_sha256'], url_identity_sha256(secret_url))
            self.assertEqual(result['expected_selector_sha256'], evidence_hash(secret_selector))
            self.assertEqual(json.loads(report_text)['schema'],
                'NOX_B3_READONLY_BROWSER_FRAME_EVIDENCE_V6')


    def test_native_bridge_done_terminal_across_later_network_chunk(self):
        """Chromium mock transport: a later NDJSON frame must veto a prior done.

        This exercises bridge source in the real browser engine, without an
        inference request, server owner mutation or an S03 write.
        """
        from playwright.async_api import async_playwright

        async def run():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True, executable_path='/usr/bin/chromium')
                try:
                    page = await browser.new_page()
                    async def local_page(route):
                        await route.fulfill(
                            status=200, content_type='text/html',
                            body='<html><body><main id="resonance">mock</main></body></html>')
                    await page.route('**/nox-web-v29/pc/resonance.html', local_page)
                    await page.goto('http://127.0.0.1:18775/nox-web-v29/pc/resonance.html')
                    await page.evaluate("""() => {
                        window.NOX_NATIVE_OWNER = true;
                        window.__nativeCase = 'valid';
                        window.__nativePosts = 0;
                        window.__historyGets = 0;
                        const id = 'a'.repeat(32), eid = 'ex00001';
                        const pack = value => new Response(JSON.stringify(value), {
                            status:200, headers:{'Content-Type':'application/json'}
                        });
                        window.fetch = async (url,opts) => {
                            if (url === '/api/nox/chat/stream') {
                                window.__nativePosts++;
                                const frames = [
                                    {type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
                                    {type:'start',...(window.__nativeCase==='modelless'?{}:{model:
                                         window.__nativeCase==='labeldrift'?'other-local-mock':
                                         ({unknownlabel:'UNKNOWN', lowerunknown:'unknown',
                                            mixedunknown:'UnKnOwN', navalue:'N/A',
                                            nonemodel:'None', nullmodel:'null',
                                            unsetmodel:'UNSET', unavailmodel:'not available',
                                            nomodel:'no-model'})[window.__nativeCase]||'pinned-local-mock'})},
                                    {type:'delta',text:'world'},
                                    {type:'done',saved:true,s03_integrated:true,
                                     dialog_id:id,exchange_id:(window.__nativeCase === 'keep' ? 'ex00002' : window.__nativeCase === 'keep3' ? 'ex00004' : ['lostfirst','labeldrift'].includes(window.__nativeCase) ? 'ex00005' : ['lost','reordered'].includes(window.__nativeCase) ? 'ex00003' : eid)}
                                ].map(JSON.stringify).join('\\n') + '\\n';
                                const kind = window.__nativeCase;
                                const bytes = new TextEncoder();
                                const stream = new ReadableStream({start(ctrl) {
                                    const encoded = bytes.encode(frames);
                                    if (kind === 'badutf8') encoded[frames.indexOf('world')] = 255;
                                    ctrl.enqueue(encoded);
                                    if (kind === 'late') {
                                        setTimeout(() => {
                                            ctrl.enqueue(bytes.encode(
                                                JSON.stringify({type:'delta',text:'unapproved'})
                                                + '\\n'));
                                            ctrl.close();
                                        }, 15);
                                    } else ctrl.close();
                                }});
                                return new Response(stream, {status:200});
                            }
                            if (String(url).startsWith('/api/ui/memory/dialogs/history?')) {
                                window.__historyGets++;
                                const kind=window.__nativeCase;
                                const currentId=kind === 'keep' ? 'ex00002' :
                                    kind === 'keep3' ? 'ex00004' :
                                    ['lostfirst','labeldrift'].includes(kind) ? 'ex00005' :
                                    (kind === 'lost' || kind === 'reordered') ? 'ex00003' : eid;
                                const priorId=['reordered','badutf8'].includes(kind) ? 'ex00002' : eid;
                                const current=[
                                    {role:'user',content:'hello',exchange_id:currentId},
                                    {role:'assistant',content:kind==='badutf8'?'\ufffdorld':'world',exchange_id:currentId}
                                ];
                                const previous=[
                                    {role:'user',content:'hello',exchange_id:priorId},
                                    {role:'assistant',content:'world',exchange_id:priorId}
                                ];
                                const second=[
                                    {role:'user',content:'hello',exchange_id:'ex00002'},
                                    {role:'assistant',content:'world',exchange_id:'ex00002'}
                                ];
                                const third=[
                                    {role:'user',content:'hello',exchange_id:'ex00004'},
                                    {role:'assistant',content:'world',exchange_id:'ex00004'}
                                ];
                                // 'keep' is a valid second turn retaining the first;
                                // 'lost' is a later turn with its previous pair gone.
                                return pack({status:'READY',dialog_id:id,messages:
                                    kind === 'labeldrift' ? [...previous,...second,...third,...current] :
                                    kind === 'keep3' ? [...previous,...second,...current] :
                                    kind === 'lostfirst' ? [...second,...third,...current] :
                                    ['keep','badutf8'].includes(kind) ? [...previous,...current] :
                                    kind === 'reordered' ? [...current,...previous] : current});
                            }
                            throw Error('UNEXPECTED_TEST_NATIVE_ROUTE');
                        };
                    }""")
                    bridge = (pathlib.Path(__file__).parent /
                              'nox-v135-resonance-owner-bridge.js').read_text('utf8')
                    await page.add_script_tag(content=bridge)
                    self.assertEqual(
                        await page.evaluate("window.__NOX_V135_OWNER_RESONANCE"),
                        'OWNER_NATIVE_ONLY')
                    async def exchange(mode):
                        return await page.evaluate("""async mode => {
                            window.__nativeCase=mode;
                            const r=await fetch('/api/nox/chat',{
                                method:'POST',
                                body:JSON.stringify({request_id:'b3-'+mode,
                                    message:'hello',dialog_id:'a'.repeat(32)})
                            });
                            return {sse:await r.text(),
                                posts:window.__nativePosts,
                                reads:window.__historyGets};
                        }""", mode)
                    good = await exchange('valid')
                    self.assertIn('"type":"done"', good['sse'])
                    self.assertIn('"history_persisted":true', good['sse'])
                    self.assertEqual(good['posts'], 1)
                    self.assertEqual(good['reads'], 1)
                    delayed = await exchange('late')
                    self.assertIn('HOLD_NATIVE_TRAILING_FRAME_AFTER_DONE',
                                  delayed['sse'])
                    self.assertNotIn('"type":"done"', delayed['sse'])
                    self.assertEqual(delayed['posts'], 2)
                    self.assertEqual(delayed['reads'], 1)
                    retained = await exchange('keep')
                    self.assertIn('"type":"done"', retained['sse'])
                    self.assertEqual(retained['posts'], 3)
                    self.assertEqual(retained['reads'], 2)
                    third = await exchange('keep3')
                    self.assertIn('"type":"done"', third['sse'])
                    self.assertEqual(third['posts'], 4)
                    self.assertEqual(third['reads'], 3)
                    missing_ancestor = await exchange('lostfirst')
                    self.assertIn('HOLD_DIALOG_PRIOR_EXCHANGE_LOST', missing_ancestor['sse'])
                    self.assertNotIn('"type":"done"', missing_ancestor['sse'])
                    self.assertEqual(missing_ancestor['posts'], 5)
                    self.assertEqual(missing_ancestor['reads'], 4)
                    reordered = await exchange('reordered')
                    self.assertIn('HOLD_DIALOG_HISTORY_READBACK', reordered['sse'])
                    self.assertNotIn('"type":"done"', reordered['sse'])
                    self.assertEqual(reordered['posts'], 6)
                    self.assertEqual(reordered['reads'], 5)
                    lost = await exchange('lost')
                    self.assertIn('HOLD_DIALOG_PRIOR_EXCHANGE_LOST', lost['sse'])
                    self.assertNotIn('"type":"done"', lost['sse'])
                    self.assertEqual(lost['posts'], 7)
                    self.assertEqual(lost['reads'], 6)
                    corrupted = await exchange('badutf8')
                    self.assertIn('"type":"error"', corrupted['sse'])
                    self.assertNotIn('"type":"done"', corrupted['sse'])
                    self.assertEqual(corrupted['posts'], 8)
                    self.assertEqual(corrupted['reads'], 6)
                    drift = await exchange('labeldrift')
                    self.assertIn('HOLD_DIALOG_MODEL_DRIFT', drift['sse'])
                    self.assertNotIn('"type":"done"', drift['sse'])
                    self.assertEqual(drift['posts'], 9)
                    self.assertEqual(drift['reads'], 7)
                    for idx, mode in enumerate((
                            'modelless', 'unknownlabel', 'lowerunknown',
                            'mixedunknown', 'navalue', 'nonemodel', 'nullmodel',
                            'unsetmodel', 'unavailmodel', 'nomodel'), 10):
                        missing = await exchange(mode)
                        self.assertIn('HOLD_NATIVE_MODEL_START_LABEL', missing['sse'])
                        self.assertNotIn('"type":"done"', missing['sse'])
                        self.assertEqual(missing['posts'], idx)
                        self.assertEqual(missing['reads'], 7)
                finally:
                    await browser.close()
        asyncio.run(run())



    def test_verified_dialog_capacity_never_evicts_witnessed_exchange(self):
        """Actual Chromium with mocked native: 129th dialog must not lose prior proof."""
        from playwright.async_api import async_playwright

        async def run():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True, executable_path='/usr/bin/chromium')
                try:
                    page = await browser.new_page()

                    async def local_page(route):
                        await route.fulfill(status=200, content_type='text/html',
                            body='<html><body><main id="resonance">mock</main></body></html>')

                    await page.route('**/nox-web-v29/pc/resonance.html', local_page)
                    await page.goto('http://127.0.0.1:18775/nox-web-v29/pc/resonance.html')
                    await page.evaluate("""() => {
                        window.NOX_NATIVE_OWNER = true;
                        window.__capNativePosts = 0;
                        const lastMessage = new Map();
                        const pair = (eid, message) => [
                            {role:'user', content:message, exchange_id:eid},
                            {role:'assistant', content:'ready', exchange_id:eid}
                        ];
                        window.fetch = async (url, opts) => {
                            if(url === '/api/nox/chat/stream'){
                                const input = JSON.parse(opts.body);
                                lastMessage.set(input.dialog_id, input.message);
                                window.__capNativePosts++;
                                const eid = input.message === 'again' ? 'cap-two' : 'cap-one';
                                const frames = [
                                    {type:'preparing', stream_mode:'NATIVE_TOKEN_STREAM'},
                                    {type:'start', model:'pinned-local-mock'},
                                    {type:'delta', text:'ready'},
                                    {type:'done', saved:true, s03_integrated:true,
                                     dialog_id:input.dialog_id, exchange_id:eid}
                                ].map(JSON.stringify).join('\\n') + '\\n';
                                return new Response(frames, {status:200});
                            }
                            if(String(url).startsWith('/api/ui/memory/dialogs/history?')){
                                const id = new URL(url, location.href).searchParams.get('dialog_id');
                                const again = lastMessage.get(id) === 'again';
                                const messages = [
                                    ...pair('cap-one', 'hello'),
                                    ...(again ? pair('cap-two', 'again') : [])
                                ];
                                return new Response(JSON.stringify({
                                    status:'READY', dialog_id:id, messages
                                }), {status:200, headers:{'Content-Type':'application/json'}});
                            }
                            throw Error('UNEXPECTED_TEST_ROUTE');
                        };
                    }""")
                    bridge = (pathlib.Path(__file__).parent /
                              'nox-v135-resonance-owner-bridge.js').read_text('utf8')
                    await page.add_script_tag(content=bridge)
                    verdict = await page.evaluate("""async () => {
                        const ask = async (i, message='hello') => {
                            const dialog_id = i.toString(16).padStart(32, '0');
                            const r = await fetch('/api/nox/chat', {
                                method:'POST',
                                body:JSON.stringify({
                                    request_id:'cap-'+i+'-'+message, message, dialog_id
                                })
                            });
                            return await r.text();
                        };
                        let bad = null;
                        for(let i=0;i<128;i++){
                            const s=await ask(i);
                            if(!s.includes('"type":"done"')){bad={i,s};break;}
                        }
                        const before = window.__capNativePosts;
                        const denied = await ask(128);
                        const after = window.__capNativePosts;
                        const revisited = await ask(0, 'again');
                        return {bad, before, denied, after, revisited,
                                total:window.__capNativePosts};
                    }""")
                    self.assertIsNone(verdict['bad'])
                    self.assertEqual(verdict['before'], 128)
                    self.assertIn('HOLD_DIALOG_PIN_CAPACITY', verdict['denied'])
                    self.assertNotIn('"type":"done"', verdict['denied'])
                    self.assertEqual(verdict['after'], 128)
                    self.assertIn('"type":"done"', verdict['revisited'])
                    self.assertEqual(verdict['total'], 129)
                finally:
                    await browser.close()

        asyncio.run(run())

    def test_same_dialog_foreign_interleave_fails_before_accepted_done(self):
        """Real Chromium / synthetic native: third turn must reject alien S03 pair."""
        from playwright.async_api import async_playwright

        async def run():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True, executable_path='/usr/bin/chromium')
                try:
                    page = await browser.new_page()
                    async def local_page(route):
                        await route.fulfill(
                            status=200, content_type='text/html',
                            body='<html><main id="resonance">mock</main></html>')
                    await page.route('**/nox-web-v29/pc/resonance.html', local_page)
                    await page.goto('http://127.0.0.1:18775/nox-web-v29/pc/resonance.html')
                    await page.evaluate("""() => {
                        window.NOX_NATIVE_OWNER=true;
                        window.__posts=0;
                        window.__reads=0;
                        const did='a'.repeat(32);
                        const rows=[
                            ['one','answer1','ex00001'],
                            ['two','answer2','ex00002'],
                            ['three','answer3','ex00003']];
                        window.fetch=async url=>{
                            if(url==='/api/nox/chat/stream'){
                                const row=rows[window.__posts++];
                                const frames=[
                                    {type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
                                    {type:'start',model:'mock-pinned'},
                                    {type:'delta',text:row[1]},
                                    {type:'done',saved:true,s03_integrated:true,
                                     dialog_id:did,exchange_id:row[2]}];
                                return new Response(
                                    frames.map(JSON.stringify).join('\\n')+'\\n',
                                    {status:200});
                            }
                            if(String(url).startsWith('/api/ui/memory/dialogs/history?')){
                                window.__reads++;
                                const messages=rows.slice(0,window.__posts)
                                    .flatMap(row=>[
                                        {role:'user',content:row[0],exchange_id:row[2]},
                                        {role:'assistant',content:row[1],exchange_id:row[2]}]);
                                if(window.__posts===3)
                                    messages.splice(4,0,
                                        {role:'user',content:'alien',exchange_id:'foreign'},
                                        {role:'assistant',content:'reply',exchange_id:'foreign'});
                                return new Response(JSON.stringify({
                                    status:'READY',dialog_id:did,messages
                                }),{status:200});
                            }
                            throw Error('UNEXPECTED_NATIVE_ROUTE');
                        };
                    }""")
                    bridge=(pathlib.Path(__file__).parent /
                            'nox-v135-resonance-owner-bridge.js').read_text('utf8')
                    await page.add_script_tag(content=bridge)
                    outcome=await page.evaluate("""async () => {
                        const results=[];
                        for(const message of ['one','two','three']){
                            const response=await fetch('/api/nox/chat',{
                                method:'POST',
                                body:JSON.stringify({dialog_id:'a'.repeat(32),
                                    request_id:'b3-interleave-'+message,message})
                            });
                            const events=(await response.text()).split('\\n\\n')
                                .filter(Boolean).map(s=>JSON.parse(s.slice(6)));
                            results.push({
                                done:events.filter(x=>x.type==='done'),
                                error:events.filter(x=>x.type==='error')
                            });
                        }
                        return {results,posts:window.__posts,reads:window.__reads};
                    }""")
                    self.assertEqual(outcome['posts'],3)
                    self.assertEqual(outcome['reads'],3)
                    self.assertEqual([len(x['done']) for x in outcome['results']],
                                     [1,1,0])
                    self.assertEqual([len(x['error']) for x in outcome['results']],
                                     [0,0,1])
                    self.assertIn('HOLD_DIALOG_PRIOR_EXCHANGE_LOST',
                                  outcome['results'][2]['error'][0]['error'])
                finally:
                    await browser.close()

        asyncio.run(run())


    def test_same_dialog_overlapping_browser_stream_has_single_native_post(self):
        """One in-flight browser turn per dialog, including release after done."""
        from playwright.async_api import async_playwright

        async def run():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True, executable_path='/usr/bin/chromium')
                try:
                    page = await browser.new_page()
                    async def local_page(route):
                        await route.fulfill(
                            status=200, content_type='text/html',
                            body='<html><body><main>isolated mock</main></body></html>')
                    await page.route('**/nox-web-v29/pc/resonance.html', local_page)
                    await page.goto('http://127.0.0.1:18775/nox-web-v29/pc/resonance.html')
                    await page.evaluate("""() => {
                        window.NOX_NATIVE_OWNER=true;
                        window.__nativePosts=0;
                        window.__phases=[];
                        window.addEventListener('nox:native-phase',
                            e=>window.__phases.push(e.detail.phase));
                        window.__releaseFirst=null;
                        const did='a'.repeat(32);
                        const response=value=>new Response(JSON.stringify(value),
                            {status:200,headers:{'Content-Type':'application/json'}});
                        window.fetch=async url=>{
                            if(url==='/api/nox/chat/stream'){
                                const n=++window.__nativePosts;
                                if(n===1)await new Promise(resolve=>window.__releaseFirst=resolve);
                                if(n===3)await new Promise(resolve=>window.__releaseAbort=resolve);
                                const frames=[
                                    {type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
                                    {type:'start',model:'mock'},
                                    {type:'delta',text:n===1?'answer1':'answer2'},
                                    {type:'done',saved:true,s03_integrated:true,
                                     dialog_id:did,exchange_id:n===1?'ex00001':'ex00002'}
                                ].map(JSON.stringify).join('\\n')+'\\n';
                                return new Response(frames,{status:200});
                            }
                            if(String(url).startsWith('/api/ui/memory/dialogs/history?')){
                                const a=[
                                    {role:'user',content:'hello',exchange_id:'ex00001'},
                                    {role:'assistant',content:'answer1',exchange_id:'ex00001'}
                                ];
                                const b=[
                                    {role:'user',content:'hello',exchange_id:'ex00002'},
                                    {role:'assistant',content:'answer2',exchange_id:'ex00002'}
                                ];
                                return response({status:'READY',dialog_id:did,
                                    messages:window.__nativePosts===1?a:[...a,...b]});
                            }
                            throw Error('UNEXPECTED_NATIVE_ROUTE');
                        };
                    }""")
                    bridge=(pathlib.Path(__file__).parent /
                            'nox-v135-resonance-owner-bridge.js').read_text('utf8')
                    await page.add_script_tag(content=bridge)
                    # Malformed request identity must be rejected BEFORE any
                    # native dialog create or model POST, not downgraded to JSON.
                    malformed = await page.evaluate("""async () => {
                        const results=[];
                        for(const request_id of [null,17,'','   ']){
                            const r=await fetch('/api/nox/chat',{
                                method:'POST',
                                body:JSON.stringify({message:'hello',request_id})
                            });
                            results.push({status:r.status,body:await r.text()});
                        }
                        return {results,posts:window.__nativePosts};
                    }""")
                    self.assertEqual(malformed['posts'], 0)
                    self.assertEqual(len(malformed['results']), 4)
                    for case in malformed['results']:
                        self.assertEqual(case['status'], 422)
                        self.assertIn('HOLD_REQUEST_ID_SCOPE', case['body'])
                    actual=await page.evaluate("""async () => {
                        const body=JSON.stringify({
                            dialog_id:'a'.repeat(32),message:'hello',request_id:'b3-test'});
                        const first=fetch('/api/nox/chat',{method:'POST',body});
                        for(let n=0;n<100 && !window.__releaseFirst;n++)
                            await new Promise(resolve=>setTimeout(resolve,3));
                        if(!window.__releaseFirst)return {error:'FIRST_NATIVE_NOT_STARTED'};
                        const second=await fetch('/api/nox/chat',{method:'POST',body});
                        const rejected=await second.text();
                        const atOverlap=window.__nativePosts;
                        window.__releaseFirst();
                        const completed=await (await first).text();
                        const replay=await (await fetch('/api/nox/chat',
                            {method:'POST',body})).text();
                        const atReplay=window.__nativePosts;
                        const nextBody=JSON.stringify({dialog_id:'a'.repeat(32),
                            message:'hello',request_id:'b3-next'});
                        const third=await (await fetch('/api/nox/chat',
                            {method:'POST',body:nextBody})).text();
                        const abortBody=JSON.stringify({dialog_id:'a'.repeat(32),
                            message:'hello',request_id:'b3-stop'});
                        const ac=new AbortController();
                        const stop=fetch('/api/nox/chat',
                            {method:'POST',body:abortBody,signal:ac.signal});
                        for(let n=0;n<100&&!window.__releaseAbort;n++)
                            await new Promise(resolve=>setTimeout(resolve,3));
                        if(!window.__releaseAbort)
                            return {error:'ABORT_NATIVE_NOT_STARTED'};
                        ac.abort();
                        const stopped=await (await stop).text();
                        const stopPhase=window.__phases.at(-1);
                        const afterStop=await (await fetch('/api/nox/chat',
                            {method:'POST',body:abortBody})).text();
                        const atStopReplay=window.__nativePosts;
                        window.__releaseAbort();
                        return {atOverlap,rejected,completed,replay,atReplay,third,
                            stopped,stopPhase,afterStop,atStopReplay,posts:window.__nativePosts};
                    }""")
                    self.assertNotIn('error', actual)
                    self.assertEqual(actual['atOverlap'], 1)
                    self.assertIn('HOLD_REQUEST_REPLAY', actual['rejected'])
                    self.assertNotIn('"type":"done"', actual['rejected'])
                    self.assertIn('"type":"done"', actual['completed'])
                    self.assertIn('HOLD_REQUEST_REPLAY', actual['replay'])
                    self.assertNotIn('"type":"done"', actual['replay'])
                    self.assertEqual(actual['atReplay'], 1)
                    self.assertIn('"type":"done"', actual['third'])
                    self.assertIn('STREAM_STOP_REQUESTED', actual['stopped'])
                    self.assertEqual(actual['stopPhase'], 'stopped')
                    self.assertNotIn('"type":"done"', actual['stopped'])
                    self.assertIn('HOLD_REQUEST_REPLAY', actual['afterStop'])
                    self.assertEqual(actual['atStopReplay'], 3)
                    self.assertEqual(actual['posts'], 3)
                finally:
                    await browser.close()
        asyncio.run(run())




    def test_new_dialog_request_id_replay_fenced_before_native_create(self):
        """One request_id cannot create a second dialog or invoke a second model."""
        from playwright.async_api import async_playwright

        async def run():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True, executable_path='/usr/bin/chromium')
                try:
                    page = await browser.new_page()
                    async def local_page(route):
                        await route.fulfill(status=200, content_type='text/html',
                                            body='<html><body>mock B3 replay</body></html>')
                    await page.route('**/nox-web-v29/pc/resonance.html', local_page)
                    await page.goto('http://127.0.0.1:18775/nox-web-v29/pc/resonance.html')
                    await page.evaluate("""() => {
                        window.NOX_NATIVE_OWNER=true;
                        window.__created=0;
                        window.__modelPosts=0;
                        const response=value=>new Response(JSON.stringify(value),
                            {status:200,headers:{'Content-Type':'application/json'}});
                        window.fetch=async (url,init={})=>{
                            if(url==='/api/ui/memory/dialogs/create'){
                                const n=++window.__created;
                                return response({dialog_id:'a'.repeat(31)+n,title:'new'});
                            }
                            if(url==='/api/nox/chat/stream'){
                                window.__modelPosts++;
                                const data=JSON.parse(init.body);
                                const n=data.dialog_id.slice(-1);
                                const frames=[
                                    {type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
                                    {type:'start',model:'existing-mock-native'},
                                    {type:'delta',text:'answer'+n},
                                    {type:'done',saved:true,s03_integrated:true,
                                     dialog_id:data.dialog_id,exchange_id:'ex-new-'+n}
                                ].map(JSON.stringify).join('\\n')+'\\n';
                                return new Response(frames,{status:200});
                            }
                            if(String(url).startsWith('/api/ui/memory/dialogs/history?')){
                                const id=new URL(url,location.href).searchParams.get('dialog_id');
                                const n=id.slice(-1);
                                return response({status:'READY',dialog_id:id,messages:[
                                    {role:'user',content:'hello',exchange_id:'ex-new-'+n},
                                    {role:'assistant',content:'answer'+n,
                                     exchange_id:'ex-new-'+n}
                                ]});
                            }
                            throw Error('UNEXPECTED_MOCK_ENDPOINT '+url);
                        };
                    }""")
                    bridge=(pathlib.Path(__file__).parent /
                            'nox-v135-resonance-owner-bridge.js').read_text('utf8')
                    await page.add_script_tag(content=bridge)
                    actual=await page.evaluate("""async () => {
                        const send=async request_id=>{
                            const r=await fetch('/api/nox/chat',{method:'POST',
                                body:JSON.stringify({message:'hello',request_id})});
                            return await r.text();
                        };
                        const first=await send('global-new-id');
                        const replay=await send('global-new-id');
                        const fresh=await send('global-fresh-id');
                        return {first,replay,fresh,creates:window.__created,
                            posts:window.__modelPosts};
                    }""")
                    self.assertIn('"type":"done"', actual['first'])
                    self.assertIn('HOLD_REQUEST_REPLAY', actual['replay'])
                    self.assertNotIn('"type":"done"', actual['replay'])
                    self.assertIn('"type":"done"', actual['fresh'])
                    self.assertEqual(actual['creates'], 2)
                    self.assertEqual(actual['posts'], 2)
                finally:
                    await browser.close()
        asyncio.run(run())


    def test_native_endpoints_reject_http_redirect_before_fallback_browser(self):
        """Native chat POST and memory GET must not follow browser redirects."""
        from playwright.async_api import async_playwright

        async def run():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True, executable_path='/usr/bin/chromium')
                try:
                    page = await browser.new_page()
                    fallbacks = []

                    async def local_page(route):
                        await route.fulfill(
                            status=200, content_type='text/html',
                            body='<html><body>isolated redirect test</body></html>')

                    async def stream_redirect(route):
                        await route.fulfill(status=307, headers={
                            'Location': '/api/nox/chat/stream/unsafe-fallback'})

                    async def history_redirect(route):
                        await route.fulfill(status=302, headers={
                            'Location': '/api/ui/memory/history-unsafe-fallback'})

                    async def forbidden_fallback(route):
                        fallbacks.append(route.request.url)
                        await route.fulfill(
                            status=200, content_type='application/json',
                            body='{"status":"READY","messages":[]}')

                    await page.route('**/nox-web-v29/pc/resonance.html', local_page)
                    await page.route('**/api/nox/chat/stream', stream_redirect)
                    await page.route(
                        '**/api/ui/memory/dialogs/history?*', history_redirect)
                    await page.route(
                        '**/api/nox/chat/stream/unsafe-fallback',
                        forbidden_fallback)
                    await page.route(
                        '**/api/ui/memory/history-unsafe-fallback',
                        forbidden_fallback)
                    await page.goto(
                        'http://127.0.0.1:18775/nox-web-v29/pc/resonance.html')
                    await page.evaluate('window.NOX_NATIVE_OWNER=true')
                    bridge = (pathlib.Path(__file__).parent /
                              'nox-v135-resonance-owner-bridge.js').read_text('utf8')
                    await page.add_script_tag(content=bridge)
                    result = await page.evaluate("""async () => {
                        const did='a'.repeat(32);
                        const chat=await fetch('/api/nox/chat',{
                            method:'POST',
                            body:JSON.stringify({
                                dialog_id:did,
                                request_id:'b3-native-redirect-case',
                                message:'hello'
                            })
                        });
                        const chatBody=await chat.text();
                        const history=await fetch(
                            '/api/nox/history?dialog_id='+did);
                        return {
                            chatStatus:chat.status,
                            chatBody,
                            historyStatus:history.status,
                            historyBody:await history.text()
                        };
                    }""")
                    self.assertEqual(result['chatStatus'], 200)
                    self.assertIn('"type":"error"', result['chatBody'])
                    self.assertNotIn('"type":"done"', result['chatBody'])
                    self.assertEqual(result['historyStatus'], 503)
                    self.assertIn('HOLD', result['historyBody'])
                    self.assertEqual(fallbacks, [])
                finally:
                    await browser.close()
        asyncio.run(run())



    def test_owner_route_alias_does_not_escape_browser_guard(self):
        """Real Chromium: encoded/cased/query chat aliases must not bypass owner."""
        from playwright.async_api import async_playwright

        async def run():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True, executable_path='/usr/bin/chromium')
                try:
                    page = await browser.new_page()

                    async def local_page(route):
                        await route.fulfill(status=200, content_type='text/html',
                                            body='<html><body>owner-route fixture</body></html>')

                    await page.route('**/nox-web-v29/pc/resonance.html', local_page)
                    await page.goto(
                        'http://127.0.0.1:18775/nox-web-v29/pc/resonance.html')
                    await page.evaluate("""() => {
                        window.NOX_NATIVE_OWNER=true;
                        window.__nativeDirect=[];
                        window.fetch=async (path, opts) => {
                            window.__nativeDirect.push(String(path));
                            return new Response(JSON.stringify({
                                status:'READY',dialog_id:'a'.repeat(32),
                                messages:[]
                            }),{status:200,headers:{
                                'Content-Type':'application/json'}});
                        };
                    }""")
                    bridge = (pathlib.Path(__file__).parent /
                              'nox-v135-resonance-owner-bridge.js').read_text('utf8')
                    await page.add_script_tag(content=bridge)
                    result = await page.evaluate("""async () => {
                        const id='a'.repeat(32);
                        const cases=[
                            ['/API/NOX/CHAT',{method:'POST'}],
                            ['/%61pi/nox/chat',{method:'POST'}],
                            ['/api/nox/%63hat',{method:'POST'}],
                            ['/api/nox/chat?wrong=1',{method:'POST'}],
                            ['/api/nox/chat',{method:'GET'}],
                            ['/api/nox/chat/',{method:'POST'}],
                            ['/api/nox/chat/stream/',{method:'POST'}],
                            ['/api/nox/chat/stream//',{method:'GET'}],
                            ['/api/nox/chat/experimental',{method:'GET'}],
                            ['/api/nox/chat/stream',{method:'POST'}],
                            ['/api/nox/chat/stream?bypass=1',{method:'GET'}],
                            ['/%61pi/nox/chat/stream',{method:'POST'}],
                            ['/%61pi/nox/history?dialog_id='+id,{method:'GET'}],
                            // Canonical legacy owner endpoints must not leak
                            // unsupported methods into the native fetch.
                            ['/api/nox/history?dialog_id='+id,{method:'POST'}],
                            ['/api/nox/dialogs/new',{method:'GET'}],
                            ['/api/nox/dialog/rename',{method:'GET'}],
                        ];
                        const statuses=[];
                        for(const [path, opts] of cases) {
                            const r=await fetch(path, opts);
                            const data=await r.json();
                            statuses.push([r.status,data.error]);
                        }
                        const before=window.__nativeDirect.slice();
                        const allowed=await fetch(
                            '/api/nox/history?dialog_id='+id);
                        // An explicit empty RequestInit body overrides the
                        // original Request payload; it must NOT reach native.
                        const oldRequest=new Request(location.origin+'/api/nox/chat',{
                            method:'POST',body:JSON.stringify({
                                message:'old-should-not-send',
                                request_id:'b3-empty-body-override',
                                dialog_id:id
                            })
                        });
                        const invalid=await fetch(oldRequest,{body:''});
                        const invalidData=await invalid.json();
                        // A Request's original signal survives explicit init.body.
                        // Aborting it must prevent even one native model POST.
                        const aborter=new AbortController();
                        const signalRequest=new Request(location.origin+'/api/nox/chat',{
                            method:'POST',signal:aborter.signal,body:JSON.stringify({
                                message:'old-model-prompt',
                                request_id:'b3-signal-old',
                                dialog_id:id
                            })
                        });
                        aborter.abort();
                        const stopped=await fetch(signalRequest,{body:JSON.stringify({
                            message:'new-model-prompt',
                            request_id:'b3-signal-new',
                            dialog_id:id
                        })});
                        const stoppedFrame=await stopped.text();
                        const jsonAborter=new AbortController();
                        const jsonRequest=new Request(location.origin+'/api/nox/chat',{
                            method:'POST',signal:jsonAborter.signal,
                            body:JSON.stringify({message:'old-json-prompt'})
                        });
                        jsonAborter.abort();
                        const stoppedJSON=await fetch(jsonRequest,{body:JSON.stringify({
                            message:'new-json-prompt'
                        })});
                        const stoppedJSONData=await stoppedJSON.json();
                        return {statuses,before,
                            allowedStatus:allowed.status,
                            emptyBodyStatus:invalid.status,
                            emptyBodyError:invalidData.error,
                            stoppedFrame,stoppedJSONStatus:stoppedJSON.status,
                            stoppedJSONError:stoppedJSONData.error,
                            direct:window.__nativeDirect.slice()};
                    }""")
                    self.assertEqual(result['statuses'],
                        [[422,'HOLD_OWNER_ROUTE_ALIAS']] * 16)
                    self.assertEqual(result['before'], [])
                    self.assertEqual(result['allowedStatus'], 200)
                    self.assertEqual(result['emptyBodyStatus'], 400)
                    self.assertEqual(result['emptyBodyError'], 'INVALID_JSON')
                    self.assertIn('"error":"STREAM_STOP_REQUESTED"', result['stoppedFrame'])
                    self.assertNotIn('"type":"done"', result['stoppedFrame'])
                    self.assertEqual(result['stoppedJSONStatus'], 503)
                    self.assertEqual(result['stoppedJSONError'], 'STREAM_STOP_REQUESTED')
                    self.assertEqual(len(result['direct']), 1)
                    self.assertIn('/api/ui/memory/dialogs/history?',
                                  result['direct'][0])
                finally:
                    await browser.close()
        asyncio.run(run())


    def test_native_delta_forwarded_without_synthetic_raf_pacing(self):
        """Chromium: one native delta remains one SSE token without timer/rAF waits."""
        from playwright.async_api import async_playwright

        async def run():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True, executable_path='/usr/bin/chromium')
                try:
                    page = await browser.new_page()

                    async def fixture(route):
                        await route.fulfill(
                            status=200, content_type='text/html',
                            body='<html><body>isolated B3 native-delta fixture</body></html>')
                    await page.route('**/nox-web-v29/pc/resonance.html', fixture)
                    await page.goto(
                        'http://127.0.0.1:18775/nox-web-v29/pc/resonance.html')
                    await page.evaluate("""() => {
                        window.NOX_NATIVE_OWNER=true;
                        window.__posts=0;
                        window.__reads=0;
                        window.__rafCalls=0;
                        window.requestAnimationFrame=()=>{
                            window.__rafCalls++;
                            return 1; // A hidden or throttled-tab rAF never fires.
                        };
                        const id='a'.repeat(32);
                        window.__answer='Ж'.repeat(512)+'🧠';
                        const pack=value=>new Response(JSON.stringify(value),{
                            status:200,headers:{'Content-Type':'application/json'}
                        });
                        window.fetch=async (url)=>{
                            if(url==='/api/nox/chat/stream'){
                                window.__posts++;
                                const text=[
                                    {type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
                                    {type:'start',model:'existing-native-fixture'},
                                    {type:'delta',text:window.__answer},
                                    {type:'done',saved:true,s03_integrated:true,
                                        dialog_id:id,exchange_id:'ex-b3-raf'}
                                ].map(JSON.stringify).join('\\n')+'\\n';
                                return new Response(text,{status:200});
                            }
                            if(String(url).startsWith(
                                    '/api/ui/memory/dialogs/history?')){
                                window.__reads++;
                                return pack({status:'READY',dialog_id:id,messages:[
                                    {role:'user',content:'native',exchange_id:'ex-b3-raf'},
                                    {role:'assistant',content:window.__answer,
                                        exchange_id:'ex-b3-raf'}
                                ]});
                            }
                            throw Error('UNEXPECTED_NATIVE_ROUTE:'+url);
                        };
                    }""")
                    bridge = (pathlib.Path(__file__).parent /
                              'nox-v135-resonance-owner-bridge.js').read_text('utf8')
                    await page.add_script_tag(content=bridge)
                    result = await page.evaluate("""async () => {
                        const start=performance.now();
                        const response=await fetch('/api/nox/chat',{
                            method:'POST',
                            body:JSON.stringify({dialog_id:'a'.repeat(32),
                                request_id:'b3-single-native-delta',
                                message:'native'})
                        });
                        const sse=await response.text();
                        const events=sse.split('\\n\\n').filter(Boolean).map(
                            row=>JSON.parse(row.replace(/^data: /,'')));
                        return {
                            posts:window.__posts,
                            reads:window.__reads,
                            rafCalls:window.__rafCalls,
                            elapsedMs:performance.now()-start,
                            tokens:events.filter(e=>e.type==='token').map(e=>e.t),
                            done:events.filter(e=>e.type==='done'),
                            errors:events.filter(e=>e.type==='error'),
                            answer:window.__answer
                        };
                    }""")
                    self.assertEqual(result['posts'], 1)
                    self.assertEqual(result['reads'], 1)
                    self.assertEqual(result['rafCalls'], 0)
                    self.assertEqual(''.join(result['tokens']), result['answer'])
                    self.assertLessEqual(len(result['tokens']), 2)
                    self.assertEqual(len(result['done']), 1)
                    self.assertEqual(result['done'][0]['s03_integrated'], True)
                    self.assertEqual(result['errors'], [])
                    # Elapsed time is recorded as synthetic browser evidence;
                    # never claim this measures live production frame time.
                    self.assertGreaterEqual(result['elapsedMs'], 0)
                finally:
                    await browser.close()
        asyncio.run(run())



    def test_native_large_unicode_grapheme_stream_no_glyph_array(self):
        """Headless Chromium: large split clusters preserve bytes without Array.from."""
        from playwright.async_api import async_playwright

        async def run():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True, executable_path='/usr/bin/chromium')
                try:
                    page = await browser.new_page()

                    async def fixture(route):
                        await route.fulfill(
                            status=200, content_type='text/html',
                            body='<html><body>isolated B3 grapheme fixture</body></html>')
                    await page.route('**/nox-web-v29/pc/resonance.html', fixture)
                    await page.goto(
                        'http://127.0.0.1:18775/nox-web-v29/pc/resonance.html')
                    await page.evaluate("""() => {
                        window.NOX_NATIVE_OWNER=true;
                        window.__posts=0;
                        window.__reads=0;
                        window.__answer='Ж'.repeat(4096)+'👩‍💻e\u0301';
                        window.__answer2='🇪🇸'.repeat(128)+'👨‍👩‍👧‍👦e\u0301';
                        window.__longCluster=Array.from({length:9},()=>'\u0301'.repeat(1024));
                        const id='a'.repeat(32);
                        const parts=['Ж'.repeat(4096)+'👩','‍','💻e','\u0301'];
                        const parts2=['🇪🇸'.repeat(128)+'👨','‍','👩‍👧‍👦e','\u0301'];
                        const pack=data=>new Response(JSON.stringify(data),{
                            status:200,headers:{'Content-Type':'application/json'}
                        });
                        window.fetch=async url=>{
                            if(url==='/api/nox/chat/stream'){
                                const n=++window.__posts;
                                const frames=[
                                    {type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
                                    {type:'start',model:'pinned-existing-native-fixture'},
                                    ...(n===1?parts:n===2?parts2:window.__longCluster)
                                        .map(text=>({type:'delta',text})),
                                    {type:'done',saved:true,s03_integrated:true,
                                        dialog_id:id,exchange_id:'ex-b3-grapheme-'+n}
                                ];
                                return new Response(frames.map(JSON.stringify).join('\\n')+'\\n',{
                                    status:200});
                            }
                            if(String(url).startsWith('/api/ui/memory/dialogs/history?')){
                                window.__reads++;
                                return pack({status:'READY',dialog_id:id,messages:[
                                    {role:'user',content:'unicode',exchange_id:'ex-b3-grapheme-1'},
                                    {role:'assistant',content:window.__answer,
                                        exchange_id:'ex-b3-grapheme-1'},
                                    ...(window.__posts===2?[
                                      {role:'user',content:'unicode2',exchange_id:'ex-b3-grapheme-2'},
                                      {role:'assistant',content:window.__answer2,
                                          exchange_id:'ex-b3-grapheme-2'}]:[])
                                ]});
                            }
                            throw Error('UNEXPECTED_NATIVE_ROUTE:'+url);
                        };
                    }""")
                    bridge = (pathlib.Path(__file__).parent /
                              'nox-v135-resonance-owner-bridge.js').read_text('utf8')
                    await page.add_script_tag(content=bridge)
                    result = await page.evaluate("""async () => {
                        // A full grapheme iterator walk on every delta is forbidden.
                        Array.from=()=>{throw Error('HOLD_GLYPH_ARRAY_MATERIALIZATION');};
                        const segProto=Object.getPrototypeOf(new Intl.Segmenter().segment('Ж'));
                        segProto[Symbol.iterator]=()=>{throw Error('HOLD_SEGMENTER_FULL_WALK');};
                        const send=async (request_id,message)=>{
                            const response=await fetch('/api/nox/chat',{
                                method:'POST',body:JSON.stringify({
                                    dialog_id:'a'.repeat(32),request_id,message
                                })
                            });
                            const raw=await response.text();
                            const events=raw.split('\\n\\n').filter(Boolean)
                              .map(row=>JSON.parse(row.replace(/^data: /,'')));
                            return {
                                text:events.filter(e=>e.type==='token').map(e=>e.t).join(''),
                                done:events.filter(e=>e.type==='done'),
                                errors:events.filter(e=>e.type==='error')
                            };
                        };
                        const first=await send('b3-grapheme-large-first','unicode');
                        const second=await send('b3-grapheme-large-second','unicode2');
                        const third=await send('b3-grapheme-run-hold','unicode3');
                        return {posts:window.__posts,reads:window.__reads,
                            first,second,third,answer:window.__answer,answer2:window.__answer2};
                    }""")
                    self.assertEqual(result['posts'], 3)
                    self.assertEqual(result['reads'], 2)
                    for k,answer in (('first','answer'),('second','answer2')):
                        self.assertEqual(result[k]['text'], result[answer])
                        self.assertEqual(len(result[k]['done']), 1)
                        self.assertTrue(result[k]['done'][0]['s03_integrated'])
                        self.assertEqual(result[k]['errors'], [])
                    self.assertEqual(result['third']['done'], [])
                    self.assertEqual(len(result['third']['errors']), 1)
                    self.assertIn('HOLD_GRAPHEME_RUN',result['third']['errors'][0]['error'])
                finally:
                    await browser.close()
        asyncio.run(run())



    def test_native_start_done_model_label_consistency_fails_closed(self):
        """Chromium mocked-native stream: start/done serving label drift cannot emit done."""
        from playwright.async_api import async_playwright

        async def run():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True, executable_path='/usr/bin/chromium')
                try:
                    page = await browser.new_page()

                    async def fixture(route):
                        await route.fulfill(
                            status=200, content_type='text/html',
                            body='<html><body>B3 serving label fixture</body></html>')
                    await page.route('**/nox-web-v29/pc/resonance.html', fixture)
                    await page.goto(
                        'http://127.0.0.1:18775/nox-web-v29/pc/resonance.html')
                    await page.evaluate("""() => {
                        window.NOX_NATIVE_OWNER=true;
                        window.__posts=0;window.__reads=0;
                        const history=Object.create(null);
                        const pack=data=>new Response(JSON.stringify(data),{
                            status:200,headers:{'Content-Type':'application/json'}
                        });
                        window.fetch=async (url,init)=>{
                            if(url==='/api/nox/chat/stream'){
                                window.__posts++;
                                const data=JSON.parse(init.body);
                                const mode=data.message;
                                const answer='answer:'+mode;
                                const exchange='ex-model-'+mode;
                                history[data.dialog_id]={mode,answer,exchange};
                                const done={type:'done',saved:true,s03_integrated:true,
                                    dialog_id:data.dialog_id,exchange_id:exchange};
                                if(mode==='mismatch')done.model='other-model';
                                if(mode==='match')done.model='existing-model';
                                if(mode==='malformed')done.model=42;
                                const frames=[
                                    {type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
                                    {type:'start',model:'existing-model'},
                                    {type:'delta',text:answer},
                                    done
                                ];
                                if(mode==='paddedstart')frames[1].model=' existing-model ';
                                if(mode==='longstart')frames[1].model='x'.repeat(97);
                                if(mode==='controlstart')frames[1].model='existing-\\nmodel';
                                if(mode==='blankstart')frames[1].model='  ';
                                if(mode==='bidistart')frames[1].model='existing-\\u202e-model';
                                if(mode==='zerostart')frames[1].model='existing-\\u200b-model';
                                 if(mode==='softstart')frames[1].model='existing-\\u00ad-model';
                                 if(mode==='joinstart')frames[1].model='existing-\\u2060-model';
                                 if(mode==='graphemestart')frames[1].model='existing-\\u034f-model';
                                return new Response(frames.map(JSON.stringify).join('\\n')+'\\n',{
                                    status:200
                                });
                            }
                            if(String(url).startsWith('/api/ui/memory/dialogs/history?')){
                                window.__reads++;
                                const id=new URL(url,'http://localhost')
                                    .searchParams.get('dialog_id');
                                const row=history[id];
                                if(!row)throw Error('NO_HISTORY_FOR:'+id);
                                return pack({status:'READY',dialog_id:id,messages:[
                                    {role:'user',content:row.mode,
                                        exchange_id:row.exchange},
                                    {role:'assistant',content:row.answer,
                                        exchange_id:row.exchange}
                                ]});
                            }
                            throw Error('UNEXPECTED_NATIVE_ROUTE:'+url);
                        };
                    }""")
                    bridge = (pathlib.Path(__file__).parent /
                              'nox-v135-resonance-owner-bridge.js').read_text('utf8')
                    await page.add_script_tag(content=bridge)
                    result = await page.evaluate("""async () => {
                        const rows=[];
                        for(const [i,mode] of
                            ['mismatch','match','absent','malformed','paddedstart',
                             'longstart','controlstart','blankstart','bidistart','zerostart',
                              'softstart','joinstart','graphemestart'].entries()){
                            const postsBefore=window.__posts;
                            const readsBefore=window.__reads;
                            const id=i.toString(16).repeat(32);
                            const response=await fetch('/api/nox/chat',{
                                method:'POST',body:JSON.stringify({
                                    dialog_id:id,request_id:'b3-model-'+mode,
                                    message:mode
                                })
                            });
                            const raw=await response.text();
                            const events=raw.split('\\n\\n').filter(Boolean)
                              .map(row=>JSON.parse(row.replace(/^data: /,'')));
                            rows.push({
                                mode,posts:window.__posts-postsBefore,
                                reads:window.__reads-readsBefore,
                                done:events.filter(e=>e.type==='done'),
                                errors:events.filter(e=>e.type==='error'),
                                tokens:events.filter(e=>e.type==='token')
                                    .map(e=>e.t).join('')
                            });
                        }
                        return rows;
                    }""")
                    self.assertEqual(len(result), 13)
                    for row in result:
                        self.assertEqual(row['posts'], 1)
                        # A terminal HOLD can withhold its last carried grapheme;
                        # only accepted streams promise complete visible text.
                        self.assertTrue(('answer:'+row['mode']).startswith(row['tokens']))
                        if row['mode'] in ('mismatch', 'malformed', 'paddedstart',
                                           'longstart', 'controlstart', 'blankstart',
                                           'bidistart', 'zerostart', 'softstart',
                                            'joinstart', 'graphemestart'):
                            self.assertEqual(row['reads'], 0)
                            self.assertEqual(row['done'], [])
                            self.assertEqual(len(row['errors']), 1)
                            expected = ('HOLD_NATIVE_MODEL_START_LABEL'
                                        if row['mode'].endswith('start') else
                                        'HOLD_NATIVE_MODEL_RECEIPT_DRIFT')
                            self.assertIn(expected, row['errors'][0]['error'])
                        else:
                            self.assertEqual(row['tokens'], 'answer:'+row['mode'])
                            self.assertEqual(row['reads'], 1)
                            self.assertEqual(row['errors'], [])
                            self.assertEqual(len(row['done']), 1)
                            self.assertEqual(row['done'][0]['model_label'],
                                             'existing-model')
                            self.assertIs(row['done'][0]['model_identity_verified'],
                                          False)
                finally:
                    await browser.close()
        asyncio.run(run())


    def test_native_burst_phase_event_coalescing_preserves_sse_and_s03(self):
        """Real Chromium with synthetic native transport, not live serving acceptance."""
        from playwright.async_api import async_playwright

        async def run():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True, executable_path='/usr/bin/chromium')
                try:
                    page = await browser.new_page()

                    async def fixture(route):
                        await route.fulfill(
                            status=200, content_type='text/html',
                            body='<html><body>B3 phase burst synthetic fixture</body></html>')
                    await page.route('**/nox-web-v29/pc/resonance.html', fixture)
                    await page.goto(
                        'http://127.0.0.1:18775/nox-web-v29/pc/resonance.html')
                    await page.evaluate("""() => {
                        window.NOX_NATIVE_OWNER=true;
                        window.__phases=[];
                        window.__posts=0;
                        window.__reads=0;
                        window.addEventListener('nox:native-phase',
                            e=>window.__phases.push(e.detail.phase));
                        const id='a'.repeat(32);
                        const exchange='ex-phase-burst';
                        window.__burst=Array.from({length:512},(_,i)=>i%2?'Ж':'🧠');
                        const pack=data=>new Response(JSON.stringify(data),{
                            status:200,headers:{'Content-Type':'application/json'}
                        });
                        window.fetch=async (url,init)=>{
                            if(url==='/api/nox/chat/stream'){
                                window.__posts++;
                                const frames=[
                                    {type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
                                    {type:'start',model:'pinned-existing-native-fixture'},
                                    ...window.__burst.map(text=>({type:'delta',text})),
                                    {type:'done',saved:true,s03_integrated:true,
                                     dialog_id:id,exchange_id:exchange}
                                ];
                                return new Response(
                                    frames.map(JSON.stringify).join('\\n')+'\\n',
                                    {status:200});
                            }
                            if(String(url).startsWith('/api/ui/memory/dialogs/history?')){
                                window.__reads++;
                                return pack({status:'READY',dialog_id:id,messages:[
                                    {role:'user',content:'burst',exchange_id:exchange},
                                    {role:'assistant',content:window.__burst.join(''),
                                     exchange_id:exchange}
                                ]});
                            }
                            throw Error('UNEXPECTED_NATIVE_ROUTE:'+url);
                        };
                    }""")
                    bridge = (pathlib.Path(__file__).parent /
                              'nox-v135-resonance-owner-bridge.js').read_text('utf8')
                    await page.add_script_tag(content=bridge)
                    result = await page.evaluate("""async () => {
                        const resp=await fetch('/api/nox/chat',{
                            method:'POST',body:JSON.stringify({
                                dialog_id:'a'.repeat(32),
                                request_id:'b3-phase-burst-512',
                                message:'burst'
                            })
                        });
                        const raw=await resp.text();
                        const events=raw.split('\\n\\n').filter(Boolean)
                            .map(row=>JSON.parse(row.replace(/^data: /,'')));
                        return {
                            phases:window.__phases,
                            posts:window.__posts,
                            reads:window.__reads,
                            expected:window.__burst.join(''),
                            actual:events.filter(e=>e.type==='token')
                                .map(e=>e.t).join(''),
                            done:events.filter(e=>e.type==='done'),
                            errors:events.filter(e=>e.type==='error')
                        };
                    }""")
                    # Hundreds of genuine browser-consumed SSE token deltas
                    # must not cause hundreds of duplicate main-thread events.
                    self.assertEqual(result['phases'], ['waiting', 'speaking', 'idle'])
                    self.assertEqual(result['posts'], 1)
                    self.assertEqual(result['reads'], 1)
                    self.assertEqual(result['actual'], result['expected'])
                    self.assertEqual(result['errors'], [])
                    self.assertEqual(len(result['done']), 1)
                    self.assertTrue(result['done'][0]['s03_integrated'])
                    self.assertTrue(result['done'][0]['history_persisted'])
                finally:
                    await browser.close()

        asyncio.run(run())



    def test_native_reader_cancel_keeps_terminal_stopped_phase(self):
        """Real Chromium, synthetic native abort; never a live S03 acceptance."""
        from playwright.async_api import async_playwright

        async def run():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True, executable_path='/usr/bin/chromium')
                try:
                    page = await browser.new_page()

                    async def fixture(route):
                        await route.fulfill(
                            status=200, content_type='text/html',
                            body='<html><body>B3 STOP phase fixture</body></html>')
                    await page.route('**/nox-web-v29/pc/resonance.html', fixture)
                    await page.goto(
                        'http://127.0.0.1:18775/nox-web-v29/pc/resonance.html')
                    await page.evaluate("""() => {
                        window.NOX_NATIVE_OWNER=true;
                        window.__phases=[];
                        window.__posts=0;
                        window.__aborts=0;
                        window.addEventListener('nox:native-phase',
                            e=>window.__phases.push(e.detail.phase));
                        window.fetch=(url,init)=>{
                            if(url==='/api/nox/chat/stream'){
                                window.__posts++;
                                return new Promise((resolve,reject)=>{
                                    init.signal.addEventListener('abort',()=>{
                                        window.__aborts++;
                                        reject(Error('SYNTHETIC_NATIVE_ABORT'));
                                    },{once:true});
                                });
                            }
                            throw Error('UNEXPECTED_NATIVE_ROUTE:'+url);
                        };
                    }""")
                    bridge=(pathlib.Path(__file__).parent /
                            'nox-v135-resonance-owner-bridge.js').read_text('utf8')
                    await page.add_script_tag(content=bridge)
                    actual=await page.evaluate("""async () => {
                        const response=await fetch('/api/nox/chat',{
                            method:'POST',body:JSON.stringify({
                                dialog_id:'a'.repeat(32),
                                request_id:'b3-native-stop-phase-cancel',
                                message:'stop'
                            })
                        });
                        const reader=response.body.getReader();
                        const first=await Promise.race([
                            reader.read(),
                            new Promise((_,reject)=>setTimeout(
                                ()=>reject(Error('META_TIMEOUT')),1000))
                        ]);
                        for(let i=0;i<100&&!window.__posts;i++)
                            await new Promise(resolve=>setTimeout(resolve,2));
                        if(!window.__posts)return {error:'NO_NATIVE_POST'};
                        await reader.cancel('CLIENT_STOP');
                        await new Promise(resolve=>setTimeout(resolve,30));
                        return {
                            first:new TextDecoder().decode(first.value),
                            phases:window.__phases,
                            posts:window.__posts,
                            aborts:window.__aborts
                        };
                    }""")
                    self.assertNotIn('error', actual)
                    self.assertIn('"type":"meta"', actual['first'])
                    self.assertEqual(actual['posts'], 1)
                    self.assertEqual(actual['aborts'], 1)
                    self.assertEqual(actual['phases'], ['waiting', 'stopped'])
                finally:
                    await browser.close()
        asyncio.run(run())




    def test_cancel_from_accepted_idle_does_not_rewrite_stopped(self):
        """Real Chromium + synthetic native; accepted DONE stays idle."""
        from playwright.async_api import async_playwright

        async def run():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True, executable_path='/usr/bin/chromium')
                try:
                    page = await browser.new_page()
                    async def fixture(route):
                        await route.fulfill(status=200, content_type='text/html',
                                            body='<html>B3 idle terminal</html>')
                    await page.route('**/nox-web-v29/pc/resonance.html', fixture)
                    await page.goto(
                        'http://127.0.0.1:18775/nox-web-v29/pc/resonance.html')
                    await page.evaluate("""() => {
                        window.NOX_NATIVE_OWNER=true;
                        window.__phases=[];window.__posts=0;
                        window.__reads=0;window.__cancels=0;
                        window.addEventListener('nox:native-phase',e=>{
                            window.__phases.push(e.detail.phase);
                            if(e.detail.phase==='idle'&&window.__reader){
                                window.__cancels++;
                                window.__reader.cancel('CLIENT_SEES_ACCEPTED_IDLE');
                            }
                        });
                        window.fetch=async (url,init)=>{
                            if(url==='/api/nox/chat/stream'){
                                window.__posts++;
                                const d=JSON.parse(init.body);
                                const frames=[
                                    {type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
                                    {type:'start',model:'fixed-native-fixture'},
                                    {type:'delta',text:'Готово 🧠'},
                                    {type:'done',saved:true,s03_integrated:true,
                                     dialog_id:d.dialog_id,exchange_id:'b3-idle-accepted-1'}
                                ];
                                return new Response(
                                    frames.map(JSON.stringify).join('\\n')+'\\n');
                            }
                            if(String(url).startsWith(
                                '/api/ui/memory/dialogs/history?')){
                                window.__reads++;
                                return new Response(JSON.stringify({
                                    status:'READY',dialog_id:'a'.repeat(32),
                                    messages:[
                                        {role:'user',content:'Проверка',
                                         exchange_id:'b3-idle-accepted-1'},
                                        {role:'assistant',content:'Готово 🧠',
                                         exchange_id:'b3-idle-accepted-1'}
                                    ]
                                }),{status:200});
                            }
                            throw Error('UNEXPECTED_NATIVE_ROUTE:'+url);
                        };
                    }""")
                    bridge=(pathlib.Path(__file__).parent /
                            'nox-v135-resonance-owner-bridge.js').read_text('utf8')
                    await page.add_script_tag(content=bridge)
                    actual=await page.evaluate("""async () => {
                        const r=await fetch('/api/nox/chat',{
                            method:'POST',body:JSON.stringify({
                                dialog_id:'a'.repeat(32),
                                request_id:'b3-accepted-idle-cancel',
                                message:'Проверка'
                            })
                        });
                        window.__reader=r.body.getReader();
                        await window.__reader.read();
                        for(let n=0;n<100&&!window.__cancels;n++)
                            await new Promise(resolve=>setTimeout(resolve,3));
                        return {phases:window.__phases,posts:window.__posts,
                            reads:window.__reads,cancels:window.__cancels};
                    }""")
                    self.assertEqual(actual['posts'],1)
                    self.assertEqual(actual['reads'],1)
                    self.assertEqual(actual['cancels'],1)
                    self.assertEqual(actual['phases'],
                                     ['waiting','speaking','idle'])
                finally:
                    await browser.close()
        asyncio.run(run())


    def test_native_abort_signal_terminal_phase_source_contract(self):
        """Preserve SSE STOP receipt while keeping browser phase stopped."""
        bridge = (pathlib.Path(__file__).parent /
                  'nox-v135-resonance-owner-bridge.js').read_text('utf8')
        self.assertIn("error:nativeSignal.aborted?'stopped':'error'", bridge)
        self.assertIn("error:nativeSignal.aborted?'STREAM_STOP_REQUESTED'", bridge)
        self.assertIn("upstreamAbort.abort();\n    if(phasePrev!=='idle')stopPhase();", bridge)



    def test_json_escaped_lone_surrogate_fails_before_s03(self):
        """Real Chromium with synthetic native, not a production readback."""
        from playwright.async_api import async_playwright
        async def run():
            async with async_playwright() as pw:
                browser=await pw.chromium.launch(
                    headless=True,executable_path='/usr/bin/chromium')
                try:
                    page=await browser.new_page()
                    async def fixture(route):
                        await route.fulfill(status=200,content_type='text/html',
                                            body='<html>B3 scalar fixture</html>')
                    await page.route('**/nox-web-v29/pc/resonance.html',fixture)
                    await page.goto(
                        'http://127.0.0.1:18775/nox-web-v29/pc/resonance.html')
                    await page.evaluate("""() => {
                        window.NOX_NATIVE_OWNER=true;
                        window.__reads=0;window.__posts=0;const state={};
                        window.fetch=async (url,init)=>{
                            if(url==='/api/nox/chat/stream'){
                                window.__posts++;
                                const d=JSON.parse(init.body),m=d.message;
                                const parts=m==='bad-high'?['A',String.fromCharCode(0xD800)]
                                    :m==='bad-low'?['A',String.fromCharCode(0xDC00)]
                                    :m==='good-split'?[String.fromCharCode(0xD83D),
                                        String.fromCharCode(0xDE80)]:['Ж','🧠'];
                                const exchange='ex-b3-'+m;
                                state[d.dialog_id]=[m,parts.join(''),exchange];
                                const frames=[
                                    {type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
                                    {type:'start',model:'fixed-native-fixture'},
                                    ...parts.map(text=>({type:'delta',text})),
                                    {type:'done',saved:true,s03_integrated:true,
                                     dialog_id:d.dialog_id,exchange_id:exchange}];
                                return new Response(
                                    frames.map(JSON.stringify).join('\\n')+'\\n',
                                    {status:200});
                            }
                            if(String(url).startsWith('/api/ui/memory/dialogs/history?')){
                                window.__reads++;
                                const id=new URL(url,'http://localhost')
                                    .searchParams.get('dialog_id');
                                const s=state[id];
                                return new Response(JSON.stringify({
                                    status:'READY',dialog_id:id,messages:[
                                        {role:'user',content:s[0],exchange_id:s[2]},
                                        {role:'assistant',content:s[1],exchange_id:s[2]}
                                    ]}),{status:200});
                            }
                            throw Error('UNEXPECTED_NATIVE_ROUTE');
                        };
                    }""")
                    bridge=(pathlib.Path(__file__).parent/
                            'nox-v135-resonance-owner-bridge.js').read_text('utf8')
                    await page.add_script_tag(content=bridge)
                    rows=await page.evaluate("""async () => {
                        const rows=[];
                        for(const [i,m] of
                             ['bad-high','bad-low','good-split','good-utf8'].entries()){
                            const prior=window.__reads;
                            const r=await fetch('/api/nox/chat',{
                                method:'POST',body:JSON.stringify({
                                    dialog_id:String(i+1).repeat(32),
                                    request_id:'b3-scalar-'+m,message:m
                                })
                            });
                            const events=(await r.text()).split('\\n\\n')
                                .filter(Boolean).map(x=>JSON.parse(x.slice(6)));
                            rows.push({mode:m,reads:window.__reads-prior,
                                done:events.filter(x=>x.type==='done'),
                                errors:events.filter(x=>x.type==='error'),
                                text:events.filter(x=>x.type==='token')
                                    .map(x=>x.t).join('')});
                        }
                        return {rows,posts:window.__posts};
                    }""")
                    self.assertEqual(rows['posts'],4)
                    for r in rows['rows']:
                        if r['mode'].startswith('bad'):
                            self.assertEqual(r['reads'],0)
                            self.assertEqual(r['done'],[])
                            self.assertEqual(len(r['errors']),1)
                            self.assertIn('HOLD_NATIVE_SURROGATE',
                                          r['errors'][0]['error'])
                        else:
                            self.assertEqual(r['reads'],1)
                            self.assertEqual(r['errors'],[])
                            self.assertEqual(len(r['done']),1)
                            self.assertEqual(r['text'],
                                '🚀' if r['mode']=='good-split' else 'Ж🧠')
                finally:
                    await browser.close()
        asyncio.run(run())



    def test_current_exchange_requires_latest_history_tail(self):
        """Chromium synthetic-native: an older exchange cannot be approved as latest."""
        from playwright.async_api import async_playwright

        async def run():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True, executable_path='/usr/bin/chromium')
                try:
                    page = await browser.new_page()
                    async def fixture(route):
                        await route.fulfill(status=200, content_type='text/html',
                                            body='<html>B3 history tail fixture</html>')
                    await page.route('**/nox-web-v29/pc/resonance.html', fixture)
                    await page.goto(
                        'http://127.0.0.1:18775/nox-web-v29/pc/resonance.html')
                    await page.evaluate("""() => {
                        window.NOX_NATIVE_OWNER=true;
                        window.__posts=0;window.__reads=0;
                        const did='a'.repeat(32);
                        const rows=[
                            ['one','answer1','b3-tail-ex1'],
                            ['two','answer2','b3-tail-ex2'],
                            ['three','answer3','b3-tail-ex3']];
                        window.fetch=async (url,init)=>{
                            if(url==='/api/nox/chat/stream'){
                                const row=rows[window.__posts++];
                                const frames=[
                                    {type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
                                    {type:'start',model:'mock-pinned'},
                                    {type:'delta',text:row[1]},
                                    {type:'done',saved:true,s03_integrated:true,
                                     dialog_id:did,exchange_id:row[2]}];
                                return new Response(
                                    frames.map(JSON.stringify).join('\\n')+'\\n',
                                    {status:200});
                            }
                            if(String(url).startsWith(
                                '/api/ui/memory/dialogs/history?')){
                                window.__reads++;
                                const messages=rows.slice(0,window.__posts)
                                    .flatMap(row=>[
                                        {role:'user',content:row[0],exchange_id:row[2]},
                                        {role:'assistant',content:row[1],exchange_id:row[2]}]);
                                if(window.__posts===3)messages.push(
                                    {role:'user',content:'later',exchange_id:'foreign'},
                                    {role:'assistant',content:'reply',exchange_id:'foreign'});
                                return new Response(JSON.stringify({
                                    status:'READY',dialog_id:did,messages
                                }),{status:200});
                            }
                            throw Error('UNEXPECTED_NATIVE_ROUTE');
                        };
                    }""")
                    bridge=(pathlib.Path(__file__).parent /
                            'nox-v135-resonance-owner-bridge.js').read_text('utf8')
                    await page.add_script_tag(content=bridge)
                    actual=await page.evaluate("""async () => {
                        const out=[];
                        for(const message of ['one','two','three']){
                            const r=await fetch('/api/nox/chat',{
                                method:'POST',body:JSON.stringify({
                                    dialog_id:'a'.repeat(32),
                                    request_id:'b3-tail-'+message,message})
                            });
                            const events=(await r.text()).split('\\n\\n')
                                .filter(Boolean).map(s=>JSON.parse(s.slice(6)));
                            out.push({done:events.filter(x=>x.type==='done'),
                                      error:events.filter(x=>x.type==='error')});
                        }
                        return {out,posts:window.__posts,reads:window.__reads};
                    }""")
                    self.assertEqual(actual['posts'],3)
                    self.assertEqual(actual['reads'],3)
                    self.assertEqual([len(x['done']) for x in actual['out']],
                                     [1,1,0])
                    self.assertEqual([len(x['error']) for x in actual['out']],
                                     [0,0,1])
                    self.assertIn('HOLD_DIALOG_HISTORY_READBACK',
                                  actual['out'][2]['error'][0]['error'])
                finally:
                    await browser.close()
        asyncio.run(run())


    def test_native_history_rejects_foreign_scoped_rows_before_browser_done(self):
        """Synthetic Chromium two turns, not live S03 or serving evidence."""
        from playwright.async_api import async_playwright

        async def run():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True, executable_path='/usr/bin/chromium')
                try:
                    for mode in ('tagged', 'legacy', 'foreign_current',
                                 'foreign_ancestor', 'null_current',
                                 'model_current', 'model_ancestor', 'model_null',
                                 'model_label_current', 'model_label_ancestor',
                                 'model_consistent'):
                        page = await browser.new_page()
                        async def fixture(route):
                            await route.fulfill(status=200, content_type='text/html',
                                                body='<html>B3 row-scope fixture</html>')
                        await page.route('**/nox-web-v29/pc/resonance.html', fixture)
                        await page.goto('http://127.0.0.1:18775/nox-web-v29/pc/resonance.html')
                        await page.evaluate("""mode => {
                          window.NOX_NATIVE_OWNER=true;
                          window.__posts=0;window.__reads=0;
                          const did='a'.repeat(32),foreign='b'.repeat(32);
                          const rows=[['hello','world','b3-scope-ex1'],
                                      ['again','reply','b3-scope-ex2']];
                          window.fetch=async (url,init)=>{
                            if(url==='/api/nox/chat/stream'){
                              const row=rows[window.__posts++];
                              const frames=[
                                {type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
                                {type:'start',model:'mock-pinned'},
                                {type:'delta',text:row[1]},
                                {type:'done',saved:true,s03_integrated:true,
                                 dialog_id:did,exchange_id:row[2]}];
                              return new Response(frames.map(JSON.stringify).join('\\n')+'\\n',{status:200});
                            }
                            if(String(url).startsWith('/api/ui/memory/dialogs/history?')){
                              window.__reads++;
                              const messages=rows.slice(0,window.__posts).flatMap(row=>[
                                {role:'user',content:row[0],exchange_id:row[2],dialog_id:did},
                                {role:'assistant',content:row[1],exchange_id:row[2],dialog_id:did}]);
                              if(mode==='legacy')messages.forEach(m=>delete m.dialog_id);
                              if(window.__posts===2){
                                if(mode==='foreign_current')messages[3].dialog_id=foreign;
                                if(mode==='foreign_ancestor')messages[0].dialog_id=foreign;
                                if(mode==='null_current')messages[3].dialog_id=null;
                                if(mode==='model_current')messages[3].model='other-model';
                                if(mode==='model_ancestor')messages[1].model='other-model';
                                if(mode==='model_null')messages[3].model=null;
                                if(mode==='model_label_current')messages[3].model_label='other-model';
                                if(mode==='model_label_ancestor')messages[1].model_label='other-model';
                                if(mode==='model_consistent')messages.forEach(m=>{if(m.role==='assistant'){m.model='mock-pinned';m.model_label='mock-pinned';}});
                              }
                              return new Response(JSON.stringify({
                                status:'READY',dialog_id:did,messages
                              }),{status:200});
                            }
                            throw Error('UNEXPECTED_NATIVE_ROUTE');
                          };
                        }""",mode)
                        bridge=(pathlib.Path(__file__).parent /
                                'nox-v135-resonance-owner-bridge.js').read_text('utf8')
                        await page.add_script_tag(content=bridge)
                        actual=await page.evaluate("""async () => {
                          const out=[];
                          for(const [i,message] of ['hello','again'].entries()){
                            const r=await fetch('/api/nox/chat',{
                              method:'POST',body:JSON.stringify({
                                dialog_id:'a'.repeat(32),
                                request_id:'b3-row-scope-'+i,message})
                            });
                            const events=(await r.text()).split('\\n\\n')
                              .filter(Boolean).map(s=>JSON.parse(s.slice(6)));
                            out.push({done:events.filter(e=>e.type==='done'),
                                      error:events.filter(e=>e.type==='error')});
                          }
                          return {out,posts:window.__posts,reads:window.__reads};
                        }""")
                        self.assertEqual((actual['posts'],actual['reads']),(2,2))
                        self.assertEqual(len(actual['out'][0]['done']),1)
                        self.assertEqual(actual['out'][0]['error'],[])
                        if mode in ('tagged','legacy','model_consistent'):
                            self.assertEqual(len(actual['out'][1]['done']),1)
                            self.assertEqual(actual['out'][1]['error'],[])
                        else:
                            self.assertEqual(actual['out'][1]['done'],[])
                            self.assertEqual(len(actual['out'][1]['error']),1)
                            self.assertIn('HOLD_DIALOG_HISTORY_SCOPE',
                                          actual['out'][1]['error'][0]['error'])
                        await page.close()
                finally:
                    await browser.close()
        asyncio.run(run())



    def test_b3_simple_text_fastpath_preserves_unicode_stream(self):
        """Synthetic Chromium stream only; not a native serving/S03 receipt."""
        from playwright.async_api import async_playwright

        async def run():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True, executable_path='/usr/bin/chromium')
                try:
                    for chunks in (['Ab', 'Пр'] * 120,
                                   ['A', '\u0301', 'B', '👩', '\u200d', '💻']):
                        page = await browser.new_page()
                        async def fixture(route):
                            await route.fulfill(status=200, content_type='text/html',
                                                body='<html>B3 grapheme fixture</html>')
                        await page.route('**/nox-web-v29/pc/resonance.html', fixture)
                        await page.goto('http://127.0.0.1:18775/nox-web-v29/pc/resonance.html')
                        await page.evaluate("""chunks => {
                          window.NOX_NATIVE_OWNER=true;
                          const did='a'.repeat(32),answer=chunks.join('');
                          window.__segmentCalls=0;
                          const Original=Intl.Segmenter;
                          Intl.Segmenter=class extends Original {
                            segment(text){window.__segmentCalls++;return super.segment(text)}
                          };
                          window.fetch=async url=>{
                            if(url==='/api/nox/chat/stream'){
                              const rows=[{type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},
                                {type:'start',model:'mock-pinned'},
                                ...chunks.map(text=>({type:'delta',text})),
                                {type:'done',saved:true,s03_integrated:true,
                                 dialog_id:did,exchange_id:'r31-test-1'}];
                              return new Response(rows.map(JSON.stringify).join('\\n')+'\\n');
                            }
                            if(String(url).startsWith('/api/ui/memory/dialogs/history?'))
                              return new Response(JSON.stringify({status:'READY',dialog_id:did,
                                messages:[{role:'user',content:'check',exchange_id:'r31-test-1'},
                                {role:'assistant',content:answer,exchange_id:'r31-test-1'}]}));
                            throw Error('UNEXPECTED_NATIVE_ROUTE');
                          };
                        }""", chunks)
                        bridge=(pathlib.Path(__file__).parent /
                                'nox-v135-resonance-owner-bridge.js').read_text('utf8')
                        await page.add_script_tag(content=bridge)
                        out=await page.evaluate("""async () => {
                          const r=await fetch('/api/nox/chat',{method:'POST',
                            body:JSON.stringify({dialog_id:'a'.repeat(32),
                              request_id:'r31-test-1',message:'check'})});
                          const events=(await r.text()).split('\\n\\n').filter(Boolean)
                            .map(s=>JSON.parse(s.slice(6)));
                          return {text:events.filter(e=>e.type==='token').map(e=>e.t).join(''),
                            chunks:events.filter(e=>e.type==='token').map(e=>e.t),
                            done:events.filter(e=>e.type==='done').length,
                            errors:events.filter(e=>e.type==='error'),
                            segmentCalls:window.__segmentCalls};
                        }""")
                        self.assertEqual(out['text'], ''.join(chunks))
                        self.assertEqual((out['done'],out['errors']),(1,[]))
                        if len(chunks)>100:
                            self.assertEqual(out['segmentCalls'],0)
                        else:
                            self.assertGreater(out['segmentCalls'],0)
                            self.assertEqual(out['chunks'],['A\u0301','B','👩\u200d💻'])
                        await page.close()
                finally:
                    await browser.close()
        asyncio.run(run())


if __name__ == '__main__':
    unittest.main()
