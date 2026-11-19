"""V135 acceptance uses a synthetic ZIP, not a claim of live Vast deployment."""
from __future__ import annotations
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from coordination.onepass import v135_resonance_owner_stage as m


class V135NoLossTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        d = Path(temp.name)
        self.frozen = d / "frozen.zip"
        self.stage = d / "v134-fixture.zip"
        self.output = d / "v135.zip"
        self.js = Path("coordination/onepass/nox-v135-resonance-owner-bridge.js")
        self.source = {
            "site/pc/resonance.html": b"<html><head></head><body>REAL V24</body></html>",
            "site/pc/v22/resonance.template.html": b'<html><head><base href="../"></head><body>REAL V22</body></html>',
            "site/nox-ui.js": b"ONEHOST_ORIGINAL_SHA_PIN",
        }
        for i in range(m.FROZEN_N - len(self.source)):
            self.source[f"site/assets/keep_{i:04d}.css"] = b"opaque original"
        self.assertEqual(len(self.source), m.FROZEN_N)
        with zipfile.ZipFile(self.frozen, "w") as z:
            for path, blob in sorted(self.source.items()):
                z.writestr(path, blob)
        with zipfile.ZipFile(self.stage, "w") as z:
            for path, blob in sorted(self.source.items()):
                z.writestr(path, blob)
            z.writestr("site/nox-legacy-chat-bridge-v293.js", b"V134 existing other pages")
            z.writestr("NOX_V134_NATIVE_OWNER_COMPAT_MANIFEST.json",
                       b'{"native_owner_deployed":false}')
        self.sha = m.file_sha(self.stage)
        self.frozen_sha = m.file_sha(self.frozen)
        patched = patch.object(m, "FROZEN_SHA", self.frozen_sha)
        patched.start()
        self.addCleanup(patched.stop)

    def test_preserves_1089_originals_and_owner_v122_js(self):
        receipt = m.build(self.stage, self.frozen, self.js, self.output,
                          expected_source_sha=self.sha)
        self.assertEqual(receipt["state"], "NOX_V135_VERIFIED_SOURCE_ONLY")
        self.assertTrue(receipt["rollback_bytes_verified"])
        self.assertEqual(receipt["original_frozen_entries_retained"], 1089)
        with zipfile.ZipFile(self.stage) as a, zipfile.ZipFile(self.output) as z:
            self.assertEqual(z.read("site/nox-ui.js"), a.read("site/nox-ui.js"))
            self.assertEqual(z.read("site/nox-legacy-chat-bridge-v293.js"),
                             a.read("site/nox-legacy-chat-bridge-v293.js"))
            self.assertEqual(z.testzip(), None)
            for path in m.PAGES:
                self.assertEqual(z.read(m.ROLLBACK+path), a.read(path))
                self.assertIn(m.SCRIPT_URL.encode(), z.read(path))
                self.assertIn(m.OBS_SCRIPT_URL.encode(), z.read(path))
            meta = json.loads(z.read(m.MANIFEST))
            self.assertFalse(meta["production_deployed"])
            self.assertTrue(meta["original_S03_unchanged"])
            self.assertTrue(meta["native_owner_only"])
            self.assertFalse(meta["native_observer_attached_in_live_onehost"])
            self.assertFalse(meta["process_control_actions_enabled"])
            policy = json.loads(z.read(m.CAP_POLICY))
            self.assertEqual(policy["schema"], "NOX_V135_OWNER_BRIDGE_CAP_POLICY_V2")
            self.assertEqual(meta["owner_bridge_cap_policy"]["sha256"], m.CAP_POLICY_SHA256)
            self.assertEqual(meta["owner_bridge_cap_policy"]["max_bridge_bytes"], 24805)
            self.assertEqual(meta["added_js_bytes"], 24293)
            self.assertEqual(meta["added_js_sha256"], policy["bridge_sha256"])
            self.assertEqual(z.read(m.OBS_JS),
                             m.OBS_SOURCE.read_bytes())
            self.assertEqual(z.read(m.NATIVE_SELF_MODULE),
                             m.NATIVE_SELF_SOURCE.read_bytes())
            self.assertEqual(z.read(m.NATIVE_RESPONSE_MODULE),
                             m.NATIVE_RESPONSE_SOURCE.read_bytes())
        self.assertEqual(receipt["output_entries"], m.FROZEN_N+2+len(m.PAGES)+6)

    def test_owner_bridge_limit_accepts_current_patch_and_rejects_overflow(self):
        current = self.js.read_bytes()
        self.assertLessEqual(len(current), m.MAX_OWNER_BRIDGE_BYTES)
        oversized = self.frozen.parent / "oversized-owner-bridge.js"
        oversized.write_bytes(
            current + b" " * (m.MAX_OWNER_BRIDGE_BYTES - len(current) + 1)
        )
        with self.assertRaisesRegex(ValueError, "HOLD_OWNER_BRIDGE_BOUNDS"):
            m.build(self.stage, self.frozen, oversized, self.output,
                    expected_source_sha=self.sha)
        self.assertFalse(self.output.exists())

    def test_cap_policy_tampering_is_rejected(self):
        policy = self.frozen.parent / "tampered-policy.json"
        policy.write_text(json.dumps({"schema":"NOX_V135_OWNER_BRIDGE_CAP_POLICY_V3",
                                      "measured_bridge_bytes":24293,
                                      "max_bridge_bytes":999999,
                                      "reserve_bytes":512,
                                      "bridge_sha256":"dff8fa66d2b822ab0055ccfacbf25f6b1eaa9a96ca02c60f1049f3799f8accd7"}))
        with patch.object(m, "CAP_POLICY_SOURCE", policy):
            with self.assertRaisesRegex(ValueError, "HOLD_OWNER_BRIDGE_CAP_POLICY_SHA"):
                m.build(self.stage, self.frozen, self.js, self.output,
                        expected_source_sha=self.sha)
        self.assertFalse(self.output.exists())

    def test_exact_same_source_is_bitwise_repeatable(self):
        a = m.build(self.stage, self.frozen, self.js, self.output,
                    expected_source_sha=self.sha)
        copy = self.output.with_name("again.zip")
        b = m.build(self.stage, self.frozen, self.js, copy,
                    expected_source_sha=self.sha)
        self.assertEqual(a["sha256"], b["sha256"])

    def test_sha_drift_is_rejected_without_output(self):
        with self.assertRaisesRegex(ValueError, "HOLD_SOURCE_SHA_DRIFT"):
            m.build(self.stage, self.frozen, self.js, self.output,
                    expected_source_sha="0"*64)
        self.assertFalse(self.output.exists())

    def test_frozen_drift_is_rejected(self):
        with patch.object(m, "FROZEN_SHA", "f"*64):
            with self.assertRaisesRegex(ValueError, "HOLD_FROZEN_ORIGINAL_SHA"):
                m.build(self.stage, self.frozen, self.js, self.output,
                        expected_source_sha=self.sha)

    def test_no_overwrite_old_candidate(self):
        self.output.write_bytes(b"owner bytes")
        with self.assertRaisesRegex(ValueError, "HOLD_OUTPUT_OVERWRITE"):
            m.build(self.stage, self.frozen, self.js, self.output,
                    expected_source_sha=self.sha)
        self.assertEqual(self.output.read_bytes(), b"owner bytes")

    def test_preexisting_v135_script_rejected(self):
        stage2 = self.stage.with_name("wrong.zip")
        with zipfile.ZipFile(self.stage) as src, zipfile.ZipFile(stage2, "w") as z:
            for x in src.infolist():
                z.writestr(x, src.read(x))
            z.writestr(m.JS, b"bad duplicate")
        with self.assertRaisesRegex(ValueError, "HOLD_UNEXPECTED_STAGE_OR_EXISTING_PATCH"):
            m.build(stage2, self.frozen, self.js, self.output,
                    expected_source_sha=m.file_sha(stage2))
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
