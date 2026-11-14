"""R67: one frozen original WPF/OneHost source identity across all 3 staging contracts.
A stale SHA must fail BEFORE the installed native Windows stage; no E07 claims.
"""
import ast
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "coordination/e06"
MAIN = SRC / "MainWindow.NativeP02.cs"
BRIDGE = SRC / "OneHostP02WebView2Bridge.cs"
STAGER = SRC / "stage_native_p02.py"
COMPILER = SRC / "t06_compile_original_wpf_p02.py"
BUILDER = SRC / "build_onehost_installer.ps1"

def blob(path):
    data = path.read_bytes()
    # Original compiler admits only plain exact-byte Git sources or CRLF
    # canonicalization, never arbitrary rewriting of source or signature.
    if b"\r\n" in data and b"\r" not in data.replace(b"\r\n", b""):
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") +
                        b"\0" + data).hexdigest()

def expected_compiler_pins(path):
    root = ast.parse(path.read_text(encoding="utf-8"))
    assignments = [node for node in root.body if isinstance(node, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "EXPECTED"
                           for t in node.targets)]
    if len(assignments) != 1:
        raise AssertionError("E06_EXPECTED_PIN_CONTRACT_MISSING")
    return ast.literal_eval(assignments[0].value)

class OriginalNativeSourcePins(unittest.TestCase):
    def test_donor_sha_pins_are_consistent_across_original_active_staging(self):
        main, bridge, stager = blob(MAIN), blob(BRIDGE), blob(STAGER)
        compiler = expected_compiler_pins(COMPILER)
        builder = BUILDER.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        stager_text = STAGER.read_text(encoding="utf-8")
        self.assertIn('ADDON_SHA="' + main + '"', stager_text)
        self.assertIn("p=$t06Stage;sha='" + stager + "'", builder)
        self.assertIn("p=$t06Addon;sha='" + main + "'", builder)
        self.assertIn(
            "dest='Integration/OneHostP02WebView2Bridge.cs';blob='" +
            bridge + "'", builder)
        self.assertEqual(compiler["coordination/e06/MainWindow.NativeP02.cs"], main)
        self.assertEqual(compiler["coordination/e06/OneHostP02WebView2Bridge.cs"], bridge)
        self.assertEqual(compiler["coordination/e06/stage_native_p02.py"], stager)

    def test_old_donor_pins_cannot_be_reused_for_new_onehost(self):
        compiler = expected_compiler_pins(COMPILER)
        self.assertNotEqual(
            compiler["coordination/e06/MainWindow.NativeP02.cs"],
            "9be154ae8b87566db8d694add9b2e694329f16f9")
        self.assertNotEqual(
            compiler["coordination/e06/OneHostP02WebView2Bridge.cs"],
            "ba135a93cb4cad964a352c3af9d2d87e4fe20157")

if __name__ == "__main__":
    unittest.main()
