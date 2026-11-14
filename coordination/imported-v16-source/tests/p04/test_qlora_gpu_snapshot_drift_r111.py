"""P04 engine must recheck actual UUID VRAM identity before training and during monitoring."""
import inspect
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Packages" / "P04"))
import train_qlora as engine


class GpuTrainInventoryParity(unittest.TestCase):
    def test_matching_snapshot(self):
        self.assertIsNone(engine.require_gpu_snapshot_consistency("12288", {"total_mib": 12288}))

    def test_stale_or_swapped_uuid_view_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "GPU_TOTAL_MEMORY_SNAPSHOT_DRIFT"):
            engine.require_gpu_snapshot_consistency("12288", {"total_mib": 8192})

    def test_missing_or_ambiguous_snapshot_rejected(self):
        for inventory, live in [
            (None, {"total_mib": 12288}), ("", {"total_mib": 12288}),
            ("not-a-number", {"total_mib": 12288}), ("12288", {}),
            ("12288", {"total_mib": None}), ("12288", {"total_mib": True}),
            ("12288", {"total_mib": "12288"}), ("12288", {"total_mib": 0}),
        ]:
            with self.subTest(inventory=inventory, live=live):
                with self.assertRaisesRegex(RuntimeError, "GPU_TOTAL_MEMORY_SNAPSHOT_DRIFT"):
                    engine.require_gpu_snapshot_consistency(inventory, live)

    def test_early_rejection_precedes_gpu_lock(self):
        main = inspect.getsource(engine.main)
        early = 'require_gpu_snapshot_consistency(chosen["memory_total_mib"], vram_headroom)'
        self.assertIn(early, main)
        self.assertLess(main.index(early), main.index("lock_fd = acquire_gpu_lock"))

    def test_live_monitor_rechecks_identity_before_recording_free_vram(self):
        main = inspect.getsource(engine.main)
        live = 'require_gpu_snapshot_consistency(chosen["memory_total_mib"], current_vram)'
        self.assertIn(live, main)
        self.assertLess(main.index(live), main.index('monitor["vram_free_mib"] = current_vram["free_mib"]'))

if __name__ == "__main__":
    unittest.main()
