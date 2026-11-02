"""Native STOP/SID grant/source HEAD witness after official metadata parsing.
Original A1 code only; no real network, native Windows, or model installation.
"""
import unittest
from nox_selfbuilder.a1_official_catalog import probe_official_catalog
from nox_selfbuilder.worms import WormHold

HEAD = "a" * 40


class RevokingResponse(dict):
    """Exercise a native witness changing during _parse after post-fetch check."""
    def __init__(self, revoke):
        super().__init__(info={"name": "ruff", "version": "1.0.0"}, urls=[])
        self.revoke = revoke

    def get(self, key, default=None):
        if key == "urls":
            self.revoke()
        return super().get(key, default)


class LastMetadataRevocationTests(unittest.TestCase):
    def setUp(self):
        self.native = {"stop": False, "grant": True, "head": HEAD, "epoch": 9}
        self.calls = 0

    def run_checked(self, revoke):
        def read(url, *, host):
            self.calls += 1
            self.assertEqual(host, "pypi.org")
            return RevokingResponse(revoke)
        return probe_official_catalog(
            "owner", [("pypi", "ruff")], source_head=HEAD,
            current_head=lambda: self.native["head"],
            authorize=lambda _s, scope: self.native["grant"] and scope == "worm.official_catalog.read",
            native_stop=lambda: self.native["stop"], fetch_json=read,
            stop_epoch=lambda: self.native["epoch"], expected_stop_epoch=9)

    def test_stop_during_metadata_parse_discards_final_candidate(self):
        with self.assertRaisesRegex(WormHold, "A1_CATALOG_STOP_GRANT_OR_HEAD_CHANGED"):
            self.run_checked(lambda: self.native.__setitem__("stop", True))
        self.assertEqual(self.calls, 1)

    def test_epoch_change_during_metadata_parse_discards_final_candidate(self):
        with self.assertRaisesRegex(WormHold, "A1_CATALOG_STOP_GRANT_OR_HEAD_CHANGED"):
            self.run_checked(lambda: self.native.__setitem__("epoch", 10))
        self.assertEqual(self.calls, 1)

    def test_native_grant_change_during_metadata_parse_discards_final_candidate(self):
        with self.assertRaisesRegex(WormHold, "A1_CATALOG_STOP_GRANT_OR_HEAD_CHANGED"):
            self.run_checked(lambda: self.native.__setitem__("grant", False))
        self.assertEqual(self.calls, 1)

    def test_unchanged_native_witness_keeps_readonly_review(self):
        result = self.run_checked(lambda: None)
        self.assertEqual(result["network_calls"], 1)
        self.assertEqual(result["candidates"][0]["license"], "REVIEW_REQUIRED")
        self.assertFalse(result["native_install_approved"])


if __name__ == "__main__":
    unittest.main()
