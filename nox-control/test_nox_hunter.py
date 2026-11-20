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
