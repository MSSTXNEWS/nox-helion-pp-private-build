"""Fail-closed AMD GPU sensor contract for original NOX R8 native source.

SOURCE_ONLY: does not prove the real owner machine has an AMD hot-spot sensor.
Run in source repo: python coordination/nox-r8/tests/test_r8_amd_telemetry_source.py
"""
from pathlib import Path
import re
import unittest

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "overrides" / "src" / "MainWindow.xaml.cs"
FALLBACK = HERE / "src" / "MainWindow.xaml.cs"
SOURCE = SRC if SRC.is_file() else FALLBACK


class AmdSensorFailClosed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SOURCE.read_text(encoding="utf-8-sig")

    def test_real_provider_only(self):
        s = self.text
        self.assertIn("Get-CimInstance -Namespace 'root/LibreHardwareMonitor' -ClassName Sensor", s)
        self.assertIn("SensorType -eq 'Temperature'", s)
        self.assertIn("amdgpu|atigpu", s)
        self.assertIn("hot\\s*spot|junction", s)
        self.assertIn("GetAmdGpuTelemetryOrHold()", s)

    def test_no_zero_or_missing_sensor_accepted(self):
        s = self.text
        for token in ("p.ExitCode != 0", "!double.IsFinite(hotSpot)",
                      "hotSpot <= 0", "hotSpot > 125",
                      "AMD_HOTSPOT_MISSING_OR_INVALID_HOLD",
                      "AMD_SENSOR_TIMEOUT_HOLD"):
            self.assertIn(token, s, token)

    def test_training_remains_blocked_without_worker(self):
        s = self.text
        for token in ("trainingSafe = false", "NO_ATTESTED_GPU_WORKER",
                      "AWAITING_VERIFIED_WORKER", "trainingStarted=false",
                      "checkpointVerified = false"):
            self.assertIn(token, s, token)

    def test_source_not_fabricating_other_telemetry(self):
        s = self.text
        for token in ("telemetryPartial = true",
                      "vramTotalMiB = (double?)null",
                      "vramUsedMiB = (double?)null",
                      "utilizationPercent = (int?)null"):
            self.assertIn(token, s, token)
        self.assertNotRegex(s, r"hotSpot\\s*=\\s*0\\s*;")

if __name__ == "__main__":
    unittest.main()
