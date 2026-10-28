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


def verified_event():
    return {"schema": "NOX-INSTALLER-EVENT-v3", "run_id": G2_RUN,
            "event_id": "evt-r04", "event_type": "task.completed",
            "task_id": "G2-05-R04", "package_id": "P05",
            "action_id": "space.news", "timestamp_utc": utc(),
            "state": "COMPLETED", "source": "E05",
            "message": "fixture", "evidence_verified": True}


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


    def test_30_native_gateway_revoked_after_binding_denies_mobile(self):
        self.bind()
        self.remote_gateway = False
        self.assertFalse(self.host.advertise(self.session)["mobile.connect"]["enabled"])
        with self.assertRaises(G2Hold):
            self.mobile.connect(self.session, {"want": ["space.news"]})

    def test_31_owner_receipts_are_snapshotted_before_preimage_seal(self):
        receipts = dict(OWNER_SHA)
        binder = G2OneHostBinder(
            self.host, BoundPort,
            existing_p02=self.p02, existing_p03=self.p03,
            e05=self.e05, mobile=self.mobile,
            existing_p02_voice=None, source_lock_sha256=SOURCE,
            owner_receipts_sha256=receipts,
            verify_original_preimages=lambda s, r: r == OWNER_SHA,
            existing_host_mutation_lock=self.registry_lock)
        receipts["P02"] = "0" * 64
        got = binder.bind()
        self.assertIn("models.catalog", got)
        self.assertEqual(self.host.ports["models.catalog"].evidence_id, OWNER_SHA["P03"])

    def test_32_reject_nonmapping_owner_receipt_contract(self):
        with self.assertRaises(G2Hold):
            G2OneHostBinder(
                self.host, BoundPort,
                existing_p02=self.p02, existing_p03=self.p03,
                e05=self.e05, mobile=self.mobile,
                existing_p02_voice=None, source_lock_sha256=SOURCE,
                owner_receipts_sha256=None,
                verify_original_preimages=lambda s, r: True,
                existing_host_mutation_lock=self.registry_lock)


    def test_33_gateway_revoked_while_host_advertises(self):
        self.bind()
        original = self.host.advertise
        def revoke(session):
            answer = original(session)
            self.remote_gateway = False
            return answer
        self.host.advertise = revoke
        with self.assertRaises(G2Hold):
            self.mobile.connect(self.session, {"want": ["space.news"]})

    def test_34_native_private_peer_revoked_while_advertising(self):
        self.bind()
        original = self.host.advertise
        def revoke(session):
            answer = original(session)
            self.peer_ok = False
            return answer
        self.host.advertise = revoke
        with self.assertRaises(G2Denied):
            self.mobile.connect(self.session, {"want": ["space.news"]})

    def test_35_malformed_host_advertisement_fails_closed(self):
        self.bind()
        self.host.advertise = lambda _session: None
        with self.assertRaises(G2Hold):
            self.mobile.connect(self.session, {"want": ["space.news"]})

    def test_36_source_lock_drifts_during_owner_registration(self):
        checks = []
        def changing_preimage(source_sha, receipts):
            checks.append((source_sha, dict(receipts)))
            return len(checks) == 1
        binder = G2OneHostBinder(
            self.host, BoundPort,
            existing_p02=self.p02, existing_p03=self.p03,
            e05=self.e05, mobile=self.mobile, existing_p02_voice=None,
            source_lock_sha256=SOURCE, owner_receipts_sha256=OWNER_SHA,
            verify_original_preimages=changing_preimage,
            existing_host_mutation_lock=self.registry_lock)
        with self.assertRaises(G2Hold):
            binder.bind()
        self.assertEqual(len(checks), 2)
        self.assertEqual(self.host.ports, {})

    def test_37_owner_overwrites_prior_port_rollback_exact(self):
        previous = BoundPort(lambda s, p: "untouched", lambda: True,
                             "older-owner-receipt", 2)
        self.host.ports["custom.owner.route"] = previous
        class MalformedP02:
            def register(self, host, receipt):
                host.ports["custom.owner.route"] = BoundPort(
                    lambda s, p: "overwritten", lambda: True, receipt, 2)
                return frozenset()
        with self.assertRaises(G2Hold):
            self.bind(p02=MalformedP02())
        self.assertIs(self.host.ports["custom.owner.route"], previous)
        self.assertEqual(len(self.host.ports), 1)


    def test_38_feed_source_after_fetch_is_quarantined(self):
        self.bind()
        original = self.e05_fake.snapshot
        def invalid(session):
            raw = original(session)
            raw["Tiles"][0]["SourceUtc"] = utc(NOW)
            raw["Tiles"][0]["FetchedUtc"] = utc(NOW - timedelta(seconds=5))
            return raw
        self.e05_fake.snapshot = invalid
        r = self.host.execute("space.news", {}, self.session)
        self.assertEqual(r["status"], "N_D")
        self.assertIsNone(r["source"])

    def test_39_feed_fetch_after_snapshot_is_quarantined(self):
        self.e05_fake.at = NOW - timedelta(seconds=6)
        self.bind()
        r = self.host.execute("space.news", {}, self.session)
        self.assertEqual(r["status"], "N_D")

    def test_40_sensor_observation_after_snapshot_is_n_d(self):
        self.e05_fake.at = NOW - timedelta(seconds=3)
        self.e05_fake.sensors = [{
            "Key": "cpu.system.percent", "Value": 32, "Status": "LIVE",
            "Source": "OWNER5_HARDWARE", "ObservedAtUtc": utc(NOW)}]
        self.bind()
        r = self.host.execute("system.telemetry", {}, self.session)
        self.assertIsNone(r["sensors"]["cpu.system.percent"]["value"])

    def test_41_vram_requires_same_sample_instant(self):
        self.e05_fake.sensors = [
            {"Key": "gpu.vram.used_bytes", "Value": 3, "Status": "LIVE",
             "Source": "OWNER5_HARDWARE", "ObservedAtUtc": utc(NOW)},
            {"Key": "gpu.vram.total_bytes", "Value": 8, "Status": "LIVE",
             "Source": "OWNER5_HARDWARE",
             "ObservedAtUtc": utc(NOW - timedelta(seconds=2))}]
        self.bind()
        r = self.host.execute("system.telemetry", {}, self.session)
        self.assertIsNone(r["sensors"]["gpu.vram.used_bytes"]["value"])
        self.assertIsNone(r["sensors"]["gpu.vram.total_bytes"]["value"])

    def test_42_verified_event_without_native_receipt_is_hold(self):
        published = []
        with self.assertRaises(G2Hold):
            relay_existing_events_v3(
                verified_event(), run_id=G2_RUN, trusted_owner=lambda: True,
                existing_publish=lambda event: (published.append(event) or True))
        self.assertEqual(published, [])

    def test_43_verified_event_with_test_only_receipt_can_relay(self):
        published = []
        event = verified_event()
        self.assertTrue(relay_existing_events_v3(
            event, run_id=G2_RUN, trusted_owner=lambda: True,
            trusted_evidence=lambda e: e["event_id"] == "evt-r04",
            existing_publish=lambda e: (published.append(e) or True)))
        self.assertEqual(published, [event])
        self.assertIsNot(published[0], event)

    def test_44_native_event_attestor_exception_fails_closed(self):
        published = []
        def broken(_event):
            raise RuntimeError("native receipt offline")
        with self.assertRaises(G2Hold):
            relay_existing_events_v3(
                verified_event(), run_id=G2_RUN, trusted_owner=lambda: True,
                trusted_evidence=broken,
                existing_publish=lambda e: (published.append(e) or True))
        self.assertFalse(published)

    def test_45_csrf_rotation_during_host_advertise_denied(self):
        self.bind()
        original = self.host.advertise
        old_peer = self.mobile.peer
        csrf = [b"x" * 32]
        def rotated_peer(session):
            proof = old_peer(session)
            proof["expected_csrf"] = csrf[0]
            proof["received_csrf"] = csrf[0]
            return proof
        self.mobile.peer = rotated_peer
        def rotate(session):
            answer = original(session)
            csrf[0] = b"z" * 32
            return answer
        self.host.advertise = rotate
        with self.assertRaises(G2Denied):
            self.mobile.connect(self.session, {"want": ["space.news"]})

    def test_46_source_lock_revoked_during_evidence_attestation(self):
        state = [True, False]
        published = []
        def seal():
            return state.pop(0)
        with self.assertRaises(G2Hold):
            relay_existing_events_v3(
                verified_event(), run_id=G2_RUN, trusted_owner=seal,
                trusted_evidence=lambda _: True,
                existing_publish=lambda e: (published.append(e) or True))
        self.assertEqual(published, [])


    def test_47_owner2_missing_mandatory_route_rolls_back(self):
        class PartialP02:
            def register(_, host, *, receipt):
                host.bind("helion.chat", BoundPort(
                    lambda s, p: {}, lambda: True, receipt, 2))
                return frozenset({"helion.chat"})
        with self.assertRaises(G2Hold):
            self.bind(p02=PartialP02())
        self.assertEqual(self.host.ports, {})

    def test_48_owner2_forged_receipt_rolls_back(self):
        real = self.p02
        class ForgedP02:
            def register(_, host, *, receipt):
                wired = real.register(host, receipt=receipt)
                port = host.ports["helion.chat"]
                host.ports["helion.chat"] = BoundPort(
                    port.call, port.available, "f" * 64, 2)
                return wired
        with self.assertRaises(G2Hold):
            self.bind(p02=ForgedP02())
        self.assertEqual(self.host.ports, {})

    def test_49_owner3_missing_mandatory_route_rolls_back(self):
        class PartialP03:
            def register(_, host, port_type, *, receipt):
                host.bind("models.catalog", port_type(
                    lambda s, p: {}, lambda: True, receipt, 3))
                return frozenset({"models.catalog"})
        with self.assertRaises(G2Hold):
            self.bind(p03=PartialP03())
        self.assertEqual(self.host.ports, {})

    def test_50_owner3_forged_receipt_rolls_back(self):
        real = self.p03
        class ForgedP03:
            def register(_, host, port_type, *, receipt):
                wired = real.register(host, port_type, receipt=receipt)
                port = host.ports["models.catalog"]
                host.ports["models.catalog"] = BoundPort(
                    port.call, port.available, "e" * 64, 3)
                return wired
        with self.assertRaises(G2Hold):
            self.bind(p03=ForgedP03())
        self.assertEqual(self.host.ports, {})

    def test_51_unbound_claimed_owner_route_is_hold(self):
        real = self.p02
        class ExtraP02:
            def register(_, host, *, receipt):
                return real.register(host, receipt=receipt) | {"route.not.real"}
        with self.assertRaises(G2Hold):
            self.bind(p02=ExtraP02())
        self.assertEqual(self.host.ports, {})

    def test_52_orphan_vram_used_is_not_live(self):
        self.e05_fake.sensors = [{
            "Key": "gpu.vram.used_bytes", "Value": 4096, "Status": "LIVE",
            "Source": "OWNER5_GPU", "ObservedAtUtc": utc()}]
        self.bind()
        got = self.host.execute("system.telemetry", {}, self.session)["sensors"]
        self.assertIsNone(got["gpu.vram.used_bytes"]["value"])
        self.assertIsNone(got["gpu.vram.total_bytes"]["value"])

    def test_53_orphan_vram_total_is_not_live(self):
        self.e05_fake.sensors = [{
            "Key": "gpu.vram.total_bytes", "Value": 8192, "Status": "LIVE",
            "Source": "OWNER5_GPU", "ObservedAtUtc": utc()}]
        self.bind()
        got = self.host.execute("system.telemetry", {}, self.session)["sensors"]
        self.assertIsNone(got["gpu.vram.used_bytes"]["value"])
        self.assertIsNone(got["gpu.vram.total_bytes"]["value"])

    def test_54_fractional_vram_bytes_are_not_live(self):
        self.e05_fake.sensors = [
            {"Key": "gpu.vram.used_bytes", "Value": 4.5, "Status": "LIVE",
             "Source": "OWNER5_GPU", "ObservedAtUtc": utc()},
            {"Key": "gpu.vram.total_bytes", "Value": 8192, "Status": "LIVE",
             "Source": "OWNER5_GPU", "ObservedAtUtc": utc()}]
        self.bind()
        got = self.host.execute("system.telemetry", {}, self.session)["sensors"]
        self.assertIsNone(got["gpu.vram.used_bytes"]["value"])
        self.assertIsNone(got["gpu.vram.total_bytes"]["value"])

    def test_55_nontext_event_message_is_denied(self):
        event = verified_event()
        event["message"] = {"price": 123}
        with self.assertRaises(G2Denied):
            relay_existing_events_v3(event, run_id=G2_RUN,
                trusted_owner=lambda: True, trusted_evidence=lambda _: True,
                existing_publish=lambda _: True)

    def test_56_unverified_event_source_revoked_before_publish(self):
        state = iter([True, False])
        outgoing = []
        event = verified_event()
        event["evidence_verified"] = False
        with self.assertRaises(G2Hold):
            relay_existing_events_v3(event, run_id=G2_RUN,
                trusted_owner=lambda: next(state),
                existing_publish=lambda e: (outgoing.append(e) or True))
        self.assertEqual(outgoing, [])

    def test_57_sip_native_provider_revocation_prevents_readiness(self):
        class Voice:
            online = True
            def available(self, route):
                return True
            def verified_sip(self):
                return self.online
            def dial_with_native_quote(self, session, payload):
                raise AssertionError("No paid call in a component test")
        voice = Voice()
        self.host.native_approve = lambda *_args: True
        binder = G2OneHostBinder(
            self.host, BoundPort, existing_p02=self.p02,
            existing_p03=self.p03, e05=self.e05, mobile=self.mobile,
            existing_p02_voice=voice, source_lock_sha256=SOURCE,
            owner_receipts_sha256=OWNER_SHA,
            verify_original_preimages=lambda *_args: True,
            existing_host_mutation_lock=self.registry_lock)
        binder.bind()
        self.assertIn("calls.dial", self.host.ports)
        self.assertTrue(self.host.ports["calls.dial"].available())
        voice.online = False
        self.assertFalse(self.host.ports["calls.dial"].available())

    def test_58_blank_feed_source_is_not_verified(self):
        original = self.e05_fake.snapshot
        def fake(session):
            raw = original(session)
            raw["Tiles"][0]["Source"] = "   "
            return raw
        self.e05_fake.snapshot = fake
        self.bind()
        got = self.host.execute("space.news", {}, self.session)
        self.assertEqual(got["status"], "N_D")
        self.assertIsNone(got["source"])

    def test_59_unbounded_event_message_is_denied(self):
        event = verified_event()
        event["message"] = "X" * 481
        with self.assertRaises(G2Denied):
            relay_existing_events_v3(event, run_id=G2_RUN,
                trusted_owner=lambda: True, trusted_evidence=lambda _: True,
                existing_publish=lambda _: True)


    def test_60_evidence_callback_cannot_rewrite_published_snapshot(self):
        event = verified_event()
        event["metadata"] = {"devices": ["native"]}
        published = []
        def attestor(copy):
            copy["metadata"]["devices"].append("injected")
            copy["message"] = "rewritten"
            return True
        self.assertTrue(relay_existing_events_v3(
            event, run_id=G2_RUN, trusted_owner=lambda: True,
            trusted_evidence=attestor,
            existing_publish=lambda x: (published.append(x) or True)))
        self.assertEqual(published[0]["metadata"], {"devices": ["native"]})
        self.assertEqual(published[0]["message"], "fixture")
        self.assertEqual(event["metadata"], {"devices": ["native"]})

    def test_61_caller_mutation_during_evidence_denies_publish(self):
        event, published = verified_event(), []
        def attestor(_copy):
            event["message"] = "late mutation"
            return True
        with self.assertRaises(G2Hold):
            relay_existing_events_v3(
                event, run_id=G2_RUN, trusted_owner=lambda: True,
                trusted_evidence=attestor,
                existing_publish=lambda x: (published.append(x) or True))
        self.assertEqual(published, [])

    def test_62_owner_mutation_before_publish_denies(self):
        event, published, state = verified_event(), [], [0]
        def owner():
            state[0] += 1
            if state[0] == 3:
                event["source"] = "unexpected"
            return True
        with self.assertRaises(G2Hold):
            relay_existing_events_v3(
                event, run_id=G2_RUN, trusted_owner=owner,
                trusted_evidence=lambda _: True,
                existing_publish=lambda x: (published.append(x) or True))
        self.assertEqual(published, [])

    def test_63_binary_event_extra_denied(self):
        event = verified_event()
        event["binary"] = b"secret"
        with self.assertRaises(G2Denied):
            relay_existing_events_v3(event, run_id=G2_RUN,
                trusted_owner=lambda: True, trusted_evidence=lambda _: True,
                existing_publish=lambda _: True)

    def test_64_nonfinite_event_extra_denied(self):
        event = verified_event()
        event["value"] = float("nan")
        with self.assertRaises(G2Denied):
            relay_existing_events_v3(event, run_id=G2_RUN,
                trusted_owner=lambda: True, trusted_evidence=lambda _: True,
                existing_publish=lambda _: True)

    def test_65_oversized_event_extra_denied(self):
        event = verified_event()
        event["padding"] = "X" * 8193
        with self.assertRaises(G2Denied):
            relay_existing_events_v3(event, run_id=G2_RUN,
                trusted_owner=lambda: True, trusted_evidence=lambda _: True,
                existing_publish=lambda _: True)

    def test_66_noncanonical_tuple_denied(self):
        event = verified_event()
        event["tuple_payload"] = ("one", "two")
        with self.assertRaises(G2Denied):
            relay_existing_events_v3(event, run_id=G2_RUN,
                trusted_owner=lambda: True, trusted_evidence=lambda _: True,
                existing_publish=lambda _: True)

    def test_67_valid_unicode_stable_event(self):
        event = verified_event()
        event["message"] = "Luz — свет"
        published = []
        self.assertTrue(relay_existing_events_v3(event, run_id=G2_RUN,
            trusted_owner=lambda: True, trusted_evidence=lambda _: True,
            existing_publish=lambda x: (published.append(x) or True)))
        self.assertEqual(published, [event])


    def test_68_list_event_type_denied(self):
        event, sent = verified_event(), []
        event["event_type"] = ["task.completed"]
        with self.assertRaises(G2Denied):
            relay_existing_events_v3(event, run_id=G2_RUN,
                trusted_owner=lambda: True, trusted_evidence=lambda _: True,
                existing_publish=lambda x: (sent.append(x) or True))
        self.assertEqual(sent, [])

    def test_69_dict_event_state_denied(self):
        event, sent = verified_event(), []
        event["state"] = {"state": "COMPLETED"}
        with self.assertRaises(G2Denied):
            relay_existing_events_v3(event, run_id=G2_RUN,
                trusted_owner=lambda: True, trusted_evidence=lambda _: True,
                existing_publish=lambda x: (sent.append(x) or True))
        self.assertEqual(sent, [])

    def test_70_unverified_completed_denied(self):
        event, sent = verified_event(), []
        event.update(event_type="task.completed", evidence_verified=False)
        with self.assertRaises(G2Hold):
            relay_existing_events_v3(event, run_id=G2_RUN,
                trusted_owner=lambda: True,
                existing_publish=lambda x: (sent.append(x) or True))
        self.assertEqual(sent, [])

    def test_71_unverified_model_stop_denied(self):
        event, sent = verified_event(), []
        event.update(event_type="model.stopped", state="RUNNING", evidence_verified=False)
        with self.assertRaises(G2Hold):
            relay_existing_events_v3(event, run_id=G2_RUN,
                trusted_owner=lambda: True,
                existing_publish=lambda x: (sent.append(x) or True))
        self.assertEqual(sent, [])

    def test_72_unverified_checkpoint_denied(self):
        event, sent = verified_event(), []
        event.update(event_type="checkpoint.saved", state="RUNNING", evidence_verified=False)
        with self.assertRaises(G2Hold):
            relay_existing_events_v3(event, run_id=G2_RUN,
                trusted_owner=lambda: True,
                existing_publish=lambda x: (sent.append(x) or True))
        self.assertEqual(sent, [])

    def test_73_unverified_acceptance_denied(self):
        event, sent = verified_event(), []
        event.update(event_type="acceptance.updated", state="RUNNING", evidence_verified=False)
        with self.assertRaises(G2Hold):
            relay_existing_events_v3(event, run_id=G2_RUN,
                trusted_owner=lambda: True,
                existing_publish=lambda x: (sent.append(x) or True))
        self.assertEqual(sent, [])

    def test_74_verified_terminal_with_owner_receipt(self):
        event, sent, seen = verified_event(), [], []
        self.assertTrue(relay_existing_events_v3(event, run_id=G2_RUN,
            trusted_owner=lambda: True,
            trusted_evidence=lambda x: (seen.append(x) or True),
            existing_publish=lambda x: (sent.append(x) or True)))
        self.assertEqual(seen, [event])
        self.assertEqual(sent, [event])

    def test_75_unverified_running_progress_permitted(self):
        event, sent = verified_event(), []
        event.update(event_type="task.progress", state="RUNNING", evidence_verified=False)
        self.assertTrue(relay_existing_events_v3(event, run_id=G2_RUN,
            trusted_owner=lambda: True,
            existing_publish=lambda x: (sent.append(x) or True)))
        self.assertEqual(sent, [event])

    def test_76_unhashable_sensor_does_not_abort_cpu(self):
        self.e05_fake.sensors = [
            {"Key": ["gpu.percent"], "Value": 99, "Status": "LIVE",
             "Source": "UNTRUSTED", "ObservedAtUtc": utc()},
            {"Key": "cpu.system.percent", "Value": 17, "Status": "LIVE",
             "Source": "OWNER5_HARDWARE", "ObservedAtUtc": utc()}]
        self.bind()
        sensors = self.host.execute("system.telemetry", {}, self.session)["sensors"]
        self.assertEqual(sensors["cpu.system.percent"]["value"], 17)
        self.assertNotIn("gpu.percent", sensors)

    def test_77_unhashable_route_denied(self):
        with self.assertRaises(G2Denied):
            self.e05.read(self.session, ["space.news"], {})

    def test_78_source_lock_callback_error_hold(self):
        def broken():
            raise RuntimeError("SourceLock unavailable")
        with self.assertRaises(G2Hold):
            relay_existing_events_v3(verified_event(), run_id=G2_RUN,
                trusted_owner=broken, trusted_evidence=lambda _: True,
                existing_publish=lambda _: True)

    def test_79_unverified_ready_denied(self):
        event, sent = verified_event(), []
        event.update(event_type="task.progress", state="READY", evidence_verified=False)
        with self.assertRaises(G2Hold):
            relay_existing_events_v3(event, run_id=G2_RUN,
                trusted_owner=lambda: True,
                existing_publish=lambda x: (sent.append(x) or True))
        self.assertEqual(sent, [])

    def test_80_unverified_stopped_denied(self):
        event, sent = verified_event(), []
        event.update(event_type="task.progress", state="STOPPED", evidence_verified=False)
        with self.assertRaises(G2Hold):
            relay_existing_events_v3(event, run_id=G2_RUN,
                trusted_owner=lambda: True,
                existing_publish=lambda x: (sent.append(x) or True))
        self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
