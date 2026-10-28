import unittest
from g2_gpu_sample_gate import valid_sample_id, enforce_gpu_tile_sample

T = "2026-10-28T11:00:00Z"

def live(value, source="NVML"):
    return {"value": value, "status": "LIVE", "source": source}

class SampleCoherence(unittest.TestCase):
    def frame(self, source="NVML", sample="A", t1=T, t2=T):
        safe = {"gpu.percent": live(30), "gpu.temperature.c": live(60, source)}
        observed = {"gpu.percent": t1, "gpu.temperature.c": t2}
        samples = {"gpu.percent": sample, "gpu.temperature.c": sample}
        return safe, observed, samples

    def test_01_equal_native_sample_accepted(self):
        a,b,c = self.frame()
        enforce_gpu_tile_sample(a,b,c)
        self.assertEqual(a["gpu.percent"]["status"], "LIVE")
    def test_02_provider_mismatch_quarantined(self):
        a,b,c = self.frame(source="WMI")
        enforce_gpu_tile_sample(a,b,c)
        self.assertTrue(all(x["status"] == "N_D" for x in a.values()))
    def test_03_sample_mismatch_quarantined(self):
        a,b,c = self.frame()
        c["gpu.temperature.c"]="B"
        enforce_gpu_tile_sample(a,b,c)
        self.assertTrue(all(x["value"] is None for x in a.values()))
    def test_04_partial_sample_id_quarantined(self):
        a,b,c = self.frame()
        c["gpu.temperature.c"] = None
        enforce_gpu_tile_sample(a,b,c)
        self.assertTrue(all(x["status"] == "N_D" for x in a.values()))
    def test_05_both_legacy_absent_supported(self):
        a,b,c = self.frame()
        c = {}
        enforce_gpu_tile_sample(a,b,c)
        self.assertEqual(a["gpu.temperature.c"]["value"], 60)
    def test_06_six_seconds_quarantined(self):
        a,b,c = self.frame(t2="2026-10-28T11:00:06Z")
        enforce_gpu_tile_sample(a,b,c)
        self.assertEqual(a["gpu.percent"]["status"], "N_D")
    def test_07_five_seconds_accepted(self):
        a,b,c = self.frame(t2="2026-10-28T11:00:05Z")
        enforce_gpu_tile_sample(a,b,c)
        self.assertEqual(a["gpu.percent"]["value"], 30)
    def test_08_invalid_timestamp_quarantined(self):
        a,b,c = self.frame(t2="2026-02-30T11:00:00Z")
        enforce_gpu_tile_sample(a,b,c)
        self.assertTrue(all(x["status"] == "N_D" for x in a.values()))
    def test_09_cpu_untouched(self):
        a,b,c = self.frame(source="WMI")
        a["cpu.system.percent"] = live(12, "OS")
        enforce_gpu_tile_sample(a,b,c)
        self.assertEqual(a["cpu.system.percent"]["value"], 12)
    def test_10_single_gpu_metric_untouched(self):
        a={"gpu.percent":live(12)}
        enforce_gpu_tile_sample(a, {"gpu.percent":T}, {})
        self.assertEqual(a["gpu.percent"]["value"], 12)
    def test_11_valid_sample_id_lexical(self):
        self.assertTrue(valid_sample_id("E05.native-17"))
        self.assertFalse(valid_sample_id("bad\u202e"))
        self.assertFalse(valid_sample_id("  "))
        self.assertFalse(valid_sample_id(None))
    def test_12_nonfinite_utc_shape_quarantined(self):
        a,b,c = self.frame(t2="2026-10-28T11:00:00+01:00")
        enforce_gpu_tile_sample(a,b,c)
        self.assertTrue(all(x["status"] == "N_D" for x in a.values()))

if __name__ == "__main__": unittest.main()

