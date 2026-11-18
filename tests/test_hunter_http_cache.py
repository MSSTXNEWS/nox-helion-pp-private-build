import io
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import patch
from urllib.error import HTTPError

from nox_selfbuilder.worms import WormHold, WormSwarm, WormTask
from nox_selfbuilder import worm_providers as p


class Response:
    def __init__(self, url, raw=b'{"items":[]}', headers=None, status=200):
        self.url, self.body, self.headers, self.status = url, io.BytesIO(raw), headers or {}, status
    def geturl(self): return self.url
    def read(self, count): return self.body.read(count)
    def __enter__(self): return self
    def __exit__(self, *args): self.body.close()


class CacheTests(unittest.TestCase):
    URL = 'https://api.github.com/test'
    def setUp(self):
        self.now = [0.0]
        self.wall = datetime(2026, 11, 17, tzinfo=timezone.utc)
        self.cache = p.HTTPSourceCache(clock=lambda: self.now[0], wall_clock=lambda: self.wall.timestamp())
    def fetch(self, transport, **kw):
        return p.fetch_official_json(self.URL, host='api.github.com', cache=self.cache,
                                     read_urlopen=transport, **kw)

    def test_freshness_then_conditional_304_reuses_validated_body(self):
        calls = []
        def transport(req, timeout):
            calls.append(req)
            if len(calls) == 1:
                return Response(req.full_url, headers={'ETag': '"one"', 'Cache-Control': 'max-age=60', 'Age': '10'})
            self.assertEqual(req.get_header('If-none-match'), '"one"')
            return Response(req.full_url, raw=b'', headers={'Cache-Control': 'max-age=60'}, status=304)
        self.assertEqual(self.fetch(transport), {'items': []})
        self.now[0] = 49
        self.assertEqual(self.fetch(transport), {'items': []})
        self.assertEqual(len(calls), 1)
        self.now[0] = 50
        self.assertEqual(self.fetch(transport), {'items': []})
        self.assertEqual(len(calls), 2)
        self.now[0] = 90
        self.fetch(transport)
        self.assertEqual(len(calls), 2)

    def test_urllib_304_and_last_modified(self):
        calls = []
        stamp = 'Tue, 17 Nov 2026 00:00:00 GMT'
        def transport(req, timeout):
            calls.append(req)
            if len(calls) == 1:
                return Response(req.full_url, headers={'Last-Modified': stamp})
            self.assertEqual(req.get_header('If-modified-since'), stamp)
            raise HTTPError(req.full_url, 304, 'Not Modified', {}, io.BytesIO(b''))
        self.fetch(transport)
        self.assertEqual(self.fetch(transport), {'items': []})

    def test_unbound_304_never_creates_fake_success(self):
        with self.assertRaisesRegex(WormHold, '304_WITHOUT_CACHE'):
            self.fetch(lambda req, timeout: Response(req.full_url, status=304))
        self.assertEqual(self.cache._entries, {})

    def test_retry_after_429_blocks_network_until_exact_deadline(self):
        calls = []
        def transport(req, timeout):
            calls.append(req)
            if len(calls) == 1:
                raise HTTPError(req.full_url, 429, 'Rate limit', {'Retry-After': '60'}, io.BytesIO(b''))
            return Response(req.full_url)
        with self.assertRaisesRegex(WormHold, 'HTTP_HOLD'):
            self.fetch(transport)
        self.now[0] = 59
        with self.assertRaisesRegex(WormHold, 'RETRY_AFTER'):
            self.fetch(transport)
        self.assertEqual(len(calls), 1)
        self.now[0] = 60
        self.assertEqual(self.fetch(transport), {'items': []})
        self.assertEqual(len(calls), 2)

    def test_retry_after_http_date_and_no_stale_body_on_failure(self):
        self.fetch(lambda req, timeout: Response(req.full_url, headers={'ETag': '"ok"'}))
        retry = format_datetime(self.wall + timedelta(seconds=120), usegmt=True)
        with self.assertRaisesRegex(WormHold, 'HTTP_HOLD'):
            self.fetch(lambda req, timeout: Response(req.full_url, headers={'Retry-After': retry}, status=503))
        self.now[0] = 119
        with self.assertRaisesRegex(WormHold, 'RETRY_AFTER'):
            self.fetch(lambda *a, **k: self.fail('network before Retry-After'))

    def test_forbidden_with_retry_after_is_respected(self):
        with self.assertRaisesRegex(WormHold, 'HTTP_HOLD'):
            self.fetch(lambda req, timeout: Response(req.full_url,
                headers={'Retry-After': '45'}, status=403))
        self.now[0] = 44
        with self.assertRaisesRegex(WormHold, 'RETRY_AFTER'):
            self.fetch(lambda *a, **k: self.fail('403 retry too soon'))

    def test_network_error_backoff_is_bounded_and_retries(self):
        def unavailable(*a, **k): raise OSError('offline')
        for _ in range(15):
            with self.assertRaisesRegex(WormHold, 'NETWORK_OR_JSON_HOLD'):
                self.fetch(unavailable)
            row = next(iter(self.cache._entries.values()))
            delay = row['retry_at'] - self.now[0]
            self.assertGreater(delay, 0)
            self.assertLessEqual(delay, 300)
            self.now[0] = row['retry_at']
        self.assertEqual(self.fetch(lambda req, timeout: Response(req.full_url)), {'items': []})

    def test_no_store_and_vary_do_not_cache(self):
        for headers in ({'Cache-Control': 'no-store, max-age=300'}, {'Vary': '*'}, {'Vary': 'Cookie'}):
            with self.subTest(headers=headers):
                self.fetch(lambda req, timeout: Response(req.full_url, headers=headers))
                self.assertEqual(self.cache._entries, {})

    def test_invalid_json_does_not_poison_fresh_cache(self):
        with self.assertRaisesRegex(WormHold, 'NETWORK_OR_JSON_HOLD'):
            self.fetch(lambda req, timeout: Response(req.full_url, raw=b'bad', headers={'Cache-Control': 'max-age=600'}))
        self.assertEqual(self.cache._entries, {})
        self.assertEqual(self.fetch(lambda req, timeout: Response(req.full_url)), {'items': []})

    def test_invalid_xml_does_not_poison_fresh_cache(self):
        for raw in (b'<rss>', b'<!DOCTYPE root><rss/>'):
            with self.subTest(raw=raw), self.assertRaises(WormHold):
                p.fetch_official_feed('https://example.org/feed', host='example.org', cache=self.cache,
                    read_urlopen=lambda req, timeout: Response(req.full_url, raw=raw, headers={'Cache-Control': 'max-age=600'}))
            self.assertEqual(self.cache._entries, {})

    def test_cache_is_bounded_and_keyed_by_url(self):
        cache = p.HTTPSourceCache(clock=lambda: 0, max_entries=2)
        for index in range(4):
            p.fetch_official_json(self.URL + str(index), host='api.github.com', cache=cache,
                read_urlopen=lambda req, timeout: Response(req.full_url, headers={'Cache-Control': 'max-age=600'}))
        self.assertEqual(len(cache._entries), 2)
        self.assertEqual([key[0] for key in cache._entries], [self.URL+'2', self.URL+'3'])

    def test_default_provider_maps_have_isolated_cache_and_still_observe_stop(self):
        url = 'https://example.org/feed'
        raw = b'<rss><channel><item><title>News</title><link>https://example.org/one</link><description>One</description></item></channel></rss>'
        calls, stop = [], [False]
        def transport(req, timeout):
            calls.append(req.full_url)
            return Response(req.full_url, raw=raw, headers={'Cache-Control': 'max-age=600'})
        first, _ = p.approved_provider_map(approved_feed_url=url, native_stop=lambda: stop[0])
        second, _ = p.approved_provider_map(approved_feed_url=url, native_stop=lambda: False)
        task = WormTask('task', 'ATLAS', 'markets', 'leaders', 'approved_feeds', 'query', '2026-11-17')
        with patch.object(p, '_strict_urlopen', transport):
            first['approved_feeds'](task); first['approved_feeds'](task)
            second['approved_feeds'](task)
            self.assertEqual(len(calls), 2)
            stop[0] = True
            with self.assertRaisesRegex(WormHold, 'STOP_REVOKED'):
                first['approved_feeds'](task)
            self.assertEqual(len(calls), 2)

    def test_swarm_dedup_survives_day_rollover_but_accepts_changed_content(self):
        seen, title = [], ['First']
        def provider(task):
            return [{'url': 'https://example.org/one', 'title': title[0], 'excerpt': 'Evidence', 'source_id': 'one'}]
        swarm = WormSwarm(provider_map={'approved_feeds': provider}, source_hosts={'approved_feeds': 'example.org'},
                          admit=lambda *a: True, persist=lambda session, finding: seen.append(finding) or True,
                          native_stop=lambda: False)
        swarm.set_enabled('owner', True)
        start = datetime(2026, 11, 17, tzinfo=timezone.utc)
        swarm.tick('owner', now=start, max_tasks=1)
        swarm.tick('owner', now=start+timedelta(days=1), max_tasks=1)
        self.assertEqual(len(seen), 1)
        title[0] = 'Changed'
        swarm.tick('owner', now=start+timedelta(days=2), max_tasks=1)
        self.assertEqual(len(seen), 2)


if __name__ == '__main__':
    unittest.main()
