"""Verify exact policy-only serving successor without executing host controls."""
from __future__ import annotations
import base64
import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from owner_chat_terminal_guard_v6 import prepare, EXPECTED_INPUT_SHA256

class PolicyOnlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / "package_policy_only_v1/owner_chat_policy_only_embedded_entry.py"
        spec = importlib.util.spec_from_file_location("_nox_policy_only_v1", path)
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def test_exact_ui_preserved(self):
        m = self.m
        expected = prepare((ROOT / "nox-v24-chat-nonempty-current.js").read_bytes())
        self.assertEqual(m.SPEC["before"]["ui"], m.SPEC["after_ui_sha256"])
        self.assertEqual(m.SPEC["asset_bytes"], {"before": 33756, "after": 33756})
        self.assertEqual(base64.b64decode(m.BUNDLE["public_chat.js"], validate=True), expected)
        self.assertEqual(hashlib.sha256(expected).hexdigest(), m.SPEC["after_ui_sha256"])
        self.assertEqual(m.UI_BEFORE_SHA, EXPECTED_INPUT_SHA256)
        self.assertEqual(m.UI_AFTER_SHA, m.SPEC["after_ui_sha256"])

    def test_policy_only_source_target_and_fixed_proof(self):
        m = self.m
        self.assertEqual(set(m.TARGETS), {"slim"})
        self.assertEqual(set(m.SPEC["before"]), {"slim", "ui"})
        self.assertEqual(m.SPEC["idle_gate"]["stable_samples"], 2)
        self.assertFalse(m.SPEC["idle_gate"]["atomic_admission_fence"])
        self.assertEqual(len(m.SPEC["assets"]), 4)
        self.assertEqual(m.SPEC["new_rules_utf8_bytes"], 3980)
        self.assertTrue(m.SPEC["new_rules_assignment_sha256"])
        patch = base64.b64decode(m.BUNDLE["policy_patch.py"], validate=True)
        self.assertIn(b"def patch_slim", patch)
        source = (ROOT / "package_policy_only_v1/owner_chat_policy_only_embedded_entry.py").read_text()
        self.assertIn("for name, target in TARGETS.items():", source)
        self.assertNotIn("ui_after_sha256=rows[1]", source)

if __name__ == "__main__":
    unittest.main()
