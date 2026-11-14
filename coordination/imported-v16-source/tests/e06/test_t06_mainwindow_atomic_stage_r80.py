"""R80: original T06 staging must not damage disposable MainWindow on commit error."""
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

STAGER_PATH = Path(os.environ["NOX_TEST_STAGE_PATH"])

def load_stager():
    spec=importlib.util.spec_from_file_location("stage_native_p02_r80",STAGER_PATH)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class OriginalOneHostAtomicStage(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"R11"
        self.root.mkdir()
        self.main=self.root/"MainWindow.xaml.cs"
        self.baseline=(
            'class MainWindow {\n'
            '            core.SetVirtualHostNameToFolderMapping("nox.local", assets, CoreWebView2HostResourceAccessKind.DenyCors);\n'
            '            _initialized = true;\n'
            '        Closing += (_, _) => WriteLog("CLOSE");\n'
            '            switch (type)\n'
            '}\n'
        ).encode("utf-8")
        self.main.write_bytes(self.baseline)
        self.addon=Path(self.temp.name)/"MainWindow.NativeP02.cs"
        self.addon.write_bytes(b"// owned native partial fixture\n")
        self.module=load_stager()
        self.module.MAIN_SHA=hashlib.sha256(self.baseline).hexdigest()
        self.module.ADDON_SHA=self.module.blob(self.addon.read_bytes())
        self.staged=self.root/"Integration/MainWindow.NativeP02.cs"

    def test_commit_failure_preserves_main_and_removes_only_owned_addon(self):
        with mock.patch("os.replace",side_effect=OSError("R80_SIMULATED_ATOMIC_PUBLISH_FAIL")) as commit:
            with self.assertRaisesRegex(OSError,"R80_SIMULATED_ATOMIC_PUBLISH_FAIL"):
                self.module.run(self.root,self.addon)
        self.assertEqual(commit.call_count,1)
        self.assertEqual(self.main.read_bytes(),self.baseline)
        self.assertFalse(self.staged.exists())
        self.assertEqual(list(self.root.glob(".nox-native-stage-*.tmp")),[])

    def test_success_stages_both_original_onehost_sources(self):
        self.module.run(self.root,self.addon)
        self.assertEqual(self.staged.read_bytes(),self.addon.read_bytes())
        edited=self.main.read_text("utf-8")
        self.assertIn("await InitializeNativeP02Async(core);",edited)
        self.assertIn("ShutdownNativeP02();",edited)
        self.assertIn("TryDispatchLegacyNative(json.RootElement, e.Source)",edited)
        self.assertEqual(list(self.root.glob(".nox-native-stage-*.tmp")),[])

if __name__=="__main__":
    unittest.main()
