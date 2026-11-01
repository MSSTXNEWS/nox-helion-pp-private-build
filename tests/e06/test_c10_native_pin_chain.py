"""C10: The existing Windows native stage and build must pin CURRENT source blobs."""
from __future__ import annotations
import hashlib
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]

def git_blob(path):
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\\0" + data).hexdigest()

class NativePinChain(unittest.TestCase):
    def test_native_addon_and_stage_pins_match_current_bytes(self):
        stage_path = ROOT / "coordination/e06/stage_native_p02.py"
        addon_path = ROOT / "coordination/e06/MainWindow.NativeP02.cs"
        builder_path = ROOT / "coordination/e06/build_onehost_installer.ps1"
        stage = stage_path.read_text("utf-8")
        build = builder_path.read_text("utf-8")
        addon_sha = git_blob(addon_path)
        stage_sha = git_blob(stage_path)
        source_pin = re.findall(r'^ADDON_SHA="([0-9a-f]{40})"$', stage, re.M)
        stage_pin = re.findall(r"@\\{p=\\$t06Stage;sha='([0-9a-f]{40})'", build)
        addon_pin = re.findall(r"@\\{p=\\$t06Addon;sha='([0-9a-f]{40})'", build)
        self.assertEqual(source_pin, [addon_sha])
        self.assertEqual(stage_pin, [stage_sha])
        self.assertEqual(addon_pin, [addon_sha])

if __name__ == "__main__":
    unittest.main()
