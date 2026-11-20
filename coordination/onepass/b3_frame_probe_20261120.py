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


async def _measure_async(url, output, chromium, baseline, fixture_html, expected_selector):
    from playwright.async_api import async_playwright
    verify_url(url)
    out = pathlib.Path(output)
    out.mkdir(parents=True, exist_ok=True)
    result = {
        'schema': 'NOX_B3_READONLY_BROWSER_FRAME_EVIDENCE_V2',
        'scope': 'browser-only; not model/weights/tokenizer/S03 acceptance',
        'url': url, 'time_utc': datetime.now(timezone.utc).isoformat(),
        'sample_js': '90 consecutive real requestAnimationFrame intervals',
        'runs': [], 'blocked_mutating_requests': 0, 'blocked_model_posts': 0,
        'blocked_websocket_connections': 0,
        'service_workers_blocked': True,
        'native_s03_verified': False, 'installed_model_identity_verified': False,
        'synthetic_fixture': fixture_html is not None,
        'expected_selector_checked': expected_selector is not None,
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
                        if fixture_html is not None:
                            await page.set_content(fixture_html, wait_until='domcontentloaded')
                        else:
                            response = await page.goto(url, wait_until='domcontentloaded', timeout=12000)
                            if not response or response.status >= 400:
                                raise RuntimeError('HOLD_BROWSER_PAGE_HTTP')
                        if expected_selector:
                            await page.locator(expected_selector).first.wait_for(state='visible', timeout=12000)
                        await page.wait_for_timeout(350)
                        frame_samples = await page.evaluate(SAMPLE_JS)
                        mode = 'reduced' if reduced else 'normal'
                        filename = f'b3_{width}x{height}_{mode}.png'
                        path = out / filename
                        await page.screenshot(path=str(path), full_page=False)
                        proof = hashlib.sha256(path.read_bytes()).hexdigest()
                        entry = {'width': width, 'height': height, 'mode': mode,
                            'screenshot': filename, 'screenshot_sha256': proof,
                            'screenshot_bytes': path.stat().st_size,
                            'frame_time': summarize(frame_samples)}
                        result['runs'].append(entry)
                    finally:
                        await context.close()
        finally:
            await browser.close()
    if baseline:
        old = json.loads(pathlib.Path(baseline).read_text(encoding='utf8'))
        previous = {(x['width'], x['height'], x['mode']): x for x in old.get('runs', [])}
        for row in result['runs']:
            ref = previous.get((row['width'], row['height'], row['mode']))
            row['before_after_p95_delta_ms'] = round(
                row['frame_time']['p95_ms'] - ref['frame_time']['p95_ms'], 3) if ref else None
        result['baseline_file'] = pathlib.Path(baseline).name
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
