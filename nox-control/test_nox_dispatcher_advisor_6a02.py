"""6A02: catalog exhaustion never bypasses native owner lease/CAS or RAM gates."""
import importlib.util
from pathlib import Path
import unittest
import json
import tempfile

spec = importlib.util.spec_from_file_location(
    "nox_dispatcher_advisor", Path(__file__).with_name("nox_dispatcher_advisor.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def snapshot():
    return {
        "stop_active": False, "onehost": {"healthy": True},
        "s03": {"readback_verified": True}, "trainer": {"running": False},
        "gpu": {"temperature_sensor_valid": True},
        "disk": {"free_gib": 90},
        "native_queue": {
            "admission_state": "NATIVE_QUEUE_REVIEWED_CATALOG_EXHAUSTED",
            "jobs_started": 0,
            "workers": [{"state": "RUNNING", "current_task": None}],
            "maintenance_busy": False, "active_claims": False,
            "resource_headroom_bytes": 3*1024**3,
        },
    }


def codes(data, verifier=None):
    return [row["code"] for row in mod.assess(
        data, owner_snapshot_verifier=verifier)]


class NativeRefillSourceGateTests(unittest.TestCase):
    def test_missing_native_queue_is_explicit_hold(self):
        # Before this guard, a healthy-looking snapshot without any native
        # owner evidence could return NO_UNVERIFIED_TUNING instead of HOLD.
        for value in (None, False, [], "RUNNING"):
            with self.subTest(value=value):
                s = snapshot()
                s["native_queue"] = value
                found = codes(s)
                self.assertIn("NATIVE_QUEUE_UNVERIFIED", found)
                self.assertNotIn("NO_UNVERIFIED_TUNING", found)
                self.assertNotIn("NATIVE_REFILL_OWNER_REVIEW_REQUIRED", found)

    def test_idle_without_lease_and_source_is_hold(self):
        result = mod.assess(snapshot())
        self.assertIn("NATIVE_REFILL_OWNER_HOLD", [r["code"] for r in result])
        self.assertNotIn("IDLE_NATIVE_CATALOG_EXHAUSTED", [r["code"] for r in result])
        self.assertTrue(all("Publish one" not in row["advice"] for row in result))

    def test_attested_still_requires_live_owner_review(self):
        s = snapshot()
        s["native_queue"].update(owner_lease_cas_verified=True,
                                 immutable_task_source_verified=True,
                                 owner_evidence_age_sec=0)
        # A JSON payload cannot self-attest, even with age=0 and CAS=true.
        self.assertIn("NATIVE_REFILL_OWNER_HOLD", codes(s))
        observed = []
        def authenticated_owner_verifier(exact_snapshot):
            observed.append(exact_snapshot is s)
            return exact_snapshot is s
        self.assertIn("NATIVE_REFILL_OWNER_REVIEW_REQUIRED",
                      codes(s, authenticated_owner_verifier))
        self.assertNotIn("NATIVE_REFILL_OWNER_HOLD",
                         codes(s, authenticated_owner_verifier))
        self.assertEqual(observed, [True, True])

    def test_unverified_or_failed_owner_callback_holds(self):
        s = snapshot()
        s["native_queue"].update(owner_lease_cas_verified=True,
                                 immutable_task_source_verified=True,
                                 owner_evidence_age_sec=0)
        def raises(_):
            raise RuntimeError("missing owner attestation")
        for verifier in (None, lambda _: False, lambda _: 1, raises):
            with self.subTest(verifier=str(verifier)):
                self.assertIn("NATIVE_REFILL_OWNER_HOLD", codes(s, verifier))
                self.assertNotIn("NATIVE_REFILL_OWNER_REVIEW_REQUIRED",
                                 codes(s, verifier))

    def test_stale_or_malformed_owner_evidence_never_suggests_refill(self):
        for age in (None, -1, 31, True, 0.5, "0"):
            with self.subTest(age=age):
                s = snapshot()
                s["native_queue"].update(owner_lease_cas_verified=True,
                                         immutable_task_source_verified=True,
                                         owner_evidence_age_sec=age)
                self.assertIn("NATIVE_REFILL_OWNER_HOLD",
                              codes(s, lambda exact: exact is s))
                self.assertNotIn("NATIVE_REFILL_OWNER_REVIEW_REQUIRED",
                                 codes(s, lambda exact: exact is s))

    def test_owner_evidence_age_exact_boundary_is_review_only(self):
        # Boundary ages are caller-reported; even the positive case is only
        # a review hint, never an owner publisher authorization.
        for age, expected in ((0, "NATIVE_REFILL_OWNER_REVIEW_REQUIRED"),
                              (30, "NATIVE_REFILL_OWNER_REVIEW_REQUIRED"),
                              (31, "NATIVE_REFILL_OWNER_HOLD")):
            with self.subTest(age=age):
                s = snapshot()
                s["native_queue"].update(owner_lease_cas_verified=True,
                                         immutable_task_source_verified=True,
                                         owner_evidence_age_sec=age)
                self.assertIn(expected, codes(s, lambda exact: exact is s))
                rejected = ("NATIVE_REFILL_OWNER_HOLD" if age <= 30
                            else "NATIVE_REFILL_OWNER_REVIEW_REQUIRED")
                self.assertNotIn(rejected, codes(s, lambda exact: exact is s))

    def test_low_missing_or_bad_memory_is_not_admitted(self):
        for value in (None, 53_993_472, -1, 2.5*1024**3, True):
            with self.subTest(value=value):
                s = snapshot()
                s["native_queue"].update(owner_lease_cas_verified=True,
                                         immutable_task_source_verified=True,
                                         resource_headroom_bytes=value)
                self.assertIn("NATIVE_REFILL_OWNER_HOLD",
                              codes(s, lambda exact: exact is s))
                self.assertNotIn("NATIVE_REFILL_OWNER_REVIEW_REQUIRED",
                                 codes(s, lambda exact: exact is s))

    def test_active_claim_or_missing_maintenance_clearance_is_hold(self):
        for field, value in (("active_claims", True), ("maintenance_busy", True),
                             ("maintenance_busy", None)):
            with self.subTest(field=field, value=value):
                s = snapshot()
                s["native_queue"].update(owner_lease_cas_verified=True,
                                         immutable_task_source_verified=True)
                s["native_queue"][field] = value
                self.assertIn("NATIVE_REFILL_OWNER_HOLD",
                              codes(s, lambda exact: exact is s))

    def test_advice_output_cannot_overwrite_snapshot_or_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "owner-snapshot.json"
            original = json.dumps(snapshot(), sort_keys=True)
            evidence.write_text(original, encoding="utf8")
            report = {"schema_version": 1, "mode": "read_only", "advice": []}
            with self.assertRaisesRegex(SystemExit, "HOLD_OWNER_ADVICE_OUTPUT_COLLISION"):
                mod._write_report(evidence, evidence, report)
            self.assertEqual(evidence.read_text(encoding="utf8"), original)
            link = root / "advisor.json"
            link.symlink_to(evidence)
            with self.assertRaisesRegex(SystemExit, "HOLD_OWNER_ADVICE_OUTPUT_COLLISION|HOLD_OWNER_ADVICE_OUTPUT_UNSAFE"):
                mod._write_report(evidence, link, report)
            self.assertEqual(evidence.read_text(encoding="utf8"), original)

    def test_atomic_advice_receipt_replaces_complete_json_without_temp_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "owner-snapshot.json"
            evidence.write_text(json.dumps(snapshot()), encoding="utf8")
            output = root / "advisor.json"
            output.write_text('{"previous":"complete"}\n', encoding="utf8")
            report = {"schema_version": 1, "mode": "read_only", "advice": [
                {"code": "NATIVE_REFILL_OWNER_HOLD", "urgency": "hold", "advice": "Await owner."}
            ]}
            mod._write_report(evidence, output, report)
            self.assertEqual(json.loads(output.read_text(encoding="utf8")), report)
            self.assertEqual(list(root.glob(".advisor.json.*.tmp")), [])

    def test_owner_snapshot_reader_refuses_symlinks_and_unbounded_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            safe = root / "current.json"
            data = snapshot()
            safe.write_text(json.dumps(data), encoding="utf8")
            self.assertEqual(mod._read_snapshot_json(safe), data)
            symlink = root / "alias.json"
            symlink.symlink_to(safe)
            with self.assertRaisesRegex(SystemExit, "HOLD_OWNER_TELEMETRY_JSON_INVALID"):
                mod._read_snapshot_json(symlink)
            oversize = root / "oversize.json"
            with oversize.open("wb") as handle:
                handle.truncate(mod.MAX_OWNER_SNAPSHOT_BYTES + 1)
            with self.assertRaisesRegex(SystemExit, "HOLD_OWNER_TELEMETRY_JSON_INVALID"):
                mod._read_snapshot_json(oversize)

    def test_missing_stop_is_higher_priority(self):
        s = snapshot()
        s.pop("stop_active")
        self.assertEqual(codes(s), ["STOP_STATE_UNVERIFIED"])


if __name__ == "__main__":
    unittest.main()
