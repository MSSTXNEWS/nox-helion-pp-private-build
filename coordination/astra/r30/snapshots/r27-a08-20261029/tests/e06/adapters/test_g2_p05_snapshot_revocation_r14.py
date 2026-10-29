"""E06 source-only P05 native snapshot-revocation regression.

No network, mock data passed as LIVE, new service, or public gateway.
Run with: python -m unittest tests/e06/adapters/test_g2_p05_snapshot_revocation_r14.py
These tests are NOT equivalent to installed Windows / E07 acceptance.
"""
from __future__ import annotations

import pathlib
import sys
import unittest
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "coordination" / "e06" / "adapters"))
from g2_space_mobile import ExistingE05Projection, G2Hold

NOW = datetime(2026, 10, 28, 19, 5, tzinfo=timezone.utc)
FEEDS = {
    "space.news": "owner-news",
    "space.weather": "owner-weather",
    "space.fx": "owner-fx",
    "space.bitcoin": "owner-btc",
    "space.brent": "owner-brent",
}


class Owner5:
    def __init__(self, *, revoke=False, fail_second=False, live=True):
        self.live = live
        self.revoke = revoke
        self.fail_second = fail_second
        self.probes = 0

    def available(self, route):
        self.probes += 1
        if self.fail_second and self.probes > 1:
            raise RuntimeError("native provider consent revoked")
        return self.live

    def snapshot(self, session):
        if self.revoke:
            self.live = False
        now = NOW.isoformat().replace("+00:00", "Z")
        return {
            "Schema": "NOX-E05-READONLY-v1",
            "RunId": "E06-P05-R14",
            "SnapshotUtc": now,
            "Access": "READ_ONLY",
            "Tiles": [{
                "FeedId": "owner-news", "Status": "SOURCE_DATED",
                "Source": "test-only-owner-5", "SourceUtc": now,
                "FetchedUtc": now
            }],
            "Hardware": [],
            "ProductProgress": None,
        }


def projection(owner):
    return ExistingE05Projection(
        owner, run_id="E06-P05-R14", feed_ids=FEEDS, clock=lambda: NOW)


class P05NativeRevocation(unittest.TestCase):
    def test_01_feed_revoked_inside_snapshot_denied(self):
        with self.assertRaisesRegex(G2Hold, "revoked during snapshot"):
            projection(Owner5(revoke=True)).read(None, "space.news", {})

    def test_02_telemetry_revoked_inside_snapshot_denied(self):
        with self.assertRaisesRegex(G2Hold, "revoked during snapshot"):
            projection(Owner5(revoke=True)).read(None, "system.telemetry", {})

    def test_03_provider_throws_on_second_proof_denied(self):
        with self.assertRaisesRegex(G2Hold, "revoked during snapshot"):
            projection(Owner5(fail_second=True)).read(None, "space.news", {})

    def test_04_unrevoked_dated_feed_retains_source(self):
        owner = Owner5()
        result = projection(owner).read(None, "space.news", {})
        self.assertEqual(result["status"], "SOURCE_DATED")
        self.assertEqual(result["source"], "test-only-owner-5")
        self.assertEqual(owner.probes, 2)

    def test_05_unrevoked_telemetry_requires_actual_sensor(self):
        result = projection(Owner5()).read(None, "system.telemetry", {})
        self.assertEqual(result["sensors"], {})
        self.assertIsNone(result["productProgress"])
        self.assertEqual(result["productProgressStatus"], "N_D")

    def test_06_initially_unavailable_owner_remains_hold(self):
        with self.assertRaises(G2Hold):
            projection(Owner5(live=False)).read(None, "space.news", {})


if __name__ == "__main__":
    unittest.main()
