#!/usr/bin/env python3
"""NOX B3 5A05: opt-in read-only browser frame/screenshot evidence.

This tool never sends model messages. It blocks browser-initiated
mutating HTTP methods, service workers and WebSocket connections,
records blocked attempts, and does not authenticate or assert native
model/S03 acceptance. Screenshots stay local, not in the repo.
"""
import argparse
import asyncio
import hashlib
import json
import math
import pathlib
import statistics
from datetime import datetime, timezone
from urllib.parse import urlsplit

SIZES = [(320, 720), (390, 844), (1440, 900)]
SAMPLE_JS = """async () => {
  const values=[];
  let last;
  for(let i=0;i<91;i++){
    const t=await new Promise(resolve => requestAnimationFrame(resolve));
    if(last!==undefined) values.push(t-last);
    last=t;
  }
  return values;
}"""


def summarize(samples):
    if len(samples) < 30:
        raise ValueError('HOLD_INSUFFICIENT_REAL_FRAMES')
    ordered = sorted(float(x) for x in samples)
    if not all(0 < x < 120000 for x in ordered):
        raise ValueError('HOLD_INVALID_FRAME_TIMING')
    return {
        'frames': len(ordered),
        'median_ms': round(statistics.median(ordered), 3),
        'p95_ms': round(ordered[min(len(ordered)-1, int(.95 * len(ordered)))], 3),
        'over_50ms': sum(x > 50 for x in ordered),
    }


def verify_url(url):
    p = urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('HOLD_INVALID_BROWSER_TARGET')
    return url


def evidence_hash(value):
    """Persist only a digest, never a possible token or private URL/selector."""
    return hashlib.sha256(value.encode('utf8')).hexdigest()


def url_identity_sha256(url):
    """Pin the exact origin/path/query/hash route without recording raw URL."""
    p = urlsplit(verify_url(url))
    identity = (p.scheme.lower(), p.hostname.lower(), p.port,
                p.path, p.query, p.fragment)
    return evidence_hash(json.dumps(identity, separators=(',', ':'), ensure_ascii=True))


def require_landing_url(requested, visited):
    """Reject login/SPA redirects, using the same identity pinned in reports."""
    if url_identity_sha256(requested) != url_identity_sha256(visited):
        raise ValueError('HOLD_LIVE_LANDING_URL_MISMATCH')
    return visited


def renderer_resource_identity(inline, network):
    """Hash executed/loaded JS+CSS without persisting URLs, source or credentials.

    Network response bytes are taken from passive Playwright response events;
    this is a browser render provenance fingerprint, NOT model/tokenizer proof.
    """
    entries = []
    for kind, source in inline:
        if kind not in ('script', 'style') or not isinstance(source, str):
            raise ValueError('HOLD_LIVE_RENDER_RESOURCE_INVALID')
        if source:
            entries.append(('inline', kind, hashlib.sha256(source.encode('utf8')).hexdigest()))
    for kind, url, body in network:
        if kind not in ('script', 'stylesheet') or not isinstance(url, str) or not isinstance(body, bytes):
            raise ValueError('HOLD_LIVE_RENDER_RESOURCE_INVALID')
        entries.append(('network', kind, hashlib.sha256(url.encode('utf8')).hexdigest(),
                        hashlib.sha256(body).hexdigest()))
    if not entries:
        raise ValueError('HOLD_LIVE_RENDER_RESOURCES_MISSING')
    serialized = json.dumps(sorted(entries), separators=(',', ':'), ensure_ascii=True)
    return {'sha256': hashlib.sha256(serialized.encode('ascii')).hexdigest(),
            'count': len(entries)}


def compare_baseline(current, prior):
    """Fail closed if an old screenshot/frame report is not comparable.

    A matching browser URL is not a native/S03 identity proof. This is
    source-level frame evidence only; baseline files are not signed.
    """
    signature = ('schema', 'url_sha256', 'sample_js', 'synthetic_fixture',
                 'expected_selector_checked', 'expected_selector_sha256',
                 'landing_url_verified')
    if any(current.get(key) != prior.get(key) for key in signature):
        raise ValueError('HOLD_BASELINE_PROVENANCE_MISMATCH')
    if not isinstance(current.get('url_sha256'), str) or len(current['url_sha256']) != 64 or any(c not in '0123456789abcdef' for c in current['url_sha256']):
        raise ValueError('HOLD_BASELINE_TARGET_URL_HASH_MISSING')
    if not current.get('synthetic_fixture'):
        if not current.get('expected_selector_checked') or not current.get('expected_selector_sha256'):
            raise ValueError('HOLD_BASELINE_MISSING_LIVE_SELECTOR')
        if current.get('landing_url_verified') is not True:
            raise ValueError('HOLD_BASELINE_LANDING_URL_UNVERIFIED')
    expected = {(width, height, mode) for width, height in SIZES
                for mode in ('normal', 'reduced')}

    def index(rows):
        if not isinstance(rows, list) or len(rows) != len(expected):
            raise ValueError('HOLD_BASELINE_FRAME_COVERAGE')
        found = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('HOLD_BASELINE_FRAME_COVERAGE')
            key = (row.get('width'), row.get('height'), row.get('mode'))
            if key not in expected or key in found:
                raise ValueError('HOLD_BASELINE_FRAME_COVERAGE')
            found[key] = row
        return found

    old, new = index(prior.get('runs')), index(current.get('runs'))
    deltas = {}
    for key in expected:
        if not current.get('synthetic_fixture'):
            if (old[key].get('landing_url_sha256') != current['url_sha256'] or
                    new[key].get('landing_url_sha256') != current['url_sha256']):
                raise ValueError('HOLD_BASELINE_LANDING_HASH_MISMATCH')
            previous_resource = old[key].get('renderer_resource_sha256')
            current_resource = new[key].get('renderer_resource_sha256')
            previous_count = old[key].get('renderer_resource_count')
            current_count = new[key].get('renderer_resource_count')
            if (not isinstance(previous_resource, str) or len(previous_resource) != 64
                    or not all(ch in '0123456789abcdef' for ch in previous_resource)
                    or not isinstance(current_resource, str) or len(current_resource) != 64
                    or not all(ch in '0123456789abcdef' for ch in current_resource)
                    or type(previous_count) is not int or previous_count < 1
                    or type(current_count) is not int or current_count < 1):
                raise ValueError('HOLD_BASELINE_RENDER_IDENTITY_MISSING')
            if previous_resource != current_resource or previous_count != current_count:
                raise ValueError('HOLD_BASELINE_RENDER_IDENTITY_DRIFT')
        previous = old[key].get('frame_time')
        measured = new[key].get('frame_time')
        try:
            if not isinstance(previous, dict) or not isinstance(measured, dict):
                raise ValueError()
            frames = previous['frames']
            if frames != 90 or frames != measured['frames']:
                raise ValueError()
            p95 = float(previous['p95_ms'])
            now_p95 = float(measured['p95_ms'])
            if not (math.isfinite(p95) and math.isfinite(now_p95)
                    and 0 < p95 < 120000 and 0 < now_p95 < 120000):
                raise ValueError()
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError('HOLD_BASELINE_FRAME_INVALID') from exc
        deltas[key] = round(now_p95 - p95, 3)
    return deltas

async def sample_frames(page, timeout_seconds=15.0):
    """Bound frame sampling so a suspended rAF cannot hang the B3 browser probe.

    A timed-out sample is never promoted to frame evidence. The caller closes
    the browser context in its existing finally block.
    """
    try:
        return await asyncio.wait_for(page.evaluate(SAMPLE_JS), timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        raise ValueError('HOLD_FRAME_SAMPLE_TIMEOUT') from exc


async def _measure_async(url, output, chromium, baseline, fixture_html, expected_selector):
    from playwright.async_api import async_playwright
    verify_url(url)
    if fixture_html is None and not expected_selector:
        raise ValueError('HOLD_LIVE_SELECTOR_REQUIRED')
    out = pathlib.Path(output)
    # Evidence is single-use. A failed later run must never leave an older
    # success report or mixed screenshots at the same output path.
    try:
        out.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ValueError('HOLD_EVIDENCE_DIRECTORY_REUSED') from exc
    result = {
        'schema': 'NOX_B3_READONLY_BROWSER_FRAME_EVIDENCE_V3',
        'scope': 'browser-only; not model/weights/tokenizer/S03 acceptance',
        'url_sha256': url_identity_sha256(url), 'time_utc': datetime.now(timezone.utc).isoformat(),
        'sample_js': '90 consecutive real requestAnimationFrame intervals',
        'runs': [], 'blocked_mutating_requests': 0, 'blocked_model_posts': 0,
        'blocked_websocket_connections': 0,
        'service_workers_blocked': True,
        'native_s03_verified': False, 'installed_model_identity_verified': False,
        'synthetic_fixture': fixture_html is not None,
        'expected_selector_checked': expected_selector is not None,
        'expected_selector_sha256': evidence_hash(expected_selector) if expected_selector else None,
        'landing_url_verified': False,
        'comparison_admissible': False,
    }
    async with async_playwright() as pw:
        launch = {'headless': True}
        if chromium:
            launch['executable_path'] = chromium
        browser = await pw.chromium.launch(**launch)
        try:
            for width, height in SIZES:
                for reduced in (False, True):
                    context = await browser.new_context(
                        viewport={'width': width, 'height': height},
                        reduced_motion='reduce' if reduced else 'no-preference',
                        device_scale_factor=1, service_workers='block')
                    try:
                        async def guard(route):
                            request = route.request
                            u = urlsplit(request.url)
                            if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                                result['blocked_mutating_requests'] += 1
                                if u.path.startswith('/api/nox/chat'):
                                    result['blocked_model_posts'] += 1
                                await route.abort('blockedbyclient')
                            else:
                                await route.continue_()

                        async def guard_socket(route):
                            result['blocked_websocket_connections'] += 1
                            await route.close(code=1008, reason='READ_ONLY_BROWSER_PROBE')

                        # Context-wide interception includes a popup's first request.
                        # Service workers are disabled to prevent bypassing HTTP routes.
                        await context.route('**/*', guard)
                        # A WebSocket could mutate the service despite a read-only
                        # opening GET. Block its handshake before it connects.
                        if not hasattr(context, 'route_web_socket'):
                            raise RuntimeError('HOLD_WEBSOCKET_GUARD_UNAVAILABLE')
                        await context.route_web_socket('**/*', guard_socket)
                        page = await context.new_page()
                        page.set_default_timeout(12000)
                        network_assets, response_tasks = [], []
                        async def capture_resource(response):
                            if response.status >= 400:
                                raise ValueError('HOLD_LIVE_RENDER_RESOURCE_HTTP')
                            raw = await response.body()
                            network_assets.append((response.request.resource_type,
                                                   response.url, raw))

                        def on_response(response):
                            if response.request.resource_type in ('script', 'stylesheet'):
                                response_tasks.append(asyncio.create_task(capture_resource(response)))

                        if fixture_html is None:
                            page.on('response', on_response)
                        if fixture_html is not None:
                            await page.set_content(fixture_html, wait_until='domcontentloaded')
                        else:
                            response = await page.goto(url, wait_until='domcontentloaded', timeout=12000)
                            if not response or response.status >= 400:
                                raise RuntimeError('HOLD_BROWSER_PAGE_HTTP')
                            require_landing_url(url, page.url)
                        if expected_selector:
                            await page.locator(expected_selector).first.wait_for(state='visible', timeout=12000)
                        await page.wait_for_timeout(350)
                        if fixture_html is None:
                            require_landing_url(url, page.url)
                        frame_samples = await sample_frames(page)
                        mode = 'reduced' if reduced else 'normal'
                        filename = f'b3_{width}x{height}_{mode}.png'
                        path = out / filename
                        await page.screenshot(path=str(path), full_page=False)
                        if fixture_html is None:
                            require_landing_url(url, page.url)
                            result['landing_url_verified'] = True
                        renderer_proof = None
                        if fixture_html is None:
                            if response_tasks:
                                await asyncio.gather(*response_tasks)
                            inline_assets = await page.evaluate("""() =>
                                [...document.querySelectorAll('script:not([src]),style')]
                                    .map(e => [e.tagName.toLowerCase(), e.textContent || ''])
                            """)
                            renderer_proof = renderer_resource_identity(inline_assets, network_assets)
                        proof = hashlib.sha256(path.read_bytes()).hexdigest()
                        entry = {'width': width, 'height': height, 'mode': mode,
                            'landing_url_sha256': None if fixture_html is not None else url_identity_sha256(page.url),
                            'screenshot': filename, 'screenshot_sha256': proof,
                            'screenshot_bytes': path.stat().st_size,
                            'renderer_resource_sha256': renderer_proof['sha256'] if renderer_proof else None,
                            'renderer_resource_count': renderer_proof['count'] if renderer_proof else 0,
                            'frame_time': summarize(frame_samples)}
                        result['runs'].append(entry)
                    finally:
                        await context.close()
        finally:
            await browser.close()
    if baseline:
        baseline_path = pathlib.Path(baseline)
        baseline_bytes = baseline_path.read_bytes()
        old = json.loads(baseline_bytes.decode('utf8'))
        deltas = compare_baseline(result, old)
        for row in result['runs']:
            key = (row['width'], row['height'], row['mode'])
            row['before_after_p95_delta_ms'] = deltas[key]
        result['baseline_sha256'] = hashlib.sha256(baseline_bytes).hexdigest()
        result['comparison_scope'] = ('SYNTHETIC_ONLY' if result['synthetic_fixture']
                                      else 'LIVE_BROWSER_FRAMES_ONLY_NOT_S03')
        result['comparison_admissible'] = True
    report = out / 'b3_frame_report.json'
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    return result


def measure(url, output, chromium=None, baseline=None, fixture_html=None, expected_selector=None):
    return asyncio.run(_measure_async(url, output, chromium, baseline, fixture_html, expected_selector))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='Existing NOX browser UI URL; GET only')
    parser.add_argument('--output', required=True, help='Local private screenshot/report directory')
    parser.add_argument('--chromium', help='Optional local Chromium executable')
    parser.add_argument('--baseline', help='Local previous probe report for comparison')
    parser.add_argument('--expected-selector', help='Visible NOX UI selector to prevent login-page false PASS')
    args = parser.parse_args()
    result = measure(args.url, args.output, args.chromium, args.baseline, expected_selector=args.expected_selector)
    print(json.dumps({'runs': len(result['runs']), 'blocked_model_posts': result['blocked_model_posts'],
        'blocked_mutating_requests': result['blocked_mutating_requests'],
        'blocked_websocket_connections': result['blocked_websocket_connections'],
        'native_s03_verified': False, 'report': str(pathlib.Path(args.output) / 'b3_frame_report.json')}))


if __name__ == '__main__':
    main()
