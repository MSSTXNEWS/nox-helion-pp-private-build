import unittest
from g2_gpu_provenance import valid_source, valid_device, reconcile_gpu_tile


def live(value, source="NVML"):
    return {"value": value, "status": "LIVE", "source": source}


class E06GpuProvenance(unittest.TestCase):
    def test_01_valid_cpu_provider_unicode(self):
        self.assertTrue(valid_source("Датчик GPU NVML"))

    def test_02_blank_source_invalid(self):
        self.assertFalse(valid_source("   "))

    def test_03_hidden_bidi_invalid(self):
        self.assertFalse(valid_source("NVML\u202E"))

    def test_04_newline_source_invalid(self):
        self.assertFalse(valid_source("NVML\nSYSTEM"))

    def test_05_valid_device_ids(self):
        self.assertTrue(valid_device("GPU-0/0000:01:00.0"))
        self.assertFalse(valid_device("GPU 0"))
        self.assertFalse(valid_device(None))

    def test_06_valid_matched_vram(self):
        safe = {"gpu.vram.used_bytes": live(3), "gpu.vram.total_bytes": live(8)}
        when = {k: "2026-10-28T10:00:00Z" for k in safe}
        ids = {k: "GPU-0" for k in safe}
        reconcile_gpu_tile(safe, when, ids)
        self.assertEqual(safe["gpu.vram.used_bytes"]["value"], 3)

    def test_07_vram_different_devices_quarantined(self):
        safe = {"gpu.vram.used_bytes": live(3), "gpu.vram.total_bytes": live(8)}
        when = {k: "2026-10-28T10:00:00Z" for k in safe}
        reconcile_gpu_tile(safe, when, {"gpu.vram.used_bytes": "GPU-0", "gpu.vram.total_bytes": "GPU-1"})
        self.assertTrue(all(x["value"] is None for x in safe.values()))

    def test_08_vram_different_times_quarantined(self):
        safe = {"gpu.vram.used_bytes": live(3), "gpu.vram.total_bytes": live(8)}
        when = {"gpu.vram.used_bytes": "A", "gpu.vram.total_bytes": "B"}
        reconcile_gpu_tile(safe, when, {k: "GPU-0" for k in safe})
        self.assertTrue(all(x["status"] == "N_D" for x in safe.values()))

    def test_09_vram_inconsistent_counters(self):
        safe = {"gpu.vram.used_bytes": live(9), "gpu.vram.total_bytes": live(8)}
        reconcile_gpu_tile(safe, {k: "A" for k in safe}, {k: "GPU-0" for k in safe})
        self.assertIsNone(safe["gpu.vram.used_bytes"]["value"])

    def test_10_percent_and_temperature_cross_gpu_denied(self):
        safe = {"gpu.percent": live(25), "gpu.temperature.c": live(60)}
        reconcile_gpu_tile(safe, {}, {"gpu.percent": "GPU-0", "gpu.temperature.c": "GPU-1"})
        self.assertTrue(all(x["value"] is None for x in safe.values()))

    def test_11_vram_and_percent_cross_gpu_denied(self):
        safe = {"gpu.percent": live(30), "gpu.vram.used_bytes": live(3),
                "gpu.vram.total_bytes": live(8)}
        reconcile_gpu_tile(safe, {k: "T" for k in safe},
                           {"gpu.percent": "GPU-1", "gpu.vram.used_bytes": "GPU-0",
                            "gpu.vram.total_bytes": "GPU-0"})
        self.assertTrue(all(x["value"] is None for x in safe.values()))

    def test_12_missing_id_quarantined(self):
        safe = {"gpu.percent": live(33)}
        reconcile_gpu_tile(safe, {}, {})
        self.assertIsNone(safe["gpu.percent"]["value"])

    def test_13_cpu_untouched(self):
        safe = {"cpu.system.percent": live(22)}
        reconcile_gpu_tile(safe, {}, {})
        self.assertEqual(safe["cpu.system.percent"]["value"], 22)

    def test_14_orphan_vram_quarantined(self):
        safe = {"gpu.vram.used_bytes": live(3)}
        reconcile_gpu_tile(safe, {"gpu.vram.used_bytes": "T"}, {"gpu.vram.used_bytes": "GPU-0"})
        self.assertIsNone(safe["gpu.vram.used_bytes"]["value"])

    def test_15_valid_same_gpu_percent_and_temp(self):
        safe = {"gpu.percent": live(30), "gpu.temperature.c": live(60)}
        reconcile_gpu_tile(safe, {}, {k: "GPU-0" for k in safe})
        self.assertTrue(all(x["status"] == "LIVE" for x in safe.values()))


if __name__ == "__main__":
    unittest.main()
