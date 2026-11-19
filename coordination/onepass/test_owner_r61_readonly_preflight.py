import unittest

from coordination.onepass.owner_r61_readonly_preflight import (
    _safe_path, _safe_url, input_binding, make_report,
)


class OwnerR61ReadOnlyPreflightTests(unittest.TestCase):
    def test_accepts_owner_supplied_static_asset_url(self):
        self.assertEqual(
            _safe_url("https://example.test/nox-web-v29/pc/resonance.html"),
            "https://example.test/nox-web-v29/pc/resonance.html",
        )

    def test_rejects_url_credentials_query_fragment_and_non_static_route(self):
        for value in (
            "https://user:pass@example.test/r.html",
            "https://example.test/r.html?token=x",
            "https://example.test/r.html#section",
            "https://example.test/api/chat",
            "file:///root/nox/r.html",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _safe_url(value)

    def test_rejects_relative_and_traversal_paths(self):
        for value in ("relative/file", "/root/nox/../secret", "/root/nox/./asset.js"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _safe_path(value, "ASSET_PATH")

    def test_report_is_explicit_hold_and_contains_no_supplied_file_paths(self):
        report = make_report(
            "https://example.test/nox-web-v29/pc/resonance.html",
            "/root/nox/site/pc/resonance.html",
            "/etc/nginx/sites-enabled/nox.conf",
            "running",
        )
        self.assertEqual(
            report["result"], "HOLD_HOST_READ_CHANNEL_UNAVAILABLE_WITHOUT_MUTATION"
        )
        self.assertEqual(report["host_probe"], "NOT_RUN")
        self.assertEqual(report["asset"]["url_status"], "NOT_PROBED")
        self.assertEqual(report["asset"]["served_sha256"], "NOT_AVAILABLE")
        self.assertEqual(report["proxy"]["route_sha256"], "NOT_AVAILABLE")
        self.assertEqual(report["deployment_sha"], "NOT_AVAILABLE")
        self.assertEqual(report["processes"], "NOT_AVAILABLE")
        self.assertFalse(report["mutations_performed"])
        self.assertFalse(report["inference_performed"])
        rendered = repr(report)
        self.assertNotIn("/root/nox/site/pc/resonance.html", rendered)
        self.assertNotIn("/etc/nginx/sites-enabled/nox.conf", rendered)

    def test_input_binding_is_stable_and_sensitive_to_each_input(self):
        a = input_binding("https://example.test/a.html", "/root/nox/a.html", "/etc/nginx/x")
        b = input_binding("https://example.test/a.html", "/root/nox/b.html", "/etc/nginx/x")
        self.assertEqual(len(a), 64)
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
