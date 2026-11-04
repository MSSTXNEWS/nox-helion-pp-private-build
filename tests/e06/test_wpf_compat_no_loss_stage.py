"""Original WPF no-loss C# owner-fix stage source contract."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]
class OriginalWpfNoLossTest(unittest.TestCase):
    def test_owner_sha_and_identical_duplicate_gates(self):
        patch=(ROOT/"coordination/e06/stage_wpf_compat_no_loss.py").read_text("utf-8")
        builder=(ROOT/"coordination/e06/build_onehost_installer.ps1").read_text("utf-8")
        for name in ("T06_P03_DUPLICATE_METHODS_NOT_IDENTICAL",
                     "T06_ORIGINAL_OWNER_SOURCE_SHA_HOLD",
                     "T06_P02_OPENAI_NAMESPACE_OR_MAINWINDOW_ANCHOR_HOLD",
                     "T06_WPF_GLOBAL_USINGS_READBACK_HOLD",
                     "using NoxP01.Packages.P02.OpenAI;"):
            self.assertIn(name,patch)
        self.assertIn("E06_WPF_COMPAT_SOURCE_PIN_HOLD",builder)
        self.assertLess(builder.index("E06_WPF_EXACT_COMPAT_STAGE_HOLD"),
                        builder.index("& dotnet publish $project"))
