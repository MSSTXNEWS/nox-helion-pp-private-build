"""Original T06 same-VM Windows loader must never stage the obsolete 4-file overlay."""
import hashlib
from pathlib import Path
import tempfile
import unittest
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"coordination/e06"))
import t06_compile_original_wpf_p02 as compiler

def blob(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode("ascii")+b"\0"+data).hexdigest()

class CanonicalWpfSourceNoLoss(unittest.TestCase):
    def test_all_owner_sources_match_existing_e06_manifest(self):
        records=compiler.canonical_owner_manifest()
        self.assertEqual(len(records),18)
        self.assertEqual({dest for _,dest,_ in records},
                         compiler.REQUIRED_NATIVE_DESTINATIONS)
        for path,dest,expected in records:
            raw=(ROOT/path).read_bytes().replace(b"\r\n",b"\n")
            self.assertEqual(blob(raw),expected,(path,dest))
        self.assertEqual(
            compiler.EXPECTED["coordination/e06/MainWindow.NativeP02.cs"],
            blob((ROOT/"coordination/e06/MainWindow.NativeP02.cs").read_bytes().replace(b"\r\n",b"\n")))
        self.assertEqual(
            compiler.EXPECTED["coordination/e06/stage_native_p02.py"],
            blob((ROOT/"coordination/e06/stage_native_p02.py").read_bytes().replace(b"\r\n",b"\n")))

    def test_disposable_staging_reuses_18_original_sources(self):
        with tempfile.TemporaryDirectory(prefix="nox-t06-r47-") as temp:
            root=Path(temp)
            self.assertEqual(compiler.stage_current_owner_components(root),18)
            for path,dest,pin in compiler.canonical_owner_manifest():
                self.assertEqual(blob((root/dest).read_bytes()),pin)
            main=(root/"Integration/NativePythonPipe.cs").read_text("utf-8-sig")
            self.assertIn("RequestWpfApprovedA1Async",main)
            self.assertIn("NATIVE_JSON_DUPLICATE_FIELD_DENIED",main)
            bridge=(root/"Integration/OneHostP02WebView2Bridge.cs").read_text("utf-8-sig")
            self.assertIn("chat.stop",bridge)
            self.assertIn("NativeSidMatches",bridge)
            self.assertTrue((root/"Integration/P03/ModelCenterNativeRoutes.cs").is_file())

    def test_stale_overlay_not_selected_for_real_nsis_stage(self):
        source=(ROOT/"coordination/e06/t06_compile_original_wpf_p02.py").read_text("utf-8")
        self.assertNotIn('SRC=ROOT/"coordination/e06/t06_windows_overlay"',source)
        self.assertIn("stage_current_owner_components(R11)",source)
        self.assertIn('SRC/"coordination/e06/stage_native_p02.py"',source)
        self.assertIn('SRC/"coordination/e06/MainWindow.NativeP02.cs"',source)
        self.assertIn("T06_CANONICAL_OWNER_18_COMPONENTS_NOLOSS_HOLD",source)

if __name__=="__main__":
    unittest.main()
