"""Independent M2 R23 negative owner-path and Windows safety regression."""
import importlib.util
from pathlib import Path
import unittest
SCRIPT=Path(__file__).with_name("t06_owner_receipt_same_head_gate_r23.py")
spec=importlib.util.spec_from_file_location("owner_gate_r23",SCRIPT)
gate=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
class OwnerPathSafetyM2R23(unittest.TestCase):
 def test_unsafe_control_and_windows_ads_paths_are_rejected(self):
  for value in ("Packages/P04/source.py\nFAKE_PASS", "Packages/P04/source.py\t", "Packages/P04/source.py\r", "Packages/P04/source.py\x7f", "Packages/P04/source.py:alt", "C:/Windows/System32", "Packages/P04/\u202e.py"):
   with self.subTest(path=repr(value)):
    self.assertFalse(gate.safe_path(value))
 def test_valid_source_paths_are_preserved(self):
  for value in ("Packages/P04/model_snapshot_probe.py", "Packages/P04/weights/part-01.safetensors", "coordination/e06/test_t06_owner_receipt_same_head_gate_r23.py"):
   with self.subTest(path=value):
    self.assertTrue(gate.safe_path(value))
