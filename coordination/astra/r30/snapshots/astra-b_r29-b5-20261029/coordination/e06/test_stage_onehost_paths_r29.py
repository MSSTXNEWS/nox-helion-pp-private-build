import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('stage', Path(__file__).with_name('stage_onehost.py'))
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)

class StagingPathTests(unittest.TestCase):
    def fixture(self, root):
        folder = root / 'R11'
        (folder / 'Integration').mkdir(parents=True)
        original = folder / 'Integration/Pack01HostBridge.cs'
        original.write_text(stage.ANCHOR)
        addon = root / 'addon.cs'
        addon.write_text('void ReportOriginalPythonDiagnosticAsync() {}')
        executable = root / 'python.exe'
        executable.write_bytes(b'fixture - never executed')
        return folder, original, addon, executable

    def invoke(self, folder, addon, executable):
        with patch.object(sys, 'argv', ['stage', str(folder), str(addon), str(executable)]), patch.object(stage, 'ORIGINAL_BRIDGE_SHA256', hashlib.sha256(stage.ANCHOR.encode()).hexdigest()), patch.object(stage, 'ORIGINAL_EXE_SHA256', hashlib.sha256(executable.read_bytes()).hexdigest()):
            stage.main()

    def test_existing_receipt_denied_before_any_source_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder, original, addon, exe = self.fixture(root)
            receipt = root / 'E06_R10_SOURCE_RECEIPT.json'
            receipt.write_bytes(b'owner evidence')
            with self.assertRaises(SystemExit):
                self.invoke(folder, addon, exe)
            self.assertEqual(original.read_text(), stage.ANCHOR)
            self.assertEqual(receipt.read_bytes(), b'owner evidence')
            self.assertFalse((folder/'Integration/OriginalPythonDiagnosticBridge.cs').exists())

    def test_dangling_addon_destination_denied_without_following_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder, original, addon, exe = self.fixture(root)
            outside = root / 'outside.cs'
            dest = folder/'Integration/OriginalPythonDiagnosticBridge.cs'
            dest.symlink_to(outside)
            with self.assertRaises(SystemExit):
                self.invoke(folder, addon, exe)
            self.assertEqual(original.read_text(), stage.ANCHOR)
            self.assertFalse(outside.exists())

    def test_symlinked_stage_ancestor_denied_without_modification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder, original, addon, exe = self.fixture(root)
            link = root / 'linked'
            link.symlink_to(folder, target_is_directory=True)
            with self.assertRaises(SystemExit):
                self.invoke(link, addon, exe)
            self.assertEqual(original.read_text(), stage.ANCHOR)

    def test_original_source_pin_and_positive_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder, original, addon, exe = self.fixture(root)
            self.invoke(folder, addon, exe)
            self.assertEqual(original.read_text(), stage.REPLACEMENT)
            self.assertEqual((folder/'Integration/OriginalPythonDiagnosticBridge.cs').read_bytes(), addon.read_bytes())
            self.assertTrue((root/'E06_R10_SOURCE_RECEIPT.json').exists())

if __name__ == '__main__': unittest.main()
