"""Regression: no heavy E07 provider download without immutable E06 proof."""
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
E07 = ROOT / "coordination" / "e07"
sys.path.insert(0, str(E07))
spec = importlib.util.spec_from_file_location("b06_preprovision", E07 / "preflight_e07_producer.py")
assert spec and spec.loader
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)

SOURCE = "a" * 40
SETUP = "b" * 64
BUILD = "NOX-V16-" + "c" * 24
V = {"E07_SOURCE_SHA": SOURCE, "E07_SETUP_SHA": SETUP,
     "E07_SETUP_BYTES": "87364185", "E07_BUILD_ID": BUILD,
     "E07_OWNED_COUNT": "1007"}


class B06ProducerAdmission(unittest.TestCase):
    def test_malformed_pins_fail_before_receipts(self):
        for name, bad in (("E07_SOURCE_SHA", "old-sha"),
                          ("E07_SETUP_SHA", "0" * 63),
                          ("E07_SETUP_BYTES", "-1"),
                          ("E07_BUILD_ID", "NOT_VERIFIED"),
                          ("E07_OWNED_COUNT", "0")):
            with self.subTest(name=name), patch.object(preflight.e07, "setup_lock") as lock:
                self.assertFalse(preflight.check(Path("untrusted"), {**V, name:bad}))
                lock.assert_not_called()

    def test_missing_original_e06_handoff_never_admitted(self):
        # Uses real E07 receipt/path validation; no synthetic Setup can pass.
        self.assertFalse(preflight.check(Path("nonexistent-artifact"), V))

    def test_pass_requires_exact_source_setup_bytes_build_and_real_stage(self):
        expected = {"source_sha":SOURCE,"setup_sha256":SETUP,"setup_bytes":87364185,
                    "build_id":BUILD,"e06_samevm_pass_not_e07":True}
        with patch.object(preflight.e07, "setup_lock", return_value=expected) as lock:
            self.assertTrue(preflight.check(Path("artifact"), V))
            self.assertEqual(lock.call_count,1)
            args, kw=lock.call_args
            self.assertEqual(kw["candidate"],"d02-pinned")
            self.assertEqual(kw["pinned"]["owned_count"],1007)
            self.assertEqual(args[1].name,"E07_BUILT_HANDOFF.json")
        with patch.object(preflight.e07, "setup_lock", return_value={**expected,"build_id":"NOX-V16-"+"d"*24}):
            self.assertFalse(preflight.check(Path("artifact"),V))
        with patch.object(preflight.e07, "setup_lock", side_effect=preflight.e07.Hold("E07_E06_HANDOFF_IDENTITY_HOLD")):
            self.assertFalse(preflight.check(Path("artifact"),V))

    def test_workflow_orders_proof_before_provider_and_final_gates_both(self):
        workflow = (ROOT/".github/workflows/nox-express-independent-e07-current-d02.yml").read_text()
        source = "B06 lock exact E06 producer receipts before costly provider downloads"
        download = "Download prior SHA-pinned Authenticode-verified official Ollama x64 bytes"
        self.assertLess(workflow.index("Download immutable candidate from DIFFERENT Windows CI run"), workflow.index(source))
        self.assertLess(workflow.index(source), workflow.index(download))
        self.assertIn("steps.provider.outcome", workflow)
        self.assertIn("steps.test.outcome", workflow)
        self.assertIn("E07_SAME_SETUP_PREVIOUS_RUN_HOLD", workflow)
        self.assertIn("E07_PRODUCER_PREPROVISION_IDENTITY_HOLD", workflow)
        self.assertEqual(workflow.count("Independent installed E07 candidate lifecycle, final receipts required"), 1)


if __name__ == "__main__":
    unittest.main()
