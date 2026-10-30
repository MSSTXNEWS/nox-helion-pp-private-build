"""T06 one-host source contract; native compile and E2E remain separate."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]
class MainWindowP02Activation(unittest.TestCase):
    def test_original_source_and_no_second_host(self):
        s=(ROOT/"coordination/e06/stage_native_p02.py").read_text("utf-8")
        a=(ROOT/"coordination/e06/MainWindow.NativeP02.cs").read_text("utf-8")
        b=(ROOT/"coordination/e06/build_onehost_installer.ps1").read_text("utf-8")
        self.assertIn("6fc49544f77ec6ce2e7b2e8f3ab86c9a2a64c25d0eb3eb29547c5677851ef210",s)
        self.assertIn("await InitializeNativeP02Async(core);",s)
        self.assertIn("ShutdownNativeP02()",s)
        self.assertIn("T06_ORIGINAL_MAINWINDOW_SHA_HOLD",s)
        self.assertIn("SHA256.HashDataAsync",a)
        self.assertIn("NativePythonPipe(",a)
        self.assertIn("OneHostP02WebView2Bridge(core",a)
        self.assertIn('args.ArgumentList.Add("--native-stdio")',a)
        self.assertIn('RequestAsync("chat.model"',a)
        self.assertIn("MessageBox.Show(this",a)
        self.assertIn("P02_ORIGINAL_NATIVE_HOLD",a)
        self.assertIn("stage_native_p02.py",b)
        self.assertNotIn("HttpListener",a)
if __name__=="__main__":unittest.main()
