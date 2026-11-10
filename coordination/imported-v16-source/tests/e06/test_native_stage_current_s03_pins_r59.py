"""Current original S03 Python owner pins for immutable E06 staging.
Only source-byte verification; this is NOT installed Windows E07 proof.
"""
from __future__ import annotations
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "coordination/e06/stage_native_stdio.py"
S03 = {
 "src/nox_selfbuilder/onehost_builder.py": ("nox_selfbuilder/onehost_builder.py", "ed1f3838479f0af63ab8f88f7434e9ea06cd20f6"),
 "src/nox_selfbuilder/onehost_queue.py": ("nox_selfbuilder/onehost_queue.py", "07d77019cfc4b29001bfc7299b57a9c07a8c6e86"),
}
STALE = {
 "src/nox_selfbuilder/onehost_builder.py": "aee6910958973dda68dac601eade3969ac45d500",
 "src/nox_selfbuilder/onehost_queue.py": "035e8be10a36ceb2faba86537fd095a0849937f5",
}

def stage_module():
 spec = importlib.util.spec_from_file_location("original_e06_s03_pins", SCRIPT)
 module = importlib.util.module_from_spec(spec)
 spec.loader.exec_module(module)
 return module

class OriginalS03Pins(unittest.TestCase):
 def test_exact_original_current_git_source(self):
  stage = stage_module()
  registry = {src: (dest, blob) for src,dest,blob in stage.ADDONS}
  for src, expected in S03.items():
   with self.subTest(src=src):
    self.assertEqual(registry[src], expected)
    raw = stage.pinned_bytes(ROOT / src, expected[1])
    self.assertEqual(stage.git_blob(raw), expected[1])

 def test_old_pins_fail_closed(self):
  stage = stage_module()
  for src, old in STALE.items():
   with self.subTest(src=src):
    with self.assertRaisesRegex(RuntimeError, "E06_NATIVE_OWNER_BLOB_SHA_HOLD"):
     stage.pinned_bytes(ROOT / src, old)

 def test_complete_original_addon_inventory_retained(self):
  stage = stage_module()
  self.assertEqual(len(stage.ADDONS), 50)
  self.assertEqual(len({src for src,_,_ in stage.ADDONS}), 50)
  self.assertEqual(len({dest for _,dest,_ in stage.ADDONS}), 50)
  self.assertEqual(stage.ORIGINAL_APP_SHA256, "e43a1d1ef6875b75f4d0da1434464f675a77f3fc592941e2bb7f3410dae7cdae")

if __name__ == "__main__":
 unittest.main()
