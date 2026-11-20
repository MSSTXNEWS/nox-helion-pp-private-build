"""Offline regressions for owner-allowlisted Hunter source validation.

No network, S03, model, scheduler, or native worker access.
"""
import contextlib
import io
import json
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
            "https://@example.org/rss",    # empty userinfo is still forbidden
            "https://example.org/rs\nss", # urllib otherwise strips LF
            "https://example.org/rs\tss",
            42, None,
        ):
            with self.subTest(value=value), self.assertRaises(hunter.HunterError):
                hunter._canonical_url(value)

    def test_valid_https_and_tracking_dedup_still_work(self):
        value = hunter._canonical_url("https://example.org/rss?utm_source=x&a=1")
        self.assertEqual(value, "https://example.org/rss?a=1")

    def test_unhashable_source_kind_is_typed_hold(self):
        base = {"id": "feed", "url": "https://example.org/rss",
                "kind": [], "allowed_hosts": ["example.org"], "interval_seconds": 3600}
        with self.assertRaises(hunter.HunterError):
            hunter._validate_source(base)

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
