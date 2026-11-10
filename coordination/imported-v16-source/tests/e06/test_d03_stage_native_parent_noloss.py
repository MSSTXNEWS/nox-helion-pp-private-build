"""D03: exact native OneHost stage must never write via a foreign parent."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "coordination/e06/stage_native_p02.py"
spec = importlib.util.spec_from_file_location("d03_exact_native_stage", MODULE)
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)

class NativeStageParentNoLoss(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root / "R11"
        self.source.mkdir()
        self.outside = self.root / "foreign"
        self.outside.mkdir()
        self.addon = self.root / "MainWindow.NativeP02.cs"
        self.addon.write_bytes(b"// disposable native stage fixture\n")
        self.main = self.source / "MainWindow.xaml.cs"
        self.input = (
            '            core.SetVirtualHostNameToFolderMapping("nox.local", assets, CoreWebView2HostResourceAccessKind.DenyCors);\n'
            '            _initialized = true;\n'
            '        Closing += (_, _) => WriteLog("CLOSE");\n'
        ).encode("utf-8")
        self.main.write_bytes(self.input)

    def stage(self):
        with patch.object(owner, "MAIN_SHA", hashlib.sha256(self.input).hexdigest()), \
             patch.object(owner, "ADDON_SHA", owner.blob(self.addon.read_bytes())):
            return owner.run(self.source, self.addon)

    def test_existing_symlink_parent_refused_without_foreign_write(self):
        try:
            (self.source / "Integration").symlink_to(self.outside, target_is_directory=True)
        except (NotImplementedError, OSError):
            self.skipTest("host cannot create test symlink")
        with self.assertRaisesRegex(ValueError, "T06_NATIVE_STAGE_REPARSE_PARENT_HOLD"):
            self.stage()
        self.assertEqual(list(self.outside.iterdir()), [])
        self.assertEqual(self.main.read_bytes(), self.input)

    def test_existing_file_as_stage_directory_refused_without_loss(self):
        bad = self.source / "Integration"
        bad.write_bytes(b"FOREIGN KEEP")
        with self.assertRaisesRegex(ValueError, "T06_NATIVE_STAGE_NON_DIRECTORY_PARENT_HOLD"):
            self.stage()
        self.assertEqual(bad.read_bytes(), b"FOREIGN KEEP")
        self.assertEqual(self.main.read_bytes(), self.input)

    def test_plain_parent_stages_original_handler(self):
        self.stage()
        self.assertEqual((self.source / "Integration/MainWindow.NativeP02.cs").read_bytes(), self.addon.read_bytes())
        self.assertIn(b"await InitializeNativeP02Async(core);", self.main.read_bytes())

if __name__ == "__main__":
    unittest.main()
