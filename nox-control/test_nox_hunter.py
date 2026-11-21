"""Offline regressions for owner-allowlisted Hunter source validation.

No network, S03, model, scheduler, or native worker access.
"""
import contextlib
import io
import json
import sqlite3
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from pathlib import Path
import tempfile
import unittest

import nox_hunter as hunter


class HunterURLSafetyTests(unittest.TestCase):
    def test_malformed_urls_are_typed_holds(self):
        for value in (
            "https://[bad/rss",           # urlsplit raises ValueError
            "https://example.org:bad/rss", # .port raises ValueError
            "https://example.org:99999/rss",
            "https://localhost./rss",
            "https://127.0.0.1./rss",
            "https://10.10.10.10./rss",
            "https://0177.0.0.1/rss",
            "https://2130706433/rss",
            "https://0x7f000001/rss",
            "https://@example.org/rss",    # empty userinfo is still forbidden
            "https://example.org/rs\nss", # urllib otherwise strips LF
            "https://example.org/rs\tss",
            42, None,
        ):
            with self.subTest(value=value), self.assertRaises(hunter.HunterError):
                hunter._canonical_url(value)

    def test_idna_aliases_cannot_reach_private_or_local_hosts(self):
        # Resolver IDNA normalization can turn these into loopback endpoints.
        for hostname in (
            "127。0。0。1", "127．0．0．1", "127｡0｡0｡1",
            "ⅼocalhost", "localhost。", "0x7f．0．0．1",
        ):
            with self.subTest(hostname=hostname), self.assertRaises(hunter.HunterError):
                hunter._canonical_url("https://" + hostname + "/rss")

    def test_unicode_allowlisted_public_domain_uses_exact_ascii_idna(self):
        source = hunter._validate_source({
            "id": "idnfeed", "kind": "rss", "url": "https://bücher.example/feed",
            "allowed_hosts": ["bücher.example"], "interval_seconds": 3600,
        })
        self.assertEqual(source["url"], "https://xn--bcher-kva.example/feed")
        self.assertEqual(source["allowed_hosts"], ["xn--bcher-kva.example"])
        with self.assertRaises(hunter.HunterError):
            hunter._validate_url("https://buсher.example/feed", source["allowed_hosts"])

    def test_valid_https_and_tracking_dedup_still_work(self):
        value = hunter._canonical_url("https://example.org/rss?utm_source=x&a=1")
        self.assertEqual(value, "https://example.org/rss?a=1")
        self.assertEqual(
            hunter._canonical_url("https://EXAMPLE.ORG./rss?utm_source=x&a=1"),
            "https://example.org/rss?a=1",
        )

    def test_unhashable_source_kind_is_typed_hold(self):
        base = {"id": "feed", "url": "https://example.org/rss",
                "kind": [], "allowed_hosts": ["example.org"], "interval_seconds": 3600}
        with self.assertRaises(hunter.HunterError):
            hunter._validate_source(base)

    def test_invalid_candidate_links_are_quarantined_not_attributed_to_feed(self):
        source = hunter._validate_source({
            "id": "feed", "kind": "rss", "url": "https://example.org/feed",
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })
        parsed = [
            {"title": "valid", "url": "/article", "content": "verified-link candidate", "published": "2026-11-20"},
            {"title": "missing", "url": "", "content": "should not be from feed homepage", "published": ""},
            {"title": "unsafe", "url": "javascript:alert(1)", "content": "unsafe", "published": ""},
            {"title": "userinfo", "url": "https://name:password@example.org/post", "content": "unsafe", "published": ""},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "hunter.sqlite"
            with patch.object(hunter, "_fetch", return_value=(b"stub", None, None, "application/rss+xml", False)), \
                 patch.object(hunter, "_parse", return_value=parsed):
                out = hunter.poll_due([source], state, now=1000.0)
                self.assertEqual(out[0]["added"], 1)
                self.assertEqual(out[0]["quarantined"], 3)
                # A second due poll deduplicates; no forged feed-source row.
                out2 = hunter.poll_due([source], state, now=1100.0)
                self.assertEqual(out2[0]["added"], 0)
            with sqlite3.connect(state) as conn:
                rows = conn.execute("SELECT item_url FROM items ORDER BY item_url").fetchall()
                rejected = conn.execute("SELECT item_digest, reason FROM item_quarantine").fetchall()
            self.assertEqual(rows, [("https://example.org/article",)])
            self.assertEqual(len(rejected), 3)
            self.assertTrue(all(len(digest) == 64 and reason == "INVALID_ITEM_URL"
                                for digest, reason in rejected))
            self.assertFalse(any("password" in repr(row) for row in rejected))

    def test_json_surrogates_quarantine_only_bad_candidates(self):
        # A legal JSON escape can decode to an invalid lone surrogate.
        # Source config fails cleanly, while malformed feed items are
        # quarantined without undoing a valid candidate in the same poll.
        invalid = chr(0xD800)
        with self.assertRaises(hunter.HunterError):
            hunter._canonical_url("https://example.org/rss?bad=" + invalid)
        source = hunter._validate_source({
            "id": "jsonfeed", "kind": "github_releases",
            "url": "https://example.org/releases",
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })
        decoded = [
            {"title": "valid", "url": "https://example.org/post", "content": "normal", "published": ""},
            {"title": "broken" + invalid, "url": "https://example.org/bad", "content": "raw", "published": ""},
            {"title": "unsafe", "url": "https://example.org/" + invalid, "content": "raw", "published": ""},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.sqlite"
            with patch.object(hunter, "_fetch", return_value=(b"json", None, None, "application/json", False)), \
                 patch.object(hunter, "_parse", return_value=decoded):
                result = hunter.poll_due([source], db, now=1000.0)
            self.assertEqual(result[0]["status"], "polled")
            self.assertEqual((result[0]["added"], result[0]["quarantined"]), (1, 2))
            with sqlite3.connect(db) as conn:
                items = conn.execute("SELECT title FROM items").fetchall()
                holds = conn.execute("SELECT item_digest, reason FROM item_quarantine").fetchall()
            self.assertEqual(items, [("valid",)])
            self.assertEqual(len(holds), 2)
            self.assertTrue(all(len(digest) == 64 and reason == "INVALID_ITEM_URL"
                                for digest, reason in holds))

    def test_invalid_published_unicode_quarantines_only_bad_item(self):
        # GitHub JSON allows escaped lone surrogates in published_at. These
        # must never reach SQLite and roll back a healthy sibling entry.
        bad_date = "2026-" + chr(0xD800)
        source = hunter._validate_source({
            "id": "releases", "kind": "github_releases",
            "url": "https://example.org/releases",
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })
        items = [
            {"title": "healthy", "content": "valid", "url": "/good",
             "published": "2026-11-20"},
            {"title": "broken", "content": "valid", "url": "/bad",
             "published": bad_date},
            {"title": "wrong-date-type", "content": "valid", "url": "/bad-type",
             "published": ["not", "a", "date"]},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "hunter.sqlite"
            with patch.object(hunter, "_fetch", return_value=(b"json", None, None,
                                                               "application/json", False)), \
                 patch.object(hunter, "_parse", return_value=items):
                result = hunter.poll_due([source], db, now=1000.0)
            self.assertEqual(result[0]["status"], "polled")
            self.assertEqual((result[0]["added"], result[0]["quarantined"]), (1, 2))
            with sqlite3.connect(db) as conn:
                saved = conn.execute("SELECT title,published FROM items").fetchall()
                rejected = conn.execute("SELECT item_digest FROM item_quarantine").fetchall()
            self.assertEqual(saved, [("healthy", "2026-11-20")])
            self.assertEqual(len(rejected), 2)
            self.assertTrue(all(len(row[0]) == 64 for row in rejected))

    def test_crossref_malformed_date_parts_preserve_healthy_siblings(self):
        # Bad Crossref dates must not roll back the entire read-only feed.
        # A string cannot be converted into a fake character-by-character date.
        source = hunter._validate_source({
            "id": "crossref", "kind": "crossref",
            "url": "https://api.crossref.org/works",
            "allowed_hosts": ["api.crossref.org"], "interval_seconds": 60,
        })
        rows = [
            {"DOI": "10.1234/valid", "title": ["good"], "URL": "https://doi.org/10.1234/valid",
             "published-online": {"date-parts": [[2026, 11, 20]]}},
            {"DOI": "10.1234/scalar", "title": ["scalar-date"],
             "URL": "https://doi.org/10.1234/scalar",
             "published-online": {"date-parts": [2026]}},
            {"DOI": "10.1234/string", "title": ["string-date"],
             "URL": "https://doi.org/10.1234/string",
             "published-online": {"date-parts": ["2026-11-20"]}},
            {"DOI": "10.1234/invalid-month", "title": ["invalid-month"],
             "URL": "https://doi.org/10.1234/invalid-month",
             "published-online": {"date-parts": [[2026, 99, 20]]}},
            {"DOI": "10.1234/invalid-day", "title": ["invalid-day"],
             "URL": "https://doi.org/10.1234/invalid-day",
             "published-online": {"date-parts": [[2026, 2, 31]]}},
            {"DOI": "10.1234/leap", "title": ["leap"],
             "URL": "https://doi.org/10.1234/leap",
             "published-online": {"date-parts": [[2024, 2, 29]]}},
            {"DOI": "10.1234/normalized", "title": ["normalized"],
             "URL": "https://doi.org/10.1234/normalized",
             "published-online": {"date-parts": [[2026, 2, 3]]}},
            {"DOI": "10.1234/created", "title": ["created-only"],
             "URL": "https://doi.org/10.1234/created",
             "created": {"date-parts": [[2026, 11, 20]]}},
            {"DOI": "10.1234/fallback", "title": ["fallback-online"],
             "URL": "https://doi.org/10.1234/fallback",
             "published-print": {"date-parts": [[2026, 2, 30]]},
             "published-online": {"date-parts": [[2026, 1, 5]]}},
            {"DOI": "10.1234/issued", "title": ["issued-year"],
             "URL": "https://doi.org/10.1234/issued",
             "issued": {"date-parts": [[2025]]}},
        ]
        body = json.dumps({"message": {"items": rows}}).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.sqlite"
            with patch.object(hunter, "_fetch", return_value=(body, None, None,
                                                               "application/json", False)):
                result = hunter.poll_due([source], state, now=1000.0)
            self.assertEqual(result[0]["status"], "polled")
            self.assertEqual(result[0]["added"], 10)
            with sqlite3.connect(state) as conn:
                found = conn.execute("SELECT title,published FROM items ORDER BY title").fetchall()
            self.assertEqual(found, [
                ("created-only", ""),
                ("fallback-online", "2026-01-05"),
                ("good", "2026-11-20"),
                ("invalid-day", ""),
                ("invalid-month", ""),
                ("issued-year", "2025"),
                ("leap", "2024-02-29"),
                ("normalized", "2026-02-03"),
                ("scalar-date", ""),
                ("string-date", ""),
            ])

    def test_html_page_uses_its_real_source_url(self):
        source = hunter._validate_source({
            "id": "page", "kind": "html_page", "url": "https://example.org/page",
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })
        record = hunter._item_record(source, {"title": "page", "content": "text",
                                               "url": source["url"], "published": ""}, 1000.0)
        self.assertEqual(record[1], source["url"])

    def test_http_error_receipts_redact_urls_and_query_credentials(self):
        canary = "SENSITIVE_QUERY_CANARY_DO_NOT_STORE"
        endpoint = "https://example.org/feed?token=" + canary
        source = hunter._validate_source({
            "id": "sensitive", "kind": "rss", "url": endpoint,
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.sqlite"
            failures = [
                (HTTPError(endpoint, 401, "denied " + canary, {}, None),
                 "HTTPError: status=401"),
                (URLError("connection failed for " + endpoint),
                 "URLError: str"),
            ]
            for step, (raised, expected) in enumerate(failures):
                with patch.object(hunter, "_fetch", side_effect=raised):
                    result = hunter.poll_due([source], db, now=1000.0 + step * 600)
                self.assertEqual(result[0]["status"], "error")
                self.assertEqual(result[0]["error"], expected)
                self.assertNotIn(canary, json.dumps(result))
            with sqlite3.connect(db) as conn:
                saved = conn.execute("SELECT last_error FROM source_state WHERE source_id=?",
                                     ("sensitive",)).fetchone()[0]
                self.assertEqual(saved, "URLError: str")
                self.assertNotIn(canary, saved)

    def test_http_304_rechecks_cached_body_against_current_size_budget(self):
        # A smaller later max_bytes must not be bypassed by a 304 cached body.
        source = hunter._validate_source({
            "id": "cached", "kind": "rss", "url": "https://example.org/feed",
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })
        cached = {"body": b"x" * 2048, "etag": "v1",
                  "last_modified": None, "content_type": "application/rss+xml"}
        not_modified = HTTPError(source["url"], 304, "Not Modified", {}, None)
        with patch.object(hunter, "build_opener") as opener:
            opener.return_value.open.side_effect = not_modified
            with self.assertRaisesRegex(hunter.HunterError, "cached response exceeds max_bytes"):
                hunter._fetch(source, cached, max_bytes=1024)
            body, etag, modified, content_type, reused = hunter._fetch(
                source, cached, max_bytes=2048)
        self.assertEqual(body, cached["body"])
        self.assertEqual(etag, "v1")
        self.assertIsNone(modified)
        self.assertEqual(content_type, "application/rss+xml")
        self.assertTrue(reused)

    def test_http_cache_blob_is_lazy_until_304(self):
        # Even a large old BLOB must not be loaded into Python heap on HTTP 200.
        source = hunter._validate_source({
            "id": "lazy", "kind": "rss", "url": "https://example.org/feed",
            "allowed_hosts": ["example.org"], "interval_seconds": 60,
        })

        class FreshResponse:
            headers = {"ETag": "new"}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, size): return b"<rss/>"

        with tempfile.TemporaryDirectory() as tmp:
            conn = sqlite3.connect(str(Path(tmp) / "state.sqlite"))
            conn.row_factory = sqlite3.Row
            try:
                hunter._init_db(conn)
                conn.execute(
                    "INSERT INTO http_cache(source_id,url,etag,last_modified,content_type,"
                    "body,fetched_at,checked_at) VALUES(?,?,?,?,?,?,?,?)",
                    ("lazy", source["url"], "old", None, "application/rss+xml",
                     sqlite3.Binary(b"x" * (2 * 1024 * 1024)), 10, 10),
                )
                conn.commit()
                sql = []
                conn.set_trace_callback(sql.append)
                with patch.object(hunter, "build_opener") as opener, \
                     patch.object(hunter, "_parse", return_value=[]):
                    opener.return_value.open.return_value = FreshResponse()
                    first = hunter._poll_one(conn, source, 1000, 1024)
                    self.assertEqual(first["status"], "polled")
                    self.assertFalse(any("SELECT body FROM http_cache" in q for q in sql))
                    sql.clear()
                    opener.return_value.open.side_effect = HTTPError(
                        source["url"], 304, "Not Modified", {}, None)
                    second = hunter._poll_one(conn, source, 1100, 1024)
                    self.assertEqual(second["status"], "not_modified")
                    self.assertEqual(sum("SELECT body FROM http_cache" in q for q in sql), 1)
                body = conn.execute(
                    "SELECT body FROM http_cache WHERE source_id='lazy'").fetchone()[0]
                self.assertEqual(body, b"<rss/>")
            finally:
                conn.close()

    def test_cli_returns_structured_config_error_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "sources.json"
            state = Path(tmp) / "state.sqlite"
            config.write_text(json.dumps({"schema": hunter.SCHEMA, "sources": [{
                "id": "feed", "kind": "rss", "url": "https://[bad/rss",
                "allowed_hosts": ["example.org"], "interval_seconds": 3600
            }]}), encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = hunter.main(["--config", str(config), "--state", str(state)])
            self.assertEqual(result, 2)
            self.assertEqual(json.loads(stderr.getvalue())["status"], "config_error")
            self.assertFalse(state.exists())


if __name__ == "__main__":
    unittest.main()
