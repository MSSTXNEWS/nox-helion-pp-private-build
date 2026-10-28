"""Windows-targetable component contract tests against PINNED real owner source.

The workflow checks out exact Git commits for P02/P03/P05/PACK01 read-only.
These tests are synthetic in-process scenarios, NOT a final EXE test.
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys
import threading
import time
import unittest
from datetime import datetime, timezone, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "coordination" / "e06" / "adapters"))
OWNER = pathlib.Path(os.environ["NOX_G2_OWNER_FIXTURE_ROOT"])
# Import actual pinned owner modules (never a substituted mock implementation).
sys.path.insert(0, str(OWNER / "P02"))
sys.path.insert(0, str(OWNER / "P03"))
sys.path.insert(0, str(OWNER / "PACK01"))
from native_bridge import NoxPackHost, NativeSession, BoundPort, ExistingP02Adapter
from p03_onehost_port import P03OneHostPort
from p02_capabilities import Identity, authorize_private_mobile
from g2_space_mobile import (
    G2Hold, G2Denied, G2OneHostBinder, ExistingE05Projection,
    PrivateMobileContract, relay_existing_events_v3,
)

G2_RUN = "NOX-V16-E06-G2-05-20261028-C01"
NOW = datetime(2026, 10, 28, 3, 10, tzinfo=timezone.utc)
SOURCE = "a" * 64
OWNER_SHA = {"P02": "b" * 64, "P03": "c" * 64, "P05": "d" * 64}
FEED_ID = {"space.news": "rss1", "space.weather": "openmeteo",
           "space.fx": "ecb", "space.bitcoin": "btc",
           "space.brent": "brent"}


def utc(t=NOW):
    return t.isoformat().replace("+00:00", "Z")


class FakeOllama:
    def __init__(self):
        self.stops = 0
    def models(self):
        return ["qwen3:4b"]
    def stream(self, model, history):
        yield {"delta": "ready", "done": True}
    def stop(self):
        self.stops += 1


class FakeStore:
    def history(self, tenant, principal, chat, limit):
        return []
    def add_message(self, tenant, principal, chat, role, content):
        return "saved"
    def store_file(self, *args):
        return {"storedId": "fixture-only"}


class FakeE05:
    def __init__(self):
        self.run_id = G2_RUN
        self.at = NOW
        self.live = True
        self.seal = False
        self.tile_status = "SOURCE_DATED"
        self.sensors = []
        self.progress = 99
    def available(self, route):
        return self.live
    def product_receipts_sealed(self):
        return self.seal
    def snapshot(self, _session):
        return {
            "Schema": "NOX-E05-READONLY-v1",
            "RunId": self.run_id, "SnapshotUtc": utc(self.at),
            "Access": "READ_ONLY",
            "Tiles": [{"FeedId": key, "Source": "OWNER5_APPROVED",
                       "Status": self.tile_status, "SourceUtc": utc(),
                       "FetchedUtc": utc(), "Preview": None}
                      for key in FEED_ID.values()],
            "Hardware": list(self.sensors),
            "ProductProgress": self.progress,
        }


class G2ComponentTests(unittest.TestCase):
    def setUp(self):
        catalog = json.loads((OWNER / "PACK01" / "catalog.json").read_text(encoding="utf-8"))
        self.host = NoxPackHost(catalog)
        self.ollama = FakeOllama()
        self.p02 = ExistingP02Adapter(self.ollama, FakeStore())
        self.p03 = P03OneHostPort(
            self.ollama,
            catalog_path=OWNER / "P03" / "catalog30.discovery.json",
        )
        self.e05_fake = FakeE05()
        self.e05 = ExistingE05Projection(
            self.e05_fake, run_id=G2_RUN, feed_ids=FEED_ID, clock=lambda: NOW)
        self.session = NativeSession(
            "tenant", "user", "chat", frozenset(self.host.routes),
            frozenset({"mobile.connect", "chat.history", "chat.voice"}))
        self.approval = True
        self.registry_lock = threading.RLock()
        self.identity = Identity("tenant", "user", "HELION", "Persona",
                                 "auth-session")
        self.peer_ok = True
        self.csrf_ok = True
        self.remote_gateway = True # synthetic owner-host health attestation, not public HTTP
        self.proof_expiry = time.monotonic() + 45
        def peer(_session):
            return {
                "identity": self.identity, "verified_private_peer": self.peer_ok,
                "trusted_origin": "https://nox.tailnet.example",
                "observed_origin": "https://nox.tailnet.example",
                "expected_csrf": b"x" * 32,
                "received_csrf": b"x" * 32 if self.csrf_ok else b"y" * 32,
                "native_session_approved": True, "expires_at": self.proof_expiry,
            }
        self.mobile = PrivateMobileContract(
            authorize_private_mobile, peer, self.host, time.monotonic,
            gateway_ready=lambda: self.remote_gateway)

    def bind(self, *, source=SOURCE, owner_sha=None, mobile=True,
             preimage=True, p03=None, p02=None):
        binder = G2OneHostBinder(
            self.host, BoundPort,
            existing_p02=p02 if p02 is not None else self.p02,
            existing_p03=p03 if p03 is not None else self.p03,
            e05=self.e05, mobile=self.mobile if mobile else None,
            existing_p02_voice=None, source_lock_sha256=source,
            owner_receipts_sha256=owner_sha if owner_sha is not None else OWNER_SHA,
            verify_original_preimages=lambda s, r: preimage,
            existing_host_mutation_lock=self.registry_lock)
        return binder.bind()

    def test_01_exact_pinned_original_host_and_adapters(self):
        got = self.bind()
        self.assertEqual(len(got), 16)
        self.assertEqual(len(self.host.routes), 50)
        self.assertEqual(len(self.host.ports), 16)
        self.assertTrue({"models.catalog", "models.installed", "models.digest"} <= got)
        self.assertTrue({"space.news", "space.brent", "system.telemetry"} <= got)
        self.assertEqual(self.host.execute("models.installed", {}, self.session)["models"][0]["tag"],
                         "qwen3:4b")

    def test_02_original_source_lock_required(self):
        with self.assertRaises(G2Hold):
            self.bind(source=None)
        self.assertFalse(self.host.ports)

    def test_03_no_fake_owner_sha(self):
        with self.assertRaises(G2Hold):
            self.bind(owner_sha={"P02": "wrong", "P03": "c" * 64, "P05": "d" * 64})
        self.assertFalse(self.host.ports)

    def test_04_real_preimage_check_fail_closed(self):
        with self.assertRaises(G2Hold):
            self.bind(preimage=False)
        self.assertFalse(self.host.ports)

    def test_05_owner_collision_preserves_existing_binding(self):
        before = BoundPort(lambda s, p: "existing", lambda: True, "original receipt", 5)
        self.host.bind("space.news", before)
        with self.assertRaises(G2Hold):
            self.bind()
        self.assertIs(self.host.ports["space.news"], before)
        self.assertEqual(len(self.host.ports), 1)

    def test_06_atomic_rollback_after_owner_failure(self):
        class BrokenP03:
            def register(self, host, port, receipt):
                host.bind("models.catalog", port(
                    lambda s, p: {}, lambda: True, receipt, 3))
                raise RuntimeError("injected owner failure")
        with self.assertRaises(G2Hold):
            self.bind(p03=BrokenP03())
        self.assertEqual(self.host.ports, {})

    def test_07_catalog_discovery_never_auto_downloads(self):
        self.bind()
        result = self.host.execute("models.catalog", {}, self.session)
        self.assertEqual(len(result["models"]), 30)
        self.assertFalse(result["downloadEligible"])
        self.assertNotIn("models.pull", self.host.ports)

    def test_08_stop_reuses_existing_client(self):
        self.bind()
        r = self.host.execute("chat.stop", {}, self.session)
        self.assertTrue(r["stopRequested"])
        self.assertEqual(self.ollama.stops, 1)

    def test_09_readonly_news_source_datetime(self):
        self.bind()
        result = self.host.execute("space.news", {}, self.session)
        self.assertEqual(result["status"], "SOURCE_DATED")
        self.assertEqual(result["source"], "OWNER5_APPROVED")
        self.assertIsNone(result["preview"])

    def test_10_feed_stale_and_fake_price_not_filled(self):
        self.e05_fake.tile_status = "STALE"
        self.bind()
        result = self.host.execute("space.brent", {}, self.session)
        self.assertEqual(result["status"], "STALE")
        self.assertIsNone(result["preview"])
        self.assertIsNone(result["source"])

    def test_11_feed_no_current_owner_mapping_n_d(self):
        self.e05_fake.snapshot = lambda _s: {
            **FakeE05.snapshot(self.e05_fake, _s), "Tiles": []
        }
        self.bind()
        self.assertEqual(self.host.execute("space.fx", {}, self.session)["status"], "N_D")

    def test_12_unverified_progress_never_99_percent(self):
        self.bind()
        result = self.host.execute("system.telemetry", {}, self.session)
        self.assertIsNone(result["productProgress"])
        self.assertEqual(result["productProgressStatus"], "N_D")

    def test_13_fresh_sealed_progress_is_explicitly_separate(self):
        self.e05_fake.seal = True
        self.bind()
        r = self.host.execute("system.telemetry", {}, self.session)
        self.assertEqual(r["productProgress"], 99)
        self.assertEqual(r["productProgressStatus"], "VERIFIED")

    def test_14_unverified_sensor_is_n_d_not_zero(self):
        self.e05_fake.sensors = [{
            "Key": "gpu.percent", "Value": 86, "Status": "UNVERIFIED",
            "Source": "fake", "ObservedAtUtc": utc()}]
        self.bind()
        r = self.host.execute("system.telemetry", {}, self.session)
        self.assertIsNone(r["sensors"]["gpu.percent"]["value"])

    def test_15_live_sensor_with_source_uses_real_owner_data_only(self):
        self.e05_fake.sensors = [{
            "Key": "cpu.system.percent", "Value": 21, "Status": "LIVE",
            "Source": "OWNER5_HARDWARE", "ObservedAtUtc": utc()}]
        self.bind()
        r = self.host.execute("system.telemetry", {}, self.session)
        self.assertEqual(r["sensors"]["cpu.system.percent"]["value"], 21)

    def test_16_inconsistent_vram_values_do_not_escape(self):
        self.e05_fake.sensors = [
            {"Key": "gpu.vram.used_bytes", "Value": 30, "Status": "LIVE",
             "Source": "SENSOR_A", "ObservedAtUtc": utc()},
            {"Key": "gpu.vram.total_bytes", "Value": 20, "Status": "LIVE",
             "Source": "SENSOR_A", "ObservedAtUtc": utc()},
        ]
        self.bind()
        result = self.host.execute("system.telemetry", {}, self.session)
        self.assertIsNone(result["sensors"]["gpu.vram.used_bytes"]["value"])

    def test_17_reject_p05_foreign_run_and_raw_urls(self):
        self.e05_fake.run_id = "FOREIGN"
        self.bind()
        with self.assertRaises(G2Hold):
            self.e05.read(self.session, "space.weather", {})
        with self.assertRaises(G2Denied):
            self.e05.read(self.session, "space.news", {"url": "http://127.0.0.1"})

    def test_18_private_gateway_policy_original_owner2(self):
        self.bind()
        result = self.host.execute(
            "mobile.connect", {"want": ["space.news", "helion.chat"]}, self.session)
        self.assertEqual(result["mode"], "PRIVATE_NATIVE_ATTESTED")
        self.assertTrue(result["gatewayListening"])
        self.assertEqual(result["allowed"], ["space.news", "helion.chat"])

    def test_19_public_peer_denied(self):
        self.peer_ok = False
        self.bind()
        with self.assertRaises(G2Denied):
            self.mobile.connect(self.session, {"want": ["space.news"]})

    def test_20_bad_csrf_denied(self):
        self.csrf_ok = False
        self.bind()
        with self.assertRaises(G2Denied):
            self.mobile.connect(self.session, {"want": ["space.news"]})

    def test_21_remote_sip_training_installs_forbidden(self):
        self.bind()
        for unsafe in ("calls.dial", "training.start", "models.pull", "system.pc_control"):
            with self.subTest(unsafe=unsafe):
                with self.assertRaises(G2Denied):
                    self.mobile.connect(self.session, {"want": [unsafe]})
        self.assertNotIn("calls.dial", self.host.ports)

    def test_22_remote_page_claims_never_authenticate(self):
        self.bind()
        with self.assertRaises(G2Denied):
            self.mobile.connect(self.session, {
                "want": ["space.news"], "native_session_approved": True
            })

    def test_23_expired_private_session_denied(self):
        self.proof_expiry = time.monotonic() - 1
        self.bind()
        with self.assertRaises(G2Denied):
            self.mobile.connect(self.session, {"want": ["helion.chat"]})

    def test_24_existing_events_v3_only_one_publisher(self):
        seen = []
        event = {"schema": "NOX-INSTALLER-EVENT-v3", "run_id": G2_RUN,
                 "event_id": "evt1", "event_type": "task.started",
                 "task_id": "E06-05", "package_id": "P05",
                 "action_id": "space", "timestamp_utc": utc(),
                 "state": "RUNNING", "source": "E05",
                 "message": "Started", "evidence_verified": False}
        self.assertTrue(relay_existing_events_v3(
            event, run_id=G2_RUN, trusted_owner=lambda: True,
            existing_publish=lambda e: (seen.append(e) or True)))
        self.assertEqual(seen, [event])

    def test_25_reject_unapproved_cpu_event_and_missing_source_lock(self):
        event = {"schema": "NOX-INSTALLER-EVENT-v3", "run_id": G2_RUN,
                 "event_id": "evt2", "event_type": "cpu.sample",
                 "task_id": "E06-05", "package_id": "P05",
                 "action_id": "hardware", "timestamp_utc": utc(),
                 "state": "RUNNING", "source": "E05",
                 "message": "CPU", "evidence_verified": False}
        with self.assertRaises(G2Denied):
            relay_existing_events_v3(event, run_id=G2_RUN,
                                     trusted_owner=lambda: True,
                                     existing_publish=lambda _: True)
        with self.assertRaises(G2Hold):
            relay_existing_events_v3(event, run_id=G2_RUN,
                                     trusted_owner=lambda: False,
                                     existing_publish=lambda _: True)

    def test_26_voice_and_sip_unavailable_is_hold(self):
        self.bind()
        self.assertNotIn("translate.ru_es", self.host.ports)
        self.assertNotIn("maestro.spanish", self.host.ports)
        self.assertNotIn("calls.dial", self.host.ports)

    def test_27_second_binder_cannot_overwrite_first(self):
        self.bind()
        before = dict(self.host.ports)
        with self.assertRaises(G2Hold):
            self.bind()
        self.assertEqual(self.host.ports, before)

    def test_29_offline_mobile_gateway_not_advertised_as_live(self):
        self.remote_gateway = False
        self.bind()
        self.assertNotIn("mobile.connect", self.host.ports)
        self.assertFalse(self.host.advertise(self.session)["mobile.connect"]["enabled"])
        with self.assertRaises(G2Hold):
            self.mobile.connect(self.session, {"want": ["space.news"]})

    def test_28_invalid_telemetry_snapshot_timestamp_rejected(self):
        self.e05_fake.at = NOW - timedelta(minutes=3)
        self.bind()
        with self.assertRaises(G2Hold):
            self.e05.read(self.session, "system.telemetry", {})


if __name__ == "__main__":
    unittest.main()
