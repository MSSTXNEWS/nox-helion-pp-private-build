"""Original-checkout regression: malformed pinned Python cannot partially stage."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

STAGE = Path(__file__).resolve().parents[2] / "coordination/e06/stage_native_stdio.py"

def stage_module():
    spec = importlib.util.spec_from_file_location("i1_e06_pinned_syntax", STAGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class PinnedPythonPreflight(unittest.TestCase):
    def test_broken_second_donor_fails_before_writing_first(self):
        mod=stage_module()
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)
            (source/"helion").mkdir()
            app=source/"helion/app.py"
            original=(
                "def main():\n"
                "    parser.add_argument('--diagnose',action='store_true',help='headless functional contracts check')\n"
                "    args=parser.parse_args()\n"
            ).encode()
            app.write_bytes(original)
            addons=(("good.py","nox_selfbuilder/good.py","a"*40),
                    ("bad.py","nox_selfbuilder/bad.py","b"*40))
            payload={"a"*40:b"x=1\n","b"*40:b"def broken(:\n"}
            with patch.object(mod,"ADDONS",addons), patch.object(
                 mod,"ORIGINAL_APP_SHA256",hashlib.sha256(original).hexdigest()), patch.object(
                 mod,"pinned_bytes",side_effect=lambda src,blob:payload[blob]):
                with self.assertRaisesRegex(RuntimeError,"E06_NATIVE_PINNED_PYTHON_SYNTAX_HOLD"):
                    mod.stage(source)
            self.assertEqual(app.read_bytes(),original)
            self.assertFalse((source/"nox_selfbuilder/good.py").exists())
            self.assertFalse((source/"nox_selfbuilder/bad.py").exists())

if __name__=="__main__":
    unittest.main()
