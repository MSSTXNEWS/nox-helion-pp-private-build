"""M04 P03 source-policy regression: hostile GPU flag cannot bypass VRAM.
No native attestations, downloads, weights, queue writes or Windows claims.
Run: PYTHONPATH=Packages/P03/Admission python -m unittest discover -s Packages/P03/Admission -p test_m04_gpu_flag_boolean_gate.py -v
"""
import unittest

import p03_modelcenter_gate as gate
from test_p03_modelcenter_gate import example


class M04GpuFlagBooleanGate(unittest.TestCase):
    @staticmethod
    def decide(flag, vram=0):
        evidence, context = example()
        evidence["requiresGPU"] = flag
        context["nativeMeasuredHardware"]["vramBytes"] = vram
        # TEST-ONLY stand-in: this is NOT the real native E06 attestor.
        return gate.admit_for_existing_downloader(
            evidence, context, lambda _e, _c: True
        )

    def test_nonboolean_gpu_flag_must_hold_before_existing_queue(self):
        for flag in ("true", "false", 1, 0, None, [], {}):
            with self.subTest(flag=repr(flag)):
                outcome = self.decide(flag)
                self.assertEqual(outcome.status, "HOLD")
                self.assertIn("GPU_REQUIREMENTS_UNVERIFIED", outcome.reasons)
                self.assertIsNone(outcome.existing_route)

    def test_real_true_gpu_flag_with_insufficient_vram_holds(self):
        result = self.decide(True, vram=1)
        self.assertEqual(result.status, "HOLD")
        self.assertIn("INSUFFICIENT_REAL_VRAM", result.reasons)

    def test_real_false_gpu_flag_with_measured_disk_can_pass_source_policy(self):
        result = self.decide(False, vram=0)
        self.assertEqual(result.status, "PASS_FOR_EXISTING_QUEUE")
        self.assertEqual(result.existing_route, "EnqueueVerifiedPullAsync")
        # Source-policy admission does NOT mean a live native owner or weights.


if __name__ == "__main__":
    unittest.main()
