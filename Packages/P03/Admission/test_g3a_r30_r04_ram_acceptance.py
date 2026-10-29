"""G3-A R30 R04: offline RAM admission and backward-compatibility regressions.

No model downloads, network, native host or Windows CI. A test-only callback
is NOT an actual E06 rights/SourceLock/hardware attestation.
Run: cd Packages/P03/Admission && python -m unittest
    test_g3a_r30_r03_memory_budget_red test_g3a_r30_r04_ram_acceptance
"""
import unittest

from p03_modelcenter_gate import admit_for_existing_downloader
from test_p03_modelcenter_gate import example


class G3ARamAdmission(unittest.TestCase):
    def evaluate(self, mutate):
        evidence, context = example()
        mutate(evidence, context)
        calls = []
        def synthetic_native(_e, _c):
            calls.append(1)
            return True
        return admit_for_existing_downloader(evidence, context, synthetic_native), calls

    def test_gpu_model_with_measured_ram_can_continue_to_attestor(self):
        def mutate(e, c):
            e["recommendedRamBytes"] = 500000
            c["nativeMeasuredHardware"]["availableRamBytes"] = 500000
        result, calls = self.evaluate(mutate)
        self.assertEqual(result.status, "PASS_FOR_EXISTING_QUEUE")
        self.assertEqual(calls, [1])

    def test_cpu_only_model_with_measured_ram_can_continue_to_attestor(self):
        def mutate(e, c):
            e["requiresGPU"] = False
            e["requiredVramBytes"] = None
            e["recommendedRamBytes"] = 500000
            c["nativeMeasuredHardware"]["availableRamBytes"] = 600000
        result, calls = self.evaluate(mutate)
        self.assertEqual(result.status, "PASS_FOR_EXISTING_QUEUE")
        self.assertEqual(calls, [1])

    def test_boolean_native_ram_sensor_fails_closed(self):
        def mutate(e, c):
            e["recommendedRamBytes"] = 500000
            c["nativeMeasuredHardware"]["availableRamBytes"] = True
        result, calls = self.evaluate(mutate)
        self.assertIn("NATIVE_RAM_SENSOR_MISSING", result.reasons)
        self.assertEqual(calls, [])

    def test_negative_native_ram_sensor_fails_closed(self):
        def mutate(e, c):
            e["recommendedRamBytes"] = 500000
            c["nativeMeasuredHardware"]["availableRamBytes"] = -1
        result, calls = self.evaluate(mutate)
        self.assertIn("NATIVE_RAM_SENSOR_MISSING", result.reasons)
        self.assertEqual(calls, [])

    def test_gpu_only_legacy_vram_evidence_still_follows_native_attestor(self):
        result, calls = self.evaluate(lambda e, c: None)
        self.assertEqual(result.status, "PASS_FOR_EXISTING_QUEUE")
        self.assertEqual(calls, [1])

    def test_cpu_only_does_not_accept_unexpected_vram_field(self):
        def mutate(e, c):
            e["requiresGPU"] = False
            e["requiredVramBytes"] = 0
            e["recommendedRamBytes"] = 500000
            c["nativeMeasuredHardware"]["availableRamBytes"] = 800000
        result, calls = self.evaluate(mutate)
        self.assertIn("GPU_FLAG_AND_VRAM_REQUIREMENT_MISMATCH", result.reasons)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
