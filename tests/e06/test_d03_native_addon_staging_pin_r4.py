"""D03: original native WPF owner and T06 staging must share exact Git blobs.

Source-only regression: no installed Windows receipt or release acceptance.
"""
import hashlib
import importlib.util
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
STAGE = ROOT / "coordination/e06/stage_native_p02.py"
OWNER = ROOT / "coordination/e06/MainWindow.NativeP02.cs"
BUILDER = ROOT / "coordination/e06/build_onehost_installer.ps1"


def git_blob(path):
    raw = path.read_bytes()
    # The repository stores its canonical Git blobs using LF even when a
    # Windows checkout materializes CRLF. A bare CR is not a reviewed source.
    if b"\r" in raw:
        if b"\r" in raw.replace(b"\r\n", b""):
            raise AssertionError("D03_UNREVIEWED_BARE_CR_HOLD")
        raw = raw.replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


class OriginalNativeAddonPinR4(unittest.TestCase):
    def test_stager_matches_original_owner_and_builder(self):
        source = STAGE.read_text(encoding="utf-8")
        build = BUILDER.read_text(encoding="utf-8")
        matches = re.findall(r'^ADDON_SHA="([a-f0-9]{40})"$', source, re.M)
        self.assertEqual(matches, [git_blob(OWNER)])
        stage_pins = re.findall(r"@\{p=\$t06Stage;sha='([a-f0-9]{40})'", build)
        owner_pins = re.findall(r"@\{p=\$t06Addon;sha='([a-f0-9]{40})'", build)
        self.assertEqual(stage_pins, [git_blob(STAGE)])
        self.assertEqual(owner_pins, [git_blob(OWNER)])
        self.assertIn('if blob(extra)!=ADDON_SHA:', source)
        self.assertIn('if blob(canonical)!=ADDON_SHA:', source)
        self.assertIn('T06_NATIVE_ADDON_GIT_BLOB_HOLD', source)

    def test_wrong_owner_bytes_refuse_without_writing_stage(self):
        spec = importlib.util.spec_from_file_location("nox_d03_stage_native_p02", STAGE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "R11"
            root.mkdir()
            main = root / "MainWindow.xaml.cs"
            preimage = b"untouched original source fixture"
            main.write_bytes(preimage)
            foreign = root / "foreign-owner.cs"
            foreign.write_bytes(b"not the original pinned owner\n")
            with patch.object(module, "MAIN_SHA", hashlib.sha256(preimage).hexdigest()):
                with self.assertRaisesRegex(ValueError, "T06_NATIVE_ADDON_GIT_BLOB_HOLD"):
                    module.run(root, foreign)
            self.assertEqual(main.read_bytes(), preimage)
            self.assertFalse((root / "Integration/MainWindow.NativeP02.cs").exists())


if __name__ == "__main__":
    unittest.main()
