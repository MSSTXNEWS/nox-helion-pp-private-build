"""EV-A03 focused OFF-TREE regressions. Invoke with PYTHONPATH=src python -m unittest ..."""
import io
import unittest
from nox_selfbuilder.worms import WormHold, WormTask
from nox_selfbuilder import worm_providers as p


def task(provider):
    return WormTask("task123", "ATLAS", "open_source", "reuse", provider, "nox security", "2026-11-01")


class Response:
    def __init__(self, url, payload, length=None):
        self._url, self._buf = url, io.BytesIO(payload)
        self.headers = {"Content-Length": str(len(payload) if length is None else length)}
    def geturl(self): return self._url
    def read(self, n): return self._buf.read(n)
    def __enter__(self): return self
    def __exit__(self, *args): pass


class Tests(unittest.TestCase):
    FEED = "https://github.com/nox/nox/releases.atom"
    ATOM = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
      <title>Signed NOX sample</title><summary>New &lt;b&gt;release&lt;/b&gt; candidate</summary>
      <link rel="alternate" href="https://github.com/nox/nox/releases/tag/v1"/>
      <updated>2026-11-01T15:30:00Z</updated></entry></feed>'''

    def test_explicit_owner_feed_map(self):
        mapping, hosts = p.approved_provider_map(approved_feed_url=self.FEED,
                         feed_fetch=lambda u, host: p.fetch_official_feed(u, host=host,
                             read_urlopen=lambda req, timeout: Response(req.full_url, self.ATOM)))
        self.assertIn('approved_feeds', mapping)
        self.assertEqual(hosts['approved_feeds'], 'github.com')
        rows = mapping['approved_feeds'](task('approved_feeds'))
        self.assertEqual(rows[0]['url'], 'https://github.com/nox/nox/releases/tag/v1')
        self.assertIn('New release candidate', rows[0]['excerpt'])
        self.assertEqual(rows[0]['license'], 'REVIEW_REQUIRED')
        self.assertEqual(len(rows[0]['source_id']), 36)

    def test_rss_same_source_host(self):
        xml = b'<rss><channel><item><title>Actual notice</title><link>https://example.org/news/1</link><description>Evidence</description></item></channel></rss>'
        rows = p.official_feed(task('approved_feeds'), feed_url='https://example.org/rss.xml',
                     source_host='example.org', fetch=lambda u,host: p.ET.fromstring(xml))
        self.assertEqual(rows[0]['url'], 'https://example.org/news/1')

    def test_host_spoof_or_different_article_dropped(self):
        xml = b'<rss><channel><item><title>A</title><link>https://evil.test/x</link><description>B</description></item></channel></rss>'
        rows = p.official_feed(task('approved_feeds'), feed_url=self.FEED,
                     source_host='github.com', fetch=lambda u,host: p.ET.fromstring(xml))
        self.assertEqual(rows, [])

    def test_rss_atom_max_records(self):
        item = b'<item><title>Title</title><link>https://example.org/x</link><description>News</description></item>'
        xml = b'<rss><channel>' + item * 20 + b'</channel></rss>'
        rows = p.official_feed(task('approved_feeds'), feed_url='https://example.org/rss',
                     source_host='example.org', fetch=lambda u,host: p.ET.fromstring(xml))
        self.assertEqual(len(rows), p.MAX_RECORDS)

    def test_native_stop_before_network(self):
        called=[]
        with self.assertRaisesRegex(WormHold, 'WORM_NATIVE_STOP_REVOKED'):
            p.official_feed(task('approved_feeds'), feed_url=self.FEED, source_host='github.com',
                            fetch=lambda *args, **kw: called.append('fetch'), stop=lambda: True)
        self.assertEqual(called, [])

    def test_stop_after_network(self):
        seen=iter([False,True])
        with self.assertRaisesRegex(WormHold, 'WORM_NATIVE_STOP_REVOKED'):
            p.official_feed(task('approved_feeds'), feed_url=self.FEED, source_host='github.com',
                            fetch=lambda *a,**kw: p.ET.fromstring(self.ATOM), stop=lambda: next(seen))

    def test_feed_xml_entity_denied(self):
        xml=b'<!DOCTYPE a [ <!ENTITY ex "bad">]><rss><channel/></rss>'
        with self.assertRaisesRegex(WormHold, 'WORM_FEED_DTD_DENIED'):
            p.fetch_official_feed(self.FEED, host='github.com',
                 read_urlopen=lambda req,timeout: Response(req.full_url,xml))

    def test_feed_xml_invalid(self):
        with self.assertRaisesRegex(WormHold, 'WORM_FEED_XML_INVALID'):
            p.fetch_official_feed(self.FEED, host='github.com',
                 read_urlopen=lambda req,timeout: Response(req.full_url,b'<rss>'))

    def test_feed_byte_quota(self):
        xml=b'A'*(p.MAX_FEED_BYTES+1)
        with self.assertRaisesRegex(WormHold, 'WORM_PROVIDER_RESPONSE_QUOTA'):
            p.fetch_official_feed(self.FEED, host='github.com',
                 read_urlopen=lambda req,timeout: Response(req.full_url,xml))

    def test_redirect_denied_without_second_fetch(self):
        with self.assertRaisesRegex(WormHold, 'WORM_PROVIDER_REDIRECT_DENIED'):
            p._NoRedirect().redirect_request(None,None,302,'Found',{},'https://other.example.net/x')

    def test_injected_redirect_denied(self):
        with self.assertRaisesRegex(WormHold, 'WORM_PROVIDER_REDIRECT_DENIED'):
            p.fetch_official_feed(self.FEED, host='github.com',
                 read_urlopen=lambda req,timeout: Response('https://evil.test/feed',b'<rss/>'))

    def test_origin_private_address_denied(self):
        for host in ('127.0.0.1','localhost','metadata.local','2001:db8::1'):
            with self.subTest(host=host), self.assertRaises(WormHold):
                p._approved_url('https://'+host+'/feed',host)

    def test_owner_feed_not_configured(self):
        mapping, hosts=p.approved_provider_map(github_enabled=True)
        self.assertNotIn('approved_feeds', mapping)
        self.assertEqual(hosts['github_api'],'github.com')

    def test_github_existing_response_citation(self):
        rows=p.github_repositories(task('github_api'),fetch=lambda url,host: {
            'items':[{'html_url':'https://github.com/foo/bar','full_name':'foo/bar',
                      'description':'Read-only source', 'archived':False,'stargazers_count':3}]})
        self.assertEqual(rows[0]['source_id'],'github:foo/bar')
        self.assertEqual(rows[0]['license'],'REVIEW_REQUIRED')

    def test_unapproved_feed_task_denied(self):
        with self.assertRaisesRegex(WormHold, 'WORM_PROVIDER_TASK_NOT_ALLOWED'):
            p.official_feed(task('youtube_api'), feed_url=self.FEED, source_host='github.com')

    def test_github_native_stop_before_fetch(self):
        called=[]
        with self.assertRaisesRegex(WormHold, 'WORM_NATIVE_STOP_REVOKED'):
            p.github_repositories(task('github_api'),
                fetch=lambda *a, **kw: called.append('fetched'), stop=lambda: True)
        self.assertEqual(called, [])

    def test_github_native_stop_after_fetch_discards_results(self):
        checks=iter((False, True))
        fetches=[]
        def fetch(*args, **kwargs):
            fetches.append(True)
            return {'items':[{'html_url':'https://github.com/foo/bar',
                'full_name':'foo/bar','description':'signed source','archived':False}]}
        with self.assertRaisesRegex(WormHold, 'WORM_NATIVE_STOP_REVOKED'):
            p.github_repositories(task('github_api'),fetch=fetch,stop=lambda:next(checks))
        self.assertEqual(fetches,[True])

    def test_youtube_native_stop_before_key_network(self):
        calls=[]
        with self.assertRaisesRegex(WormHold, 'WORM_NATIVE_STOP_REVOKED'):
            p.youtube_public_video_search(task('youtube_api'),api_key='n'*24,
                fetch=lambda *a,**kw:calls.append(True), stop=lambda:True)
        self.assertEqual(calls,[])

    def test_missing_stop_status_fails_closed(self):
        for cb in (lambda:None,lambda:'False'):
            with self.subTest(cb=cb), self.assertRaisesRegex(WormHold,'WORM_NATIVE_STOP_REVOKED'):
                p.github_repositories(task('github_api'), stop=cb,
                    fetch=lambda *a,**k:self.fail('NETWORK_AFTER_INVALID_STOP'))

    def test_native_stop_probe_exception_fails_closed(self):
        def lost(): raise OSError('native bridge disconnected')
        with self.assertRaisesRegex(WormHold,'WORM_NATIVE_STOP_UNAVAILABLE'):
            p.official_feed(task('approved_feeds'),feed_url=self.FEED,
                source_host='github.com',stop=lost,
                fetch=lambda *a,**kw:self.fail('NETWORK_AFTER_BRIDGE_FAILURE'))

    def test_provider_map_github_stop_through_existing_callback(self):
        checks=[]
        def stopped(): checks.append(True); return True
        providers,hosts=p.approved_provider_map(github_enabled=True,
            native_stop=stopped,official_fetch=lambda *a,**kw:self.fail('NETWORK_DENIED'))
        with self.assertRaisesRegex(WormHold,'WORM_NATIVE_STOP_REVOKED'):
            providers['github_api'](task('github_api'))
        self.assertEqual(checks,[True])
        self.assertEqual(hosts['github_api'],'github.com')

    def test_json_strict_default_transport(self):
        original=p.build_opener
        saw=[]
        class FakeOpener:
            def open(self, req, timeout):
                return Response(req.full_url,b'{"items":[]}')
        def fake_build_opener(*handlers):
            saw.extend(handlers)
            return FakeOpener()
        p.build_opener=fake_build_opener
        try:
            got=p.fetch_official_json('https://api.github.com/test',host='api.github.com')
        finally:
            p.build_opener=original
        self.assertEqual(got,{'items':[]})
        self.assertTrue(any(isinstance(h,p._NoRedirect) for h in saw))


if __name__ == '__main__': unittest.main()
