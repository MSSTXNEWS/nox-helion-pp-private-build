"""G3-A R30 R03: RED regressions for missing host RAM budget gate.

Only synthetic offline context; never a verified rights/hardware receipt.
Expected: fail on current R02 source until RAM admission guard lands.
Run from Packages/P03/Admission:
    python -m unittest test_g3a_r30_r03_memory_budget_red
"""
import unittest
from test_p03_modelcenter_gate import example
from p03_modelcenter_gate import admit_for_existing_downloader


class G3AMemoryPreflight(unittest.TestCase):
    def evaluate(self, change):
        evidence, context = example()
        change(evidence, context)
        calls = []
        def native(_e, _c):
            calls.append(1)
            return True
        result = admit_for_existing_downloader(evidence, context, native)
        return result, calls

    def test_native_attestor_not_called_for_unmeasured_ram(self):
        result, calls = self.evaluate(
            lambda e, c: e.update(recommendedRamBytes=500000))
        self.assertEqual(result.status, "HOLD")
        self.assertIn("NATIVE_RAM_SENSOR_MISSING", result.reasons)
        self.assertFalse(calls)

    def test_cpu_model_missing_ram_requirement_must_hold(self):
        result, calls = self.evaluate(
            lambda e, c: e.update(requiresGPU=False, requiredVramBytes=None))
        self.assertIn("MODEL_MEMORY_REQUIREMENTS_UNVERIFIED", result.reasons)
        self.assertFalse(calls)

    def test_insufficient_host_ram_must_hold(self):
        def change(e, c):
            e["recommendedRamBytes"] = 500000
            c["nativeMeasuredHardware"]["availableRamBytes"] = 499999
        result, calls = self.evaluate(change)
        self.assertIn("INSUFFICIENT_REAL_RAM", result.reasons)
        self.assertFalse(calls)

    def test_boolean_ram_budget_not_accepted(self):
        result, calls = self.evaluate(
            lambda e, c: e.update(recommendedRamBytes=True))
        self.assertIn("RAM_REQUIREMENT_INVALID", result.reasons)
        self.assertFalse(calls)

    def test_cpu_claim_with_gpu_vram_must_hold(self):
        result, calls = self.evaluate(
            lambda e, c: e.update(requiresGPU=False, recommendedRamBytes=500000))
        self.assertIn("GPU_FLAG_AND_VRAM_REQUIREMENT_MISMATCH", result.reasons)
        self.assertFalse(calls)


if __name__ == "__main__":
    unittest.main()
